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
import re
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

app = Flask(__name__)
CORS(app)

# Database configuration
DATABASE = 'lexiboost.db'

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with required tables"""
    conn = get_db_connection()
    
    # Users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Words table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            definition TEXT NOT NULL,
            difficulty_level INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User words (wrongbook) table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            word_id INTEGER,
            correct_count INTEGER DEFAULT 0,
            last_reviewed TIMESTAMP,
            next_review TIMESTAMP,
            srs_interval INTEGER DEFAULT 0,
            in_wrongbook BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')
    
    # Sessions table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_date DATE,
            total_questions INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            completed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Question attempts table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS question_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            word_id INTEGER,
            question_text TEXT,
            correct_answer TEXT,
            user_answer TEXT,
            is_correct BOOLEAN,
            explanation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id),
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def seed_initial_data():
    """Seed database with initial vocabulary words"""
    conn = get_db_connection()
    
    # Check if words already exist
    existing = conn.execute('SELECT COUNT(*) as count FROM words').fetchone()
    if existing['count'] > 0:
        conn.close()
        return
    
    # Sample vocabulary words for kids
    sample_words = [
        ('happy', 'feeling or showing pleasure or contentment'),
        ('run', 'move at a speed faster than a walk'),
        ('book', 'a written or printed work consisting of pages'),
        ('cat', 'a small domesticated carnivorous mammal'),
        ('big', 'of considerable size or extent'),
        ('red', 'of a color at the end of the spectrum'),
        ('house', 'a building for human habitation'),
        ('water', 'a colorless, transparent liquid'),
        ('tree', 'a woody perennial plant'),
        ('friend', 'a person whom one knows and likes'),
        ('school', 'an institution for education'),
        ('play', 'engage in activity for enjoyment'),
        ('food', 'any nutritious substance that people eat'),
        ('dog', 'a domesticated carnivorous mammal'),
        ('sun', 'the star around which the earth orbits'),
        ('moon', 'the natural satellite of the earth'),
        ('car', 'a road vehicle powered by an engine'),
        ('bird', 'a warm-blooded egg-laying vertebrate'),
        ('fish', 'a limbless cold-blooded vertebrate animal'),
        ('flower', 'the reproductive structure of a flowering plant')
    ]
    
    for word, definition in sample_words:
        conn.execute(
            'INSERT INTO words (word, definition) VALUES (?, ?)',
            (word, definition)
        )
    
    conn.commit()
    conn.close()

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

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file"""
    if not PyPDF2:
        raise ImportError("PyPDF2 is required for PDF processing")
    
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")

def extract_words_from_text(text):
    """Extract unique words from text, filtering out common words and noise"""
    # Convert to lowercase and extract words (letters only)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Common words to filter out (basic stop words)
    stop_words = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did', 'she', 'use', 'way', 'what', 'when', 'will', 'with', 'have', 'this', 'that', 'they', 'from', 'been', 'each', 'like', 'more', 'said', 'some', 'time', 'very', 'were', 'well', 'come', 'down', 'first', 'good', 'into', 'just', 'look', 'make', 'many', 'over', 'than', 'them', 'these', 'would', 'about', 'after', 'before', 'could', 'other', 'right', 'their', 'there', 'water', 'where', 'which', 'words', 'write'
    }
    
    # Filter out stop words and duplicates
    unique_words = list(set([word for word in words if word not in stop_words and len(word) >= 3]))
    
    return sorted(unique_words)

def extract_categories_from_pdf_metadata(pdf_file):
    """Extract categories from PDF metadata or attachments (basic implementation)"""
    # This is a basic implementation - in practice, you'd need more sophisticated
    # logic to extract categories from PDF attachments or specific sections
    categories = {}
    
    try:
        if PyPDF2:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            # Check if there are any annotations or metadata that might contain categories
            if pdf_reader.metadata:
                # Look for category information in metadata
                for key, value in pdf_reader.metadata.items():
                    if 'category' in str(key).lower() or 'subject' in str(key).lower():
                        # Basic parsing - this would need to be customized based on actual PDF structure
                        pass
    except Exception:
        pass
    
    return categories

@app.route('/api/preprocess-pdf', methods=['POST'])
def preprocess_pdf():
    """Preprocess PDF file and generate TSV format"""
    if not PyPDF2:
        return jsonify({'error': 'PDF processing not available - PyPDF2 not installed'}), 500
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be PDF format'}), 400
    
    try:
        # Extract text from PDF
        pdf_text = extract_text_from_pdf(file)
        
        # Extract words from the text
        words = extract_words_from_text(pdf_text)
        
        # Extract categories (basic implementation)
        file.seek(0)  # Reset file pointer
        categories = extract_categories_from_pdf_metadata(file)
        
        # Generate TSV content
        tsv_lines = ['word\tcategory\tmeaning\tmeaning1\tsentence']
        
        for word in words:
            # Get category for word (if available)
            category = categories.get(word, '')
            
            # For this basic implementation, we'll use the word as both meaning and meaning1
            # In a real scenario, you'd want to look up actual definitions
            meaning = f"a word related to {word}"
            meaning1 = f"definition of {word}"
            
            # Generate a sentence using the existing sentence generation logic
            sentence = generate_sentence_with_word(word)
            
            # Add to TSV
            tsv_lines.append(f"{word}\t{category}\t{meaning}\t{meaning1}\t{sentence}")
        
        # Create response with TSV content
        tsv_content = '\n'.join(tsv_lines)
        
        return jsonify({
            'message': f'Successfully processed PDF and extracted {len(words)} words',
            'word_count': len(words),
            'tsv_content': tsv_content,
            'words_processed': words[:10]  # Show first 10 words as preview
        })
    
    except Exception as e:
        return jsonify({'error': f'Error processing PDF: {str(e)}'}), 400

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