#!/usr/bin/env python3
"""
Stock Analyzer API Server
Serves stock data to the frontend via a simple Flask API.

Usage:
    pip install flask flask-cors yfinance requests
    python server.py
    
Then open http://localhost:5000 in your browser.
"""

from flask import Flask, jsonify, request, render_template, session, redirect
from flask_cors import CORS
from functools import wraps
import os
import json
import requests
from supabase import create_client
from PIL import Image
from io import BytesIO
import uuid


# Import our stock analyzer modules
from data_fetcher import get_stock_data
from scoring import calculate_score

import time

TICKER_TAPE_CACHE = None
TICKER_TAPE_CACHE_TIME = 0
TICKER_TAPE_TTL = 120  # seconds


app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)  # Allow cross-origin requests

# ============================================
# CONFIGURATION
# ============================================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-this-in-production')

# Supabase Configuration - Set these as environment variables or replace with your values
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://wtxxnhjknjwmlsqxdovv.supabase.co')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind0eHhuaGprbmp3bWxzcXhkb3Z2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU5NTY2MDQsImV4cCI6MjA4MTUzMjYwNH0.5gBkeZj8JOo2GEQ1AOmsarLV5WJ1-pZUZbDwbChgZPw')

SUPABASE_SERVICE_ROLE_KEY = os.environ.get(
    'SUPABASE_SERVICE_ROLE_KEY',  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind0eHhuaGprbmp3bWxzcXhkb3Z2Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTk1NjYwNCwiZXhwIjoyMDgxNTMyNjA0fQ.dNzVNFHniymLC1__--0-l7q4pQrALwbqRzCZXZWup10'
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)

print("=== SUPABASE CONNECTION TEST ===")

try:
    test = supabase.table('usernames').select('*').limit(1).execute()
    print("DB CONNECTED. Rows:", test.data)
except Exception as e:
    print("DB CONNECTION FAILED:", e)

print("=== END SUPABASE CONNECTION TEST ===")


# Load tickers
TICKER_FILE = os.path.join(os.path.dirname(__file__), "tickers.json")
with open(TICKER_FILE, "r") as f:
    ALL_TICKERS = json.load(f)
print(f"Loaded {len(ALL_TICKERS)} tickers")


# ============================================
# SUPABASE AUTH HELPERS
# ============================================
def get_user_from_token(access_token: str) -> dict | None:
    """Verify a Supabase JWT and return user data."""
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


def get_username_from_db(user_id: str) -> str | None:
    """Look up a user's display_name from the usernames table."""
    if not user_id:
        return None
    
    try:
        result = supabase.table('usernames') \
            .select('display_name') \
            .eq('user_id', user_id) \
            .limit(1) \
            .execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0].get('display_name')
        return None
    except Exception as e:
        print(f"Error fetching username from DB: {e}")
        return None

@app.route("/auth/reset")
def auth_reset():
    return render_template("reset.html")

def require_auth(f):
    """Decorator to protect API routes that require authentication."""
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
        
        # Get username from database
        db_username = get_username_from_db(user.get('id'))
        if db_username:
            session['display_name'] = db_username
        else:
            meta = user.get('user_metadata') or {}
            session['display_name'] = meta.get('display_name') or meta.get('full_name')

        request.user = user
        return f(*args, **kwargs)
    
    return decorated_function


