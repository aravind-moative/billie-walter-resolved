#!/usr/bin/env python3
"""
Check verification details in database
"""

import sqlite3
from pathlib import Path

def check_details():
    db_path = Path(__file__).parent / "app" / "databases" / "myusage.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check phone_verifications table
    cursor.execute("SELECT * FROM phone_verifications")
    records = cursor.fetchall()
    
    print(f"📊 Verification Records: {len(records)}")
    for i, record in enumerate(records, 1):
        print(f"\nRecord {i}:")
        print(f"  ID: {record[0]}")
        print(f"  Phone: {record[1]}")
        print(f"  Account ID: {record[2]}")
        print(f"  Verified At: {record[3]}")
        print(f"  Session ID: {record[4]}")
        print(f"  Verification Method: {record[5]}")
        print(f"  Is Active: {record[6]}")
    
    conn.close()

if __name__ == "__main__":
    check_details()
