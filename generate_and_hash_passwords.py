#!/usr/bin/env python3
"""
Script to generate unique secure passwords for all users, hash them with bcrypt,
update the database, and output plain text passwords for login.
Run this once to fix the password mismatch issue.
"""

import sys
import os
import secrets
import string
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from passlib.hash import bcrypt
from sqlalchemy import create_engine, text
from database import DATABASE_URL

def generate_secure_password(length=12):
    """Generate a cryptographically secure random password."""
    # Use letters, digits, and safe special characters
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_and_hash_all_passwords():
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Get all users
        result = conn.execute(text("SELECT user_id, email, role FROM user ORDER BY user_id"))
        users = result.fetchall()
        
        print(f"Found {len(users)} users in database")
        print("=" * 80)
        print(f"{'User ID':<8} {'Email':<35} {'Role':<10} {'Plain Password':<20} {'Status'}")
        print("=" * 80)
        
        updated_count = 0
        password_list = []
        
        for user in users:
            user_id, email, role = user
            
            # Generate unique secure password
            plain_password = generate_secure_password(12)
            
            # Hash with bcrypt
            hashed_password = bcrypt.hash(plain_password)
            
            # Update database
            conn.execute(
                text("UPDATE user SET password = :hashed WHERE user_id = :uid"),
                {"hashed": hashed_password, "uid": user_id}
            )
            
            password_list.append({
                'user_id': user_id,
                'email': email,
                'role': role,
                'plain_password': plain_password
            })
            
            # Print for immediate use (masked for security in logs, but shown here for you)
            print(f"{user_id:<8} {email:<35} {role:<10} {plain_password:<20} Updated")
            updated_count += 1
        
        conn.commit()
        
        print("=" * 80)
        print(f"\n✅ Successfully updated {updated_count} passwords")
        print("\n📋 LOGIN CREDENTIALS (Save these securely!):")
        print("-" * 80)
        
        # Group by role for easier reading
        for role in ['admin', 'Faculty', 'Student']:
            role_users = [u for u in password_list if u['role'] == role]
            if role_users:
                print(f"\n### {role.upper()} USERS ({len(role_users)} users) ###")
                for u in role_users:
                    print(f"  ID: {u['user_id']:3} | {u['email']:<35} | Pass: {u['plain_password']}")
        
        print("\n" + "=" * 80)
        print("⚠️  IMPORTANT: Save these passwords NOW. They won't be shown again!")
        print("⚠️  After logging in, each user should change their password immediately.")
        print("=" * 80)
        
        # Also save to a file for backup
        import json
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"generated_passwords_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(password_list, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Passwords also saved to: {filename}")
        print("   (Delete this file after distributing credentials!)")

if __name__ == "__main__":
    generate_and_hash_all_passwords()