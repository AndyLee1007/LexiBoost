#!/usr/bin/env python3
"""
LexiBoost - English Vocabulary Learning App for Kids
Main Flask application entry point
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import csv
import io
from datetime import datetime, timedelta
import random
import os
import atexit
from definition_service import definition_service
from question_preloader import question_preloader

app = Flask(__name__)
CORS(app)

# Database configuration
DATABASE = 'lexiboost.db'

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
    conn = get_db_connection()
    
    # Create new session
    session_date = datetime.now().date()
    cursor = conn.execute(
        'INSERT INTO sessions (user_id, session_date) VALUES (?, ?)',
        (user_id, session_date)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Start question preloader for this session
    question_preloader.start_session_preloader(session_id, user_id)
    
    return jsonify({'session_id': session_id})

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
    max_questions = get_max_questions_per_session()
    question_count = conn.execute(
        'SELECT COUNT(*) as count FROM question_attempts WHERE session_id = ?',
        (session_id,)
    ).fetchone()['count']
    if question_count >= max_questions:
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
    # Get words already asked in this session to avoid repetition
    asked_word_ids = set()
    asked_words = conn.execute('''
        SELECT DISTINCT word_id FROM question_attempts 
        WHERE session_id = ?
    ''', (session_id,)).fetchall()
    asked_word_ids = {row['word_id'] for row in asked_words}

    # Candidate words: due wrongbook first, then unseen (exclude already asked)
    wrongbook_words = conn.execute('''
        SELECT w.*, uw.next_review, uw.srs_interval 
        FROM words w 
        JOIN user_words uw ON w.id = uw.word_id 
        WHERE uw.user_id = ? AND uw.in_wrongbook = 1 
          AND (uw.next_review IS NULL OR uw.next_review <= datetime('now'))
          AND TRIM(w.word) <> ''
        ORDER BY uw.next_review ASC
        LIMIT 50
    ''', (user_id,)).fetchall()
    
    # Filter out already asked words
    wrongbook_words = [w for w in wrongbook_words if w['id'] not in asked_word_ids]

    unseen_words = conn.execute('''
        SELECT w.* FROM words w
        WHERE TRIM(w.word) <> ''
          AND w.id NOT IN (SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?)
        ORDER BY RANDOM()
        LIMIT 50
    ''', (user_id,)).fetchall()
    
    # Filter out already asked words
    unseen_words = [w for w in unseen_words if w['id'] not in asked_word_ids]

    # Select target word for fallback generation
    candidates = list(wrongbook_words) + list(unseen_words)
    
    # Check if we have any valid candidates
    if not candidates:
        # Check if it's because all words have been exhausted in this session
        total_wrongbook = conn.execute('''
            SELECT COUNT(*) as count FROM user_words uw
            JOIN words w ON w.id = uw.word_id
            WHERE uw.user_id = ? AND uw.in_wrongbook = 1 
              AND (uw.next_review IS NULL OR uw.next_review <= datetime('now'))
              AND TRIM(w.word) <> ''
        ''', (user_id,)).fetchone()['count']
        
        total_unseen = conn.execute('''
            SELECT COUNT(*) as count FROM words w
            WHERE TRIM(w.word) <> ''
              AND w.id NOT IN (SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?)
        ''', (user_id,)).fetchone()['count']
        
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
        if not is_correct:
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
        'hover_zh_enabled': _env_flag('LEXIBOOST_HOVER_ZH', default=False)
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

@app.route('/api/preloader/status/<int:session_id>')
def get_preloader_status(session_id):
    """Get preloader queue status for debugging"""
    status = question_preloader.get_queue_status(session_id)
    return jsonify(status)

def cleanup_preloaders():
    """Cleanup all preloader threads on app exit"""
    for session_id in list(question_preloader.preload_threads.keys()):
        question_preloader.stop_session_preloader(session_id)

# Register cleanup function
atexit.register(cleanup_preloaders)

if __name__ == '__main__':
    try:
        # Run the application
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        cleanup_preloaders()