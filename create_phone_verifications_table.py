#!/usr/bin/env python3
"""
Script to create the phone_verifications table in the database
"""

import sqlite3
from pathlib import Path
from datetime import datetime

def create_phone_verifications_table():
    """Create the phone_verifications table"""
    
    db_path = Path(__file__).parent / "app" / "databases" / "myusage.db"
    print(f"Creating phone_verifications table in: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Create phone_verifications table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS phone_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            account_id TEXT,
            verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            verification_method TEXT DEFAULT 'phone_number',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        cursor.execute(create_table_sql)
        
        # Create index for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phone_verifications_phone ON phone_verifications(phone_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phone_verifications_active ON phone_verifications(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phone_verifications_session ON phone_verifications(session_id)")
        
        conn.commit()
        
        # Verify table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='phone_verifications'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            print("✅ phone_verifications table created successfully!")
            
            # Show table structure
            cursor.execute("PRAGMA table_info(phone_verifications)")
            columns = cursor.fetchall()
            print("\nTable structure:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")
            
            # Check if there are any existing records
            cursor.execute("SELECT COUNT(*) FROM phone_verifications")
            count = cursor.fetchone()[0]
            print(f"\nExisting records: {count}")
            
        else:
            print("❌ Failed to create phone_verifications table")
            
        conn.close()
        
    except Exception as e:
        print(f"Error creating table: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_phone_verifications_table()
