#!/usr/bin/env python3
"""
Quick check of current database state and verification flow
"""

import sqlite3
from pathlib import Path

def quick_check():
    """Quick check of current state"""
    
    print("🔍 Quick Check - Current State")
    print("=" * 40)
    
    # Check phone verifications
    conn = sqlite3.connect('app/databases/myusage.db')
    cursor = conn.cursor()
    
    # Check active verifications
    cursor.execute("""
        SELECT phone_number, account_id, verified_at, is_active 
        FROM phone_verifications 
        WHERE is_active = 1
        ORDER BY verified_at DESC
        LIMIT 1
    """)
    active_verification = cursor.fetchone()
    
    if active_verification:
        phone, account_id, verified_at, is_active = active_verification
        print(f"✅ Active verification found:")
        print(f"   Phone: {phone}")
        print(f"   Account: {account_id}")
        print(f"   Verified: {verified_at}")
        print(f"   Active: {is_active}")
        
        # Check customer data
        cursor.execute("SELECT name FROM accounts WHERE phone = ?", (phone,))
        customer = cursor.fetchone()
        if customer:
            print(f"   Customer: {customer[0]}")
        
        # Check meter reading
        cursor.execute("SELECT reading_value, usage FROM readings WHERE account_id = ?", (account_id,))
        reading = cursor.fetchone()
        if reading:
            reading_value, usage = reading
            print(f"   Meter reading: {reading_value} gallons")
            print(f"   Usage: {usage} gallons")
        else:
            print(f"   ❌ No meter reading found")
            
    else:
        print(f"❌ No active verification found")
        
        # Check if any verifications exist
        cursor.execute("SELECT COUNT(*) FROM phone_verifications")
        total_verifications = cursor.fetchone()[0]
        print(f"   Total verifications in table: {total_verifications}")
        
        # Check if customer exists
        cursor.execute("SELECT name, phone FROM accounts WHERE phone = '8056882679'")
        customer = cursor.fetchone()
        if customer:
            name, phone = customer
            print(f"   Customer exists: {name} ({phone})")
        else:
            print(f"   ❌ Customer not found")
    
    conn.close()
    print(f"\n🎯 Quick check completed!")

if __name__ == "__main__":
    quick_check()
