#!/usr/bin/env python3
"""
Check the phone_verifications table structure
"""

import sqlite3
from pathlib import Path

def check_table_structure():
    """Check the phone_verifications table structure"""
    
    db_path = Path(__file__).parent / "app" / "databases" / "myusage.db"
    print(f"Checking table structure in: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check table structure
        cursor.execute("PRAGMA table_info(phone_verifications)")
        columns = cursor.fetchall()
        
        print(f"\n📋 phone_verifications table structure:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]}) - Default: {col[4]} - NotNull: {col[3]}")
        
        # Check if table has any data
        cursor.execute("SELECT COUNT(*) FROM phone_verifications")
        count = cursor.fetchone()[0]
        print(f"\n📊 Total records: {count}")
        
        if count > 0:
            cursor.execute("SELECT * FROM phone_verifications LIMIT 1")
            sample = cursor.fetchone()
            print(f"📝 Sample record: {sample}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_table_structure()
