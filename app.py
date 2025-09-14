#!/usr/bin/env python3
"""
LexiBoost - English Vocabulary Learning App for Kids
Main Flask application entry point
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import json
import csv
import io
from datetime import datetime, timedelta
import random
import os

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
    """Start a new quiz session"""
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
    
    return jsonify({'session_id': session_id})

@app.route('/api/sessions/<int:session_id>/question')
def get_question(session_id):
    """Get next question; returns i18n choices and hover flag, with strict word validation."""
    conn = get_db_connection()

    # 1) validate session
    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    user_id = session['user_id']

    # 2) stop at 50 questions
    question_count = conn.execute(
        'SELECT COUNT(*) as count FROM question_attempts WHERE session_id = ?',
        (session_id,)
    ).fetchone()['count']
    if question_count >= 50:
        conn.close()
        return jsonify({'session_complete': True})

    # 3) candidate words: due wrongbook first, then unseen
    #    严格过滤：word 非空且 definition_en 非空
    wrongbook_words = conn.execute('''
        SELECT w.*, uw.next_review, uw.srs_interval 
        FROM words w 
        JOIN user_words uw ON w.id = uw.word_id 
        WHERE uw.user_id = ? AND uw.in_wrongbook = 1 
          AND (uw.next_review IS NULL OR uw.next_review <= datetime('now'))
          AND TRIM(w.word) <> '' AND TRIM(IFNULL(w.definition_en,'')) <> ''
        ORDER BY uw.next_review ASC
        LIMIT 20
    ''', (user_id,)).fetchall()

    unseen_words = conn.execute('''
        SELECT w.* FROM words w
        WHERE TRIM(w.word) <> '' AND TRIM(IFNULL(w.definition_en,'')) <> ''
          AND w.id NOT IN (SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?)
        ORDER BY RANDOM()
        LIMIT 20
    ''', (user_id,)).fetchall()

    # 4) 合并并在 Python 侧再做一次保险过滤
    def _valid(row):
        return bool((row['word'] or '').strip()) and bool((row['definition_en'] or '').strip())
    candidates = [w for w in (list(wrongbook_words) + list(unseen_words)) if _valid(w)]

    if not candidates:
        conn.close()
        return jsonify({'error': 'No valid words available. Please seed the DB or clean empty rows.'}), 400

    target = random.choice(candidates)
    word_id = target['id']
    word_txt = (target['word'] or '').strip()
    correct_en = (target['definition_en'] or '').strip()
    correct_zh = (target['definition_zh'] or '').strip()

    # 双重保险：若仍然无效，直接换一条
    if not word_txt or not correct_en:
        for cand in candidates:
            if (cand['word'] or '').strip() and (cand['definition_en'] or '').strip():
                target = cand
                word_id = target['id']
                word_txt = (target['word'] or '').strip()
                correct_en = (target['definition_en'] or '').strip()
                correct_zh = (target['definition_zh'] or '').strip()
                break
    if not word_txt or not correct_en:
        conn.close()
        return jsonify({'error': 'No valid question can be formed for the selected word.'}), 400

    # 5) sentence: prefer DB example
    ex = conn.execute(
        'SELECT en, zh FROM word_examples WHERE word_id = ? ORDER BY RANDOM() LIMIT 1',
        (word_id,)
    ).fetchone()
    if ex and (ex['en'] or ex['zh']):
        sentence = ex['en'] or ex['zh']
    else:
        sentence = generate_sentence_with_word(word_txt)

    # 6) distractors (new schema preferred; fallback to old)
    cur = conn.execute("PRAGMA table_info(word_distractors)")
    dis_cols = {row[1] for row in cur.fetchall()}
    use_new_schema = {"ord", "en", "zh"}.issubset(dis_cols)

    distractors_i18n = []
    if use_new_schema:
        rows = conn.execute(
            'SELECT ord, en, zh FROM word_distractors WHERE word_id = ? ORDER BY ord',
            (word_id,)
        ).fetchall()
        for r in rows:
            en = (r['en'] or '').strip()
            zh = (r['zh'] or '').strip()
            if en and en != correct_en:
                distractors_i18n.append({'en': en, 'zh': zh})
    else:
        rows = conn.execute(
            'SELECT text FROM word_distractors WHERE word_id = ? ORDER BY id',
            (word_id,)
        ).fetchall()
        for r in rows:
            en = (r['text'] or '').strip()
            if en and en != correct_en:
                distractors_i18n.append({'en': en, 'zh': ''})

    # top-up if less than 2 with other words' definitions (避开正确义项 & 空值)
    need = max(0, 2 - len(distractors_i18n))
    if need > 0:
        filler = conn.execute(
            '''SELECT definition_en, definition_zh FROM words 
               WHERE id != ? AND TRIM(IFNULL(definition_en,'')) <> '' AND definition_en <> ?
               ORDER BY RANDOM() LIMIT ?''',
            (word_id, correct_en, need)
        ).fetchall()
        for r in filler:
            en = (r['definition_en'] or '').strip()
            zh = (r['definition_zh'] or '').strip()
            if en and en != correct_en:
                distractors_i18n.append({'en': en, 'zh': zh})

    # keep max 3; ensure at least 2
    distractors_i18n = distractors_i18n[:3]
    while len(distractors_i18n) < 2:
        distractors_i18n.append({'en': 'a kind of weather pattern', 'zh': '一种天气模式'})

    # 7) build choices (i18n)
    correct_pair = {'en': correct_en, 'zh': correct_zh}
    choices_i18n = [correct_pair] + distractors_i18n
    random.shuffle(choices_i18n)

    hover_zh_enabled = _env_flag('LEXIBOOST_HOVER_ZH', default=False)

    conn.close()
    return jsonify({
        'question_id': f"{session_id}_{word_id}",
        'word_id': word_id,
        'target_word': word_txt,
        'sentence': sentence,
        'question_text': f'What does "{word_txt}" mean?',
        'choices_i18n': choices_i18n,
        'correct_answer_i18n': correct_pair,
        'question_number': question_count + 1,
        'hover_zh_enabled': hover_zh_enabled
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

    # fetch zh explanation for this word (for popup bilingual content)
    w = conn.execute('SELECT definition_zh, definition_en FROM words WHERE id = ?', (word_id,)).fetchone()
    explanation_en = (w['definition_en'] or correct_answer or "").strip() if w else (correct_answer or "")
    explanation_zh = (w['definition_zh'] or "").strip() if w else ""

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
    """Import wrongbook words from CSV (columns: word, definition)."""
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
            if len(row) >= 2:
                word = (row[0] or '').strip()
                definition = (row[1] or '').strip()
                if not word or not definition:
                    continue

                # find or create word (definition_en)
                existing = conn.execute(
                    'SELECT id FROM words WHERE word = ?',
                    (word,)
                ).fetchone()
                if existing:
                    word_id = existing['id']
                else:
                    cursor = conn.execute(
                        'INSERT INTO words (word, definition_en) VALUES (?, ?)',
                        (word, definition)
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

if __name__ == '__main__':
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)