#!/usr/bin/env python3
"""
Question Preloader for LexiBoost
Implements a memory-based queue system with background thread for LLM calls
"""

from multiprocessing import pool
import os
import time
import random
import sqlite3
import threading
from collections import deque, OrderedDict
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PreloadedQuestion:
    """Data structure for preloaded questions"""
    word_id: int
    word_txt: str
    level: str
    sentence: str
    choices_i18n: List[Dict]
    correct_answer_i18n: Dict
    target_word: str
    target_word_zh: str  # Simple Chinese translation for the target word in context
    explanation_en: str
    explanation_zh: str
    created_at: float

class QuestionPreloader:
    """Memory-based question preloader with background thread"""
    
    def __init__(self, db_path: str = None):
        package_dir = Path(__file__).resolve().parent
        default_db = os.getenv("LEXIBOOST_DB_PATH", str(package_dir.parents[1] / "lexiboost.db"))
        self.db_path = db_path or default_db
        self.question_queues = {}  # session_id -> deque of PreloadedQuestion
        self.session_locks = {}    # session_id -> threading.Lock
        self.preload_threads = {}  # session_id -> threading.Thread
        self.stop_events = {}      # session_id -> threading.Event
        self.session_word_pools = {}  # session_id -> deque of candidate word dicts
        self.session_served_words = {}  # session_id -> set of word_ids already used
        
        # Global explanation cache for reuse (using OrderedDict for efficient LRU)
        self.explanation_cache = OrderedDict()  # (word, level) -> Dict
        self.cache_lock = threading.Lock()
        self.max_cache_size = int(os.getenv("LEXIBOOST_CACHE_MAX_SIZE", "1000"))
        
        # Configuration
        self.queue_size = int(os.getenv("LEXIBOOST_PRELOAD_QUEUE_SIZE", "5"))
        self.max_questions_per_session = int(os.getenv("LEXIBOOST_MAX_QUESTIONS", "50"))
        self.thread_join_timeout = float(os.getenv("LEXIBOOST_THREAD_JOIN_TIMEOUT", "5.0"))  # seconds
        
        logger.info(f"QuestionPreloader initialized: queue_size={self.queue_size}, thread_join_timeout={self.thread_join_timeout}s, max_cache_size={self.max_cache_size}")
    
    def start_session_preloader(self, session_id: int, user_id: int) -> None:
        """Start preloader thread for a session"""
        if session_id in self.preload_threads:
            logger.warning(f"Preloader already running for session {session_id}")
            return
        
        # Initialize session resources
        self.question_queues[session_id] = deque(maxlen=self.queue_size)
        self.session_locks[session_id] = threading.Lock()
        self.stop_events[session_id] = threading.Event()
        self.session_served_words[session_id] = set()

        self.session_word_pools[session_id] = self._build_session_word_pool(session_id, user_id)
        
        # Start preloader thread
        thread = threading.Thread(
            target=self._preload_worker,
            args=(session_id,),
            name=f"PreloaderThread-{session_id}",
            daemon=True
        )
        self.preload_threads[session_id] = thread
        thread.start()
        
        logger.info(f"Started preloader thread for session {session_id}")
    
    def stop_session_preloader(self, session_id: int) -> None:
        """Stop preloader thread and cleanup resources"""
        if session_id not in self.preload_threads:
            return
        
        # Signal stop
        if session_id in self.stop_events:
            self.stop_events[session_id].set()
        
        # Wait for thread to finish
        thread = self.preload_threads.get(session_id)
        if thread and thread.is_alive():
            thread.join(timeout=self.thread_join_timeout)
            if thread.is_alive():
                logger.warning(f"Preloader thread for session {session_id} did not terminate gracefully within timeout")
        
        # Cleanup resources
        self.question_queues.pop(session_id, None)
        self.session_locks.pop(session_id, None)
        self.preload_threads.pop(session_id, None)
        self.stop_events.pop(session_id, None)
        self.session_word_pools.pop(session_id, None)
        self.session_served_words.pop(session_id, None)
        
        logger.info(f"Stopped preloader thread for session {session_id}")
    
    def get_next_question(self, session_id: int) -> Optional[PreloadedQuestion]:
        """Get next preloaded question from queue"""
        if session_id not in self.question_queues:
            return None
        
        with self.session_locks[session_id]:
            queue = self.question_queues[session_id]
            
            # Return next question if available
            if queue:
                question = queue.popleft()
                logger.debug(f"Served preloaded question for word {question.word_txt}")
                return question
        
        return None
    
    def get_queue_status(self, session_id: int) -> Dict:
        """Get current queue status for monitoring"""
        if session_id not in self.question_queues:
            return {"queue_size": 0, "thread_alive": False}

        with self.session_locks[session_id]:
            queue_size = len(self.question_queues[session_id])

        thread = self.preload_threads.get(session_id)
        thread_alive = thread and thread.is_alive()

        return {
            "queue_size": queue_size,
            "thread_alive": thread_alive,
            "max_queue_size": self.queue_size
        }
    
    def get_cached_explanation(self, word: str, level: str) -> Optional[Dict]:
        """Get cached explanation for a word with LRU update"""
        cache_key = (word.lower(), level)
        with self.cache_lock:
            if cache_key in self.explanation_cache:
                # Move to end to mark as recently used
                explanation = self.explanation_cache.pop(cache_key)
                self.explanation_cache[cache_key] = explanation
                return explanation
            return None
    
    def cache_explanation(self, word: str, level: str, explanation: Dict) -> None:
        """Cache explanation for future reuse with LRU eviction"""
        cache_key = (word.lower(), level)
        with self.cache_lock:
            # Remove and re-add to move to end (LRU behavior)
            if cache_key in self.explanation_cache:
                del self.explanation_cache[cache_key]
            self.explanation_cache[cache_key] = explanation
            
            # Limit cache size with LRU eviction
            while len(self.explanation_cache) > self.max_cache_size:
                # Remove oldest entry (FIFO when cache is full)
                self.explanation_cache.popitem(last=False)

    def get_explanation_for_word_id(self, word_id: int) -> Optional[Dict]:
        """Get explanation from any preloaded question containing this word_id"""
        for session_id in self.question_queues:
            with self.session_locks.get(session_id, threading.Lock()):
                queue = self.question_queues[session_id]
                for question in queue:
                    if question.word_id == word_id:
                        return {
                            'definition_en': question.explanation_en,
                            'definition_zh': question.explanation_zh,
                            'word': question.word_txt,
                            'level': question.level
                        }
        return None
    
    def _preload_worker(self, session_id: int) -> None:
        """Background worker thread for preloading questions"""
        logger.info(f"Preloader worker started for session {session_id}")
        
        try:
            while not self.stop_events[session_id].is_set():
                try:
                    # Check if we need more questions
                    with self.session_locks[session_id]:
                        queue = self.question_queues[session_id]
                        current_size = len(queue)
                    
                    if current_size < self.queue_size:
                        # Generate a new question
                        question = self._generate_question(session_id)
                        if question:
                            with self.session_locks[session_id]:
                                self.question_queues[session_id].append(question)
                            logger.debug(f"Preloaded question for word {question.word_txt} (queue size: {len(self.question_queues[session_id])})")
                        else:
                            # No more words available, wait longer
                            time.sleep(2.0)
                    else:
                        # Queue is full enough, wait
                        time.sleep(0.5)
                
                except Exception as e:
                    logger.error(f"Error in preloader worker for session {session_id}: {e}")
                    time.sleep(1.0)
        
        except Exception as e:
            logger.error(f"Fatal error in preloader worker for session {session_id}: {e}")
        
        logger.info(f"Preloader worker stopped for session {session_id}")

    def _build_session_word_pool(self, session_id: int, user_id: int) -> deque:
        """Build the one-time candidate word list for this session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
            if not session:
                return deque()

            dictionary_id = session['dictionary_id'] if session and 'dictionary_id' in session.keys() else 1

            max_words = self.max_questions_per_session

            candidates: List[Dict] = []
            seen_ids = set()

            wrongbook_rows = conn.execute('''
                SELECT w.id, w.word, w.level, uw.next_review, uw.srs_interval, uw.correct_count
                FROM words w
                JOIN user_words uw ON w.id = uw.word_id AND uw.user_id = ?
                WHERE w.dictionary_id = ?
                  AND (uw.in_wrongbook = 1 OR uw.in_wrongbook IS NULL)
                  AND (uw.next_review IS NULL OR uw.next_review <= CURRENT_TIMESTAMP)
                  AND TRIM(w.word) <> ''
                ORDER BY 
                  CASE WHEN uw.next_review IS NULL THEN 0 ELSE 1 END,
                  uw.next_review ASC,
                  RANDOM()
                LIMIT ?
            ''', (user_id, dictionary_id, max_words)).fetchall()

            def _accumulate(rows):
                for row in rows:
                    word_id = row['id']
                    if word_id in seen_ids:
                        continue
                    candidates.append(dict(row))
                    seen_ids.add(word_id)
                    if len(candidates) >= max_words:
                        break

            _accumulate(wrongbook_rows)

            remaining = max_words - len(candidates)
            if remaining > 0:
                unseen_rows = conn.execute('''
                    SELECT w.id, w.word, w.level
                    FROM words w
                    WHERE TRIM(w.word) <> ''
                      AND w.dictionary_id = ?
                      AND w.id NOT IN (
                            SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?
                      )
                    ORDER BY RANDOM()
                    LIMIT ?
                ''', (dictionary_id, user_id, remaining)).fetchall()
                _accumulate(unseen_rows)

            return deque(candidates)

        finally:
            conn.close()
    
    def _generate_question(self, session_id: int) -> Optional[PreloadedQuestion]:
        """Generate a single question with LLM call"""
        try:
            pool = self.session_word_pools.get(session_id)
            if pool and len(pool) > 0:
                target = pool.popleft()
            else:
                logger.warning(f"No available word pool or empty pool for session {session_id}")
                return None
            
            word_id = target['id']
            word_txt = (target['word'] or '').strip()
            level = (target['level'] or 'k12').strip() if 'level' in target.keys() else 'k12'
            
            if not word_txt:
                return None
            
            # Call LLM for explanation (this is the expensive operation)
            from .definition_service import definition_service
            explanation = definition_service.get_word_explanation(word_txt, level)
            # Cache the explanation for reuse
            self.cache_explanation(word_txt, level, explanation)
            
            correct_en = explanation['definition_en']
            correct_zh = explanation['definition_zh']
            distractors_en = explanation['distractors_en']
            distractors_zh = explanation['distractors_zh']
            examples = explanation.get('examples', [])
            
            # Generate sentence
            if examples:
                sentence = examples[0]['en']
            else:
                sentence = self._generate_sentence_with_word(word_txt)
            
            # Build choices
            correct_pair = {'en': correct_en, 'zh': correct_zh}
            choices_i18n = [correct_pair]
            
            # Add distractors from LLM
            for i in range(min(3, len(distractors_en), len(distractors_zh))):
                choices_i18n.append({
                    'en': distractors_en[i],
                    'zh': distractors_zh[i]
                })
            
            # Ensure we have exactly 4 choices
            while len(choices_i18n) < 4:
                choices_i18n.append({
                    'en': 'A general concept or idea',
                    'zh': '一般概念或想法'
                })
            
            random.shuffle(choices_i18n)
            
            lock = self.session_locks.get(session_id)
            if lock:
                with lock:
                    self.session_served_words.setdefault(session_id, set()).add(word_id)
            else:
                self.session_served_words.setdefault(session_id, set()).add(word_id)

            return PreloadedQuestion(
                word_id=word_id,
                word_txt=word_txt,
                level=level,
                sentence=sentence,
                choices_i18n=choices_i18n,
                correct_answer_i18n=correct_pair,
                target_word=word_txt,
                target_word_zh=explanation.get('word_zh', correct_zh),
                explanation_en=correct_en,
                explanation_zh=correct_zh,
                created_at=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to generate question for session {session_id}: {e}")
            return None
    
    def _generate_sentence_with_word(self, word: str) -> str:
        """Generate a simple sentence with the word (fallback)"""
        templates = [
            f"The {word} is very important.",
            f"I think the {word} is interesting.",
            f"We can see the {word} here.",
            f"This {word} is quite useful.",
            f"The {word} appears frequently."
        ]
        return random.choice(templates)

# Global instance
question_preloader = QuestionPreloader()