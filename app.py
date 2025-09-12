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
from db_manager import DatabaseManager

app = Flask(__name__)
CORS(app)

# Database configuration
DATABASE = 'lexiboost.db'
db_manager = DatabaseManager(DATABASE)

def get_db_connection():
    """Get database connection"""
    return db_manager.get_db_connection()

# Mock LLM sentence generation
def generate_sentence_with_word(word):
    """Generate a simple sentence containing the target word"""
    templates = [
        f"The {word} is very important in our daily life.",
        f"I saw a beautiful {word} in the garden today.",
        f"My teacher told us about the {word} in class.",
        f"The children were excited to see the {word}.",
        f"We learned about {word} in our science lesson.",
        f"The {word} made everyone smile and laugh happily.",
        f"During summer vacation, we often see this {word}.",
        f"My family likes to talk about the {word}."
    ]
    return random.choice(templates)

def get_srs_intervals():
    """Return SRS intervals in days"""
    return [0, 1, 3, 7, 14]

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
    """Get next question for the session"""
    conn = get_db_connection()
    
    # Get session info
    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    
    user_id = session['user_id']
    
    # Check if session is complete (50 questions)
    question_count = conn.execute(
        'SELECT COUNT(*) as count FROM question_attempts WHERE session_id = ?',
        (session_id,)
    ).fetchone()['count']
    
    if question_count >= 50:
        conn.close()
        return jsonify({'session_complete': True})
    
    # Get words due for review (wrongbook) or random unseen words
    wrongbook_words = conn.execute('''
        SELECT w.*, uw.next_review, uw.srs_interval 
        FROM words w 
        JOIN user_words uw ON w.id = uw.word_id 
        WHERE uw.user_id = ? AND uw.in_wrongbook = 1 
        AND (uw.next_review IS NULL OR uw.next_review <= datetime('now'))
        ORDER BY uw.next_review ASC
        LIMIT 10
    ''', (user_id,)).fetchall()
    
    # Get unseen words
    unseen_words = conn.execute('''
        SELECT w.* FROM words w 
        WHERE w.id NOT IN (
            SELECT uw.word_id FROM user_words uw WHERE uw.user_id = ?
        )
        ORDER BY RANDOM()
        LIMIT 10
    ''', (user_id,)).fetchall()
    
    # Combine and select a word
    available_words = list(wrongbook_words) + list(unseen_words)
    if not available_words:
        conn.close()
        return jsonify({'error': 'No words available'}), 400
    
    target_word = random.choice(available_words)
    
    # Generate sentence
    sentence = generate_sentence_with_word(target_word['word'])
    
    # Generate distractors (wrong answers)
    distractors = conn.execute('''
        SELECT definition FROM words 
        WHERE id != ? AND definition != ?
        ORDER BY RANDOM()
        LIMIT 2
    ''', (target_word['id'], target_word['definition'])).fetchall()
    
    if len(distractors) < 2:
        # Fallback distractors
        distractors = [
            {'definition': 'a type of musical instrument'},
            {'definition': 'a kind of weather pattern'}
        ]
    
    # Create answer choices
    choices = [target_word['definition']] + [d['definition'] for d in distractors]
    random.shuffle(choices)
    
    conn.close()
    
    return jsonify({
        'question_id': f"{session_id}_{target_word['id']}",
        'word_id': target_word['id'],
        'sentence': sentence,
        'target_word': target_word['word'],
        'choices': choices,
        'correct_answer': target_word['definition'],
        'question_number': question_count + 1
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
    
    # Get session info
    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    user_id = session['user_id']
    
    # Record question attempt
    conn.execute('''
        INSERT INTO question_attempts 
        (session_id, word_id, question_text, correct_answer, user_answer, is_correct, explanation)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, word_id, question_text, correct_answer, user_answer, is_correct, correct_answer))
    
    # Update session score
    if is_correct:
        conn.execute(
            'UPDATE sessions SET correct_answers = correct_answers + 1, score = score + 1 WHERE id = ?',
            (session_id,)
        )
    
    conn.execute(
        'UPDATE sessions SET total_questions = total_questions + 1 WHERE id = ?',
        (session_id,)
    )
    
    # Handle wrongbook and SRS
    user_word = conn.execute(
        'SELECT * FROM user_words WHERE user_id = ? AND word_id = ?',
        (user_id, word_id)
    ).fetchone()
    
    if user_word:
        # Update existing record
        if is_correct:
            new_correct_count = user_word['correct_count'] + 1
            next_review, next_interval = calculate_next_review(user_word['srs_interval'], True)
            
            # Remove from wrongbook after 3 correct answers
            in_wrongbook = 1 if new_correct_count < 3 else 0
            
            conn.execute('''
                UPDATE user_words 
                SET correct_count = ?, last_reviewed = datetime('now'), 
                    next_review = ?, srs_interval = ?, in_wrongbook = ?
                WHERE id = ?
            ''', (new_correct_count, next_review, next_interval, in_wrongbook, user_word['id']))
        else:
            # Reset on incorrect answer
            next_review, next_interval = calculate_next_review(0, False)
            conn.execute('''
                UPDATE user_words 
                SET correct_count = 0, last_reviewed = datetime('now'),
                    next_review = ?, srs_interval = ?, in_wrongbook = 1
                WHERE id = ?
            ''', (next_review, next_interval, user_word['id']))
    else:
        # Create new user_word record
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
        'explanation': correct_answer,
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
    """Import wrongbook words from CSV"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be CSV format'}), 400
    
    try:
        # Read CSV file
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)
        
        conn = get_db_connection()
        imported_count = 0
        
        for row in csv_reader:
            if len(row) >= 2:
                word, definition = row[0].strip(), row[1].strip()
                if word and definition:
                    # Insert word if it doesn't exist
                    existing_word = conn.execute(
                        'SELECT id FROM words WHERE word = ?', (word,)
                    ).fetchone()
                    
                    if existing_word:
                        word_id = existing_word['id']
                    else:
                        cursor = conn.execute(
                            'INSERT INTO words (word, definition) VALUES (?, ?)',
                            (word, definition)
                        )
                        word_id = cursor.lastrowid
                    
                    # Add to user's wrongbook
                    existing_user_word = conn.execute(
                        'SELECT id FROM user_words WHERE user_id = ? AND word_id = ?',
                        (user_id, word_id)
                    ).fetchone()
                    
                    if not existing_user_word:
                        next_review = datetime.now()
                        conn.execute('''
                            INSERT INTO user_words 
                            (user_id, word_id, correct_count, next_review, srs_interval, in_wrongbook)
                            VALUES (?, ?, 0, ?, 0, 1)
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
    # Initialize database and seed data
    init_db()
    seed_initial_data()
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)