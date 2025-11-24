#!/usr/bin/env python3
"""
auth.py

Simple authentication module for the pedestrian prediction API.
Provides basic username/password authentication using SHA-256 hashed passwords.
"""
import json
import hashlib
import os
from functools import wraps
from flask import request, jsonify
from typing import Optional, Dict, Any


# Load users from users.json
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_users() -> Dict[str, Any]:
    """Load users from users.json file."""
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate a user with username or full name and password.

    Args:
        username: Username (e.g. 'user1') or full name (e.g. 'אור לילוז') to authenticate
        password: Plain text password

    Returns:
        True if authentication successful, False otherwise
    """
    users = load_users()

    # Try to find user by username first
    if username in users:
        user = users[username]

        # Check if user is active
        if not user.get('active', True):
            return False

        # Verify password hash
        password_hash = hash_password(password)
        return password_hash == user['password_hash']

    # If not found by username, try to find by full_name
    for user_key, user_data in users.items():
        if user_data.get('full_name') == username:
            # Check if user is active
            if not user_data.get('active', True):
                return False

            # Verify password hash
            password_hash = hash_password(password)
            return password_hash == user_data['password_hash']

    # User not found
    return False


def get_user_info(username: str) -> Optional[Dict[str, Any]]:
    """
    Get user information (without password hash).

    Args:
        username: Username (e.g. 'user1') or full name (e.g. 'אור לילוז') to look up

    Returns:
        User info dict or None if not found
    """
    users = load_users()

    # Try to find user by username first
    if username in users:
        user = users[username].copy()
        user.pop('password_hash', None)  # Never return password hash
        user['username'] = username
        return user

    # If not found by username, try to find by full_name
    for user_key, user_data in users.items():
        if user_data.get('full_name') == username:
            user = user_data.copy()
            user.pop('password_hash', None)  # Never return password hash
            user['username'] = user_key  # Return the actual username (user1, user2, etc.)
            return user

    return None


def require_auth(f):
    """
    Decorator to require authentication for Flask routes.

    Expects Basic Auth or username/password in request body.

    Usage:
        @app.route('/api/protected')
        @require_auth
        def protected_endpoint():
            username = request.auth_username  # Added by decorator
            return jsonify({"message": f"Hello {username}"})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try Basic Auth first
        auth = request.authorization
        if auth:
            username = auth.username
            password = auth.password
        else:
            # Try JSON body
            data = request.get_json(silent=True) or {}
            username = data.get('username')
            password = data.get('password')

        if not username or not password:
            return jsonify({
                "error": "Authentication required",
                "message": "Provide username and password via Basic Auth or request body"
            }), 401

        if not authenticate_user(username, password):
            return jsonify({
                "error": "Authentication failed",
                "message": "Invalid username or password"
            }), 401

        # Store username in request context for use in route
        request.auth_username = username
        return f(*args, **kwargs)

    return decorated_function


# Example usage in Flask app:
if __name__ == '__main__':
    # Test authentication
    print("Testing authentication...")

    # Test valid user
    if authenticate_user('user1', 'pedestrian2024'):
        print("[OK] user1 authentication successful")
    else:
        print("[FAIL] user1 authentication failed")

    # Test invalid password
    if not authenticate_user('user1', 'wrongpassword'):
        print("[OK] Invalid password rejected correctly")
    else:
        print("[FAIL] Invalid password accepted (security issue!)")

    # Test invalid user
    if not authenticate_user('nonexistent', 'pedestrian2024'):
        print("[OK] Nonexistent user rejected correctly")
    else:
        print("[FAIL] Nonexistent user accepted (security issue!)")

    # Get user info
    user_info = get_user_info('user1')
    if user_info:
        print(f"[OK] User info: {user_info}")

    print("\n[INFO] To use in Flask app:")
    print("  from auth import require_auth")
    print("  ")
    print("  @app.route('/api/protected')")
    print("  @require_auth")
    print("  def protected_route():")
    print("      username = request.auth_username")
    print("      return jsonify({'message': f'Hello {username}'})")
