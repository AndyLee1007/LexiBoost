#!/usr/bin/env python3
"""
LexiBoost - English Vocabulary Learning App for Kids
Main Flask application entry point
"""
import ast
import sqlite3
import json
import csv
import random
from typing import List, Dict, Any, Tuple, Optional
import os

# Database configuration
DATABASE = 'lexiboost.db'
INITIAL_CSV = os.getenv(
    "LEXIBOOST_INITIAL_CSV",
    "data/explained/b1_words_with_topics_explained.csv",
).strip()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with required tables (with distractors_en/zh)."""
    conn = get_db_connection()
    cur = conn.cursor()

    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # sessions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        session_date DATE,
        total_questions INTEGER DEFAULT 0,
        correct_answers INTEGER DEFAULT 0,
        score INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )""")

    # words - definitions are now real-time generated, not stored
    cur.execute("""
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL UNIQUE,
        category TEXT,
        level TEXT DEFAULT 'k12',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # user_words - keep for learning progress tracking
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        word_id INTEGER,
        correct_count INTEGER DEFAULT 0,
        last_reviewed TIMESTAMP,
        next_review TIMESTAMP,
        srs_interval INTEGER DEFAULT 0,
        in_wrongbook INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (word_id) REFERENCES words (id)
    )""")

    # question_attempts - keep for session tracking
    cur.execute("""
    CREATE TABLE IF NOT EXISTS question_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        word_id INTEGER,
        question_text TEXT,
        correct_answer TEXT,
        user_answer TEXT,
        is_correct INTEGER,
        explanation TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions (id),
        FOREIGN KEY (word_id) REFERENCES words (id)
    )""")

    # Indexes (only for remaining tables)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_words_word ON words(word)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_words_user_id ON user_words(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_words_word_id ON user_words(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")

    conn.commit()
    conn.close()

def seed_from_csv(csv_path: str = INITIAL_CSV) -> None:
    """Import words from CSV into SQLite (only word and metadata, definitions are real-time).

    CSV expected columns:
      word, category (optional), level (optional)
    """
    if not os.path.exists(csv_path):
        print(f"[WARN] CSV not found: {csv_path}")
        return

    # --- helpers ---
    def _line_iter(f):
        """Filter out comments (#...) and blank lines."""
        for line in f:
            s = (line or "").strip()
            if not s or s.startswith("#"):
                continue
            yield line

    conn = get_db_connection()
    cur = conn.cursor()

    inserted, updated = 0, 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(_line_iter(f))
        need = {"word"}
        miss = need - set(reader.fieldnames or [])
        if miss:
            raise ValueError(f"CSV missing columns: {miss}; got {reader.fieldnames}")

        for row in reader:
            word = (row.get("word") or "").strip()
            if not word:
                continue

            category = (row.get("category") or "").strip()
            level = (row.get("level") or "k12").strip()

            # upsert words (only word and metadata)
            cur.execute("SELECT id FROM words WHERE word = ? LIMIT 1", (word,))
            row0 = cur.fetchone()
            if row0:
                word_id = row0["id"]
                cur.execute("""
                    UPDATE words
                       SET category = ?,
                           level = ?
                     WHERE id = ?
                """, (category, level, word_id))
                updated += 1
            else:
                cursor = cur.execute("""
                    INSERT INTO words (word, category, level)
                    VALUES (?, ?, ?)
                """, (word, category, level))
                word_id = cursor.lastrowid
                inserted += 1

    conn.commit()
    conn.close()
    print(f"[INFO] CSV import done: inserted={inserted}, updated={updated}, file={csv_path}")

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


if __name__ == '__main__':
    # Initialize database and seed data
    init_db()
    seed_from_csv()