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
from typing import List, Dict, Any
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
    """Initialize database with required tables"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
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
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL UNIQUE,
        definition_en TEXT NOT NULL,
        definition_zh TEXT,
        register TEXT,
        category TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS word_pos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS word_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        en TEXT NOT NULL,
        zh TEXT,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    )""")

    cur.execute("""
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
    )""")

    cur.execute("""
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
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS word_distractors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    )""")

    # Index for faster lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_words_word ON words(word)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pos_word_id ON word_pos(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ex_word_id ON word_examples(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dis_word_id ON word_distractors(word_id)")

    conn.commit()
    conn.close()

def _parse_pos(cell: str) -> List[str]:
    if not cell:
        return []
    s = cell.strip()
    try:
        # JSON first
        return [str(x).strip() for x in json.loads(s)]
    except Exception:
        try:
            return [str(x).strip() for x in ast.literal_eval(s)]
        except Exception:
            # fallback: comma separated
            return [t.strip() for t in s.split(",") if t.strip()]

def _parse_examples(cell: str) -> List[Dict[str, Any]]:
    if not cell:
        return []
    s = cell.strip()
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    return []

def _parse_str_list(cell: str) -> List[str]:
    """Parse a list of strings from CSV cell (JSON / Python-literal / comma separated)."""
    if not cell:
        return []
    s = cell.strip()
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x).strip() for x in v]
    except Exception:
        pass
    try:
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return [str(x).strip() for x in v]
    except Exception:
        pass
    # fallback: comma separated
    return [t.strip() for t in s.split(",") if t.strip()]

def seed_from_csv(csv_path: str = INITIAL_CSV) -> None:
    """Import words and related fields from CSV into SQLite.
    CSV expected columns (some optional):
      word, category, pos, register, examples, distractors,
      definition_zh, definition_en, notes
    - pos: list[str] (JSON / Python-literal / comma-separated)
    - examples: list[{'en': str, 'zh': str}] (JSON / Python-literal)
    - distractors: list[str] (JSON / Python-literal / comma-separated)
    """
    if not os.path.exists(csv_path):
        print(f"[WARN] CSV not found: {csv_path}")
        return

    # --- helpers (local to this function) ---
    def _line_iter(f):
        """Filter out comments (#...) and blank lines."""
        for line in f:
            s = (line or "").strip()
            if not s or s.startswith("#"):
                continue
            yield line

    def _parse_str_list(cell: str) -> List[str]:
        """Parse a list of strings from CSV cell (JSON / Python-literal / comma separated)."""
        if not cell:
            return []
        s = cell.strip()
        # JSON first
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x).strip() for x in v]
        except Exception:
            pass
        # Python literal (single quotes etc.)
        try:
            v = ast.literal_eval(s)
            if isinstance(v, list):
                return [str(x).strip() for x in v]
        except Exception:
            pass
        # fallback: comma separated
        return [t.strip() for t in s.split(",") if t.strip()]

    def _parse_pos(cell: str) -> List[str]:
        return _parse_str_list(cell)

    def _parse_examples(cell: str) -> List[Dict[str, Any]]:
        """Parse examples: list of dicts with keys 'en' and 'zh'."""
        if not cell:
            return []
        s = cell.strip()
        # JSON first
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return v
        except Exception:
            pass
        # Python literal (single quotes)
        try:
            v = ast.literal_eval(s)
            if isinstance(v, list):
                return v
        except Exception:
            pass
        return []

    conn = get_db_connection()
    cur = conn.cursor()

    inserted, updated = 0, 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(_line_iter(f))
        need = {"word", "definition_en"}
        miss = need - set(reader.fieldnames or [])
        if miss:
            raise ValueError(f"CSV missing columns: {miss}; got {reader.fieldnames}")

        for row in reader:
            word = (row.get("word") or "").strip()
            if not word:
                continue

            definition_en = (row.get("definition_en") or "").strip()
            definition_zh = (row.get("definition_zh") or "").strip()
            register      = (row.get("register") or "").strip()
            category      = (row.get("category") or "").strip()
            notes         = (row.get("notes") or "").strip()

            pos_list    = _parse_pos(row.get("pos") or "")
            examples    = _parse_examples(row.get("examples") or "")
            distractors = _parse_str_list(row.get("distractors") or "")

            # upsert words
            cur.execute("SELECT id FROM words WHERE word = ? LIMIT 1", (word,))
            row0 = cur.fetchone()
            if row0:
                word_id = row0["id"]
                cur.execute("""
                    UPDATE words
                       SET definition_en = ?,
                           definition_zh = ?,
                           register      = ?,
                           category      = ?,
                           notes         = ?
                     WHERE id = ?
                """, (definition_en, definition_zh, register, category, notes, word_id))
                updated += 1
                # Clean up and rebuild children
                cur.execute("DELETE FROM word_pos         WHERE word_id = ?", (word_id,))
                cur.execute("DELETE FROM word_examples    WHERE word_id = ?", (word_id,))
                cur.execute("DELETE FROM word_distractors WHERE word_id = ?", (word_id,))
            else:
                cur.execute("""
                    INSERT INTO words(word, definition_en, definition_zh, register, category, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (word, definition_en, definition_zh, register, category, notes))
                word_id = cur.lastrowid
                inserted += 1

            # Insert pos
            for tag in pos_list:
                if tag:
                    cur.execute("INSERT INTO word_pos(word_id, tag) VALUES (?, ?)", (word_id, tag))

            # Insert examples
            for ex in examples:
                en = str(ex.get("en") or "").strip()
                zh = str(ex.get("zh") or "").strip()
                if en or zh:
                    cur.execute(
                        "INSERT INTO word_examples(word_id, en, zh) VALUES (?, ?, ?)",
                        (word_id, en, zh)
                    )

            # Insert distractors
            for d in distractors:
                d = d.strip()
                if d:
                    cur.execute(
                        "INSERT INTO word_distractors(word_id, text) VALUES (?, ?)",
                        (word_id, d)
                    )

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