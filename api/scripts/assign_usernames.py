#!/usr/bin/env python3
"""
assign_usernames.py

Reads usernames.txt and assigns real names to user1-user100 with proper roles.
Students get role='student', Admins get role='admin'.
"""
import json
import hashlib
from pathlib import Path

# Password for all users
PASSWORD = "pedestrian2024"
PASSWORD_HASH = hashlib.sha256(PASSWORD.encode()).hexdigest()

def parse_usernames_file(filepath):
    """Parse usernames.txt and separate students from admins."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    students = []
    admins = []
    is_admin_section = False

    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Check for ADMIN marker
        if line.upper() == 'ADMIN':
            is_admin_section = True
            continue

        # Clean the name (remove leading/trailing spaces and pipes)
        name = line.strip('| \t')

        if name:
            if is_admin_section:
                admins.append(name)
            else:
                students.append(name)

    return students, admins

def create_users_json(students, admins, output_path):
    """Create users.json with proper role assignments."""
    users = {}
    user_number = 1

    # Assign students
    for i, student_name in enumerate(students, start=1):
        username = f"user{user_number}"
        users[username] = {
            "password_hash": PASSWORD_HASH,
            "full_name": student_name,
            "role": "student",
            "active": True,
            "user_id": user_number
        }
        user_number += 1
        print(f"  {username} -> {student_name} (student)")

    # Assign admins
    for i, admin_name in enumerate(admins):
        username = f"user{user_number}"
        users[username] = {
            "password_hash": PASSWORD_HASH,
            "full_name": admin_name,
            "role": "admin",
            "active": True,
            "user_id": user_number
        }
        user_number += 1
        print(f"  {username} -> {admin_name} (admin)")

    # Fill remaining slots up to user100 with placeholder accounts
    while user_number <= 100:
        username = f"user{user_number}"
        users[username] = {
            "password_hash": PASSWORD_HASH,
            "full_name": f"User {user_number}",
            "role": "student",
            "active": False,  # Inactive placeholder
            "user_id": user_number
        }
        user_number += 1

    # Write to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

    return len(students), len(admins), user_number - 1

def main():
    # Paths
    api_dir = Path(__file__).parent.parent
    usernames_file = api_dir / 'usernames.txt'
    output_file = api_dir / 'users.json'

    print("=" * 60)
    print("ASSIGNING USERNAMES TO USERS")
    print("=" * 60)

    # Parse usernames
    print(f"\nReading usernames from: {usernames_file}")
    students, admins = parse_usernames_file(usernames_file)

    print(f"\nFound:")
    print(f"  - {len(students)} students")
    print(f"  - {len(admins)} admins")
    print(f"  - Total: {len(students) + len(admins)} users")

    # Create users.json
    print(f"\nAssigning users:")
    n_students, n_admins, total = create_users_json(students, admins, output_file)

    print(f"\n" + "=" * 60)
    print(f"SUCCESS! Created {output_file}")
    print(f"  - Students: {n_students} (user1-user{n_students})")
    print(f"  - Admins: {n_admins} (user{n_students+1}-user{n_students+n_admins})")
    print(f"  - Placeholders: {100 - (n_students + n_admins)} (inactive)")
    print(f"  - Total accounts: 100")
    print(f"\nPassword for all users: {PASSWORD}")
    print(f"Password hash: {PASSWORD_HASH}")
    print("=" * 60)

if __name__ == "__main__":
    main()
