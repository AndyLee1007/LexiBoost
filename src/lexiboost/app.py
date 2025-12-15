#!/usr/bin/env python3
"""
LexiBoost - English Vocabulary Learning App for Kids
Main Flask application entry point
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import time
import csv
import io
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import random
import atexit
import signal
from .definition_service import definition_service
from .question_preloader import question_preloader

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]

app = Flask(
    __name__,
    static_folder=str(PACKAGE_DIR / 'static'),
    template_folder=str(PACKAGE_DIR / 'templates')
)
CORS(app)

# Database configuration
DATABASE = os.getenv('LEXIBOOST_DB_PATH', str(PROJECT_ROOT / 'lexiboost.db'))

def _to_sql_ts(dt):
    if not dt:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_srs_intervals():
    """Return SRS intervals in days"""
    return [0, 1, 3, 7, 14]

def _env_flag(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    return str(v).lower() in ("1", "true", "yes", "on") or (default and v == "")

def get_max_questions_per_session() -> int:
    """Get the maximum number of questions per session from environment variable"""
    try:
        return int(os.getenv('LEXIBOOST_MAX_QUESTIONS', '50'))
    except (ValueError, TypeError):
        return 50

def get_time_per_question() -> int:
    """Get the time per question in seconds from environment variable"""
    try:
        return int(os.getenv('LEXIBOOST_TIME_PER_QUESTION', '600'))  # Default 10 minutes
    except (ValueError, TypeError):
        return 600

def get_available_question_count(user_id: int, dictionary_id: int) -> int:
    """Get the actual number of available questions for a user and dictionary"""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT COUNT(*) as count
            FROM words w
            LEFT JOIN user_words uw ON w.id = uw.word_id AND uw.user_id = ?
            WHERE w.dictionary_id = ?
              AND (uw.in_wrongbook = 1 OR uw.in_wrongbook IS NULL)
              AND (uw.next_review IS NULL OR uw.next_review <= CURRENT_TIMESTAMP)
        ''', (user_id, dictionary_id)).fetchone()
        
        available_count = result['count'] if result else 0
        max_questions = get_max_questions_per_session()
        
        return min(available_count, max_questions)
    finally:
        conn.close()

def get_total_session_time() -> int:
    """Get the total session time in seconds (time_per_question * max_questions)"""
    time_per_question = get_time_per_question()
    max_questions = get_max_questions_per_session()
    return time_per_question * max_questions

def calculate_actual_session_time(user_id: int, dictionary_id: int) -> int:
    """Calculate actual session time based on available questions"""
    actual_questions = get_available_question_count(user_id, dictionary_id)
    time_per_question = get_time_per_question()
    return actual_questions * time_per_question

def is_timer_enabled() -> bool:
    """Check if timer is enabled"""
    return _env_flag('LEXIBOOST_ENABLE_TIMER', default=False)

def calculate_next_review(current_interval_index, is_correct):
    """Calculate next review date based on SRS"""
    intervals = get_srs_intervals()
    
    if is_correct:
        next_index = min(current_interval_index + 1, len(intervals) - 1)
    else:
        next_index = 0  # Reset to beginning if incorrect
    
    next_interval = intervals[next_index]
    next_review = datetime.now() + timedelta(days=next_interval)
    
    return next_review, next_index

def generate_sentence_with_word(word: str, pos_tags=None) -> str:
    """
    Lightweight fallback sentence generator when no DB example exists.
    - Deterministic per word (seeded) to keep UX stable across sessions.
    - Puts the word in quotes to avoid article/inflection issues (e.g., 'a').
    """
    templates_common = [
        "My family likes to talk about '{w}'.",
        "We learned about '{w}' in class today.",
        "The teacher gave an example with '{w}'.",
        "Many people use '{w}' every day.",
        "I saw the word '{w}' in a book.",
        "This question is about '{w}'.",
        "Can you explain what '{w}' means?",
        "People often discuss '{w}' in daily life.",
    ]

    noun_like = {"n", "noun"}
    verb_like = {"v", "verb"}
    adj_like  = {"adj", "adjective"}
    adv_like  = {"adv", "adverb"}

    pos_tags = set((pos_tags or []))
    if pos_tags & verb_like:
        templates = [
            "People often '{w}' after school.",
            "They decided to '{w}' together.",
            "Try to '{w}' carefully in this task.",
            "Sometimes we need to '{w}' to solve problems.",
        ]
    elif pos_tags & adj_like:
        templates = [
            "It was a very '{w}' idea.",
            "The story sounds quite '{w}'.",
            "Her answer seems '{w}' to me.",
            "That looks rather '{w}'.",
        ]
    elif pos_tags & adv_like:
        templates = [
            "She spoke '{w}' to make everything clear.",
            "Please work '{w}' to avoid mistakes.",
            "They moved '{w}' through the hallway.",
            "He answered '{w}' during the test.",
        ]
    elif pos_tags & noun_like:
        templates = [
            "Everyone was talking about '{w}'.",
            "The museum had an exhibit about '{w}'.",
            "I read an article on '{w}' yesterday.",
            "We found more information about '{w}'.",
        ]
    else:
        templates = templates_common

    rng = random.Random(hash(word) & 0xFFFFFFFF)
    return rng.choice(templates).format(w=word)

@app.route('/')
def index():
    """Serve the main application page"""
    return render_template('index.html')

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user"""
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    conn = get_db_connection()
    try:
        cursor = conn.execute('INSERT INTO users (username) VALUES (?)', (username,))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'user_id': user_id, 'username': username})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400

