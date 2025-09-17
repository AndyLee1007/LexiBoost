#!/usr/bin/env python3
"""
Question Preloader for LexiBoost
Implements a memory-based queue system with background thread for LLM calls
"""

import os
import time
import random
import sqlite3
import threading
from collections import deque
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

from definition_service import definition_service

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
    explanation_en: str
    explanation_zh: str
    created_at: float

class QuestionPreloader:
    """Memory-based question preloader with background thread"""
    
    def __init__(self, db_path: str = "lexiboost.db"):
        self.db_path = db_path
        self.question_queues = {}  # session_id -> deque of PreloadedQuestion
        self.session_locks = {}    # session_id -> threading.Lock
        self.preload_threads = {}  # session_id -> threading.Thread
        self.stop_events = {}      # session_id -> threading.Event
        
        # Global explanation cache for reuse
        self.explanation_cache = {}  # (word, level) -> Dict
        self.cache_lock = threading.Lock()
        
        # Configuration
        self.queue_size = int(os.getenv("LEXIBOOST_PRELOAD_QUEUE_SIZE", "5"))
        self.preload_ahead = int(os.getenv("LEXIBOOST_PRELOAD_AHEAD", "3"))
        self.question_ttl = int(os.getenv("LEXIBOOST_QUESTION_TTL", "300"))  # seconds
        
        logger.info(f"QuestionPreloader initialized: queue_size={self.queue_size}, preload_ahead={self.preload_ahead}")
    
    def start_session_preloader(self, session_id: int, user_id: int) -> None:
        """Start preloader thread for a session"""
        if session_id in self.preload_threads:
            logger.warning(f"Preloader already running for session {session_id}")
            return
        
        # Initialize session resources
        self.question_queues[session_id] = deque(maxlen=self.queue_size)
        self.session_locks[session_id] = threading.Lock()
        self.stop_events[session_id] = threading.Event()
        
        # Start preloader thread
        thread = threading.Thread(
            target=self._preload_worker,
            args=(session_id, user_id),
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
            thread.join(timeout=5.0)
        
        # Cleanup resources
        self.question_queues.pop(session_id, None)
        self.session_locks.pop(session_id, None)
        self.preload_threads.pop(session_id, None)
        self.stop_events.pop(session_id, None)
        
        logger.info(f"Stopped preloader thread for session {session_id}")
    
    def get_next_question(self, session_id: int) -> Optional[PreloadedQuestion]:
        """Get next preloaded question from queue"""
        if session_id not in self.question_queues:
            return None
        
        with self.session_locks[session_id]:
            queue = self.question_queues[session_id]
            
            # Remove expired questions
            current_time = time.time()
            while queue and (current_time - queue[0].created_at) > self.question_ttl:
                expired = queue.popleft()
                logger.debug(f"Removed expired question for word {expired.word_txt}")
            
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
        """Get cached explanation for a word"""
        cache_key = (word.lower(), level)
        with self.cache_lock:
            return self.explanation_cache.get(cache_key)
    
    def cache_explanation(self, word: str, level: str, explanation: Dict) -> None:
        """Cache explanation for future reuse"""
        cache_key = (word.lower(), level)
        with self.cache_lock:
            self.explanation_cache[cache_key] = explanation
            # Limit cache size to prevent memory bloat
            if len(self.explanation_cache) > 1000:
                # Remove oldest entries (simple FIFO)
                oldest_key = next(iter(self.explanation_cache))
                del self.explanation_cache[oldest_key]

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
    
    def _preload_worker(self, session_id: int, user_id: int) -> None:
        """Background worker thread for preloading questions"""
        logger.info(f"Preloader worker started for session {session_id}")
        
        try:
            while not self.stop_events[session_id].is_set():
                try:
                    # Check if we need more questions
                    with self.session_locks[session_id]:
                        queue = self.question_queues[session_id]
                        current_size = len(queue)
                    
                    if current_size < self.preload_ahead:
                        # Generate a new question
                        question = self._generate_question(session_id, user_id)
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
    
    def _generate_question(self, session_id: int, user_id: int) -> Optional[PreloadedQuestion]:
        """Generate a single question with LLM call"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get next word using the same logic as the original app
            target = self._get_next_word_for_session(conn, session_id, user_id)
            if not target:
                conn.close()
                return None
            
            word_id = target['id']
            word_txt = (target['word'] or '').strip()
            level = (target['level'] or 'k12').strip() if 'level' in target.keys() else 'k12'
            
            if not word_txt:
                conn.close()
                return None
            
            # Call LLM for explanation (this is the expensive operation)
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
            
            conn.close()
            
            return PreloadedQuestion(
                word_id=word_id,
                word_txt=word_txt,
                level=level,
                sentence=sentence,
                choices_i18n=choices_i18n,
                correct_answer_i18n=correct_pair,
                target_word=word_txt,
                explanation_en=correct_en,
                explanation_zh=correct_zh,
                created_at=time.time()
            )
            
        except Exception as e:
            logger.error(f"Failed to generate question for session {session_id}: {e}")
            return None
    
    def _get_next_word_for_session(self, conn, session_id: int, user_id: int) -> Optional[Dict]:
        """Get next word for session (same logic as original app)"""
        # Get session info
        session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
        if not session:
            return None
        
        # Get next word using SRS logic
        target = conn.execute('''
            SELECT w.id, w.word, w.level, uw.next_review, uw.srs_interval, uw.correct_count
            FROM words w
            LEFT JOIN user_words uw ON w.id = uw.word_id AND uw.user_id = ?
            WHERE (uw.in_wrongbook = 1 OR uw.in_wrongbook IS NULL)
              AND (uw.next_review IS NULL OR uw.next_review <= CURRENT_TIMESTAMP)
            ORDER BY 
              CASE WHEN uw.next_review IS NULL THEN 0 ELSE 1 END,
              uw.next_review ASC,
              RANDOM()
            LIMIT 1
        ''', (user_id,)).fetchone()
        
        return dict(target) if target else None
    
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