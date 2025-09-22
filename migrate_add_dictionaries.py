#!/usr/bin/env python3
"""
Database migration script to add dictionary support
"""
import sqlite3
import os
import sys

DATABASE = 'lexiboost.db'

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_add_dictionaries():
    """Add dictionaries table and update existing tables"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Step 1: Create dictionaries table
        print("Creating dictionaries table...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS dictionaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )""")
        
        # Step 2: Create default dictionary for existing words
        print("Creating default dictionary...")
        cur.execute("""
        INSERT OR IGNORE INTO dictionaries (id, name, description, created_by) 
        VALUES (1, 'Default Dictionary', 'System default dictionary', NULL)
        """)
        
        # Step 3: Check if dictionary_id column exists in words table
        cur.execute("PRAGMA table_info(words)")
        columns = [column[1] for column in cur.fetchall()]
        
        if 'dictionary_id' not in columns:
            print("Adding dictionary_id to words table...")
            # Add dictionary_id column to words table
            cur.execute("""
            ALTER TABLE words ADD COLUMN dictionary_id INTEGER DEFAULT 1
            """)
            
            # Add foreign key constraint (manually since SQLite doesn't support ADD CONSTRAINT)
            # We'll handle this with application logic
            
            # Update all existing words to use default dictionary
            cur.execute("""
            UPDATE words SET dictionary_id = 1 WHERE dictionary_id IS NULL
            """)
        else:
            print("dictionary_id column already exists in words table")
        
        # Step 4: Check if dictionary_id column exists in sessions table
        cur.execute("PRAGMA table_info(sessions)")
        columns = [column[1] for column in cur.fetchall()]
        
        if 'dictionary_id' not in columns:
            print("Adding dictionary_id to sessions table...")
            # Add dictionary_id column to sessions table
            cur.execute("""
            ALTER TABLE sessions ADD COLUMN dictionary_id INTEGER DEFAULT 1
            """)
            
            # Update all existing sessions to use default dictionary
            cur.execute("""
            UPDATE sessions SET dictionary_id = 1 WHERE dictionary_id IS NULL
            """)
        else:
            print("dictionary_id column already exists in sessions table")
        
        # Step 5: Create indexes for performance
        print("Creating indexes...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_words_dictionary_id ON words(dictionary_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_dictionary_id ON sessions(dictionary_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_dictionaries_created_by ON dictionaries(created_by)")
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Verify the migration
        print("\nVerifying migration:")
        cur.execute("SELECT COUNT(*) as count FROM dictionaries")
        dict_count = cur.fetchone()['count']
        print(f"Dictionaries: {dict_count}")
        
        cur.execute("SELECT COUNT(*) as count FROM words WHERE dictionary_id = 1")
        words_count = cur.fetchone()['count']
        print(f"Words in default dictionary: {words_count}")
        
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE dictionary_id = 1") 
        sessions_count = cur.fetchone()['count']
        print(f"Sessions in default dictionary: {sessions_count}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print(f"Database {DATABASE} not found. Please run init_db.py first.")
        sys.exit(1)
    
    migrate_add_dictionaries()