"""
Supabase Authentication Module
Handles server-side auth verification and user management.
"""

import os
from functools import wraps
from flask import request, jsonify, redirect, session
import requests

# ============================================
# CONFIGURATION
# ============================================
# Set these as environment variables or replace with your values
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'YOUR_SUPABASE_URL')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', 'YOUR_SUPABASE_ANON_KEY')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')  # Optional: for admin operations


def get_user_from_token(access_token: str) -> dict | None:
    """
    Verify a Supabase JWT and return user data.
    
    Args:
        access_token: The JWT from the client
        
    Returns:
        User dict if valid, None if invalid
    """
    if not access_token:
        return None
    
    try:
        response = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                'Authorization': f'Bearer {access_token}',
                'apikey': SUPABASE_ANON_KEY
            }
        )
        
        if response.status_code == 200:
            return response.json()
        return None
        
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None


def require_auth(f):
    """
    Decorator to protect routes that require authentication.
    Checks for Supabase JWT in Authorization header or session.
    
    Usage:
        @app.route('/api/protected')
        @require_auth
        def protected_route():
            user = request.user  # User data available here
            return jsonify({'user': user['email']})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        access_token = None
        
        # Try to get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            access_token = auth_header[7:]
        
        # Fallback to session
        if not access_token:
            access_token = session.get('supabase_access_token')
        
        if not access_token:
            return jsonify({'error': 'Authentication required'}), 401
        
        user = get_user_from_token(access_token)
        if not user:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Attach user to request
        request.user = user
        return f(*args, **kwargs)
    
    return decorated_function


def require_auth_page(f):
    """
    Decorator for page routes (redirects to auth instead of JSON error).
    
    Usage:
        @app.route('/dashboard')
        @require_auth_page
        def dashboard():
            return render_template('dashboard.html')
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        access_token = session.get('supabase_access_token')
        
        if not access_token:
            return redirect('/auth')
        
        user = get_user_from_token(access_token)
        if not user:
            session.clear()
            return redirect('/auth')
        
        request.user = user
        return f(*args, **kwargs)
    
    return decorated_function


def store_session(access_token: str, refresh_token: str, user: dict):
    """
    Store Supabase tokens in Flask session.
    Call this after successful client-side authentication.
    """
    session['supabase_access_token'] = access_token
    session['supabase_refresh_token'] = refresh_token
    session['user_id'] = user.get('id')
    session['user_email'] = user.get('email')


def clear_session():
    """Clear all auth-related session data."""
    session.pop('supabase_access_token', None)
    session.pop('supabase_refresh_token', None)
    session.pop('user_id', None)
    session.pop('user_email', None)


def refresh_session() -> bool:
    """
    Attempt to refresh the access token using the refresh token.
    
    Returns:
        True if refresh successful, False otherwise
    """
    refresh_token = session.get('supabase_refresh_token')
    if not refresh_token:
        return False
    
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                'apikey': SUPABASE_ANON_KEY,
                'Content-Type': 'application/json'
            },
            json={'refresh_token': refresh_token}
        )
        
        if response.status_code == 200:
            data = response.json()
            session['supabase_access_token'] = data['access_token']
            session['supabase_refresh_token'] = data['refresh_token']
            return True
        
        return False
        
    except Exception as e:
        print(f"Error refreshing token: {e}")
        return False


# ============================================
# ADMIN FUNCTIONS (require service key)
# ============================================

def get_user_by_email(email: str) -> dict | None:
    """
    Get a user by email (requires service key).
    """
    if not SUPABASE_SERVICE_KEY:
        print("Warning: SUPABASE_SERVICE_KEY not set")
        return None
    
    try:
        response = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers={
                'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
                'apikey': SUPABASE_ANON_KEY
            },
            params={'email': email}
        )
        
        if response.status_code == 200:
            users = response.json().get('users', [])
            return users[0] if users else None
        return None
        
    except Exception as e:
        print(f"Error fetching user: {e}")
        return None


def delete_user(user_id: str) -> bool:
    """
    Delete a user by ID (requires service key).
    """
    if not SUPABASE_SERVICE_KEY:
        print("Warning: SUPABASE_SERVICE_KEY not set")
        return False
    
    try:
        response = requests.delete(
            f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
            headers={
                'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
                'apikey': SUPABASE_ANON_KEY
            }
        )
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error deleting user: {e}")
        return False
