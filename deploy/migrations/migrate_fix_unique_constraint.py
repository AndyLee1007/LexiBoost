#!/usr/bin/env python3
"""
Migration script to fix UNIQUE constraint on words table.
Changes UNIQUE constraint from 'word' to 'word + dictionary_id' combination.
"""

import sqlite3
import sys
import os
from datetime import datetime

def migrate_database():
    db_path = 'lexiboost.db'
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found!")
        return False
    
    # Create backup
    backup_path = f'lexiboost_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    
    try:
        # Copy database file for backup
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"Created backup: {backup_path}")
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        print("Starting migration...")
        
        # 1. Create new words table with correct constraints
        cur.execute("""
        CREATE TABLE words_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            category TEXT,
            level TEXT DEFAULT 'k12',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dictionary_id INTEGER DEFAULT 1,
            UNIQUE(word, dictionary_id)
        )
        """)
        
        # 2. Copy data from old table to new table
        cur.execute("""
        INSERT INTO words_new (id, word, category, level, created_at, dictionary_id)
        SELECT id, word, category, level, created_at, dictionary_id
        FROM words
        """)
        
        # 3. Drop old table
        cur.execute("DROP TABLE words")
        
        # 4. Rename new table
        cur.execute("ALTER TABLE words_new RENAME TO words")
        
        # 5. Recreate any indexes if needed
        # (Add index creation here if necessary)
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Verify the new structure
        cur.execute("PRAGMA table_info(words)")
        columns = cur.fetchall()
        print("\nNew words table structure:")
        for col in columns:
            print(f"  {col[1]} {col[2]} {'NOT NULL' if col[3] else ''} {'PRIMARY KEY' if col[5] else ''}")
        
        # Check unique constraints
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='words'")
        table_sql = cur.fetchone()
        print(f"\nNew table SQL:\n{table_sql[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Migration failed: {e}")
        if os.path.exists(backup_path):
            print(f"You can restore from backup: {backup_path}")
        return False

if __name__ == "__main__":
    print("=== LexiBoost Database Migration ===")
    print("Fixing UNIQUE constraint on words table")
    print("Changing from UNIQUE(word) to UNIQUE(word, dictionary_id)")
    print()
    
    if migrate_database():
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)