@app.route('/api/users/<username>')
def get_user(username):
    """Get user by username"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'user_id': user['id'],
            'username': user['username'],
            'created_at': user['created_at']
        })
    else:
        return jsonify({'error': 'User not found'}), 404

@app.route('/api/users/<int:user_id>/session/start', methods=['POST'])
def start_session(user_id):
    """Start a new quiz session with preloader"""
    data = request.get_json() or {}
    dictionary_id = data.get('dictionary_id', 1)  # Default to dictionary 1
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verify dictionary exists
        cur.execute("SELECT id FROM dictionaries WHERE id = ?", (dictionary_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Dictionary not found'}), 404
        
        # Create new session with dictionary and hover state
        session_date = datetime.now().date()
        session_start_time = datetime.now()
        # Check if hover functionality is enabled
        hover_zh_enabled = 1 if os.getenv('LEXIBOOST_HOVER_ZH', 'False').lower() == 'true' else 0
        
        # Calculate actual session time based on available questions
        actual_session_time = calculate_actual_session_time(user_id, dictionary_id)
        
        cursor = conn.execute(
            'INSERT INTO sessions (user_id, session_date, dictionary_id, hover_zh_enabled, session_start_time, time_limit) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, session_date, dictionary_id, hover_zh_enabled, _to_sql_ts(session_start_time), actual_session_time)
        )
        session_id = cursor.lastrowid
        conn.commit()
        
        # Start question preloader for this session
        question_preloader.start_session_preloader(session_id, user_id)
        
        time.sleep(2.0)
        # Get additional info for response
        available_questions = get_available_question_count(user_id, dictionary_id)
        
        return jsonify({
            'session_id': session_id, 
            'dictionary_id': dictionary_id,
            'available_questions': available_questions,
            'actual_session_time': actual_session_time,
            'time_per_question': get_time_per_question()
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/sessions/<int:session_id>/question')
def get_question(session_id):
    """Get next question from preloaded queue or fallback to real-time generation."""
    conn = get_db_connection()

    # 1) validate session
    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    user_id = session['user_id']

    # 2) stop at max questions per session
    max_questions_per_session = get_max_questions_per_session()
    question_count = conn.execute(
        'SELECT COUNT(*) as count FROM question_attempts WHERE session_id = ?',
        (session_id,)
    ).fetchone()['count']
    if question_count >= max_questions_per_session:
        conn.close()
        return jsonify({'session_complete': True})

    # 3) Try to get preloaded question first
    preloaded_question = question_preloader.get_next_question(session_id)
    if preloaded_question:
        conn.close()
        return jsonify({
            'question_id': f"{session_id}_{preloaded_question.word_id}",
            'word_id': preloaded_question.word_id,
            'question_number': question_count + 1,
            'target_word': preloaded_question.target_word,
            'target_word_zh': preloaded_question.target_word_zh,
            'sentence': preloaded_question.sentence,
            'choices_i18n': preloaded_question.choices_i18n,
            'correct_answer_i18n': preloaded_question.correct_answer_i18n,
            'question_text': f'What does "{preloaded_question.target_word}" mean?',
            'source': 'preloaded'  # For debugging
        })

    # 4) Fallback to original real-time generation if queue is empty
    # Get session dictionary_id for filtering
    dictionary_id = session['dictionary_id'] if session and 'dictionary_id' in session.keys() else 1
    
    # Get words already asked in this session to avoid repetition
    asked_word_ids = set()
    asked_words = conn.execute('''
        SELECT DISTINCT word_id FROM question_attempts 
        WHERE session_id = ?
    ''', (session_id,)).fetchall()
    asked_word_ids = {row['word_id'] for row in asked_words}

    # Candidate words: due wrongbook first, then unseen (exclude already asked)
    # IMPORTANT: Filter by dictionary_id to match session dictionary
    wrongbook_words = conn.execute('''
        SELECT w.*, uw.next_review, uw.srs_interval 
        FROM words w 
        JOIN user_words uw ON w.id = uw.word_id 
        WHERE uw.user_id = ? AND uw.in_wrongbook = 1 
          AND w.dictionary_id = ?
          AND (uw.next_review IS NULL OR uw.next_review <= datetime('now'))
          AND TRIM(w.word) <> ''
        ORDER BY uw.next_review ASC
        LIMIT 50
    ''', (user_id, dictionary_id)).fetchall()
    
    # Filter out already asked words
    wrongbook_words = [w for w in wrongbook_words if w['id'] not in asked_word_ids]

    unseen_words = conn.execute('''
        SELECT w.* FROM words w
        WHERE TRIM(w.word) <> ''
          AND w.dictionary_id = ?
          AND w.id NOT IN (SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?)
        ORDER BY RANDOM()
        LIMIT 50
    ''', (dictionary_id, user_id)).fetchall()
    
    # Filter out already asked words
    unseen_words = [w for w in unseen_words if w['id'] not in asked_word_ids]

    # Select target word for fallback generation
    candidates = list(wrongbook_words) + list(unseen_words)
    
    # Check if we have any valid candidates
    if not candidates:
        # Check if it's because all words have been exhausted in this session
        # IMPORTANT: Filter by dictionary_id to match session dictionary
        total_wrongbook = conn.execute('''
            SELECT COUNT(*) as count FROM user_words uw
            JOIN words w ON w.id = uw.word_id
            WHERE uw.user_id = ? AND uw.in_wrongbook = 1 
              AND w.dictionary_id = ?
              AND (uw.next_review IS NULL OR uw.next_review <= datetime('now'))
              AND TRIM(w.word) <> ''
        ''', (user_id, dictionary_id)).fetchone()['count']
        
        total_unseen = conn.execute('''
            SELECT COUNT(*) as count FROM words w
            WHERE TRIM(w.word) <> ''
              AND w.dictionary_id = ?
              AND w.id NOT IN (SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?)
        ''', (dictionary_id, user_id)).fetchone()['count']
        
        total_available = total_wrongbook + total_unseen
        
        conn.close()
        
        if total_available == 0:
            return jsonify({
                'session_complete': True,
                'message': 'No words available in the database. Please import vocabulary data.',
                'reason': 'no_words_in_db'
            })
        elif len(asked_word_ids) >= total_available:
            return jsonify({
                'session_complete': True,
                'message': f'Congratulations! You have completed all {len(asked_word_ids)} available words in this session.',
                'reason': 'all_words_completed'
            })
        else:
            return jsonify({
                'session_complete': True,
                'message': 'No more words due for review at this time. Great job!',
                'reason': 'no_words_due'
            })

    target = random.choice(candidates)
    word_id = target['id']
    word_txt = (target['word'] or '').strip()
    level = (target['level'] or 'k12').strip() if 'level' in target.keys() else 'k12'
    
    if not word_txt:
        conn.close()
        return jsonify({'error': 'Invalid word selected.'}), 400

    # Get real-time explanation from LLM (fallback mode)
    try:
        explanation = definition_service.get_word_explanation(word_txt, level)
        correct_en = explanation['definition_en']
        correct_zh = explanation['definition_zh']
        distractors_en = explanation['distractors_en']
        distractors_zh = explanation['distractors_zh']
        examples = explanation.get('examples', [])
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Failed to generate explanation: {str(e)}'}), 500

    # 6) generate sentence (use example if available, otherwise fallback)
    if examples:
        sentence = examples[0]['en']
    else:
        sentence = generate_sentence_with_word(word_txt)

    # 7) build choices (i18n) using real-time distractors
    correct_pair = {'en': correct_en, 'zh': correct_zh}
    choices_i18n = [correct_pair]

    # Add distractors from LLM (limit to 3 to make total 4 choices)
    for i in range(min(3, len(distractors_en), len(distractors_zh))):
        choices_i18n.append({
            'en': distractors_en[i],
            'zh': distractors_zh[i]
        })
    
    # Ensure we have exactly 4 choices total
    while len(choices_i18n) < 4:
        choices_i18n.append({
            'en': 'A general concept or idea',
            'zh': '一般概念或想法'
        })
    
    random.shuffle(choices_i18n)

    hover_zh_enabled = _env_flag('LEXIBOOST_HOVER_ZH', default=False)

    conn.close()
    return jsonify({
        'question_id': f"{session_id}_{word_id}",
        'word_id': word_id,
        'target_word': word_txt,
        'target_word_zh': explanation.get('word_zh', correct_zh),
        'sentence': sentence,
        'question_text': f'What does "{word_txt}" mean?',
        'choices_i18n': choices_i18n,
        'correct_answer_i18n': correct_pair,
        'question_number': question_count + 1,
        'hover_zh_enabled': hover_zh_enabled,
        'source': 'fallback'  # For debugging
    })

@app.route('/api/sessions/<int:session_id>/answer', methods=['POST'])
def submit_answer(session_id):
    """Submit answer for a question"""
    data = request.get_json()
    word_id = data.get('word_id')
    user_answer = data.get('user_answer')
    correct_answer = data.get('correct_answer')
    question_text = data.get('question_text')

    is_correct = user_answer == correct_answer

    conn = get_db_connection()

    # session & user
    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    user_id = session['user_id']

    # Try to get explanation from preloaded questions first
    preloaded_explanation = question_preloader.get_explanation_for_word_id(word_id)
    if preloaded_explanation:
        explanation_en = preloaded_explanation['definition_en']
        explanation_zh = preloaded_explanation['definition_zh']
    else:
        # Fallback to real-time generation if not in preload cache
        w = conn.execute('SELECT word, level FROM words WHERE id = ?', (word_id,)).fetchone()
        if w:
            word_txt = w['word']
            level = w['level'] or 'k12'
            try:
                explanation = definition_service.get_word_explanation(word_txt, level)
                explanation_en = explanation['definition_en']
                explanation_zh = explanation['definition_zh']
            except Exception:
                explanation_en = correct_answer or ""
                explanation_zh = ""
        else:
            explanation_en = correct_answer or ""
            explanation_zh = ""

    # record attempt
    conn.execute('''
        INSERT INTO question_attempts 
        (session_id, word_id, question_text, correct_answer, user_answer, is_correct, explanation)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, word_id, question_text, correct_answer, user_answer, is_correct, explanation_en))

    # score
    if is_correct:
        conn.execute(
            'UPDATE sessions SET correct_answers = correct_answers + 1, score = score + 1 WHERE id = ?',
            (session_id,)
        )
    conn.execute('UPDATE sessions SET total_questions = total_questions + 1 WHERE id = ?', (session_id,))

    # SRS & wrongbook
    user_word = conn.execute(
        'SELECT * FROM user_words WHERE user_id = ? AND word_id = ?',
        (user_id, word_id)
    ).fetchone()

    if user_word:
        if is_correct:
            new_correct_count = user_word['correct_count'] + 1
            next_review, next_interval = calculate_next_review(user_word['srs_interval'], True)
            in_wrongbook = 1 if new_correct_count < 3 else 0
            conn.execute('''
                UPDATE user_words 
                SET correct_count = ?, last_reviewed = datetime('now'), 
                    next_review = ?, srs_interval = ?, in_wrongbook = ?
                WHERE id = ?
            ''', (new_correct_count, next_review, next_interval, in_wrongbook, user_word['id']))
        else:
            next_review, next_interval = calculate_next_review(0, False)
            conn.execute('''
                UPDATE user_words 
                SET correct_count = 0, last_reviewed = datetime('now'),
                    next_review = ?, srs_interval = ?, in_wrongbook = 1
                WHERE id = ?
            ''', (next_review, next_interval, user_word['id']))
    else:
        # Create user_words record for first encounter (regardless of correct/incorrect)
        if is_correct:
            # First time correct
            next_review, next_interval = calculate_next_review(0, True)
            in_wrongbook = 1  # Still need more practice
            conn.execute('''
                INSERT INTO user_words 
                (user_id, word_id, correct_count, last_reviewed, next_review, srs_interval, in_wrongbook)
                VALUES (?, ?, 1, datetime('now'), ?, ?, ?)
            ''', (user_id, word_id, next_review, next_interval, in_wrongbook))
        else:
            # First time incorrect
            next_review, next_interval = calculate_next_review(0, False)
            conn.execute('''
                INSERT INTO user_words 
                (user_id, word_id, correct_count, last_reviewed, next_review, srs_interval, in_wrongbook)
                VALUES (?, ?, 0, datetime('now'), ?, ?, 1)
            ''', (user_id, word_id, next_review, next_interval))

    conn.commit()
    conn.close()

    return jsonify({
        'is_correct': is_correct,
        'explanation_en': explanation_en,
        'explanation_zh': explanation_zh,
        'score_change': 1 if is_correct else 0
    })

@app.route('/api/users/<int:user_id>/stats')
def get_user_stats(user_id):
    """Get user statistics"""
    conn = get_db_connection()
    
    # Daily stats
    today = datetime.now().date()
    daily_stats = conn.execute('''
        SELECT SUM(score) as daily_score, SUM(total_questions) as daily_questions,
               SUM(correct_answers) as daily_correct
        FROM sessions 
        WHERE user_id = ? AND session_date = ?
    ''', (user_id, today)).fetchone()
    
    # Total stats
    total_stats = conn.execute('''
        SELECT SUM(score) as total_score, SUM(total_questions) as total_questions,
               SUM(correct_answers) as total_correct
        FROM sessions 
        WHERE user_id = ?
    ''', (user_id,)).fetchone()
    
    # Wrongbook count
    wrongbook_count = conn.execute('''
        SELECT COUNT(*) as count 
        FROM user_words 
        WHERE user_id = ? AND in_wrongbook = 1
    ''', (user_id,)).fetchone()
    
    conn.close()
    
    return jsonify({
        'daily_score': daily_stats['daily_score'] or 0,
        'daily_questions': daily_stats['daily_questions'] or 0,
        'daily_correct': daily_stats['daily_correct'] or 0,
        'total_score': total_stats['total_score'] or 0,
        'total_questions': total_stats['total_questions'] or 0,
        'total_correct': total_stats['total_correct'] or 0,
        'wrongbook_count': wrongbook_count['count'] or 0
    })

@app.route('/api/sessions/<int:session_id>/stats')
def get_session_stats(session_id):
    """Get detailed statistics for a specific session"""
    conn = get_db_connection()
    
    try:
        # Get session basic info
        session = conn.execute('''
            SELECT s.*, d.name as dictionary_name
            FROM sessions s
            LEFT JOIN dictionaries d ON s.dictionary_id = d.id
            WHERE s.id = ?
        ''', (session_id,)).fetchone()
        
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Get session questions with word info
        questions = conn.execute('''
            SELECT qa.*, w.word, w.dictionary_id
            FROM question_attempts qa
            JOIN words w ON qa.word_id = w.id
            WHERE qa.session_id = ?
            ORDER BY qa.created_at
        ''', (session_id,)).fetchall()
        
        # Calculate detailed statistics
        total_questions = len(questions)
        correct_answers = sum(1 for q in questions if q['is_correct'])
        accuracy_rate = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        # Count new words vs review words
        user_id = session['user_id']
        new_words = 0
        review_words = 0
        wrong_words = 0  # Words that need more practice
        
        for q in questions:
            # Check if this word was encountered before
            prev_encounter = conn.execute('''
                SELECT uw.correct_count, uw.last_reviewed
                FROM user_words uw
                WHERE uw.user_id = ? AND uw.word_id = ?
            ''', (user_id, q['word_id'])).fetchone()
            
            if prev_encounter and prev_encounter['last_reviewed']:
                # This is a review word
                review_words += 1
                # If still getting it wrong, count as wrong word
                if prev_encounter['correct_count'] == 0:
                    wrong_words += 1
            else:
                # This is a truly new word (first encounter)
                new_words += 1
        
        return jsonify({
            'status': 'success',
            'stats': {
                'session_id': session_id,
                'user_id': session['user_id'],
                'dictionary_name': session['dictionary_name'],
                'hover_enabled': bool(session['hover_zh_enabled']),
                'created_at': session['created_at'],
                'total_questions': total_questions,
                'correct_answers': correct_answers,
                'accuracy_rate': round(accuracy_rate, 1),
                'new_words_count': new_words if new_words > 0 else wrong_words,
                'review_words_count': review_words,
                'wrong_words_count': wrong_words,
                'session_complete': session['completed'] == 1,
                'is_all_review': new_words == 0  # Flag to indicate all words are review
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>/sessions/trends')
def get_user_session_trends(user_id):
    """Get user's session trends data for chart display"""
    conn = get_db_connection()
    
    try:
        # Get query parameters
        include_hover = request.args.get('include_hover', 'true').lower() == 'true'
        limit = int(request.args.get('limit', 15))  # Default to 15 recent sessions
        
        # Base query for sessions - get most recent sessions first
        base_query = '''
            SELECT s.id, s.created_at, s.total_questions, s.correct_answers, s.hover_zh_enabled,
                   ROUND((CAST(s.correct_answers AS FLOAT) / s.total_questions) * 100, 1) as accuracy_rate
            FROM sessions s
            WHERE s.user_id = ? AND s.total_questions > 0
        '''
        
        # Add hover filter if needed
        if not include_hover:
            base_query += ' AND s.hover_zh_enabled = 0'
        
        # Order by created_at DESC to get most recent first, then limit
        base_query += ' ORDER BY s.created_at DESC LIMIT {}'.format(limit)
        
        sessions = conn.execute(base_query, (user_id,)).fetchall()
        
        # Reverse the order to show chronological progression in chart
        sessions = list(reversed(sessions))
        
        # Format data for chart (convert UTC to local time)
        trend_data = []
        for session in sessions:
            # Convert UTC timestamp to local time
            utc_dt = datetime.fromisoformat(session['created_at'])
            local_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone()
            
            trend_data.append({
                'session_id': session['id'],
                'date': local_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'accuracy_rate': session['accuracy_rate'],
                'total_questions': session['total_questions'],
                'correct_answers': session['correct_answers'],
                'hover_enabled': bool(session['hover_zh_enabled'])
            })
        
        # Calculate summary statistics
        if trend_data:
            avg_accuracy = sum(s['accuracy_rate'] for s in trend_data) / len(trend_data)
            total_sessions = len(trend_data)
            total_questions = sum(s['total_questions'] for s in trend_data)
            total_correct = sum(s['correct_answers'] for s in trend_data)
        else:
            avg_accuracy = 0
            total_sessions = 0
            total_questions = 0
            total_correct = 0
        
        return jsonify({
            'status': 'success',
            'trends': trend_data,
            'summary': {
                'avg_accuracy': round(avg_accuracy, 1),
                'total_sessions': total_sessions,
                'total_questions': total_questions,
                'total_correct': total_correct,
                'include_hover': include_hover,
                'sessions_limit': limit
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>/wrongbook/import', methods=['POST'])
def import_wrongbook(user_id):
    """Import wrongbook words from CSV (columns: word, definition - definition ignored, real-time generated)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be CSV format'}), 400

    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)

        conn = get_db_connection()
        imported_count = 0

        for row in csv_reader:
            if len(row) >= 1:
                word = (row[0] or '').strip()
                if not word:
                    continue

                # find or create word (only store word and metadata)
                existing = conn.execute(
                    'SELECT id FROM words WHERE word = ?',
                    (word,)
                ).fetchone()
                if existing:
                    word_id = existing['id']
                else:
                    cursor = conn.execute(
                        'INSERT INTO words (word) VALUES (?)',
                        (word,)
                    )
                    word_id = cursor.lastrowid

                # add to user's wrongbook if not exists
                uw = conn.execute(
                    'SELECT id FROM user_words WHERE user_id = ? AND word_id = ?',
                    (user_id, word_id)
                ).fetchone()
                if not uw:
                    next_review = datetime.now()
                    conn.execute('''
                        INSERT INTO user_words
                        (user_id, word_id, correct_count, last_reviewed, next_review, srs_interval, in_wrongbook)
                        VALUES (?, ?, 0, datetime('now'), ?, 0, 1)
                    ''', (user_id, word_id, next_review))
                    imported_count += 1

        conn.commit()
        conn.close()

        return jsonify({
            'message': f'Successfully imported {imported_count} words',
            'imported_count': imported_count
        })

    except Exception as e:
        return jsonify({'error': f'Error processing CSV: {str(e)}'}), 400

@app.route('/api/config')
def get_config():
    """Get application configuration"""
    return jsonify({
        'max_questions_per_session': get_max_questions_per_session(),
        'hover_zh_enabled': _env_flag('LEXIBOOST_HOVER_ZH', default=False),
        'timer_enabled': is_timer_enabled(),
        'time_per_question': get_time_per_question(),
        'total_session_time': get_total_session_time()  # This is now just the theoretical max
    })

@app.route('/api/self-test')
def self_test():
    """Run self-tests to validate the application"""
    tests = []
    
    try:
        # Test database connection
        conn = get_db_connection()
        conn.execute('SELECT 1').fetchone()
        conn.close()
        tests.append({'test': 'Database Connection', 'status': 'PASS'})
    except Exception as e:
        tests.append({'test': 'Database Connection', 'status': 'FAIL', 'error': str(e)})
    
    try:
        # Test word generation
        test_word = 'test'
        sentence = generate_sentence_with_word(test_word)
        if test_word in sentence:
            tests.append({'test': 'Sentence Generation', 'status': 'PASS'})
        else:
            tests.append({'test': 'Sentence Generation', 'status': 'FAIL', 'error': 'Word not in sentence'})
    except Exception as e:
        tests.append({'test': 'Sentence Generation', 'status': 'FAIL', 'error': str(e)})
    
    try:
        # Test SRS calculation
        next_review, interval = calculate_next_review(0, True)
        if isinstance(next_review, datetime) and interval >= 0:
            tests.append({'test': 'SRS Calculation', 'status': 'PASS'})
        else:
            tests.append({'test': 'SRS Calculation', 'status': 'FAIL', 'error': 'Invalid SRS result'})
    except Exception as e:
        tests.append({'test': 'SRS Calculation', 'status': 'FAIL', 'error': str(e)})
    
    all_passed = all(test['status'] == 'PASS' for test in tests)
    
    return jsonify({
        'overall_status': 'PASS' if all_passed else 'FAIL',
        'tests': tests
    })

@app.route('/api/sessions/<int:session_id>/stop', methods=['POST'])
def stop_session(session_id):
    """Stop session and cleanup preloader resources"""
    question_preloader.stop_session_preloader(session_id)
    return jsonify({'message': 'Session stopped successfully'})

@app.route('/api/sessions/<int:session_id>/complete', methods=['POST'])
def complete_session(session_id):
    """Complete session with timing information"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'completed')
        actual_time_spent = data.get('actual_time_spent', 0)
        
        # Update session with completion info
        cur.execute("""
            UPDATE sessions 
            SET completed = 1, 
                actual_time_spent = ?
            WHERE id = ?
        """, (actual_time_spent, session_id))
        
        # Get final session stats
        cur.execute("""
            SELECT total_questions, correct_answers, score
            FROM sessions 
            WHERE id = ?
        """, (session_id,))
        
        session_stats = cur.fetchone()
        
        conn.commit()
        
        # Stop preloader
        question_preloader.stop_session_preloader(session_id)
        
        return jsonify({
            'message': 'Session completed successfully',
            'reason': reason,
            'actual_time_spent': actual_time_spent,
            'final_stats': {
                'total_questions': session_stats['total_questions'] if session_stats else 0,
                'correct_answers': session_stats['correct_answers'] if session_stats else 0,
                'score': session_stats['score'] if session_stats else 0
            }
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/preloader/status/<int:session_id>')
def get_preloader_status(session_id):
    """Get preloader queue status for debugging"""
    status = question_preloader.get_queue_status(session_id)
    return jsonify(status)

# Dictionary Management API Endpoints

@app.route('/api/users/<int:user_id>/dictionaries', methods=['GET'])
def get_user_dictionaries(user_id):
    """Get all dictionaries for a user, including progress stats"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get dictionaries with word counts and user progress
        cur.execute("""
        SELECT 
            d.id,
            d.name,
            d.description,
            d.created_at,
            COUNT(DISTINCT w.id) as total_words,
            COUNT(DISTINCT uw.word_id) as encountered_words,
            COUNT(DISTINCT CASE WHEN uw.correct_count >= 1 THEN uw.word_id END) as learned_words,
            ROUND(AVG(CASE WHEN qa.id IS NOT NULL AND s.dictionary_id = d.id THEN qa.is_correct END) * 100, 1) as accuracy_rate
        FROM dictionaries d
        LEFT JOIN words w ON d.id = w.dictionary_id
        LEFT JOIN user_words uw ON w.id = uw.word_id AND uw.user_id = ?
        LEFT JOIN question_attempts qa ON w.id = qa.word_id
        LEFT JOIN sessions s ON qa.session_id = s.id AND s.user_id = ? AND s.dictionary_id = d.id
        WHERE d.created_by IS NULL OR d.created_by = ?
        GROUP BY d.id, d.name, d.description, d.created_at
        ORDER BY d.created_at DESC
        """, (user_id, user_id, user_id))
        
        dictionaries = []
        for row in cur.fetchall():
            completion_rate = 0
            encounter_rate = 0
            if row['total_words'] > 0:
                completion_rate = round((row['learned_words'] / row['total_words']) * 100, 1)
                encounter_rate = round((row['encountered_words'] / row['total_words']) * 100, 1)
            
            dictionaries.append({
                'id': row['id'],
                'name': row['name'],
                'description': row['description'],
                'created_at': row['created_at'],
                'total_words': row['total_words'],
                'encountered_words': row['encountered_words'],
                'learned_words': row['learned_words'],
                'completion_rate': completion_rate,
                'encounter_rate': encounter_rate,
                'accuracy_rate': row['accuracy_rate'] or 0
            })
        
        return jsonify({'dictionaries': dictionaries})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/dictionaries', methods=['POST'])
def create_dictionary():
    """Create a new dictionary"""
    data = request.get_json()
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    created_by = data.get('created_by')
    
    if not name:
        return jsonify({'error': 'Dictionary name is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
        INSERT INTO dictionaries (name, description, created_by)
        VALUES (?, ?, ?)
        """, (name, description, created_by))
        
        dictionary_id = cur.lastrowid
        conn.commit()
        
        return jsonify({
            'id': dictionary_id,
            'name': name,
            'description': description,
            'created_by': created_by
        }), 201
        
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Dictionary name might already exist'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/dictionaries/<int:dictionary_id>', methods=['DELETE'])
def delete_dictionary(dictionary_id):
    """Delete a dictionary and all its words"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if dictionary exists
        cur.execute("SELECT id, name FROM dictionaries WHERE id = ?", (dictionary_id,))
        dictionary = cur.fetchone()
        if not dictionary:
            return jsonify({'error': 'Dictionary not found'}), 404
        
        # Prevent deletion of default dictionary (ID = 1)
        if dictionary_id == 1:
            return jsonify({'error': 'Cannot delete the default dictionary'}), 400
        
        # Check if dictionary has any active sessions
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE dictionary_id = ?", (dictionary_id,))
        session_count = cur.fetchone()['count']
        
        # Delete associated words first
        cur.execute("DELETE FROM words WHERE dictionary_id = ?", (dictionary_id,))
        words_deleted = cur.rowcount
        
        # Delete the dictionary
        cur.execute("DELETE FROM dictionaries WHERE id = ?", (dictionary_id,))
        
        conn.commit()
        
        return jsonify({
            'message': f'Dictionary "{dictionary["name"]}" deleted successfully',
            'words_deleted': words_deleted,
            'sessions_affected': session_count
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/dictionaries/<int:dictionary_id>/import', methods=['POST'])
def import_dictionary_csv(dictionary_id):
    """Import words from CSV file into a specific dictionary"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be a CSV'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verify dictionary exists
        cur.execute("SELECT id FROM dictionaries WHERE id = ?", (dictionary_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Dictionary not found'}), 404
        
        # Parse CSV file
        file_content = file.read().decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(file_content))
        
        # Validate CSV headers
        required_fields = {'word'}
        if not required_fields.issubset(set(csv_reader.fieldnames or [])):
            return jsonify({'error': f'CSV must contain columns: {", ".join(required_fields)}'}), 400
        
        inserted = 0
        updated = 0
        
        for row in csv_reader:
            word = row.get('word', '').strip()
            if not word:
                continue
            
            category = row.get('category', '').strip()
            level = row.get('level', 'k12').strip()
            
            # Check if word already exists in this dictionary
            cur.execute("""
            SELECT id FROM words WHERE word = ? AND dictionary_id = ?
            """, (word, dictionary_id))
            
            existing = cur.fetchone()
            if existing:
                # Update existing word
                cur.execute("""
                UPDATE words SET category = ?, level = ? WHERE id = ?
                """, (category, level, existing['id']))
                updated += 1
            else:
                # Insert new word
                cur.execute("""
                INSERT INTO words (word, category, level, dictionary_id)
                VALUES (?, ?, ?, ?)
                """, (word, category, level, dictionary_id))
                inserted += 1
        
        conn.commit()
        
        return jsonify({
            'message': f'Import completed: {inserted} words added, {updated} words updated',
            'inserted': inserted,
            'updated': updated
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/users/<int:user_id>/wrongbook/import-to-dictionary', methods=['POST'])
def import_wrongbook_to_dictionary(user_id):
    """Import wrongbook CSV into a selected dictionary"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    dictionary_id = request.form.get('dictionary_id')
    
    if not dictionary_id:
        return jsonify({'error': 'Dictionary ID is required'}), 400
    
    try:
        dictionary_id = int(dictionary_id)
    except ValueError:
        return jsonify({'error': 'Invalid dictionary ID'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be a CSV'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verify dictionary exists
        cur.execute("SELECT id FROM dictionaries WHERE id = ?", (dictionary_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Dictionary not found'}), 404
        
        # Parse CSV file
        file_content = file.read().decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(file_content))
        
        # Validate CSV headers
        required_fields = {'word'}
        if not required_fields.issubset(set(csv_reader.fieldnames or [])):
            return jsonify({'error': f'CSV must contain columns: {", ".join(required_fields)}'}), 400
        
        words_added = 0
        words_marked = 0
        
        for row in csv_reader:
            word = row.get('word', '').strip()
            if not word:
                continue
            
            category = row.get('category', '').strip()
            level = row.get('level', 'k12').strip()
            
            # Check if word exists in dictionary
            cur.execute("""
            SELECT id FROM words WHERE word = ? AND dictionary_id = ?
            """, (word, dictionary_id))
            
            word_row = cur.fetchone()
            
            if not word_row:
                # Add word to dictionary
                cur.execute("""
                INSERT INTO words (word, category, level, dictionary_id)
                VALUES (?, ?, ?, ?)
                """, (word, category, level, dictionary_id))
                word_id = cur.lastrowid
                words_added += 1
            else:
                word_id = word_row['id']
            
            # Add/update user_words entry (mark as wrongbook)
            cur.execute("""
            INSERT OR REPLACE INTO user_words 
            (user_id, word_id, correct_count, last_reviewed, next_review, srs_interval, in_wrongbook)
            VALUES (?, ?, 0, NULL, datetime('now'), 0, 1)
            """, (user_id, word_id))
            words_marked += 1
        
        conn.commit()
        
        return jsonify({
            'message': f'Wrongbook import completed: {words_added} new words added, {words_marked} words marked for review',
            'words_added': words_added,
            'words_marked': words_marked
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

def cleanup_preloaders():
    """Cleanup all preloader threads on app exit"""
    print("Cleaning up preloader threads...")
    for session_id in list(question_preloader.preload_threads.keys()):
        question_preloader.stop_session_preloader(session_id)
    print("Cleanup completed.")

def signal_handler(signum, frame):
    """Handle termination signals for graceful shutdown"""
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    cleanup_preloaders()
    exit(0)

# Register cleanup function and signal handlers
atexit.register(cleanup_preloaders)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def create_app():
    """Application factory for external runners."""
    return app
def run_server():
    """Run the Flask development server using environment configuration."""
    try:
        # Determine debug mode based on environment variable
        debug_mode = os.environ.get('LEXIBOOST_ENV', 'development').lower() == 'development'
        port = int(os.environ.get('LEXIBOOST_PORT', '5000'))
        
        print(f"Starting LexiBoost server on port {port} (debug={debug_mode})")
        app.run(debug=debug_mode, host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt. Shutting down gracefully...")
        cleanup_preloaders()
    except Exception as e:
        print(f"Unexpected error during startup: {e}")
        cleanup_preloaders()
        raise


if __name__ == '__main__':
    run_server()