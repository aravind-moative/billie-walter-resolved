#!/usr/bin/env python3
"""
Quick check if verification was stored in database
"""

import sqlite3
from pathlib import Path

def quick_check():
    db_path = Path(__file__).parent / "app" / "databases" / "myusage.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check phone_verifications table
    cursor.execute("SELECT COUNT(*) FROM phone_verifications")
    count = cursor.fetchone()[0]
    print(f"Total verifications in table: {count}")
    
    if count > 0:
        cursor.execute("SELECT * FROM phone_verifications")
        records = cursor.fetchall()
        print(f"Records:")
        for record in records:
            print(f"  {record}")
    
    conn.close()

if __name__ == "__main__":
    quick_check()
