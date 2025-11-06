#!/usr/bin/env python3
"""
Database migration script to add timer-related fields to sessions table
"""

import sqlite3

# Database configuration
DATABASE = 'lexiboost.db'

def migrate_add_timer_fields():
    """Add timer-related fields to sessions table"""
    print("Starting migration: Add timer fields to sessions table")
    
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add actual_time_spent column if it doesn't exist
        if 'actual_time_spent' not in columns:
            cursor.execute("""
                ALTER TABLE sessions 
                ADD COLUMN actual_time_spent INTEGER DEFAULT 0
            """)
            print("✓ Added actual_time_spent column to sessions table")
        else:
            print("✓ actual_time_spent column already exists")
            
        # Add session_start_time column if it doesn't exist
        if 'session_start_time' not in columns:
            cursor.execute("""
                ALTER TABLE sessions 
                ADD COLUMN session_start_time TIMESTAMP
            """)
            print("✓ Added session_start_time column to sessions table")
        else:
            print("✓ session_start_time column already exists")
            
        # Add time_limit column if it doesn't exist
        if 'time_limit' not in columns:
            cursor.execute("""
                ALTER TABLE sessions 
                ADD COLUMN time_limit INTEGER DEFAULT 600
            """)
            print("✓ Added time_limit column to sessions table")
        else:
            print("✓ time_limit column already exists")
        
        conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_add_timer_fields()