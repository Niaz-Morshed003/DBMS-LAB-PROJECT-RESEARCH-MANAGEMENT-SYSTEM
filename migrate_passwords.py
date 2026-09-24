#!/usr/bin/env python3
"""
Migration script to hash all existing plain-text passwords in the database.
Run this once after deploying the password hashing changes.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from passlib.hash import bcrypt
from sqlalchemy import create_engine, text
from database import DATABASE_URL

def hash_existing_passwords():
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Get all users with their current passwords
        result = conn.execute(text("SELECT user_id, email, password, role FROM user"))
        users = result.fetchall()
        
        print(f"Found {len(users)} users in database")
        
        updated_count = 0
        skipped_count = 0
        
        for user in users:
            user_id, email, password, role = user
            
           
            if password and password.startswith('$2b$'):
                print(f"  Skipping {email} ({role}) - already hashed")
                skipped_count += 1
                continue
            
       
            if password:
                hashed = bcrypt.hash(password)
                conn.execute(
                    text("UPDATE user SET password = :hashed WHERE user_id = :uid"),
                    {"hashed": hashed, "uid": user_id}
                )
                print(f"  Hashed password for {email} ({role})")
                updated_count += 1
            else:
                print(f"  WARNING: {email} ({role}) has empty password!")
        
        conn.commit()
        print(f"\nMigration complete:")
        print(f"  Updated: {updated_count} passwords")
        print(f"  Skipped: {skipped_count} (already hashed)")

if __name__ == "__main__":
    hash_existing_passwords()