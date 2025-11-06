#!/usr/bin/env python3
"""
Migration script to add hover_zh_enabled field to sessions table
This field tracks whether LEXIBOOST_HOVER_ZH was enabled during each session
"""

import sqlite3
import sys
import os

def migrate_add_hover_field():
    """Add hover_zh_enabled field to sessions table"""
    
    # Get database path
    db_path = 'lexiboost.db'
    if not os.path.exists(db_path):
        print(f"Error: Database file {db_path} not found")
        sys.exit(1)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'hover_zh_enabled' in columns:
            print("Column 'hover_zh_enabled' already exists in sessions table")
            return
        
        # Add the new column
        print("Adding hover_zh_enabled column to sessions table...")
        cursor.execute("""
            ALTER TABLE sessions 
            ADD COLUMN hover_zh_enabled INTEGER DEFAULT 0
        """)
        
        # Set default value for existing sessions based on current environment
        # Assume existing sessions had hover disabled (conservative approach)
        cursor.execute("""
            UPDATE sessions 
            SET hover_zh_enabled = 0 
            WHERE hover_zh_enabled IS NULL
        """)
        
        conn.commit()
        print("✅ Successfully added hover_zh_enabled column to sessions table")
        
        # Verify the change
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE hover_zh_enabled IS NOT NULL")
        count = cursor.fetchone()[0]
        print(f"✅ Updated {count} existing sessions with default hover_zh_enabled=0")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    migrate_add_hover_field()