def require_auth_page(f):
    """Decorator for page routes (redirects to auth instead of JSON error)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        access_token = session.get('supabase_access_token')
        
        if not access_token:
            # Store the intended destination
            session['auth_redirect'] = request.full_path
            return redirect('/auth')
        
        user = get_user_from_token(access_token)
        if not user:
            session.clear()
            return redirect('/auth')
        
        request.user = user
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================
# PAGE ROUTES
# ============================================
@app.route('/')
def home():
    user = None
    avatar_url = None
    display_name = None

    access_token = session.get('supabase_access_token')
    if access_token:
        user = get_user_from_token(access_token)
        if user:
            meta = user.get('user_metadata') or {}
            avatar_url = meta.get('avatar_url')
            display_name = meta.get('display_name') or meta.get('full_name')

    return render_template(
        'landing.html',
        avatar_url=avatar_url,
        display_name=display_name
    )


@app.route('/auth')
def auth_page():
    """Serve the unified auth page (login/signup with OAuth)."""
    # If already logged in, redirect to app
    if session.get('supabase_access_token'):
        user = get_user_from_token(session['supabase_access_token'])
        if user:
            return redirect('/index')
    return render_template('auth.html')


@app.route('/auth/callback')
def auth_callback():
    """Handle OAuth and magic link callbacks."""
    return render_template('auth_callback.html')


# Legacy routes - redirect to new auth page
@app.route('/login')
def login_page():
    return redirect('/auth')


@app.route('/signup')
def signup_page():
    return redirect('/auth')


@app.route('/index')
@require_auth_page
def index():
    """Serve the main app page (protected)."""
    return render_template('index.html')


@app.route('/analyze')
@require_auth_page
def analyze_page():
    """Serve the analyzer page (alternate route, protected)."""
    return render_template('index.html')


# ============================================
# AUTH API ROUTES
# ============================================
@app.route('/api/auth/session', methods=['POST'])
def store_session():
    """
    Store Supabase tokens in Flask session.
    Called from frontend after successful Supabase authentication.
    """
    data = request.json
    access_token = data.get('access_token')
    refresh_token = data.get('refresh_token')
    
    if not access_token:
        return jsonify({'error': 'Missing access token'}), 400
    
    # Verify the token is valid
    user = get_user_from_token(access_token)
    if not user:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Store in session
    session['supabase_access_token'] = access_token
    session['supabase_refresh_token'] = refresh_token
    session['user_id'] = user.get('id')
    session['user_email'] = user.get('email')
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.get('id'),
            'email': user.get('email')
        }
    })


@app.route('/api/auth/user')
def get_current_user():
    access_token = None

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        access_token = auth_header[7:]

    if not access_token:
        access_token = session.get('supabase_access_token')

    if not access_token:
        return jsonify({'authenticated': False}), 200

    user = get_user_from_token(access_token)
    if not user:
        session.clear()
        return jsonify({'authenticated': False}), 200

    res = supabase.table('usernames') \
        .select('display_name, avatar_url') \
        .eq('user_id', user['id']) \
        .single() \
        .execute()

    data = res.data or {}

    avatar_url = None
    if data.get('avatar_url'):
        avatar_url = supabase.storage.from_('avatars').get_public_url(
            data['avatar_url']
        )

    return jsonify({
        'authenticated': True,
        'user': {
            'id': user.get('id'),
            'email': user.get('email'),
            'created_at': user.get('created_at'),
            'display_name': data.get('display_name'),
            'avatar_url': avatar_url
        }
    })



@app.route('/api/logout', methods=['POST'])
def logout():
    """Clear session and log out."""
    session.clear()
    return jsonify({'success': True})


# ============================================
# STOCK API ROUTES
# ============================================
@app.route('/api/search-tickers')
def search_tickers():
    """Search for ticker symbols."""
    q = request.args.get('q', '').upper()
    if not q:
        return jsonify([])

    matches = [t for t in ALL_TICKERS if t.startswith(q)]
    return jsonify(matches[:10])

@app.route('/api/debug_insert')
def debug_insert():
    REAL_USER_ID = '5ef8c6a3-339e-4cdc-96bb-a18e9247f479'

    res = supabase.table('usernames').insert({
        'user_id': REAL_USER_ID,
        'display_name': 'DEBUG_TEST_USERNAME'
    }).execute()

    return jsonify(res.data)



@app.route('/api/analyze/<ticker>')
def analyze(ticker):
    """
    Analyze a stock and return JSON data.
    
    Example: GET /api/analyze/AAPL
    """
    ticker = ticker.upper().strip()
    
    if not ticker or len(ticker) > 10:
        return jsonify({'error': 'Invalid ticker symbol'}), 400
    
    # Fetch real stock data using yfinance
    metrics = get_stock_data(ticker)
    
    if metrics is None:
        return jsonify({'error': f'Could not fetch data for {ticker}. Please check the symbol.'}), 404
    
    # Calculate distance from 52-week high
    if 'distance_from_52w_high' not in metrics:
        high = metrics.get('fifty_two_week_high', metrics['current_price'])
        current = metrics['current_price']
        metrics['distance_from_52w_high'] = ((current - high) / high) * 100
    
    # Calculate the buy consideration score
    score_data = calculate_score(metrics)
    
    # Return combined data
    return jsonify({
        'success': True,
        'ticker': ticker,
        'metrics': metrics,
        'score': score_data
    })

@app.route('/api/username_available')
def username_available():
    username = request.args.get('username', '').strip()

    if not username:
        return jsonify({'available': False})

    res = supabase.table('usernames') \
        .select('display_name') \
        .eq('display_name', username) \
        .execute()

    return jsonify({'available': len(res.data) == 0})

@app.route('/api/claim_username', methods=['POST'])
def claim_username():
    access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not access_token:
        return jsonify({'error': 'Unauthorized'}), 401

    user = get_user_from_token(access_token)
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    data = request.json
    username = data.get('username', '').strip()

    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    # Validate username format
    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400
    
    if len(username) > 30:
        return jsonify({'error': 'Username must be 30 characters or less'}), 400
    
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({'error': 'Username can only contain letters, numbers, and underscores'}), 400

    # Check if user already has a username
    existing = get_username_from_db(user['id'])
    if existing:
        return jsonify({'error': 'You already have a username', 'username': existing}), 409

    try:
        res = supabase.table('usernames').insert({
            'user_id': user['id'],
            'display_name': username
        }).execute()

        return jsonify({'success': True, 'username': username})

    except Exception as e:
        print(f"Username claim error: {e}")
        return jsonify({
            'error': 'Username already taken'
        }), 409



@app.route('/api/ticker-tape')
def ticker_tape():
    global TICKER_TAPE_CACHE, TICKER_TAPE_CACHE_TIME

    now = time.time()
    if TICKER_TAPE_CACHE and now - TICKER_TAPE_CACHE_TIME < TICKER_TAPE_TTL:
        return jsonify(TICKER_TAPE_CACHE)

    import random
    import yfinance as yf

    stock_pool = [
        'AAPL','MSFT','GOOGL','AMZN','NVDA','TSLA','META','JPM','V','WMT',
        'JNJ','PG','MA','HD','CVX','MRK','ABBV','PEP','KO','COST'
    ]

    selected = random.sample(stock_pool, 10)  # ⬅️ reduce to 10

    try:
        data = yf.download(
            selected,
            period='1d',
            progress=False,
            threads=True,
            group_by='ticker'
        )

        results = []
        for symbol in selected:
            try:
                ticker_data = data[symbol]
                current = ticker_data['Close'].iloc[-1]
                open_price = ticker_data['Open'].iloc[-1]
                change_pct = ((current - open_price) / open_price) * 100

                results.append({
                    'symbol': symbol,
                    'price': round(float(current), 2),
                    'change': round(float(change_pct), 2)
                })
            except Exception:
                continue

        response = {'success': True, 'stocks': results}
        TICKER_TAPE_CACHE = response
        TICKER_TAPE_CACHE_TIME = now

        return jsonify(response)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})

@app.route('/profile')
@require_auth_page
def profile():
    user_id = session.get('user_id')

    avatar_url = None
    display_name = None

    if user_id:
        res = supabase.table('usernames') \
            .select('display_name, avatar_url') \
            .eq('user_id', user_id) \
            .single() \
            .execute()

        if res.data:
            avatar_url = res.data.get('avatar_url')
            display_name = res.data.get('display_name')

    return render_template(
        'profile.html',
        avatar_url=avatar_url,
        display_name=display_name
    )

from werkzeug.utils import secure_filename

@app.route('/api/avatar', methods=['POST'])
@require_auth
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'No file'}), 400

    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    user_id = request.user['id']
    
    # Generate unique filename to avoid conflicts
    import uuid
    ext = os.path.splitext(file.filename)[1] or '.jpg'
    filename = f"{uuid.uuid4()}{ext}"
    path = f"{user_id}/{filename}"
    
    content = file.read()

    try:
        # Try to remove old avatar first (ignore errors)
        try:
            existing = supabase.table('usernames') \
                .select('avatar_url') \
                .eq('user_id', user_id) \
                .single() \
                .execute()
            
            if existing.data and existing.data.get('avatar_url'):
                old_path = existing.data['avatar_url']
                supabase.storage.from_('avatars').remove([old_path])
        except Exception as e:
            print(f"Could not remove old avatar: {e}")

        # Upload new avatar
        res = supabase.storage.from_('avatars').upload(
            path,
            content,
            {'content-type': file.content_type, 'upsert': 'true'}
        )

        # Save path in DB
        supabase.table('usernames').update({
            'avatar_url': path
        }).eq('user_id', user_id).execute()

        return jsonify({'success': True, 'path': path})
        
    except Exception as e:
        print(f"Avatar upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500

@app.route('/api/profile')
@require_auth
def get_profile():
    user = request.user  # from require_auth
    user_id = user['id']

    res = supabase.table('usernames') \
        .select('display_name, avatar_url') \
        .eq('user_id', user_id) \
        .single() \
        .execute()

    data = res.data or {}

    avatar_url = None
    if data.get('avatar_url'):
        avatar_url = supabase.storage.from_('avatars').get_public_url(
            data['avatar_url']
        )

    return jsonify({
        'display_name': data.get('display_name'),
        'avatar_url': avatar_url,
        'email': user.get('email'),
        'created_at': user.get('created_at')
    })


@app.route('/api/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile (display name)."""
    user = request.user
    user_id = user['id']
    
    data = request.json
    display_name = data.get('display_name', '').strip()
    
    if not display_name:
        return jsonify({'error': 'Display name required'}), 400
    
    # Validate display name format
    if len(display_name) < 3:
        return jsonify({'error': 'Display name must be at least 3 characters'}), 400
    
    if len(display_name) > 30:
        return jsonify({'error': 'Display name must be 30 characters or less'}), 400
    
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', display_name):
        return jsonify({'error': 'Display name can only contain letters, numbers, and underscores'}), 400
    
    try:
        # Check if username is taken by someone else
        existing = supabase.table('usernames') \
            .select('user_id') \
            .eq('display_name', display_name) \
            .execute()
        
        if existing.data:
            for row in existing.data:
                if row['user_id'] != user_id:
                    return jsonify({'error': 'Display name already taken'}), 409
        
        # Check if user has a record
        user_record = supabase.table('usernames') \
            .select('user_id') \
            .eq('user_id', user_id) \
            .execute()
        
        if user_record.data:
            # Update existing record
            supabase.table('usernames').update({
                'display_name': display_name
            }).eq('user_id', user_id).execute()
        else:
            # Create new record
            supabase.table('usernames').insert({
                'user_id': user_id,
                'display_name': display_name
            }).execute()
        
        session['display_name'] = display_name
        
        return jsonify({'success': True, 'display_name': display_name})
        
    except Exception as e:
        print(f"Profile update error: {e}")
        return jsonify({'error': 'Failed to update profile'}), 500


