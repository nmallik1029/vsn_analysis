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

# Import our stock analyzer modules
from data_fetcher import get_stock_data
from scoring import calculate_score

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
    """Serve the landing page."""
    return render_template('landing.html')


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
    """Get the current authenticated user."""
    access_token = None
    
    # Try Authorization header first
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        access_token = auth_header[7:]
    
    # Fallback to session
    if not access_token:
        access_token = session.get('supabase_access_token')
    
    if not access_token:
        return jsonify({'authenticated': False}), 200
    
    user = get_user_from_token(access_token)
    if not user:
        # Token expired or invalid
        session.clear()
        return jsonify({'authenticated': False}), 200
    
    # Get username from database (this is the source of truth)
    db_username = get_username_from_db(user.get('id'))
    
    # Fallback to metadata if not in database
    if not db_username:
        meta = user.get('user_metadata') or {}
        db_username = meta.get('display_name') or meta.get('full_name')
    
    return jsonify({
        'authenticated': True,
        'user': {
            'id': user.get('id'),
            'email': user.get('email'),
            'created_at': user.get('created_at'),
            'display_name': db_username
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
    """
    Fetch basic price data for multiple stocks for the ticker tape.
    Returns a random selection from a pool of popular stocks.
    """
    import random
    
    stock_pool = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'V', 'WMT',
        'JNJ', 'PG', 'MA', 'HD', 'CVX', 'MRK', 'ABBV', 'PEP', 'KO', 'COST',
        'AVGO', 'TMO', 'MCD', 'CSCO', 'ACN', 'ABT', 'DHR', 'NEE', 'LIN', 'ADBE',
        'NKE', 'TXN', 'UNH', 'CRM', 'AMD', 'INTC', 'QCOM', 'ORCL', 'IBM', 'GE',
        'BA', 'CAT', 'GS', 'AXP', 'BKNG', 'ISRG', 'MDLZ', 'PLD', 'CB', 'SO'
    ]
    
    selected = random.sample(stock_pool, 20)
    
    try:
        import yfinance as yf
        
        tickers_str = ' '.join(selected)
        data = yf.download(tickers_str, period='1d', progress=False, group_by='ticker')
        
        results = []
        for symbol in selected:
            try:
                if len(selected) == 1:
                    ticker_data = data
                else:
                    ticker_data = data[symbol] if symbol in data.columns.get_level_values(0) else None
                
                if ticker_data is not None and not ticker_data.empty:
                    current = ticker_data['Close'].iloc[-1]
                    open_price = ticker_data['Open'].iloc[-1]
                    change_pct = ((current - open_price) / open_price) * 100 if open_price > 0 else 0
                    
                    results.append({
                        'symbol': symbol,
                        'price': round(float(current), 2),
                        'change': round(float(change_pct), 2)
                    })
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                continue
        
        return jsonify({'success': True, 'stocks': results})
    
    except Exception as e:
        print(f"Ticker tape error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


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
    print("  GET  /api/health            - Health check")
    print("\nPress Ctrl+C to stop the server.\n")
    
    app.run(debug=True, port=5000)