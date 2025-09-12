#!/usr/bin/env python3
"""
LexiBoost Database Manager
Handles database initialization, connection, and data seeding
"""

import sqlite3
import csv
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, database_path='lexiboost.db'):
        self.database_path = database_path
    
    def get_db_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize database with required tables"""
        conn = self.get_db_connection()
        
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
                category TEXT,
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
        logger.info("Database tables initialized successfully")

    def load_words_from_csv(self, csv_file_path):
        """Load words from CSV file into the database"""
        if not os.path.exists(csv_file_path):
            logger.error(f"CSV file not found: {csv_file_path}")
            return 0
        
        conn = self.get_db_connection()
        loaded_count = 0
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                # Skip BOM if present
                content = file.read()
                if content.startswith('\ufeff'):
                    content = content[1:]
                
                # Parse CSV
                csv_reader = csv.DictReader(content.splitlines())
                
                for row in csv_reader:
                    word = row.get('word', '').strip()
                    category = row.get('category', '').strip()
                    
                    if word and word not in ['word', '']:  # Skip header and empty rows
                        # Check if word already exists
                        existing = conn.execute(
                            'SELECT id FROM words WHERE word = ?', (word,)
                        ).fetchone()
                        
                        if not existing:
                            # Create a simple definition for now
                            definition = f"A word in the {category} category" if category else "A vocabulary word"
                            
                            conn.execute(
                                'INSERT INTO words (word, definition, category) VALUES (?, ?, ?)',
                                (word, definition, category)
                            )
                            loaded_count += 1
                            
            conn.commit()
            logger.info(f"Successfully loaded {loaded_count} words from {csv_file_path}")
            
        except Exception as e:
            logger.error(f"Error loading CSV file {csv_file_path}: {str(e)}")
            conn.rollback()
        finally:
            conn.close()
            
        return loaded_count

    def load_words_from_directory(self, data_directory):
        """Load all CSV files from the data directory"""
        if not os.path.exists(data_directory):
            logger.error(f"Data directory not found: {data_directory}")
            return 0
        
        total_loaded = 0
        csv_files = [f for f in os.listdir(data_directory) if f.endswith('.csv')]
        
        if not csv_files:
            logger.warning(f"No CSV files found in {data_directory}")
            return 0
        
        for csv_file in csv_files:
            csv_path = os.path.join(data_directory, csv_file)
            loaded = self.load_words_from_csv(csv_path)
            total_loaded += loaded
            logger.info(f"Loaded {loaded} words from {csv_file}")
        
        return total_loaded

    def seed_fallback_data(self):
        """Seed database with fallback vocabulary words if no CSV data is loaded"""
        conn = self.get_db_connection()
        
        # Check if words already exist
        existing = conn.execute('SELECT COUNT(*) as count FROM words').fetchone()
        if existing['count'] > 0:
            conn.close()
            logger.info("Words already exist in database, skipping fallback seeding")
            return 0
        
        # Sample vocabulary words for kids
        sample_words = [
            ('happy', 'feeling or showing pleasure or contentment', 'emotion'),
            ('run', 'move at a speed faster than a walk', 'action'),
            ('book', 'a written or printed work consisting of pages', 'object'),
            ('cat', 'a small domesticated carnivorous mammal', 'animal'),
            ('big', 'of considerable size or extent', 'adjective'),
            ('red', 'of a color at the end of the spectrum', 'color'),
            ('house', 'a building for human habitation', 'place'),
            ('water', 'a colorless, transparent liquid', 'substance'),
            ('tree', 'a woody perennial plant', 'nature'),
            ('friend', 'a person whom one knows and likes', 'relationship'),
            ('school', 'an institution for education', 'place'),
            ('play', 'engage in activity for enjoyment', 'action'),
            ('food', 'any nutritious substance that people eat', 'substance'),
            ('dog', 'a domesticated carnivorous mammal', 'animal'),
            ('sun', 'the star around which the earth orbits', 'nature'),
            ('moon', 'the natural satellite of the earth', 'nature'),
            ('car', 'a road vehicle powered by an engine', 'vehicle'),
            ('bird', 'a warm-blooded egg-laying vertebrate', 'animal'),
            ('fish', 'a limbless cold-blooded vertebrate animal', 'animal'),
            ('flower', 'the reproductive structure of a flowering plant', 'nature')
        ]
        
        loaded_count = 0
        for word, definition, category in sample_words:
            conn.execute(
                'INSERT INTO words (word, definition, category) VALUES (?, ?, ?)',
                (word, definition, category)
            )
            loaded_count += 1
        
        conn.commit()
        conn.close()
        logger.info(f"Seeded {loaded_count} fallback words into database")
        return loaded_count

    def get_word_count(self):
        """Get total number of words in the database"""
        conn = self.get_db_connection()
        count = conn.execute('SELECT COUNT(*) as count FROM words').fetchone()['count']
        conn.close()
        return count

    def test_connection(self):
        """Test database connection"""
        try:
            conn = self.get_db_connection()
            conn.execute('SELECT 1').fetchone()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False