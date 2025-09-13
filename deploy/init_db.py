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

    # words
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

    # word_pos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS word_pos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    )""")

    # word_examples
    cur.execute("""
    CREATE TABLE IF NOT EXISTS word_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        en TEXT NOT NULL,
        zh TEXT,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
    )""")

    # user_words
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

    # question_attempts
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

    # --- Distractors: migrate to en/zh + ord ---
    # Check existing schema
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='word_distractors'")
    
    # fresh create (new schema)
    cur.execute("""
    CREATE TABLE word_distractors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER NOT NULL,
        ord INTEGER NOT NULL,             -- 0,1,2 to keep order
        en TEXT NOT NULL,
        zh TEXT,                          -- nullable; fill later if needed
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE,
        UNIQUE(word_id, ord)              -- exactly 3 per word by app logic
    )""")

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_words_word ON words(word)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pos_word_id ON word_pos(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ex_word_id ON word_examples(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dis_word_id ON word_distractors(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dis_word_ord ON word_distractors(word_id, ord)")

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
      word, category, pos, register, examples,
      definition_zh, definition_en, notes,
      # NEW (preferred):
      distractors_en, distractors_zh
      # OLD (still supported):
      distractors

    - pos: list[str] (JSON / Python-literal / comma-separated)
    - examples: list[{'en': str, 'zh': str}] (JSON / Python-literal)
    - distractors_en / distractors_zh: list[str] (JSON / Python-literal / comma-separated)
    - distractors (old): list[str] (JSON / Python-literal / comma-separated)
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

    # detect distractor table schema (new vs old)
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

            pos_list  = _parse_str_list(row.get("pos") or "")
            examples  = _parse_examples(row.get("examples") or "")

            # NEW preferred fields
            distractors_en = _parse_str_list(row.get("distractors_en") or "")
            distractors_zh = _parse_str_list(row.get("distractors_zh") or "")

            # OLD fallback
            old_distractors = _parse_str_list(row.get("distractors") or "")

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

            # Insert distractors (new schema -> (ord, en, zh); old schema -> text)
            
            pairs: List[Tuple[str, Optional[str]]] = []

            if distractors_en:
                # Use new fields; align length to min(len_en, len_zh) if zh provided
                if distractors_zh:
                    m = min(len(distractors_en), len(distractors_zh))
                    if m < len(distractors_en) or m < len(distractors_zh):
                        print(f"[WARN] '{word}': distractors_en/zh length mismatch; using first {m}.")
                    pairs = [(distractors_en[i], distractors_zh[i]) for i in range(m)]
                else:
                    pairs = [(d, None) for d in distractors_en]
            elif old_distractors:
                # Backward-compat: map old English-only to en, zh=None
                pairs = [(d, None) for d in old_distractors]
            else:
                pairs = []

            # keep only first 3; warn if more
            if len(pairs) > 3:
                print(f"[WARN] '{word}': more than 3 distractors provided; truncating to 3.")
                pairs = pairs[:3]

            for i, (en_txt, zh_txt) in enumerate(pairs):
                en_txt = (en_txt or "").strip()
                zh_txt = (zh_txt or None)
                if en_txt:  # must have English text
                    cur.execute(
                        "INSERT INTO word_distractors(word_id, ord, en, zh) VALUES (?, ?, ?, ?)",
                        (word_id, i, en_txt, zh_txt)
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