@app.route('/api/account', methods=['DELETE'])
@require_auth
def delete_account():
    """Delete user account and all associated data."""
    user = request.user
    user_id = user['id']
    
    try:
        # Delete avatar from storage
        try:
            avatar_record = supabase.table('usernames') \
                .select('avatar_url') \
                .eq('user_id', user_id) \
                .single() \
                .execute()
            
            if avatar_record.data and avatar_record.data.get('avatar_url'):
                supabase.storage.from_('avatars').remove([avatar_record.data['avatar_url']])
        except Exception as e:
            print(f"Could not delete avatar: {e}")
        
        # Delete username record
        try:
            supabase.table('usernames').delete().eq('user_id', user_id).execute()
        except Exception as e:
            print(f"Could not delete username record: {e}")
        
        # Delete user from Supabase Auth (requires service role key)
        try:
            response = requests.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={
                    'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
                    'apikey': SUPABASE_ANON_KEY
                }
            )
            
            if response.status_code not in [200, 204]:
                print(f"Auth user delete returned: {response.status_code}")
        except Exception as e:
            print(f"Could not delete auth user: {e}")
        
        # Clear session
        session.clear()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Account deletion error: {e}")
        return jsonify({'error': 'Failed to delete account'}), 500


# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("  STOCK ANALYZER API SERVER")
    print("="*50)
    print("\nStarting server at http://localhost:5000")
    print("Open this URL in your browser to use the app.\n")
    print("API Endpoints:")
    print("  GET  /api/analyze/<TICKER>  - Analyze a stock")
    print("  GET  /api/auth/user         - Get current user")
    print("  POST /api/auth/session      - Store auth session")
    print("  POST /api/logout            - Log out")
    print("  GET  /api/profile           - Get profile")
    print("  PUT  /api/profile           - Update profile")
    print("  DELETE /api/account         - Delete account")
    print("  GET  /api/health            - Health check")
    print("\nPress Ctrl+C to stop the server.\n")
    
    app.run(debug=True, port=5000)