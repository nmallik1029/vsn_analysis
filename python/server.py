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
import re
import math
import requests
from urllib.parse import urlparse
from supabase import create_client
from PIL import Image
from io import BytesIO
import uuid
from datetime import datetime, timedelta, timezone
from typing import Set


# Import our stock analyzer modules
from data_fetcher import get_stock_data
from scoring import calculate_score

import time

TICKER_TAPE_CACHE = None
TICKER_TAPE_CACHE_TIME = 0
TICKER_TAPE_TTL = 120  # seconds
INDEX_CACHE = {}
INDEX_CACHE_TTL = 120
SEARCH_CACHE = {}
SEARCH_CACHE_TTL = 30
LOGO_CACHE = {}
LOGO_CACHE_TTL = 60 * 60 * 6
NAME_CACHE = {}
NAME_CACHE_TTL = 60 * 60 * 24 * 7
SCREENER_CACHE = {}
SCREENER_CACHE_TTL = 120
YAHOO_QUOTE_API_AVAILABLE = True
YAHOO_SESSION = requests.Session()
YAHOO_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
})
INDEX_MAP = {
    '^GSPC': 'S&P 500',
    '^NDX': 'Nasdaq 100',
    '^DJI': 'Dow 30',
    '^RUT': 'Russell 2000',
    '^IXIC': 'Nasdaq Composite'
}
WATCHLIST = {
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'GOOGL': 'Alphabet',
    'AMZN': 'Amazon',
    'TSLA': 'Tesla',
    'NVDA': 'Nvidia',
    'META': 'Meta Platforms',
    'NFLX': 'Netflix',
    'AMD': 'Advanced Micro Devices',
    'INTC': 'Intel',
    'JPM': 'JPMorgan',
    'BAC': 'Bank of America',
    'XOM': 'Exxon Mobil',
    'CVX': 'Chevron',
    'SPY': 'SPDR S&P 500 ETF',
    'QQQ': 'Invesco QQQ'
}

DEFAULT_SCREENER_SYMBOLS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO', 'AMD', 'NFLX',
    'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'AXP', 'C', 'SCHW',
    'XOM', 'CVX', 'COP', 'SLB', 'OXY', 'EOG',
    'LLY', 'UNH', 'JNJ', 'MRK', 'ABBV', 'PFE', 'TMO', 'ISRG',
    'WMT', 'COST', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT',
    'PLTR', 'CRM', 'ORCL', 'ADBE', 'NOW', 'SNOW', 'SHOP',
    'SPY', 'QQQ', 'IWM', 'DIA'
]


app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)  # Allow cross-origin requests
# Helpful for development: reload templates when files change
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

def static_version(filename: str) -> int:
    """Return a stable cache-busting version for static assets."""
    try:
        return int(os.path.getmtime(os.path.join(app.static_folder, filename)))
    except OSError:
        return 0

app.jinja_env.globals['static_version'] = static_version

@app.after_request
def cache_versioned_static_assets(response):
    if request.path.startswith('/static/') and request.args.get('v'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

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

# Cloudflare Web Analytics (RUM) — powers /api/admin/traffic.
# CLOUDFLARE_API_TOKEN: API token with Account Analytics:Read + Zone Analytics:Read.
# CLOUDFLARE_ACCOUNT_ID: account tag (32-char hex) from the dash URL.
# CLOUDFLARE_SITE_TAG: Web Analytics site tag from /web-analytics/edit/<tag>.
CLOUDFLARE_API_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN', '')
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')
CLOUDFLARE_SITE_TAG = os.environ.get('CLOUDFLARE_SITE_TAG', '')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'gemini').strip().lower()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
GEMINI_MAX_OUTPUT_TOKENS = int(os.environ.get('GEMINI_MAX_OUTPUT_TOKENS', '8192'))

DATA_DIR = os.path.dirname(__file__)
ADMIN_FILE = os.path.join(DATA_DIR, 'admin.json')
MODERATOR_FILE = os.path.join(DATA_DIR, 'moderators.json')
FOLLOWS_FILE = os.path.join(DATA_DIR, 'follows.json')
FOLLOWS_TABLE_AVAILABLE = None

MODERATOR_EMAILS = {
    e.strip().lower() for e in os.environ.get('MODERATOR_EMAILS', '').split(',') if e.strip()
}
ENV_MODERATOR_IDS = {
    e.strip() for e in os.environ.get('MODERATOR_IDS', '').split(',') if e.strip()
}


def _load_id_file(path: str, key: str) -> Set[str]:
    try:
        if not os.path.exists(path):
            return set()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return {str(x) for x in data[key]}
        if isinstance(data, list):
            return {str(x) for x in data}
    except Exception as e:
        print(f"Failed to load id file {path}: {e}")
    return set()


def _save_id_file(path: str, key: str, values: Set[str]):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({key: sorted(values)}, f, indent=2)
    except Exception as e:
        print(f"Failed to save id file {path}: {e}")


def _load_follow_rows() -> list[dict]:
    try:
        if not os.path.exists(FOLLOWS_FILE):
            return []
        with open(FOLLOWS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        rows = data.get('follows') if isinstance(data, dict) else data
        if isinstance(rows, list):
            return [row for row in rows if row.get('follower_id') and row.get('following_id')]
    except Exception as e:
        print(f"Failed to load follows file: {e}")
    return []


def _save_follow_rows(rows: list[dict]):
    try:
        with open(FOLLOWS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'follows': rows}, f, indent=2)
    except Exception as e:
        print(f"Failed to save follows file: {e}")


ADMIN_IDS = _load_id_file(ADMIN_FILE, 'admins')
MODERATOR_IDS = _load_id_file(MODERATOR_FILE, 'moderators') | ENV_MODERATOR_IDS
LOG_FILE = os.path.join(DATA_DIR, 'mod_actions.json')
BANNED_FILE = os.path.join(DATA_DIR, 'banned.json')
# Will be initialized after helper definitions
LOCAL_BANNED_IDS = set()

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
    """Look up a user's username from the usernames table."""
    if not user_id:
        return None
    
    try:
        result = supabase.table('usernames') \
            .select('username, display_name') \
            .eq('user_id', user_id) \
            .limit(1) \
            .execute()
        
        if result.data and len(result.data) > 0:
            # Return username if it exists, otherwise fall back to display_name for backwards compatibility
            return result.data[0].get('username') or result.data[0].get('display_name')
        return None
    except Exception as e:
        print(f"Error fetching username from DB: {e}")
        return None


def is_user_banned(user_id: str) -> bool:
    """Check if a user is banned (flagged in usernames table)."""
    if not user_id:
        return False
    if user_id in LOCAL_BANNED_IDS:
        return True
    try:
        res = supabase.table('usernames') \
            .select('banned') \
            .eq('user_id', user_id) \
            .single() \
            .execute()
        if res.data and res.data.get('banned'):
            return True
    except Exception as e:
        # If the column does not exist or any error occurs, treat as not banned
        try:
            # If the error object is a dict with a message, log concise info once
            if isinstance(e, dict):
                msg = e.get('message') or str(e)
            else:
                msg = str(e)
            print(f"Error checking banned status (ignoring, treating as not banned): {msg}")
        except Exception:
            pass
    return False


def get_profiles_by_ids(user_ids: list[str]) -> dict[str, dict]:
    """Fetch username/display/avatar for a set of user IDs."""
    profiles = {}
    if not user_ids:
        return profiles
    try:
        res = supabase.table('usernames') \
            .select('user_id, username, display_name, avatar_url') \
            .in_('user_id', user_ids) \
            .execute()
        for row in res.data or []:
            avatar_url = None
            if row.get('avatar_url'):
                avatar_url = supabase.storage.from_('avatars').get_public_url(row['avatar_url'])
            profiles[row['user_id']] = {
                'id': row['user_id'],
                'username': row.get('username'),
                'display_name': row.get('display_name'),
                'avatar_url': avatar_url
            }
    except Exception as e:
        print(f"Error fetching profiles by ids: {e}")
    return profiles


def _public_profile_from_row(row: dict) -> dict:
    avatar_url = None
    if row.get('avatar_url'):
        avatar_url = supabase.storage.from_('avatars').get_public_url(row['avatar_url'])
    return {
        'id': row.get('user_id'),
        'username': row.get('username') or row.get('display_name'),
        'display_name': row.get('display_name') or row.get('username'),
        'avatar_url': avatar_url,
        'created_at': row.get('created_at'),
        'is_private': bool(row.get('is_private')),
        'social_links': {
            'twitter': row.get('twitter_handle') or '',
            'reddit': row.get('reddit_handle') or '',
            'instagram': row.get('instagram_handle') or '',
            'website': row.get('website_url') or '',
            'other': row.get('other_url') or '',
        }
    }


def is_moderator(user: dict | None) -> bool:
    """Check if a user is allowed to perform moderator actions."""
    if not user:
        return False
    if is_admin(user):
        return True
    if user.get('id') in MODERATOR_IDS:
        return True
    email = (user.get('email') or '').lower()
    return email in MODERATOR_EMAILS


def is_admin(user: dict | None) -> bool:
    """Check if a user is an administrator."""
    if not user:
        return False
    return user.get('id') in ADMIN_IDS


def load_action_logs() -> list:
    try:
        if not os.path.exists(LOG_FILE):
            return []
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"Failed to load logs: {e}")
    return []


def append_action_log(entry: dict):
    logs = load_action_logs()
    logs.append(entry)
    # keep last 200 entries
    logs = logs[-200:]
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Failed to save logs: {e}")


def load_banned_ids() -> set[str]:
    try:
        if not os.path.exists(BANNED_FILE):
            return set()
        with open(BANNED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('banned'), list):
            return {str(x) for x in data['banned']}
        if isinstance(data, list):
            return {str(x) for x in data}
    except Exception as e:
        print(f"Failed to load banned ids: {e}")
    return set()


def save_banned_ids(ids: set[str]):
    try:
        with open(BANNED_FILE, 'w', encoding='utf-8') as f:
            json.dump({'banned': sorted(ids)}, f, indent=2)
    except Exception as e:
        print(f"Failed to save banned ids: {e}")


# Initialize local banned IDs after helper definitions
LOCAL_BANNED_IDS = load_banned_ids()


def soft_delete_posts_for_user(target_user_id: str, actor_id: str | None = None, actor_username: str | None = None, reason: str = "User banned") -> int:
    """
    Soft delete all posts for a user and clean up tags. Returns number of posts affected.
    """
    deleted = 0
    try:
        res = supabase.table('posts') \
            .select('id, post_tags(tags(id, name))') \
            .eq('user_id', target_user_id) \
            .is_('deleted_at', 'null') \
            .execute()
        posts = res.data or []
        for post in posts:
            post_id = post.get('id')
            if not post_id:
                continue
            supabase.table('posts').update({'deleted_at': datetime.utcnow().isoformat()}).eq('id', post_id).execute()
            cleanup_post_tags(post_id, post)
            deleted += 1
            append_action_log({
                'type': 'delete_post',
                'timestamp': datetime.utcnow().isoformat(),
                'post_id': post_id,
                'reason': reason,
                'actor_id': actor_id,
                'actor_username': actor_username,
                'target_user_id': target_user_id
            })
    except Exception as e:
        print(f"Error soft deleting posts for user {target_user_id}: {e}")
    return deleted


def cleanup_post_tags(post_id: str, post_record: dict | None = None):
    """
    Remove tag relations for a post and decrement tag post counts.
    """
    try:
        post_tags = []
        if post_record:
            post_tags = post_record.get('post_tags') or []
        if not post_tags:
            # fetch if not provided
            res = supabase.table('post_tags').select('tags(id, name)').eq('post_id', post_id).execute()
            post_tags = res.data or []

        tag_ids = [pt.get('tags', {}).get('id') for pt in post_tags if pt.get('tags')]
        supabase.table('post_tags').delete().eq('post_id', post_id).execute()
        for tag_id in tag_ids:
            if not tag_id:
                continue
            tag_row = supabase.table('tags').select('post_count').eq('id', tag_id).single().execute()
            if tag_row.data and 'post_count' in tag_row.data:
                new_count = max(0, (tag_row.data['post_count'] or 0) - 1)
                supabase.table('tags').update({'post_count': new_count}).eq('id', tag_id).execute()
    except Exception as e:
        print(f"Error cleaning up tags for post {post_id}: {e}")

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

        if is_user_banned(user.get('id')):
            session.clear()
            return jsonify({'error': 'Account banned'}), 403
        
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

        if is_user_banned(user.get('id')):
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
    if request.host.split(':', 1)[0].lower() == 'admin.vsnanalysis.com':
        if not session.get('supabase_access_token'):
            return redirect('/auth')
        user = get_user_from_token(session['supabase_access_token'])
        if not is_admin(user):
            return redirect('https://www.vsnanalysis.com/')
        request.user = user
        return render_template('admin_dashboard.html')
    return render_template('design.html')


@app.route('/design')
def design_system():
    return render_template('design.html')


@app.route('/demo')
def demo_page():
    return render_template('demo.html')


@app.route('/landing-legacy')
def landing_legacy():
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

@app.route('/markets')
@require_auth_page
def markets_page():
    return render_template('markets.html')

@app.route('/screener')
@require_auth_page
def screener_page():
    return render_template('screener.html', active_nav='screener')

@app.route('/screener/<ticker>')
@require_auth_page
def screener_detail_page(ticker):
    ticker = re.sub(r'[^A-Za-z0-9.^-]', '', ticker or '').upper()[:16]
    return render_template('screener_detail.html', active_nav='screener', ticker=ticker)

@app.route('/chart/<ticker>')
@require_auth_page
def chart_page(ticker):
    return render_template('chart.html', ticker=ticker)


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
        .select('username, display_name, avatar_url') \
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
            'username': data.get('username'),
            'display_name': data.get('display_name'),
            'avatar_url': avatar_url
        },
        'roles': {
            'admin': is_admin(user),
            'moderator': is_moderator(user)
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
# Cache for Yahoo's "most actives" screen (top tickers by volume).
# Refreshed at most once every 5 minutes. A background thread (started at
# the bottom of this module) keeps it warm so the first user click on
# "Open the markets" doesn't pay the cold-fetch tax.
_VOLUME_CACHE = {"symbols": [], "ts": 0.0}
_VOLUME_CACHE_TTL = 300  # seconds


def _fetch_most_active(limit: int = 100) -> list[str]:
    """Return ticker symbols ordered by current trading volume (highest first).

    Backed by Yahoo's `most_actives` predefined screener. Cached in-process
    to avoid hammering Yahoo when many users hit the search. The same call
    also populates NAME_CACHE so subsequent name lookups are free.
    """
    now = time.time()
    if _VOLUME_CACHE["symbols"] and now - _VOLUME_CACHE["ts"] < _VOLUME_CACHE_TTL:
        return _VOLUME_CACHE["symbols"]
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
        params = {
            "scrIds": "most_actives",
            "count": limit,
            "start": 0,
            "formatted": "false",
            "lang": "en-US",
            "region": "US",
        }
        res = requests.get(url, params=params, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code != 200:
            return _VOLUME_CACHE["symbols"]
        payload = res.json()
        quotes = payload.get("finance", {}).get("result", [{}])[0].get("quotes", []) or []
        ordered = sorted(
            (q for q in quotes if q.get("symbol")),
            key=lambda q: q.get("regularMarketVolume", 0) or 0,
            reverse=True,
        )
        symbols = []
        for q in ordered:
            sym = q["symbol"]
            symbols.append(sym)
            # Piggy-back: warm the name cache so the search response can
            # return names without a second round-trip.
            NAME_CACHE[sym] = {
                "name": q.get("shortName") or q.get("longName") or sym,
                "exchange": q.get("fullExchangeName") or q.get("exchange") or "",
                "type": q.get("quoteType") or "EQUITY",
                "ts": now,
            }
        _VOLUME_CACHE["symbols"] = symbols
        _VOLUME_CACHE["ts"] = now
        return symbols
    except Exception as e:
        print(f"fetch most_active failed: {e}")
        return _VOLUME_CACHE["symbols"]


# Cache full search results per query so pagination doesn't re-hit Yahoo.
# Keyed by uppercase query string -> {"results": [...], "ts": float}
_TYPED_SEARCH_CACHE = {}
_TYPED_SEARCH_CACHE_TTL = 60 * 5  # 5 minutes


# Quote types our chart pipeline can actually serve (yfinance / our pricing
# code only handles US equities, ETFs, and indices reliably). Mutual funds,
# futures, options, crypto, forex etc. would show in search but 404 on the
# chart page, so we filter them out.
_CHARTABLE_QUOTE_TYPES = {"EQUITY", "ETF", "INDEX"}


def _yahoo_search_full(q: str) -> list[dict]:
    """Hit Yahoo's `/v1/finance/search`, which returns rich quote data
    (symbol, name, type, exchange) WITHOUT needing auth crumbs.

    Filtered to quote types our chart endpoint can actually load.
    Cached per-query; also warms NAME_CACHE so other code paths benefit.
    """
    key = q.upper()
    now = time.time()
    cached = _TYPED_SEARCH_CACHE.get(key)
    if cached and now - cached['ts'] < _TYPED_SEARCH_CACHE_TTL:
        return cached['results']

    results = []
    try:
        payload = _fetch_yahoo_search(q, limit=50)
        for yq in payload.get('quotes', []):
            sym = yq.get('symbol')
            if not sym:
                continue
            qtype = (yq.get('quoteType') or 'EQUITY').upper()
            if qtype not in _CHARTABLE_QUOTE_TYPES:
                continue
            name = yq.get('shortname') or yq.get('longname') or sym
            results.append({"symbol": sym, "name": name})
            NAME_CACHE[sym] = {
                "name": name,
                "exchange": yq.get('exchDisp') or yq.get('exchange') or '',
                "type": qtype,
                "ts": now,
            }
    except Exception as e:
        print(f"yahoo search failed for {q!r}: {e}")

    # Supplement with local ALL_TICKERS prefix matches Yahoo didn't return
    # (these are all US equities/ETFs from tickers.json, so chartable).
    seen = {r['symbol'] for r in results}
    for t in ALL_TICKERS:
        if t.startswith(key) and t not in seen:
            cached_name = NAME_CACHE.get(t, {}).get('name')
            results.append({"symbol": t, "name": cached_name or t})

    _TYPED_SEARCH_CACHE[key] = {"results": results, "ts": now}
    return results


@app.route('/api/search-tickers')
def search_tickers():
    """Paginated ticker search.

    Query params:
      q       — prefix (uppercase). Empty returns top-by-volume.
      offset  — page start (default 0)
      limit   — page size (default 20, max 50)

    Returns `[{ "symbol": ..., "name": ... }]`.
    """
    q = request.args.get('q', '').upper().strip()
    try:
        offset = max(0, int(request.args.get('offset', 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = max(1, min(50, int(request.args.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20

    if not q:
        # Empty query -> top by volume (cached, warmed at boot)
        by_volume = _fetch_most_active(limit=200)
        page = by_volume[offset:offset + limit]
        info = _enrich_with_names(page) if page else {}
        return jsonify([
            {"symbol": s, "name": (info.get(s) or {}).get("name", s)}
            for s in page
        ])

    # Non-empty query -> Yahoo search, which returns names alongside symbols
    # and covers stocks/funds/futures/indices like TradingView does.
    full = _yahoo_search_full(q)
    return jsonify(full[offset:offset + limit])


def _enrich_with_names(symbols: list[str]) -> dict:
    """Look up name + exchange for a batch of tickers, with long-lived cache."""
    global YAHOO_QUOTE_API_AVAILABLE
    now = time.time()
    info_by_symbol = {}
    to_fetch = []
    for s in symbols:
        cached = NAME_CACHE.get(s)
        if cached and now - cached['ts'] < NAME_CACHE_TTL:
            info_by_symbol[s] = cached
        else:
            to_fetch.append(s)

    if to_fetch and YAHOO_QUOTE_API_AVAILABLE:
        try:
            url = 'https://query2.finance.yahoo.com/v7/finance/quote'
            resp = YAHOO_SESSION.get(url, params={'symbols': ','.join(to_fetch)}, timeout=5)
            if resp.status_code in {401, 403}:
                YAHOO_QUOTE_API_AVAILABLE = False
                return info_by_symbol
            resp.raise_for_status()
            quotes = resp.json().get('quoteResponse', {}).get('result', []) or []
            for q in quotes:
                sym = q.get('symbol')
                if not sym:
                    continue
                info = {
                    'name': q.get('shortName') or q.get('longName') or sym,
                    'exchange': q.get('fullExchangeName') or q.get('exchange') or '',
                    'type': q.get('quoteType') or 'EQUITY',
                    'ts': now,
                }
                NAME_CACHE[sym] = info
                info_by_symbol[sym] = info
        except Exception as e:
            print(f"Name enrichment failed: {e}")

    return info_by_symbol


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _conviction_from_raw(raw: float) -> float:
    """Convert a weighted component score into a wider, stable conviction score."""
    return _clamp(100 / (1 + math.exp(-((raw - 50) / 11))))


def _percentile_map(rows: list[dict], key: str, higher_is_better: bool = True) -> dict:
    values = []
    for row in rows:
        value = _safe_float(row.get(key))
        if value is not None:
            values.append((row['symbol'], value))

    if not values:
        return {row['symbol']: 50.0 for row in rows}
    if len(values) == 1:
        return {row['symbol']: 50.0 for row in rows}
    if min(v for _, v in values) == max(v for _, v in values):
        return {row['symbol']: 50.0 for row in rows}

    values.sort(key=lambda item: item[1], reverse=not higher_is_better)
    scores = {}
    last_value = None
    last_score = 50.0
    total = len(values) - 1
    for idx, (symbol, value) in enumerate(values):
        if last_value is not None and value == last_value:
            score = last_score
        else:
            score = (idx / total) * 100
            last_value = value
            last_score = score
        scores[symbol] = score

    for row in rows:
        scores.setdefault(row['symbol'], 50.0)
    return scores


def _fetch_quote_batch(symbols: list[str]) -> list[dict]:
    global YAHOO_QUOTE_API_AVAILABLE
    symbols = [s.upper().strip() for s in symbols if s and re.match(r'^[A-Z0-9.^-]{1,16}$', s.upper().strip())]
    if not symbols:
        return []

    quotes = []
    if YAHOO_QUOTE_API_AVAILABLE:
        for i in range(0, len(symbols), 60):
            chunk = symbols[i:i + 60]
            try:
                resp = YAHOO_SESSION.get(
                    'https://query2.finance.yahoo.com/v7/finance/quote',
                    params={'symbols': ','.join(chunk)},
                    timeout=8
                )
                if resp.status_code in {401, 403}:
                    YAHOO_QUOTE_API_AVAILABLE = False
                    break
                resp.raise_for_status()
                quotes.extend(resp.json().get('quoteResponse', {}).get('result', []) or [])
            except Exception as e:
                print(f"Screener quote batch failed: {e}")
    if quotes:
        return quotes

    requested = set(symbols)
    predefined = _fetch_predefined_screener_quotes('most_actives', limit=max(100, len(symbols)))
    quote_by_symbol = {q.get('symbol', '').upper(): q for q in predefined if q.get('symbol')}
    quotes = [quote_by_symbol[s] for s in symbols if s in quote_by_symbol]
    missing = [s for s in symbols if s not in quote_by_symbol]
    if missing:
        quotes.extend(_fetch_yfinance_quote_batch(missing))
    return quotes


def _fetch_predefined_screener_quotes(scr_id: str, limit: int = 100) -> list[dict]:
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
        params = {
            "scrIds": scr_id,
            "count": limit,
            "start": 0,
            "formatted": "false",
            "lang": "en-US",
            "region": "US",
        }
        res = requests.get(url, params=params, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code != 200:
            return []
        quotes = res.json().get("finance", {}).get("result", [{}])[0].get("quotes", []) or []
        now = time.time()
        for q in quotes:
            sym = q.get('symbol')
            if sym:
                NAME_CACHE[sym] = {
                    "name": q.get("shortName") or q.get("longName") or sym,
                    "exchange": q.get("fullExchangeName") or q.get("exchange") or "",
                    "type": q.get("quoteType") or "EQUITY",
                    "ts": now,
                }
        return quotes
    except Exception as e:
        print(f"Predefined screener quote fetch failed: {e}")
        return []


def _fetch_yfinance_quote_batch(symbols: list[str]) -> list[dict]:
    try:
        import yfinance as yf
        data = yf.download(
            tickers=symbols,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        quotes = []
        info = _enrich_with_names(symbols)
        for sym in symbols:
            try:
                frame = data[sym] if len(symbols) > 1 else data
                if frame is None or frame.empty:
                    continue
                close = frame['Close'].dropna()
                volume = frame['Volume'].dropna()
                if close.empty:
                    continue
                last = float(close.iloc[-1])
                prev = float(close.iloc[-2]) if len(close) > 1 else last
                low = float(close.min())
                high = float(close.max())
                avg_volume = float(volume.tail(60).mean()) if not volume.empty else None
                last_volume = float(volume.iloc[-1]) if not volume.empty else None
                meta = info.get(sym, {})
                quotes.append({
                    'symbol': sym,
                    'quoteType': meta.get('type') or 'EQUITY',
                    'shortName': meta.get('name') or sym,
                    'fullExchangeName': meta.get('exchange') or '',
                    'regularMarketPrice': last,
                    'regularMarketChange': last - prev,
                    'regularMarketChangePercent': ((last - prev) / prev * 100) if prev else 0,
                    'regularMarketVolume': last_volume,
                    'averageDailyVolume3Month': avg_volume,
                    'fiftyTwoWeekLow': low,
                    'fiftyTwoWeekHigh': high,
                })
            except Exception as e:
                print(f"yfinance quote fallback failed for {sym}: {e}")
        return quotes
    except Exception as e:
        print(f"yfinance quote fallback failed: {e}")
        return []


def _volume_ratio(q: dict) -> float | None:
    volume = _safe_float(q.get('regularMarketVolume'))
    avg_volume = _safe_float(q.get('averageDailyVolume3Month')) or _safe_float(q.get('averageDailyVolume10Day'))
    if volume is None or not avg_volume:
        return None
    return volume / avg_volume


def _range_position(q: dict) -> float | None:
    price = _safe_float(q.get('regularMarketPrice'))
    low = _safe_float(q.get('fiftyTwoWeekLow'))
    high = _safe_float(q.get('fiftyTwoWeekHigh'))
    if price is None or low is None or high is None or high <= low:
        return None
    return _clamp(((price - low) / (high - low)) * 100)


def _eps_growth_proxy(q: dict) -> float | None:
    trailing = _safe_float(q.get('epsTrailingTwelveMonths'))
    forward = _safe_float(q.get('epsForward'))
    if trailing is None or forward is None or trailing <= 0:
        return None
    return ((forward - trailing) / trailing) * 100


def _inverse_positive(q: dict, *keys: str) -> float | None:
    vals = []
    for key in keys:
        value = _safe_float(q.get(key))
        if value is not None and value > 0:
            vals.append(1 / value)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _build_screener_rows(symbols: list[str], limit: int = 50) -> list[dict]:
    quotes = _fetch_quote_batch(symbols[:160])
    rows = []
    seen = set()
    for q in quotes:
        symbol = (q.get('symbol') or '').upper()
        quote_type = (q.get('quoteType') or '').upper()
        if not symbol or symbol in seen or quote_type not in {'EQUITY', 'ETF'}:
            continue
        price = _safe_float(q.get('regularMarketPrice'))
        if price is None:
            continue
        seen.add(symbol)
        row = {
            'symbol': symbol,
            'name': q.get('shortName') or q.get('longName') or NAME_CACHE.get(symbol, {}).get('name') or symbol,
            'exchange': q.get('fullExchangeName') or q.get('exchange') or '',
            'price': round(price, 2),
            'change_pct': round(_safe_float(q.get('regularMarketChangePercent'), 0.0), 2),
            'market_cap': _safe_int(q.get('marketCap')),
            'volume': _safe_int(q.get('regularMarketVolume')),
            'avg_volume': _safe_int(q.get('averageDailyVolume3Month')),
            'volume_ratio': _volume_ratio(q),
            'pe': _safe_float(q.get('trailingPE')),
            'forward_pe': _safe_float(q.get('forwardPE')),
            'price_to_book': _safe_float(q.get('priceToBook')),
            'beta': _safe_float(q.get('beta')),
            'range_position': _range_position(q),
            'eps_growth': _eps_growth_proxy(q),
            '_value_raw': _inverse_positive(q, 'trailingPE', 'forwardPE', 'priceToBook'),
            '_momentum_raw': None,
            '_growth_raw': _eps_growth_proxy(q),
            '_quality_raw': None,
            '_risk_raw': None,
        }
        volume_ratio = row['volume_ratio']
        range_pos = row['range_position']
        row['_momentum_raw'] = (
            (row['change_pct'] * 0.45) +
            ((range_pos or 50) * 0.35) +
            ((min(volume_ratio or 1, 4) / 4) * 100 * 0.20)
        )
        row['_quality_raw'] = (
            (math.log10(row['market_cap']) if row['market_cap'] > 0 else None),
            (math.log10(row['avg_volume']) if row['avg_volume'] > 0 else None),
        )
        quality_parts = [v for v in row['_quality_raw'] if v is not None]
        row['_quality_raw'] = sum(quality_parts) / len(quality_parts) if quality_parts else None
        beta = row['beta']
        row['_risk_raw'] = 100 - (abs((beta if beta is not None else 1.2) - 1) * 55)
        rows.append(row)

    if not rows:
        return []

    value_scores = _percentile_map(rows, '_value_raw', higher_is_better=True)
    momentum_scores = _percentile_map(rows, '_momentum_raw', higher_is_better=True)
    growth_scores = _percentile_map(rows, '_growth_raw', higher_is_better=True)
    quality_scores = _percentile_map(rows, '_quality_raw', higher_is_better=True)
    risk_scores = _percentile_map(rows, '_risk_raw', higher_is_better=True)

    raw_rows = []
    for row in rows:
        coverage_keys = ['pe', 'forward_pe', 'price_to_book', 'beta', 'range_position', 'eps_growth', 'volume_ratio', 'market_cap']
        coverage = sum(1 for key in coverage_keys if row.get(key) is not None and row.get(key) != 0) / len(coverage_keys)
        components = {
            'value': round(value_scores[row['symbol']], 1),
            'momentum': round(momentum_scores[row['symbol']], 1),
            'growth': round(growth_scores[row['symbol']], 1),
            'quality': round(quality_scores[row['symbol']], 1),
            'risk': round(risk_scores[row['symbol']], 1),
        }
        raw = (
            components['value'] * 0.27 +
            components['momentum'] * 0.25 +
            components['growth'] * 0.18 +
            components['quality'] * 0.18 +
            components['risk'] * 0.12
        )
        row['components'] = components
        row['_raw_score'] = raw
        row['confidence'] = round(_clamp(coverage * 100), 0)
        raw_rows.append(row)

    rank_scores = _percentile_map(raw_rows, '_raw_score', higher_is_better=True)
    for row in raw_rows:
        score = round(_conviction_from_raw(row['_raw_score']), 0)
        row['score'] = score
        row['rank_percentile'] = round(rank_scores[row['symbol']], 0)
        if score >= 85:
            row['verdict'] = 'High conviction'
        elif score >= 65:
            row['verdict'] = 'Constructive'
        elif score >= 45:
            row['verdict'] = 'Mixed'
        elif score >= 25:
            row['verdict'] = 'Weak setup'
        else:
            row['verdict'] = 'Avoid for now'
        row['reasons'] = _screener_reasons(row)
        for private_key in list(row.keys()):
            if private_key.startswith('_'):
                row.pop(private_key, None)

    return sorted(raw_rows, key=lambda r: (r['score'], r['confidence']), reverse=True)[:limit]


def _screener_row_for_ticker(ticker: str) -> dict | None:
    ticker = ticker.upper().strip()
    universe = list(dict.fromkeys(DEFAULT_SCREENER_SYMBOLS + _fetch_most_active(limit=120) + [ticker]))
    rows = _build_screener_rows(universe, limit=len(universe))
    for row in rows:
        if row.get('symbol') == ticker:
            return row
    single = _build_screener_rows([ticker], limit=1)
    return single[0] if single else None


def _stock_history_summary(ticker: str) -> dict:
    cache_key = f"history-summary:{ticker}"
    now = time.time()
    cached = SCREENER_CACHE.get(cache_key)
    if cached and now - cached['ts'] < 60 * 30:
        return cached['data']
    summary = {'returns': {}, 'sparkline': [], 'technical': {}, 'seasonality': []}
    try:
        import yfinance as yf
        hist = yf.download(ticker, period="10y", interval="1d", progress=False, auto_adjust=False)
        if hist is None or hist.empty:
            return summary
        close = hist['Close']
        if hasattr(close, 'columns'):
            close = close.iloc[:, 0]
        close = close.dropna()
        volume = hist['Volume'] if 'Volume' in hist else None
        if volume is not None and hasattr(volume, 'columns'):
            volume = volume.iloc[:, 0]
        volume = volume.dropna() if volume is not None else None
        if close.empty:
            return summary
        last = float(close.iloc[-1])
        windows = {
            '5D': 5,
            '1M': 21,
            '6M': 126,
            'YTD': None,
            '1Y': 252,
            '5Y': 1260,
            '10Y': 2520,
        }
        returns = {}
        for label, days in windows.items():
            try:
                if label == 'YTD':
                    year = close[close.index.year == close.index[-1].year]
                    start = float(year.iloc[0]) if not year.empty else None
                elif len(close) > days:
                    start = float(close.iloc[-days - 1])
                elif label in {'5Y', '10Y'} and len(close) > 200:
                    start = float(close.iloc[0])
                else:
                    start = None
                returns[label] = round(((last - start) / start) * 100, 2) if start else None
            except Exception:
                returns[label] = None
        all_start = float(close.iloc[0]) if len(close) else None
        returns['All'] = round(((last - all_start) / all_start) * 100, 2) if all_start else None

        ma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
        ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
        high_52 = float(close.tail(252).max()) if len(close) >= 60 else float(close.max())
        low_52 = float(close.tail(252).min()) if len(close) >= 60 else float(close.min())
        range_pos = ((last - low_52) / (high_52 - low_52) * 100) if high_52 > low_52 else None
        three_month = returns.get('6M')
        trend_score = 0
        trend_score += 1 if ma50 and last > ma50 else -1
        trend_score += 1 if ma200 and last > ma200 else -1
        trend_score += 1 if range_pos and range_pos > 60 else -1 if range_pos and range_pos < 35 else 0
        technical = {
            'price_vs_50d': round(((last - ma50) / ma50) * 100, 2) if ma50 else None,
            'price_vs_200d': round(((last - ma200) / ma200) * 100, 2) if ma200 else None,
            'range_position': round(range_pos, 1) if range_pos is not None else None,
            'volume_vs_60d': round((float(volume.iloc[-1]) / float(volume.tail(60).mean())) * 100, 1) if volume is not None and not volume.empty and float(volume.tail(60).mean()) else None,
            'summary': 'Constructive' if trend_score >= 2 else 'Weak' if trend_score <= -2 else 'Mixed',
            'momentum_6m': three_month,
        }
        month_returns = []
        monthly = close.resample('ME').last().pct_change().dropna() * 100
        if not monthly.empty:
            grouped = monthly.groupby(monthly.index.month).mean()
            labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            month_returns = [
                {'month': labels[i - 1], 'avg_return': round(float(grouped.get(i, 0)), 2)}
                for i in range(1, 13)
            ]
        tail = close.tail(160)
        summary = {
            'returns': returns,
            'sparkline': [round(float(x), 2) for x in tail.values],
            'chart': [
                {'time': idx.strftime('%Y-%m-%d'), 'value': round(float(value), 2)}
                for idx, value in tail.items()
            ],
            'technical': technical,
            'seasonality': month_returns,
        }
        SCREENER_CACHE[cache_key] = {'ts': now, 'data': summary}
        return summary
    except Exception as e:
        print(f"history summary failed for {ticker}: {e}")
        return summary


def _related_stock_cards(ticker: str, metrics: dict | None) -> list[dict]:
    candidates = [s for s in DEFAULT_SCREENER_SYMBOLS if s != ticker][:80]
    sector = (metrics or {}).get('sector') or ''
    industry = (metrics or {}).get('industry') or ''
    preferred = []
    if 'Motor' in industry or ticker in {'F', 'GM', 'TSLA', 'RIVN', 'NIO'}:
        preferred = ['GM', 'TSLA', 'RIVN', 'NIO', 'STLA', 'TM']
    elif 'Technology' in sector or ticker in {'AAPL', 'MSFT', 'NVDA', 'AMD'}:
        preferred = ['MSFT', 'AAPL', 'NVDA', 'AMD', 'AVGO', 'ORCL']
    elif 'Financial' in sector or ticker in {'JPM', 'BAC', 'WFC'}:
        preferred = ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C']
    symbols = list(dict.fromkeys([s for s in preferred if s != ticker] + candidates))[:12]
    cards = []
    for row in _build_screener_rows(symbols, limit=6):
        cards.append({
            'symbol': row.get('symbol'),
            'name': row.get('name'),
            'price': row.get('price'),
            'change_pct': row.get('change_pct'),
            'score': row.get('score'),
        })
    return cards


def _screener_reasons(row: dict) -> dict:
    components = row.get('components') or {}
    ranked = sorted(components.items(), key=lambda item: item[1], reverse=True)
    positives = []
    cautions = []
    for name, score in ranked[:2]:
        if score >= 65:
            positives.append(f"{name.title()} ranks well versus the current screen.")
    for name, score in sorted(components.items(), key=lambda item: item[1])[:2]:
        if score <= 40:
            cautions.append(f"{name.title()} is a relative drag in this universe.")
    if row.get('range_position') is not None:
        positives.append(f"Price sits around the {round(row['range_position'])}th percentile of its 52-week range.")
    if row.get('volume_ratio') is not None and row['volume_ratio'] >= 1.5:
        positives.append("Volume is running meaningfully above its recent average.")
    if row.get('confidence', 0) < 70:
        cautions.append("Several inputs are missing, so confidence is lower.")
    return {
        'positive': positives[:3] or ['No single factor dominates; this is a balanced relative ranking.'],
        'caution': cautions[:3] or ['No major relative weakness stood out in the available data.']
    }


def _screener_universe_symbols(universe: str, query: str, limit: int) -> list[str]:
    if query:
        return [r['symbol'] for r in _yahoo_search_full(query)[:max(limit, 30)]]
    if universe == 'watchlist':
        return list(WATCHLIST.keys())
    if universe == 'default':
        return DEFAULT_SCREENER_SYMBOLS
    active = _fetch_most_active(limit=max(120, limit * 3))
    return active or DEFAULT_SCREENER_SYMBOLS


def _fallback_screener_analysis(row: dict) -> dict:
    components = row.get('components') or {}
    best = max(components, key=components.get) if components else 'setup'
    worst = min(components, key=components.get) if components else 'data quality'
    return {
        'source': 'deterministic fallback',
        'verdict': row.get('verdict', 'Mixed'),
        'summary': f"{row.get('symbol')} screens as {row.get('verdict', 'mixed').lower()} with a conviction score of {row.get('score')}.",
        'thesis': (
            f"The strongest part of the setup is {best}, while {worst} is the area that needs the most confirmation. "
            "The score should be read as a structured screen, not a buy or sell instruction."
        ),
        'setup_quality': (
            "The current setup is based on relative factor strength inside the selected universe. "
            "A stronger read would combine a high conviction score, above-average momentum, solid quality, and no obvious valuation penalty."
        ),
        'supporting_points': (row.get('reasons') or {}).get('positive', [])[:3],
        'risks': (row.get('reasons') or {}).get('caution', [])[:3],
        'scenario_analysis': [
            'Bull case: the strongest factor continues to lead and the weaker factor stops deteriorating.',
            'Base case: the stock remains a watchlist candidate until more factors line up.',
            'Bear case: the weakest factor continues to pressure the setup and the screen score fades.'
        ],
        'what_to_watch': [
            'Whether volume confirms the current move.',
            'Whether valuation stays reasonable versus peers.',
            f"Whether the weak point, {worst}, improves on the next screen."
        ],
        'confidence': 'medium' if row.get('confidence', 0) >= 70 else 'low'
    }


def _screener_analysis_prompt(row: dict) -> dict:
    return {
        'symbol': row.get('symbol'),
        'company': row.get('name'),
        'score': row.get('score'),
        'verdict': row.get('verdict'),
        'confidence': row.get('confidence'),
        'components': row.get('components'),
        'metrics': {
            'price': row.get('price'),
            'change_pct': row.get('change_pct'),
            'market_cap': row.get('market_cap'),
            'volume': row.get('volume'),
            'volume_ratio': row.get('volume_ratio'),
            'pe': row.get('pe'),
            'forward_pe': row.get('forward_pe'),
            'price_to_book': row.get('price_to_book'),
            'beta': row.get('beta'),
            'range_position': row.get('range_position'),
            'eps_growth': row.get('eps_growth'),
            **(row.get('metrics') or {}),
        },
        'news': row.get('news') or [],
        'analyst_context': row.get('analyst_context') or {},
        'model_rules': [
            'Use only the supplied data.',
            'Do not claim this is financial advice.',
            'Be direct and explain why the score is strong, weak, or mixed.',
            'Return one complete valid JSON object that satisfies the schema. Do not truncate the final field.'
        ]
    }


def _screener_analysis_schema(include_openai_strict: bool = False) -> dict:
    schema = {
        'type': 'object',
        'required': ['source', 'verdict', 'summary', 'thesis', 'setup_quality', 'supporting_points', 'risks', 'scenario_analysis', 'what_to_watch', 'confidence'],
        'properties': {
            'source': {'type': 'string'},
            'verdict': {'type': 'string'},
            'summary': {'type': 'string'},
            'thesis': {'type': 'string'},
            'setup_quality': {'type': 'string'},
            'supporting_points': {'type': 'array', 'items': {'type': 'string'}},
            'risks': {'type': 'array', 'items': {'type': 'string'}},
            'scenario_analysis': {'type': 'array', 'items': {'type': 'string'}},
            'what_to_watch': {'type': 'array', 'items': {'type': 'string'}},
            'confidence': {'type': 'string', 'enum': ['low', 'medium', 'high']}
        }
    }
    if include_openai_strict:
        schema['additionalProperties'] = False
    return schema


def _llm_system_prompt() -> str:
    return (
        'You are an equity screener analyst for VSN Analysis. Write a useful mini analyst note, '
        'not a one-sentence blurb. Reason from provided metrics only. Be specific about what the '
        'screen likes, what it dislikes, and what would change the conclusion. Do not present the '
        'output as financial advice.'
    )


def _parse_llm_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for idx, char in enumerate(cleaned):
            if char not in '[{':
                continue
            try:
                obj, _ = decoder.raw_decode(cleaned[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _llm_configured() -> bool:
    if LLM_PROVIDER == 'gemini':
        return bool(GEMINI_API_KEY)
    if LLM_PROVIDER == 'openai':
        return bool(OPENAI_API_KEY)
    return bool(GEMINI_API_KEY or OPENAI_API_KEY)


def _active_llm_model() -> str | None:
    if LLM_PROVIDER == 'gemini' and GEMINI_API_KEY:
        return GEMINI_MODEL
    if LLM_PROVIDER == 'openai' and OPENAI_API_KEY:
        return OPENAI_MODEL
    if GEMINI_API_KEY:
        return GEMINI_MODEL
    if OPENAI_API_KEY:
        return OPENAI_MODEL
    return None


def _gemini_screener_analysis(row: dict) -> dict:
    if not GEMINI_API_KEY:
        return _fallback_screener_analysis(row)

    prompt = _screener_analysis_prompt(row)
    try:
        resp = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent',
            headers={
                'x-goog-api-key': GEMINI_API_KEY,
                'Content-Type': 'application/json',
            },
            json={
                'contents': [{
                    'role': 'user',
                    'parts': [{
                        'text': f"{_llm_system_prompt()}\n\nAnalyze this screener row:\n{json.dumps(prompt)}"
                    }]
                }],
                'generationConfig': {
                    'responseMimeType': 'application/json',
                    'responseJsonSchema': _screener_analysis_schema(),
                    'maxOutputTokens': GEMINI_MAX_OUTPUT_TOKENS,
                    'temperature': 0.35,
                }
            },
            timeout=20
        )
        resp.raise_for_status()
        payload = resp.json()
        finish_reason = payload.get('candidates', [{}])[0].get('finishReason')
        parts = payload.get('candidates', [{}])[0].get('content', {}).get('parts', []) or []
        text = ''.join(part.get('text', '') for part in parts)
        parsed = _parse_llm_json(text)
        if parsed:
            parsed['source'] = 'Gemini'
            return parsed
        print(f"Gemini screener analysis returned malformed JSON (finish={finish_reason}, chars={len(text)}): {text[:500]!r}")
        fallback = _fallback_screener_analysis(row)
        fallback['source'] = 'Gemini failed - backup shown'
        fallback['summary'] = 'Gemini returned an incomplete response, so VSN is showing the deterministic backup note.'
        return fallback
    except Exception as e:
        print(f"Gemini screener analysis failed: {e}")
        return _fallback_screener_analysis(row)


def _openai_screener_analysis(row: dict) -> dict:
    if not OPENAI_API_KEY:
        return _fallback_screener_analysis(row)

    prompt = _screener_analysis_prompt(row)
    schema = _screener_analysis_schema(include_openai_strict=True)

    try:
        resp = requests.post(
            'https://api.openai.com/v1/responses',
            headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': OPENAI_MODEL,
                'input': [
                    {
                        'role': 'system',
                        'content': _llm_system_prompt()
                    },
                    {
                        'role': 'user',
                        'content': json.dumps(prompt)
                    }
                ],
                'text': {
                    'format': {
                        'type': 'json_schema',
                        'name': 'stock_screener_reasoning',
                        'strict': True,
                        'schema': schema
                    }
                },
                'max_output_tokens': 2600,
            },
            timeout=20
        )
        resp.raise_for_status()
        payload = resp.json()
        text = payload.get('output_text')
        if not text:
            parts = []
            for item in payload.get('output', []) or []:
                for content in item.get('content', []) or []:
                    if content.get('type') in {'output_text', 'text'} and content.get('text'):
                        parts.append(content['text'])
            text = ''.join(parts)
        parsed = _parse_llm_json(text)
        if parsed:
            parsed['source'] = 'OpenAI'
            return parsed
        fallback = _fallback_screener_analysis(row)
        fallback['source'] = 'OpenAI failed - backup shown'
        return fallback
    except Exception as e:
        print(f"OpenAI screener analysis failed: {e}")
        return _fallback_screener_analysis(row)


def _screener_llm_analysis(row: dict) -> dict:
    if LLM_PROVIDER == 'openai':
        return _openai_screener_analysis(row)
    if LLM_PROVIDER == 'gemini':
        return _gemini_screener_analysis(row)
    if GEMINI_API_KEY:
        return _gemini_screener_analysis(row)
    if OPENAI_API_KEY:
        return _openai_screener_analysis(row)
    return _fallback_screener_analysis(row)


def _fetch_yahoo_search(query: str, limit: int = 12) -> dict:
    url = 'https://query2.finance.yahoo.com/v1/finance/search'
    params = {
        'q': query,
        'quotesCount': limit,
        'newsCount': 0,
        'enableFuzzyQuery': 'false'
    }
    resp = YAHOO_SESSION.get(url, params=params, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _fetch_yahoo_trending(region: str = 'US') -> list[dict]:
    url = f'https://query2.finance.yahoo.com/v1/finance/trending/{region}'
    resp = YAHOO_SESSION.get(url, timeout=5)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get('finance', {}).get('result', [])
    if not results:
        return []
    return results[0].get('quotes', [])


def _score_quote(symbol: str, name: str, query: str) -> int:
    if not query:
        return 50
    q = query.upper()
    s = (symbol or '').upper()
    n = (name or '').upper()
    if s == q:
        return 100
    if s.startswith(q):
        # shorter completions rank higher (AA before AAPL when query is 'A')
        return 90 - min(len(s) - len(q), 20)
    # Word-boundary match in company name
    for word in n.split():
        if word.startswith(q):
            return 50
    if q in s:
        return 40
    if q in n:
        return 25
    return 0


def _filter_quotes(quotes: list[dict], mode: str, query: str = '', yahoo_known: set = None) -> list[dict]:
    yahoo_known = yahoo_known or set()
    scored = []
    for quote in quotes:
        quote_type = quote.get('quoteType', '')
        if mode == 'indices':
            if quote_type != 'INDEX':
                continue
        else:
            if quote_type not in ('EQUITY', 'ETF'):
                continue
        symbol = quote.get('symbol') or ''
        name = quote.get('shortname') or quote.get('longname') or symbol
        exchange = quote.get('exchDisp') or quote.get('exchange') or ''

        relevance = _score_quote(symbol, name, query)
        # Below this threshold the match is too tenuous to show
        if query and relevance < 25:
            continue
        # Bonus for tickers Yahoo also surfaced (popularity signal)
        if symbol in yahoo_known:
            relevance += 15
        # Bonus for tickers we already know have a logo
        cached = LOGO_CACHE.get(symbol.upper())
        if cached and cached.get('url'):
            relevance += 10

        scored.append((relevance, {
            'symbol': symbol,
            'name': name,
            'exchange': exchange,
            'type': quote_type
        }))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [r for _, r in scored[:10]]


LOGO_SOURCES = (
    lambda s: f'https://financialmodelingprep.com/image-stock/{s}.png',
    lambda s: f'https://assets.parqet.com/logos/symbol/{s}',
)


@app.route('/api/logo/<symbol>')
def get_logo(symbol):
    symbol = (symbol or '').upper().strip()
    if not symbol:
        return jsonify({'success': False})

    now = time.time()
    cached = LOGO_CACHE.get(symbol)
    if cached and now - cached['ts'] < LOGO_CACHE_TTL:
        if cached['url']:
            return jsonify({'success': True, 'logo_url': cached['url']})
        return jsonify({'success': False})

    for build_url in LOGO_SOURCES:
        url = build_url(symbol)
        try:
            r = requests.head(url, timeout=3, allow_redirects=True)
            if r.status_code == 200 and r.headers.get('Content-Type', '').startswith('image'):
                LOGO_CACHE[symbol] = {'ts': now, 'url': url}
                return jsonify({'success': True, 'logo_url': url})
        except Exception:
            continue

    LOGO_CACHE[symbol] = {'ts': now, 'url': None}
    return jsonify({'success': False})


@app.route('/api/search')
def search_symbols():
    query = request.args.get('q', '').strip()
    mode = request.args.get('type', 'symbols').strip().lower()
    if mode not in ('symbols', 'indices'):
        mode = 'symbols'

    cache_key = (query.upper(), mode)
    now = time.time()
    cached = SEARCH_CACHE.get(cache_key)
    if cached and now - cached['ts'] < SEARCH_CACHE_TTL:
        return jsonify({'success': True, 'results': cached['data']})

    try:
        quotes = []
        yahoo_known = set()  # symbols Yahoo returned for this query — popularity signal
        if query and mode == 'symbols':
            # Hit Yahoo first to learn which tickers it considers relevant
            try:
                payload = _fetch_yahoo_search(query)
                for yq in payload.get('quotes', []):
                    sym = yq.get('symbol')
                    if sym:
                        yahoo_known.add(sym)
                        quotes.append(yq)
            except Exception:
                pass

            # Prefix-match locally against the full ticker universe — surfaces
            # obvious results (AAPL, AMD, AMZN for 'A') that Yahoo misses on
            # short queries. Enrich with names from Yahoo's batch quote endpoint.
            q_upper = query.upper()
            local_matches = [t for t in ALL_TICKERS if t.startswith(q_upper)][:15]
            seen = {q.get('symbol') for q in quotes}
            new_matches = [s for s in local_matches if s not in seen]
            if new_matches:
                info_by_symbol = _enrich_with_names(new_matches)
                for sym in new_matches:
                    info = info_by_symbol.get(sym, {})
                    quotes.append({
                        'symbol': sym,
                        'shortname': info.get('name', sym),
                        'exchDisp': info.get('exchange', ''),
                        'quoteType': info.get('type', 'EQUITY'),
                    })
        elif query:
            payload = _fetch_yahoo_search(query)
            quotes = payload.get('quotes', [])
        else:
            if mode == 'indices':
                payload = _fetch_yahoo_search('index')
                quotes = payload.get('quotes', [])
            else:
                quotes = _fetch_yahoo_trending('US')

        results = _filter_quotes(quotes, mode, query, yahoo_known)
        SEARCH_CACHE[cache_key] = {'ts': now, 'data': results}
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        print(f"Search API error: {e}")
        return jsonify({'success': False, 'results': []})

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


@app.route('/api/screener')
def screener_api():
    """Return a relative, data-backed screener universe."""
    universe = request.args.get('universe', 'active').strip().lower()
    if universe not in {'active', 'watchlist', 'default'}:
        universe = 'active'
    query = request.args.get('q', '').upper().strip()
    query = re.sub(r'[^A-Z0-9.^-]', '', query)[:16]
    try:
        limit = max(5, min(100, int(request.args.get('limit', 50))))
    except (TypeError, ValueError):
        limit = 50

    cache_key = f"{universe}:{query}:{limit}"
    now = time.time()
    cached = SCREENER_CACHE.get(cache_key)
    if cached and now - cached['ts'] < SCREENER_CACHE_TTL:
        return jsonify(cached['data'])

    symbols = _screener_universe_symbols(universe, query, limit)
    rows = _build_screener_rows(symbols, limit=limit)
    payload = {
        'success': True,
        'universe': universe,
        'query': query,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'llm_enabled': _llm_configured(),
        'llm_provider': LLM_PROVIDER,
        'rows': rows,
        'method': {
            'summary': 'Relative multi-factor screen with percentile scoring across the selected universe.',
            'weights': {
                'value': 27,
                'momentum': 25,
                'growth': 18,
                'quality': 18,
                'risk': 12
            }
        }
    }
    SCREENER_CACHE[cache_key] = {'ts': now, 'data': payload}
    return jsonify(payload)


@app.route('/api/screener/reason', methods=['POST'])
def screener_reason_api():
    data = request.get_json(silent=True) or {}
    row = data.get('row') or {}
    if not isinstance(row, dict) or not row.get('symbol'):
        return jsonify({'success': False, 'error': 'Missing screener row'}), 400
    analysis = _screener_llm_analysis(row)
    return jsonify({
        'success': True,
        'llm_enabled': _llm_configured(),
        'provider': LLM_PROVIDER if _llm_configured() else None,
        'model': _active_llm_model(),
        'analysis': analysis
    })


@app.route('/api/screener/<ticker>')
def screener_detail_api(ticker):
    ticker = re.sub(r'[^A-Za-z0-9.^-]', '', ticker or '').upper()[:16]
    if not ticker:
        return jsonify({'success': False, 'error': 'Invalid ticker'}), 400

    row = _screener_row_for_ticker(ticker)
    metrics = get_stock_data(ticker)
    if row is None and metrics:
        row = {
            'symbol': ticker,
            'name': metrics.get('name') or ticker,
            'score': 50,
            'rank_percentile': 50,
            'verdict': 'Mixed',
            'confidence': 50,
            'components': {'value': 50, 'momentum': 50, 'growth': 50, 'quality': 50, 'risk': 50},
            'reasons': {'positive': ['Detailed metrics are available.'], 'caution': ['Relative screener data was limited.']},
            'price': metrics.get('current_price'),
            'change_pct': metrics.get('day_change_percent'),
            'market_cap': metrics.get('market_cap'),
            'pe': metrics.get('pe_ratio'),
            'forward_pe': metrics.get('forward_pe'),
            'price_to_book': metrics.get('price_to_book'),
            'beta': metrics.get('beta'),
        }
    if row is None:
        return jsonify({'success': False, 'error': f'Could not screen {ticker}'}), 404

    score_data = calculate_score(metrics) if metrics else None
    news = (metrics or {}).get('news') or []
    detail_metrics = metrics or {}
    history = _stock_history_summary(ticker)
    related = _related_stock_cards(ticker, detail_metrics)
    analysis_context = {
        **row,
        'metrics': {
            'sector': detail_metrics.get('sector'),
            'industry': detail_metrics.get('industry'),
            'current_price': detail_metrics.get('current_price'),
            'previous_close': detail_metrics.get('previous_close'),
            'day_change': detail_metrics.get('day_change'),
            'day_change_percent': detail_metrics.get('day_change_percent'),
            'fifty_two_week_high': detail_metrics.get('fifty_two_week_high'),
            'fifty_two_week_low': detail_metrics.get('fifty_two_week_low'),
            'pe_ratio': detail_metrics.get('pe_ratio'),
            'forward_pe': detail_metrics.get('forward_pe'),
            'peg_ratio': detail_metrics.get('peg_ratio'),
            'price_to_book': detail_metrics.get('price_to_book'),
            'profit_margin': detail_metrics.get('profit_margin'),
            'return_on_equity': detail_metrics.get('return_on_equity'),
            'revenue_growth': detail_metrics.get('revenue_growth'),
            'earnings_growth': detail_metrics.get('earnings_growth'),
            'debt_to_equity': detail_metrics.get('debt_to_equity'),
            'current_ratio': detail_metrics.get('current_ratio'),
            'dividend_yield': detail_metrics.get('dividend_yield'),
            'beta': detail_metrics.get('beta'),
            'volatility': detail_metrics.get('volatility'),
        },
        'analyst_context': {
            'target_price': detail_metrics.get('target_price'),
            'target_high': detail_metrics.get('target_high'),
            'target_low': detail_metrics.get('target_low'),
            'recommendation': detail_metrics.get('recommendation'),
            'recommendation_mean': detail_metrics.get('recommendation_mean'),
            'number_of_analysts': detail_metrics.get('number_of_analysts'),
            'legacy_score': score_data,
        },
        'news': news[:6],
        'history': history,
        'related_stocks': related,
    }
    return jsonify({
        'success': True,
        'ticker': ticker,
        'row': row,
        'metrics': detail_metrics,
        'score': score_data,
        'news': news,
        'history': history,
        'related_stocks': related,
        'analysis_context': analysis_context,
        'llm_enabled': _llm_configured(),
        'llm_provider': LLM_PROVIDER,
    })


# ===========================
# Markets data (indices)
# ===========================
def _range_to_period_interval(range_key: str):
    mapping = {
        '1d': ('5d', '5m'),
        '5d': ('10d', '30m'),
        '1m': ('1mo', '1h'),
        '6m': ('6mo', '1d'),
        '1y': ('1y', '1d'),
        '5y': ('5y', '1wk'),
        'max': ('max', '1wk'),
    }
    return mapping.get(range_key, ('10d', '30m'))


def get_index_snapshot(symbol: str, name: str, range_key: str):
    """Fetch index snapshot with short history; cached for speed."""
    now = time.time()
    cache_key = f"{symbol}:{range_key}"
    cached = INDEX_CACHE.get(cache_key)
    if cached and now - cached['ts'] < INDEX_CACHE_TTL:
        return cached['data']
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        period, interval = _range_to_period_interval(range_key)
        hist = ticker.history(period=period, interval=interval)
        if hist is None or hist.empty:
            hist = ticker.history(period="1mo", interval="1d")
        if hist is None or hist.empty:
            return None
        closes = hist['Close'].dropna()
        if closes.empty:
            return None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) > 1 else last
        change = last - prev
        pct = (change / prev * 100) if prev else 0
        tail = closes.tail(200)
        data = {
            'symbol': symbol,
            'name': name,
            'price': round(last, 2),
            'change': round(change, 2),
            'change_pct': round(pct, 2),
            'labels': [idx.strftime('%Y-%m-%d %H:%M') for idx in tail.index],
            'prices': [round(float(x), 2) for x in tail.values],
            'currency': 'USD'
        }
        INDEX_CACHE[cache_key] = {'ts': now, 'data': data}
        return data
    except Exception as e:
        print(f"Index fetch failed for {symbol}: {e}")
        return None


# ============================================
# WATCHLIST (multiple per user)
# ============================================
def _watchlist_quote_map(symbols: list[str]) -> dict:
    """Fetch live quotes for a set of symbols keyed by symbol."""
    if not symbols:
        return {}
    quotes = _fetch_quote_batch(symbols)
    by_symbol = {}
    for q in quotes:
        sym = (q.get('symbol') or '').upper()
        if sym:
            by_symbol[sym] = q
    return by_symbol


def _serialize_watchlist_items(rows: list[dict]) -> list[dict]:
    symbols = [r['symbol'] for r in rows]
    quote_map = _watchlist_quote_map(symbols)
    name_map = _enrich_with_names([s for s in symbols if s not in quote_map])
    out = []
    for r in rows:
        sym = r['symbol']
        q = quote_map.get(sym, {})
        price = _safe_float(q.get('regularMarketPrice'))
        added_price = _safe_float(r.get('added_price'))
        change_since_pct = None
        if price is not None and added_price not in (None, 0):
            change_since_pct = round(((price - added_price) / added_price) * 100, 2)
        name = (
            q.get('shortName') or q.get('longName')
            or NAME_CACHE.get(sym, {}).get('name')
            or name_map.get(sym, {}).get('name')
            or sym
        )
        out.append({
            'symbol': sym,
            'name': name,
            'exchange': q.get('fullExchangeName') or q.get('exchange') or NAME_CACHE.get(sym, {}).get('exchange') or '',
            'price': round(price, 2) if price is not None else None,
            'change_pct': round(_safe_float(q.get('regularMarketChangePercent'), 0.0), 2) if q else None,
            'day_change': round(_safe_float(q.get('regularMarketChange'), 0.0), 2) if q else None,
            'added_price': round(added_price, 2) if added_price is not None else None,
            'added_at': r.get('added_at'),
            'change_since_added_pct': change_since_pct,
        })
    return out


def _clean_watchlist_name(name) -> str:
    if not isinstance(name, str):
        return ''
    return name.strip()[:80]


def _get_user_watchlist(user_id: str, wl_id: str):
    """Return a single watchlist row owned by the user, or None."""
    try:
        res = supabase.table('watchlists') \
            .select('id, name, position, created_at') \
            .eq('user_id', user_id) \
            .eq('id', wl_id) \
            .single() \
            .execute()
        return res.data
    except Exception:
        return None


@app.route('/watchlist')
@require_auth_page
def watchlist_page():
    return render_template('watchlist.html', active_nav='watchlist')


@app.route('/watchlist/<wl_id>')
@require_auth_page
def watchlist_detail_page(wl_id):
    return render_template('watchlist_detail.html', active_nav='watchlist', watchlist_id=wl_id)


@app.route('/api/watchlists', methods=['GET'])
@require_auth
def watchlists_list():
    user_id = request.user.get('id')
    try:
        wl_res = supabase.table('watchlists') \
            .select('id, name, position, created_at') \
            .eq('user_id', user_id) \
            .order('position', desc=False) \
            .order('created_at', desc=False) \
            .execute()
        watchlists = wl_res.data or []
        items_res = supabase.table('watchlist') \
            .select('watchlist_id, symbol') \
            .eq('user_id', user_id) \
            .execute()
        items = items_res.data or []
    except Exception as e:
        print(f"watchlists_list failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to load watchlists'}), 500

    by_wl = {}
    for it in items:
        by_wl.setdefault(it['watchlist_id'], []).append(it['symbol'])

    out = []
    for wl in watchlists:
        symbols = by_wl.get(wl['id'], [])
        out.append({
            'id': wl['id'],
            'name': wl['name'],
            'position': wl.get('position') or 0,
            'created_at': wl.get('created_at'),
            'count': len(symbols),
            'symbols': symbols[:8],
        })
    return jsonify({'success': True, 'watchlists': out})


@app.route('/api/watchlists', methods=['POST'])
@require_auth
def watchlists_create():
    user_id = request.user.get('id')
    data = request.get_json(silent=True) or {}
    name = _clean_watchlist_name(data.get('name')) or 'Untitled'
    try:
        max_pos_res = supabase.table('watchlists') \
            .select('position') \
            .eq('user_id', user_id) \
            .order('position', desc=True) \
            .limit(1) \
            .execute()
        rows = max_pos_res.data or []
        next_pos = (rows[0]['position'] + 1) if rows else 0
        ins = supabase.table('watchlists').insert({
            'user_id': user_id,
            'name': name,
            'position': next_pos,
        }).execute()
        created = (ins.data or [{}])[0]
    except Exception as e:
        print(f"watchlist create failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to create watchlist'}), 500
    return jsonify({'success': True, 'watchlist': {
        'id': created.get('id'),
        'name': created.get('name'),
        'position': created.get('position'),
        'created_at': created.get('created_at'),
        'count': 0,
        'symbols': [],
    }})


@app.route('/api/watchlists/<wl_id>', methods=['PATCH'])
@require_auth
def watchlists_update(wl_id):
    user_id = request.user.get('id')
    if not _get_user_watchlist(user_id, wl_id):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}
    update = {}
    if 'name' in data:
        cleaned = _clean_watchlist_name(data.get('name'))
        if not cleaned:
            return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
        update['name'] = cleaned
    if 'position' in data:
        try:
            update['position'] = int(data['position'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid position'}), 400
    if not update:
        return jsonify({'success': False, 'error': 'No changes'}), 400
    try:
        supabase.table('watchlists').update(update).eq('id', wl_id).eq('user_id', user_id).execute()
    except Exception as e:
        print(f"watchlist update failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to update watchlist'}), 500
    return jsonify({'success': True})


@app.route('/api/watchlists/reorder', methods=['POST'])
@require_auth
def watchlists_reorder():
    """Body: {order: [id1, id2, ...]} — sets position for each by index."""
    user_id = request.user.get('id')
    data = request.get_json(silent=True) or {}
    order = data.get('order')
    if not isinstance(order, list) or not order:
        return jsonify({'success': False, 'error': 'Order required'}), 400
    try:
        for idx, wl_id in enumerate(order):
            if not isinstance(wl_id, str):
                continue
            supabase.table('watchlists') \
                .update({'position': idx}) \
                .eq('id', wl_id) \
                .eq('user_id', user_id) \
                .execute()
    except Exception as e:
        print(f"watchlists reorder failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to reorder'}), 500
    return jsonify({'success': True})


@app.route('/api/watchlists/<wl_id>', methods=['DELETE'])
@require_auth
def watchlists_delete(wl_id):
    user_id = request.user.get('id')
    if not _get_user_watchlist(user_id, wl_id):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    try:
        supabase.table('watchlists').delete().eq('id', wl_id).eq('user_id', user_id).execute()
    except Exception as e:
        print(f"watchlist delete failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to delete watchlist'}), 500
    return jsonify({'success': True})


@app.route('/api/watchlists/<wl_id>/items', methods=['GET'])
@require_auth
def watchlist_items_get(wl_id):
    user_id = request.user.get('id')
    wl = _get_user_watchlist(user_id, wl_id)
    if not wl:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    try:
        res = supabase.table('watchlist') \
            .select('symbol, added_price, added_at') \
            .eq('user_id', user_id) \
            .eq('watchlist_id', wl_id) \
            .order('added_at', desc=True) \
            .execute()
        rows = res.data or []
    except Exception as e:
        print(f"watchlist items get failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to load items'}), 500
    return jsonify({
        'success': True,
        'watchlist': {
            'id': wl['id'],
            'name': wl['name'],
            'created_at': wl.get('created_at'),
        },
        'items': _serialize_watchlist_items(rows),
    })


@app.route('/api/watchlists/<wl_id>/items', methods=['POST'])
@require_auth
def watchlist_items_add(wl_id):
    user_id = request.user.get('id')
    if not _get_user_watchlist(user_id, wl_id):
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    raw_symbols = data.get('symbols') or ([data.get('symbol')] if data.get('symbol') else [])
    symbols = []
    seen = set()
    for s in raw_symbols:
        if not isinstance(s, str):
            continue
        sym = re.sub(r'[^A-Za-z0-9.^-]', '', s).upper()[:16]
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    if not symbols:
        return jsonify({'success': False, 'error': 'No symbols supplied'}), 400

    quote_map = _watchlist_quote_map(symbols)

    try:
        existing = supabase.table('watchlist') \
            .select('symbol') \
            .eq('user_id', user_id) \
            .eq('watchlist_id', wl_id) \
            .in_('symbol', symbols) \
            .execute()
        already = {r['symbol'] for r in (existing.data or [])}
    except Exception as e:
        print(f"watchlist items existence check failed: {e}")
        already = set()

    now_iso = datetime.now(timezone.utc).isoformat()
    inserts = []
    for sym in symbols:
        if sym in already:
            continue
        price = _safe_float((quote_map.get(sym) or {}).get('regularMarketPrice'))
        inserts.append({
            'user_id': user_id,
            'watchlist_id': wl_id,
            'symbol': sym,
            'added_price': price,
            'added_at': now_iso,
        })

    if inserts:
        try:
            supabase.table('watchlist').insert(inserts).execute()
        except Exception as e:
            print(f"watchlist items insert failed: {e}")
            return jsonify({'success': False, 'error': 'Failed to add items'}), 500

    return watchlist_items_get(wl_id)


@app.route('/api/watchlists/<wl_id>/items/<symbol>', methods=['DELETE'])
@require_auth
def watchlist_items_remove(wl_id, symbol):
    user_id = request.user.get('id')
    if not _get_user_watchlist(user_id, wl_id):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    sym = re.sub(r'[^A-Za-z0-9.^-]', '', symbol or '').upper()[:16]
    if not sym:
        return jsonify({'success': False, 'error': 'Invalid symbol'}), 400
    try:
        supabase.table('watchlist') \
            .delete() \
            .eq('user_id', user_id) \
            .eq('watchlist_id', wl_id) \
            .eq('symbol', sym) \
            .execute()
    except Exception as e:
        print(f"watchlist item delete failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to remove item'}), 500
    return jsonify({'success': True})


@app.route('/api/markets/indices')
def markets_indices():
    range_key = request.args.get('range', '5d')
    indices = []
    for symbol, name in INDEX_MAP.items():
        snap = get_index_snapshot(symbol, name, range_key)
        if snap:
            indices.append(snap)
    if not indices:
        return jsonify({'success': False, 'error': 'No index data available'}), 500
    return jsonify({'success': True, 'indices': indices})


def _load_watch_movers():
    """Compute top gainers/losers from the watchlist using yfinance (fallback)."""
    try:
        import yfinance as yf
        tickers = list(WATCHLIST.keys())
        hist = yf.download(tickers=tickers, period="2d", interval="1d", group_by='ticker', progress=False)
        movers = []
        for sym in tickers:
            try:
                frame = hist[sym] if isinstance(hist, dict) or hasattr(hist, 'keys') else hist
                close = frame['Close'].dropna()
                if close is None or len(close) == 0:
                    continue
                last = float(close.iloc[-1])
                prev = float(close.iloc[-2]) if len(close) > 1 else last
                change = last - prev
                pct = (change / prev * 100) if prev else 0
                movers.append({
                    'symbol': sym,
                    'name': WATCHLIST.get(sym, sym),
                    'price': round(last, 2),
                    'change': round(change, 2),
                    'change_pct': round(pct, 2)
                })
            except Exception as e:
                print(f"mover calc failed for {sym}: {e}")
                continue
        gainers = sorted(movers, key=lambda x: x['change_pct'], reverse=True)[:6]
        losers = sorted(movers, key=lambda x: x['change_pct'])[:6]
        return gainers, losers
    except Exception as e:
        print(f"load_watch_movers failed: {e}")
        return [], []


def _fetch_yahoo_movers(scr_id: str, limit: int = 10):
    """
    Fetch top movers from Yahoo predefined screens (day_gainers/day_losers).
    Unofficial but reliable and real-time enough.
    """
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
        params = {
            "scrIds": scr_id,
            "count": limit,
            "start": 0,
            "formatted": "false",
            "lang": "en-US",
            "region": "US"
        }
        res = requests.get(url, params=params, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code != 200:
            return []
        payload = res.json()
        quotes = payload.get("finance", {}).get("result", [{}])[0].get("quotes", []) or []
        movers = []
        for q in quotes[:limit]:
            price = q.get("regularMarketPrice")
            change = q.get("regularMarketChange")
            pct = q.get("regularMarketChangePercent")
            if price is None or change is None or pct is None:
                continue
            movers.append({
                "symbol": q.get("symbol"),
                "name": q.get("shortName") or q.get("longName") or q.get("symbol"),
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(pct, 2)
            })
        return movers
    except Exception as e:
        print(f"fetch yahoo movers failed ({scr_id}): {e}")
        return []


@app.route('/api/markets/movers')
def markets_movers():
    gainers = _fetch_yahoo_movers('day_gainers', limit=25)
    losers = _fetch_yahoo_movers('day_losers', limit=25)
    if not gainers or not losers:
        # Fallback to watchlist-based if Yahoo fails
        gainers_fb, losers_fb = _load_watch_movers()
        if not gainers:
            gainers = gainers_fb
        if not losers:
            losers = losers_fb
    if not gainers and not losers:
        return jsonify({'success': False, 'error': 'No movers data'}), 500
    return jsonify({'success': True, 'gainers': gainers, 'losers': losers})


@app.route('/api/username_available')
def username_available():
    username = request.args.get('username', '').strip()

    if not username:
        return jsonify({'available': False})

    # Check the new 'username' column first
    res = supabase.table('usernames') \
        .select('username') \
        .eq('username', username) \
        .execute()

    if len(res.data) > 0:
        return jsonify({'available': False})

    # Also check display_name for backwards compatibility with existing users
    res = supabase.table('usernames') \
        .select('display_name') \
        .eq('display_name', username) \
        .execute()

    return jsonify({'available': len(res.data) == 0})


@app.route('/api/lookup_email_by_username')
def lookup_email_by_username():
    """
    Look up a user's email by their username.
    Used for login-by-username functionality.
    Returns the email if found, or an error if not.
    """
    username = request.args.get('username', '').strip()

    if not username:
        return jsonify({'error': 'Username required'}), 400

    try:
        # First try to look up by the new 'username' column
        res = supabase.table('usernames') \
            .select('user_id') \
            .eq('username', username) \
            .execute()

        # If not found, fall back to display_name for backwards compatibility
        if not res.data or len(res.data) == 0:
            res = supabase.table('usernames') \
                .select('user_id') \
                .eq('display_name', username) \
                .execute()

        if not res.data or len(res.data) == 0:
            return jsonify({'error': 'Username not found'}), 404

        user_id = res.data[0]['user_id']

        # Now get the email from Supabase Auth using admin API
        response = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
            headers={
                'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
                'apikey': SUPABASE_ANON_KEY
            }
        )

        if response.status_code != 200:
            return jsonify({'error': 'Could not retrieve user'}), 500

        user_data = response.json()
        email = user_data.get('email')

        if not email:
            return jsonify({'error': 'Email not found for user'}), 404

        return jsonify({'email': email})

    except Exception as e:
        print(f"Email lookup error: {e}")
        return jsonify({'error': 'Lookup failed'}), 500


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
    
    # Validate username format - strict rules for uniqueness
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
        # Store username in the new 'username' column
        # Set display_name to the same value initially (user can change it later)
        res = supabase.table('usernames').insert({
            'user_id': user['id'],
            'username': username,
            'display_name': username  # Initially same as username
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
        .select('*') \
        .eq('user_id', user_id) \
        .single() \
        .execute()

    data = res.data or {}

    avatar_url = None
    if data.get('avatar_url'):
        avatar_url = supabase.storage.from_('avatars').get_public_url(
            data['avatar_url']
        )

    # For backwards compatibility: if username doesn't exist, use display_name
    username = data.get('username') or data.get('display_name')
    display_name = data.get('display_name') or username

    return jsonify({
        'username': username,
        'display_name': display_name,
        'avatar_url': avatar_url,
        'email': user.get('email'),
        'created_at': user.get('created_at'),
        'is_private': bool(data.get('is_private')),
        'social_links': {
            'twitter': data.get('twitter_handle') or '',
            'reddit': data.get('reddit_handle') or '',
            'instagram': data.get('instagram_handle') or '',
            'website': data.get('website_url') or '',
            'other': data.get('other_url') or '',
        }
    })


@app.route('/api/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile fields. Username cannot be changed here."""
    user = request.user
    user_id = user['id']
    
    data = request.json
    display_name = data.get('display_name', '').strip()
    
    if not display_name:
        return jsonify({'error': 'Display name required'}), 400
    
    # Validate display name - more permissive than username
    if len(display_name) < 1:
        return jsonify({'error': 'Display name cannot be empty'}), 400
    
    if len(display_name) > 50:
        return jsonify({'error': 'Display name must be 50 characters or less'}), 400
    
    # Sanitize display name - allow letters, numbers, spaces, and common punctuation
    # Block obvious bad patterns
    import re
    
    # Allow letters (including unicode), numbers, spaces, hyphens, underscores, apostrophes, periods
    if not re.match(r'^[\w\s\-\'.]+$', display_name, re.UNICODE):
        return jsonify({'error': 'Display name contains invalid characters'}), 400
    
    # Basic profanity filter - expand this list as needed
    profanity_patterns = [
        r'\b(fuck|shit|ass|bitch|cunt|dick|cock|pussy|nigger|nigga|faggot|retard)\b'
    ]
    
    display_name_lower = display_name.lower()
    for pattern in profanity_patterns:
        if re.search(pattern, display_name_lower, re.IGNORECASE):
            return jsonify({'error': 'Display name contains inappropriate language'}), 400
    
    try:
        # Check if user has a record
        user_record = supabase.table('usernames') \
            .select('user_id, username') \
            .eq('user_id', user_id) \
            .execute()
        
        if user_record.data:
            update_payload = {'display_name': display_name}
            for key in ('is_private', 'twitter_handle', 'reddit_handle', 'instagram_handle', 'website_url', 'other_url'):
                if key in data:
                    value = data.get(key)
                    if isinstance(value, str):
                        value = value.strip()
                    update_payload[key] = value

            supabase.table('usernames').update(update_payload).eq('user_id', user_id).execute()
        else:
            # This shouldn't happen normally - user should have username from signup
            return jsonify({'error': 'User profile not found. Please contact support.'}), 404
        
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
# BLOG/SOCIAL API ROUTES
# ============================================

from datetime import datetime

# Content validation constants
MAX_POST_WORDS = 500
MAX_TITLE_LENGTH = 200
MAX_COMMENT_LENGTH = 2000
MAX_IMAGES_PER_POST = 4
MAX_TAGS_PER_POST = 5

def count_words(text):
    """Count words in text."""
    return len(text.split())

def sanitize_content(text):
    """Basic content sanitization."""
    if not text:
        return text
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def validate_post_content(content):
    """Validate post content."""
    if not content or not content.strip():
        return False, "Content is required"
    word_count = count_words(content)
    if word_count > MAX_POST_WORDS:
        return False, f"Content exceeds {MAX_POST_WORDS} word limit ({word_count} words)"
    return True, None

def sanitize_tag(tag):
    """Sanitize and validate a tag."""
    tag = tag.lower().strip()
    tag = re.sub(r'[^a-z0-9\-]', '', tag)
    if len(tag) < 2 or len(tag) > 30:
        return None
    return tag


def count_table_rows(table_name: str, **filters) -> int:
    """Count rows without making profile rendering depend on optional tables."""
    try:
        query = supabase.table(table_name).select('id', count='exact')
        for key, value in filters.items():
            if value is None:
                query = query.is_(key, 'null')
            else:
                query = query.eq(key, value)
        result = query.execute()
        if result.count is not None:
            return result.count
        return len(result.data or [])
    except Exception as e:
        if table_name != 'follows' or 'PGRST205' not in str(e):
            print(f"Count failed for {table_name}: {e}")
        return 0


def _mark_follows_unavailable(error: Exception):
    global FOLLOWS_TABLE_AVAILABLE
    if 'PGRST205' in str(error) or 'Could not find the table' in str(error):
        FOLLOWS_TABLE_AVAILABLE = False


def get_follow_counts(user_id: str) -> tuple[int, int]:
    """Return follower/following counts, using Supabase when available."""
    global FOLLOWS_TABLE_AVAILABLE
    if FOLLOWS_TABLE_AVAILABLE is not False:
        try:
            followers_result = supabase.table('follows') \
                .select('id', count='exact') \
                .eq('following_id', user_id) \
                .execute()
            following_result = supabase.table('follows') \
                .select('id', count='exact') \
                .eq('follower_id', user_id) \
                .execute()
            FOLLOWS_TABLE_AVAILABLE = True
            followers = followers_result.count if followers_result.count is not None else len(followers_result.data or [])
            following = following_result.count if following_result.count is not None else len(following_result.data or [])
            return followers, following
        except Exception as e:
            _mark_follows_unavailable(e)
            if FOLLOWS_TABLE_AVAILABLE is not False:
                print(f"Follow count failed: {e}")

    rows = _load_follow_rows()
    followers = sum(1 for row in rows if row.get('following_id') == user_id)
    following = sum(1 for row in rows if row.get('follower_id') == user_id)
    return followers, following


def get_public_user_stats(user_id: str) -> dict:
    """Fetch profile counters concurrently so public profiles feel immediate."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as executor:
        post_future = executor.submit(count_table_rows, 'posts', user_id=user_id, deleted_at=None)
        repost_future = executor.submit(count_table_rows, 'posts', user_id=user_id, is_repost=True)
        comment_future = executor.submit(count_table_rows, 'comments', user_id=user_id)
        follow_future = executor.submit(get_follow_counts, user_id)

        follower_count, following_count = follow_future.result()
        return {
            'post_count': post_future.result(),
            'repost_count': repost_future.result(),
            'comment_count': comment_future.result(),
            'follower_count': follower_count,
            'following_count': following_count
        }


def is_following_user(follower_id: str | None, following_id: str | None) -> bool:
    if not follower_id or not following_id:
        return False
    if FOLLOWS_TABLE_AVAILABLE is not False:
        try:
            result = supabase.table('follows') \
                .select('id') \
                .eq('follower_id', follower_id) \
                .eq('following_id', following_id) \
                .limit(1) \
                .execute()
            return bool(result.data)
        except Exception as e:
            _mark_follows_unavailable(e)

    return any(
        row.get('follower_id') == follower_id and row.get('following_id') == following_id
        for row in _load_follow_rows()
    )


def follow_user(follower_id: str, following_id: str) -> bool:
    global FOLLOWS_TABLE_AVAILABLE
    if follower_id == following_id:
        return False
    if is_following_user(follower_id, following_id):
        return True
    if FOLLOWS_TABLE_AVAILABLE is not False:
        try:
            supabase.table('follows').insert({
                'follower_id': follower_id,
                'following_id': following_id
            }).execute()
            FOLLOWS_TABLE_AVAILABLE = True
            return True
        except Exception as e:
            _mark_follows_unavailable(e)
            if FOLLOWS_TABLE_AVAILABLE is not False:
                print(f"Follow insert failed: {e}")

    rows = _load_follow_rows()
    rows.append({
        'follower_id': follower_id,
        'following_id': following_id,
        'created_at': datetime.utcnow().isoformat()
    })
    _save_follow_rows(rows)
    return True


def unfollow_user(follower_id: str, following_id: str) -> bool:
    global FOLLOWS_TABLE_AVAILABLE
    if FOLLOWS_TABLE_AVAILABLE is not False:
        try:
            supabase.table('follows') \
                .delete() \
                .eq('follower_id', follower_id) \
                .eq('following_id', following_id) \
                .execute()
            FOLLOWS_TABLE_AVAILABLE = True
            return True
        except Exception as e:
            _mark_follows_unavailable(e)
            if FOLLOWS_TABLE_AVAILABLE is not False:
                print(f"Follow delete failed: {e}")

    rows = [
        row for row in _load_follow_rows()
        if not (row.get('follower_id') == follower_id and row.get('following_id') == following_id)
    ]
    _save_follow_rows(rows)
    return True


def get_user_profile_by_username(username: str):
    """Fetch user profile data by username, including public avatar URL."""
    try:
        res = supabase.table('usernames') \
            .select('*') \
            .eq('username', username) \
            .single() \
            .execute()
        
        if not res.data:
            return None

        stats = get_public_user_stats(res.data['user_id'])
        profile = _public_profile_from_row(res.data)
        profile.update(stats)
        return profile
    except Exception as e:
        print(f"Error fetching user by username: {e}")
        return None


def get_follow_list(user_id: str, kind: str, limit: int = 50) -> list[dict]:
    """Return public profiles for followers/following. kind: followers|following."""
    id_field = 'follower_id' if kind == 'followers' else 'following_id'
    match_field = 'following_id' if kind == 'followers' else 'follower_id'
    ids = []
    try:
        if FOLLOWS_TABLE_AVAILABLE:
            result = supabase.table('follows') \
                .select(id_field) \
                .eq(match_field, user_id) \
                .limit(limit) \
                .execute()
            ids = [row.get(id_field) for row in (result.data or []) if row.get(id_field)]
    except Exception as e:
        _mark_follows_unavailable(e)

    if not ids:
        rows = _load_follow_rows()
        ids = [
            row.get(id_field) for row in rows
            if row.get(match_field) == user_id and row.get(id_field)
        ][:limit]

    profiles = get_profiles_by_ids(ids)
    return [profiles[uid] for uid in ids if uid in profiles]


@app.route('/api/posts', methods=['GET'])
def get_posts():
    """Get posts feed with pagination."""
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 20, type=int), 50)
    tag = request.args.get('tag', '').strip()
    user_id_filter = request.args.get('user_id', '').strip()
    username_filter = request.args.get('username', '').strip()
    sort = request.args.get('sort', 'recent')
    offset = (page - 1) * limit
    
    try:
        profile_row = None
        if username_filter and not user_id_filter:
            user_result = supabase.table('usernames') \
                .select('*') \
                .eq('username', username_filter) \
                .single() \
                .execute()
            if not user_result.data:
                return jsonify({'success': True, 'posts': [], 'page': page, 'limit': limit, 'has_more': False})
            profile_row = user_result.data
            user_id_filter = user_result.data['user_id']
        if user_id_filter and profile_row is None:
            profile_result = supabase.table('usernames') \
                .select('*') \
                .eq('user_id', user_id_filter) \
                .single() \
                .execute()
            profile_row = profile_result.data or {}
        if user_id_filter and profile_row and profile_row.get('is_private'):
            access_token = session.get('supabase_access_token')
            current_user = get_user_from_token(access_token) if access_token else None
            current_user_id = current_user.get('id') if current_user else None
            if current_user_id != user_id_filter and not is_following_user(current_user_id, user_id_filter):
                return jsonify({
                    'success': True,
                    'posts': [],
                    'page': page,
                    'limit': limit,
                    'has_more': False,
                    'private': True
                })

        query = supabase.table('posts') \
            .select('*, usernames!inner(username, display_name, avatar_url), post_images(id, image_path, display_order), post_tags(tags(id, name))') \
            .is_('deleted_at', 'null')
        
        if user_id_filter:
            query = query.eq('user_id', user_id_filter)
        
        if sort == 'popular':
            query = query.order('like_count', desc=True)
        else:
            query = query.order('created_at', desc=True)
        
        query = query.range(offset, offset + limit - 1)
        result = query.execute()
        posts = result.data or []
        
        if tag:
            tag_lower = tag.lower()
            posts = [p for p in posts if any(
                t.get('tags', {}).get('name', '').lower() == tag_lower 
                for t in p.get('post_tags', [])
            )]
        
        user_votes = {}
        user_reposts = set()
        access_token = session.get('supabase_access_token')
        if access_token:
            user = get_user_from_token(access_token)
            if user:
                post_ids = [p['id'] for p in posts]
                original_ids = [p.get('original_post_id') for p in posts if p.get('original_post_id')]
                repost_target_ids = list(set(post_ids + original_ids))
                if post_ids:
                    votes_result = supabase.table('post_votes') \
                        .select('post_id, vote_type') \
                        .eq('user_id', user['id']) \
                        .in_('post_id', post_ids) \
                        .execute()
                    user_votes = {v['post_id']: v['vote_type'] for v in (votes_result.data or [])}
                if repost_target_ids:
                    reposts_result = supabase.table('reposts') \
                        .select('original_post_id') \
                        .eq('user_id', user['id']) \
                        .in_('original_post_id', repost_target_ids) \
                        .execute()
                    user_reposts = {r['original_post_id'] for r in (reposts_result.data or [])}
        
        formatted_posts = []
        for post in posts:
            author_data = post.get('usernames') or {}
            avatar_url = None
            if author_data.get('avatar_url'):
                avatar_url = supabase.storage.from_('avatars').get_public_url(author_data['avatar_url'])
            
            images = []
            for img in sorted(post.get('post_images', []), key=lambda x: x.get('display_order', 0)):
                img_url = supabase.storage.from_('post-images').get_public_url(img['image_path'])
                images.append({'id': img['id'], 'url': img_url})
            
            tags = [pt.get('tags', {}).get('name') for pt in post.get('post_tags', []) if pt.get('tags')]
            
            formatted_posts.append({
                'id': post['id'],
                'title': post.get('title'),
                'content': post['content'],
                'created_at': post['created_at'],
                'like_count': post.get('like_count', 0),
                'dislike_count': post.get('dislike_count', 0),
                'comment_count': post.get('comment_count', 0),
                'repost_count': post.get('repost_count', 0),
                'is_repost': post.get('is_repost', False),
                'original_post_id': post.get('original_post_id'),
                'author': {
                    'id': post['user_id'],
                    'username': author_data.get('username') or author_data.get('display_name'),
                    'display_name': author_data.get('display_name'),
                    'avatar_url': avatar_url
                },
                'images': images,
                'tags': tags,
                'user_vote': user_votes.get(post['id']),
                'user_reposted': (post.get('original_post_id') or post['id']) in user_reposts
            })
        
        return jsonify({
            'success': True,
            'posts': formatted_posts,
            'page': page,
            'limit': limit,
            'has_more': len(posts) == limit
        })
    except Exception as e:
        print(f"Error fetching posts: {e}")
        return jsonify({'error': 'Failed to fetch posts'}), 500


@app.route('/api/users/<username>')
def get_user_by_username(username):
    """Get public profile data for a user."""
    profile = get_user_profile_by_username(username)
    if not profile:
        return jsonify({'error': 'User not found'}), 404

    access_token = session.get('supabase_access_token')
    current_user = get_user_from_token(access_token) if access_token else None
    current_user_id = current_user.get('id') if current_user else None
    profile['is_self'] = current_user_id == profile['id']
    profile['is_following'] = is_following_user(current_user_id, profile['id'])
    if profile.get('is_private') and not profile['is_self'] and not profile['is_following']:
        profile.update({
            'post_count': 0,
            'comment_count': 0,
            'repost_count': 0,
            'is_private_view': True
        })
    
    return jsonify({'success': True, 'user': profile})


@app.route('/api/users/<username>/<kind>')
def get_user_follow_list(username, kind):
    if kind not in ('followers', 'following'):
        return jsonify({'error': 'Invalid follow list'}), 404
    profile = get_user_profile_by_username(username)
    if not profile:
        return jsonify({'error': 'User not found'}), 404

    access_token = session.get('supabase_access_token')
    current_user = get_user_from_token(access_token) if access_token else None
    current_user_id = current_user.get('id') if current_user else None
    can_view = (
        not profile.get('is_private')
        or current_user_id == profile['id']
        or is_following_user(current_user_id, profile['id'])
    )
    if not can_view:
        return jsonify({'success': True, 'users': [], 'private': True})

    return jsonify({'success': True, 'users': get_follow_list(profile['id'], kind)})


@app.route('/api/users/<username>/follow', methods=['POST', 'DELETE'])
@require_auth
def follow_user_by_username(username):
    """Follow or unfollow another public profile."""
    profile = get_user_profile_by_username(username)
    if not profile:
        return jsonify({'error': 'User not found'}), 404

    follower_id = request.user['id']
    following_id = profile['id']
    if follower_id == following_id:
        return jsonify({'error': 'You cannot follow yourself'}), 400

    if request.method == 'DELETE':
        unfollow_user(follower_id, following_id)
        is_following = False
    else:
        follow_user(follower_id, following_id)
        is_following = True

    follower_count, following_count = get_follow_counts(following_id)
    return jsonify({
        'success': True,
        'is_following': is_following,
        'follower_count': follower_count,
        'following_count': following_count
    })


@app.route('/api/admin/moderators', methods=['GET', 'POST'])
@require_auth
def manage_moderators():
    """Admins can list/add moderators by username."""
    user = request.user
    if not is_admin(user):
        return jsonify({'error': 'Admin access required'}), 403

    if request.method == 'GET':
        moderator_ids = sorted(MODERATOR_IDS)
        profiles = get_profiles_by_ids(moderator_ids)
        moderator_list = []
        for mid in moderator_ids:
            profile = profiles.get(mid, {'id': mid})
            moderator_list.append(profile)
        return jsonify({'success': True, 'moderators': moderator_list})

    data = request.json or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({'error': 'Username is required'}), 400

    try:
        profile = supabase.table('usernames') \
            .select('user_id') \
            .eq('username', username) \
            .single() \
            .execute()
        if not profile.data:
            return jsonify({'error': 'Username not found'}), 404

        user_id = profile.data['user_id']
        MODERATOR_IDS.add(user_id)
        _save_id_file(MODERATOR_FILE, 'moderators', MODERATOR_IDS)
        profiles = get_profiles_by_ids([user_id])
        return jsonify({'success': True, 'moderator': profiles.get(user_id, {'id': user_id})})
    except Exception as e:
        print(f"Error adding moderator: {e}")
        return jsonify({'error': 'Failed to add moderator'}), 500


@app.route('/api/admin/moderators/remove', methods=['POST'])
@require_auth
def remove_moderator():
    """Admins can remove moderator by username."""
    user = request.user
    if not is_admin(user):
        return jsonify({'error': 'Admin access required'}), 403

    data = request.json or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({'error': 'Username is required'}), 400

    try:
        profile = supabase.table('usernames') \
            .select('user_id') \
            .eq('username', username) \
            .single() \
            .execute()
        if not profile.data:
            return jsonify({'error': 'Username not found'}), 404
        user_id = profile.data['user_id']
        if user_id in MODERATOR_IDS:
            MODERATOR_IDS.discard(user_id)
            _save_id_file(MODERATOR_FILE, 'moderators', MODERATOR_IDS)
        return jsonify({'success': True, 'user_id': user_id})
    except Exception as e:
        print(f"Error removing moderator: {e}")
        return jsonify({'error': 'Failed to remove moderator'}), 500


# ============================================
# /api/admin/traffic — Cloudflare RUM analytics
# ============================================

_CF_GRAPHQL_URL = 'https://api.cloudflare.com/client/v4/graphql'
_CF_TRAFFIC_CACHE: dict = {}   # range -> (epoch_seconds, payload)
_CF_TRAFFIC_CACHE_TTL = 60     # seconds


def _cf_range_window(range_str: str):
    """Translate '24h' / '7d' / '30d' / '90d' into a CF query window.

    Returns (start, end, prev_start, prev_end, bucket_dim) where
    bucket_dim is the GraphQL dimension to group by for the timeseries.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if range_str == '7d':
        delta = timedelta(days=7)
        bucket = 'datetimeHour'
    elif range_str == '30d':
        delta = timedelta(days=30)
        bucket = 'datetimeDay'
    elif range_str == '90d':
        delta = timedelta(days=90)
        bucket = 'datetimeDay'
    else:  # 24h default
        delta = timedelta(hours=24)
        bucket = 'datetimeFifteenMinutes'
    start = now - delta
    prev_end = start
    prev_start = start - delta
    iso = lambda d: d.strftime('%Y-%m-%dT%H:%M:%SZ')
    return iso(start), iso(now), iso(prev_start), iso(prev_end), bucket


def _cf_graphql(query: str, variables: dict) -> dict:
    """POST a GraphQL query to Cloudflare. Returns parsed `data` block or {}."""
    if not CLOUDFLARE_API_TOKEN:
        raise RuntimeError('CLOUDFLARE_API_TOKEN not configured')
    headers = {
        'Authorization': f'Bearer {CLOUDFLARE_API_TOKEN}',
        'Content-Type': 'application/json',
    }
    resp = requests.post(
        _CF_GRAPHQL_URL,
        headers=headers,
        json={'query': query, 'variables': variables},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get('errors'):
        # Log but do not crash; partial data may still be usable.
        print(f"Cloudflare GraphQL errors: {body['errors']}")
    return body.get('data') or {}


def _safe(fn, default=None):
    """Run fn(); return default on any exception (and log)."""
    try:
        return fn()
    except Exception as e:
        print(f"[/api/admin/traffic] sub-query failed: {e}")
        return default


def _delta_pct(curr, prev):
    """Percent change current vs previous. Returns None if previous is 0/None."""
    if not prev:
        return None
    try:
        return ((curr - prev) / prev) * 100.0
    except Exception:
        return None


def _fetch_cf_traffic(range_str: str) -> dict:
    """Fetch + shape Cloudflare RUM data for the dashboard.

    Returns a dict matching what templates/admin_dashboard.html's
    renderKPIs / renderChart / renderTopPaths / renderCountries / renderCWV
    expect. Sub-queries degrade independently — a single failure does not
    blank the whole dashboard.
    """
    start, end, prev_start, prev_end, bucket = _cf_range_window(range_str)
    vars_common = {
        'accountTag': CLOUDFLARE_ACCOUNT_ID,
        'siteTag': CLOUDFLARE_SITE_TAG,
        'start': start,
        'end': end,
    }

    # --- 1. Totals (current + previous) for KPI deltas ----------------
    # NOTE: rumPageloadEventsAdaptiveGroups exposes `count` reliably; the
    # `sum { visits }` / `uniq { uniques }` fields aren't part of the public
    # RUM schema, so we use `count` for all three metrics. Pageviews/Visits/
    # Unique visitors therefore all reflect the same pageload-event count
    # until we add separate visitor/session segmentation (TODO).
    totals_query = '''
      query Totals($accountTag: String!, $siteTag: String!, $start: Time!, $end: Time!, $prevStart: Time!, $prevEnd: Time!) {
        viewer {
          accounts(filter: {accountTag: $accountTag}) {
            current: rumPageloadEventsAdaptiveGroups(
              limit: 1,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end}
            ) {
              count
            }
            previous: rumPageloadEventsAdaptiveGroups(
              limit: 1,
              filter: {siteTag: $siteTag, datetime_geq: $prevStart, datetime_leq: $prevEnd}
            ) {
              count
            }
          }
        }
      }
    '''
    totals_data = _safe(lambda: _cf_graphql(totals_query, {**vars_common, 'prevStart': prev_start, 'prevEnd': prev_end}), {}) or {}
    accounts = ((totals_data.get('viewer') or {}).get('accounts') or [])
    curr_bucket = (accounts[0].get('current') if accounts else None) or [{}]
    prev_bucket = (accounts[0].get('previous') if accounts else None) or [{}]
    curr = curr_bucket[0] if curr_bucket else {}
    prev = prev_bucket[0] if prev_bucket else {}

    def _pick(b, *path):
        cur = b
        for p in path:
            if cur is None:
                return None
            cur = cur.get(p) if isinstance(cur, dict) else None
        return cur

    curr_pv = _pick(curr, 'count') or 0
    prev_pv = _pick(prev, 'count') or 0
    # Visits / unique visitors fall back to the pageview count until we
    # wire separate session/user dimensions.
    curr_vis = curr_pv
    curr_uniq = curr_pv
    prev_vis = prev_pv
    prev_uniq = prev_pv

    # --- 2. Timeseries -----------------------------------------------
    # Same simplification as totals: only `count` is reliably exposed.
    series_query = f'''
      query Series($accountTag: String!, $siteTag: String!, $start: Time!, $end: Time!) {{
        viewer {{
          accounts(filter: {{accountTag: $accountTag}}) {{
            series: rumPageloadEventsAdaptiveGroups(
              limit: 500,
              orderBy: [{bucket}_ASC],
              filter: {{siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end}}
            ) {{
              dimensions {{ {bucket} }}
              count
            }}
          }}
        }}
      }}
    '''
    series_data = _safe(lambda: _cf_graphql(series_query, vars_common), {}) or {}
    series_rows = ((((series_data.get('viewer') or {}).get('accounts') or [{}])[0]).get('series') or [])
    timeseries = []
    for row in series_rows:
        dims = row.get('dimensions') or {}
        t_raw = dims.get(bucket) or ''
        c = row.get('count') or 0
        timeseries.append({
            't': t_raw,
            'pageviews': c,
            'visits': c,
            'visitors': c,
        })

    # --- 3. Top paths -------------------------------------------------
    paths_query = '''
      query Paths($accountTag: String!, $siteTag: String!, $start: Time!, $end: Time!) {
        viewer {
          accounts(filter: {accountTag: $accountTag}) {
            paths: rumPageloadEventsAdaptiveGroups(
              limit: 10,
              orderBy: [count_DESC],
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, bot: 0}
            ) {
              dimensions { requestPath }
              count
            }
          }
        }
      }
    '''
    paths_data = _safe(lambda: _cf_graphql(paths_query, vars_common), {}) or {}
    paths_rows = ((((paths_data.get('viewer') or {}).get('accounts') or [{}])[0]).get('paths') or [])
    top_paths = []
    for row in paths_rows:
        dims = row.get('dimensions') or {}
        top_paths.append({
            'path': dims.get('requestPath') or '(unknown)',
            'views': row.get('count') or 0,
            'lcp_p75': None,  # joined in below from CWV per-path query if available
        })

    # --- 4. Countries -------------------------------------------------
    countries_query = '''
      query Countries($accountTag: String!, $siteTag: String!, $start: Time!, $end: Time!) {
        viewer {
          accounts(filter: {accountTag: $accountTag}) {
            countries: rumPageloadEventsAdaptiveGroups(
              limit: 10,
              orderBy: [count_DESC],
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, bot: 0}
            ) {
              dimensions { countryName }
              count
            }
          }
        }
      }
    '''
    countries_data = _safe(lambda: _cf_graphql(countries_query, vars_common), {}) or {}
    countries_rows = ((((countries_data.get('viewer') or {}).get('accounts') or [{}])[0]).get('countries') or [])
    countries = [
        {'country': (r.get('dimensions') or {}).get('countryName') or 'Unknown', 'views': r.get('count') or 0}
        for r in countries_rows
    ]

    # --- 5. Core Web Vitals (p75 + distributions) ---------------------
    # CF's rumWebVitalsEventsAdaptiveGroups appears to use a long-format
    # schema where each row carries `metric` (LCP/INP/CLS) and `metricRating`
    # dimensions. We split by metric via aliased sub-queries.
    cwv_query = '''
      query CWV($accountTag: String!, $siteTag: String!, $start: Time!, $end: Time!) {
        viewer {
          accounts(filter: {accountTag: $accountTag}) {
            lcpQ: rumWebVitalsEventsAdaptiveGroups(
              limit: 1,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, metric: "LCP"}
            ) { quantiles { metricValueP75 } }
            inpQ: rumWebVitalsEventsAdaptiveGroups(
              limit: 1,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, metric: "INP"}
            ) { quantiles { metricValueP75 } }
            clsQ: rumWebVitalsEventsAdaptiveGroups(
              limit: 1,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, metric: "CLS"}
            ) { quantiles { metricValueP75 } }
            lcpDist: rumWebVitalsEventsAdaptiveGroups(
              limit: 10,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, metric: "LCP"}
            ) {
              dimensions { metricRating }
              count
            }
            inpDist: rumWebVitalsEventsAdaptiveGroups(
              limit: 10,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, metric: "INP"}
            ) {
              dimensions { metricRating }
              count
            }
            clsDist: rumWebVitalsEventsAdaptiveGroups(
              limit: 10,
              filter: {siteTag: $siteTag, datetime_geq: $start, datetime_leq: $end, metric: "CLS"}
            ) {
              dimensions { metricRating }
              count
            }
          }
        }
      }
    '''
    cwv_data = _safe(lambda: _cf_graphql(cwv_query, vars_common), {}) or {}
    cwv_acct = (((cwv_data.get('viewer') or {}).get('accounts') or [{}])[0]) if cwv_data else {}

    def _p75(node_list):
        if not node_list:
            return None
        row = node_list[0] if node_list else {}
        return ((row.get('quantiles') or {}).get('metricValueP75'))

    def _rating_dist(rows):
        # rows: [{dimensions: {metricRating: 'good'|'needsImprovement'|'poor'}, count: N}, ...]
        buckets = {'good': 0, 'needsImprovement': 0, 'poor': 0}
        total = 0
        for r in rows or []:
            rating = (r.get('dimensions') or {}).get('metricRating')
            c = r.get('count') or 0
            if rating in buckets:
                buckets[rating] += c
            total += c
        if total <= 0:
            return None
        return {
            'good': buckets['good'] / total,
            'ni':   buckets['needsImprovement'] / total,
            'poor': buckets['poor'] / total,
        }

    cwv = {
        'lcp_p75': _p75(cwv_acct.get('lcpQ')),
        'inp_p75': _p75(cwv_acct.get('inpQ')),
        'cls_p75': _p75(cwv_acct.get('clsQ')),
        'lcp_dist': _rating_dist(cwv_acct.get('lcpDist')),
        'inp_dist': _rating_dist(cwv_acct.get('inpDist')),
        'cls_dist': _rating_dist(cwv_acct.get('clsDist')),
    }

    return {
        'success': True,
        'range': range_str,
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'kpis': {
            'pageviews': curr_pv,
            'pageviews_delta': _delta_pct(curr_pv, prev_pv),
            'visits': curr_vis,
            'visits_delta': _delta_pct(curr_vis, prev_vis),
            'visitors': curr_uniq,
            'visitors_delta': _delta_pct(curr_uniq, prev_uniq),
            'lcp_p75': cwv['lcp_p75'],
        },
        'timeseries': timeseries,
        'top_paths': top_paths,
        'countries': countries,
        'cwv': cwv,
    }


@app.route('/api/admin/traffic')
@require_auth
def admin_traffic():
    """Cloudflare Web Analytics (RUM) aggregates for the admin dashboard."""
    user = request.user
    if not is_admin(user):
        return jsonify({'error': 'Admin access required'}), 403

    if not (CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_SITE_TAG):
        return jsonify({
            'error': 'Cloudflare analytics not configured. Set CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_SITE_TAG.'
        }), 503

    range_str = (request.args.get('range') or '24h').lower()
    if range_str not in {'24h', '7d', '30d', '90d'}:
        range_str = '24h'

    # Tiny in-process cache keyed by range to avoid hammering CF on every poll.
    now_s = time.time()
    cached = _CF_TRAFFIC_CACHE.get(range_str)
    if cached and (now_s - cached[0]) < _CF_TRAFFIC_CACHE_TTL:
        return jsonify(cached[1])

    try:
        payload = _fetch_cf_traffic(range_str)
        _CF_TRAFFIC_CACHE[range_str] = (now_s, payload)
        return jsonify(payload)
    except Exception as e:
        print(f"[/api/admin/traffic] fatal: {e}")
        return jsonify({'error': 'Failed to fetch Cloudflare analytics', 'detail': str(e)}), 502


@app.route('/api/users/<username>/comments')
def get_user_comments(username):
    """Get comments authored by a user, with pagination."""
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 20, type=int), 50)
    offset = (page - 1) * limit
    
    profile = get_user_profile_by_username(username)
    if not profile:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        comment_result = supabase.table('comments') \
            .select('id, content, created_at, like_count, dislike_count, post_id') \
            .eq('user_id', profile['id']) \
            .is_('deleted_at', 'null') \
            .order('created_at', desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()
        
        comments = comment_result.data or []
        post_ids = list({c['post_id'] for c in comments if c.get('post_id')})
        
        posts_map = {}
        if post_ids:
            posts_res = supabase.table('posts') \
                .select('id, title') \
                .in_('id', post_ids) \
                .execute()
            posts_map = {p['id']: p for p in (posts_res.data or [])}
        
        # Fetch current user's votes for these comments (if logged in)
        access_token = session.get('supabase_access_token')
        user_votes = {}
        if access_token:
            user = get_user_from_token(access_token)
            if user:
                comment_ids = [c['id'] for c in comments]
                if comment_ids:
                    votes_result = supabase.table('comment_votes') \
                        .select('comment_id, vote_type') \
                        .eq('user_id', user['id']) \
                        .in_('comment_id', comment_ids) \
                        .execute()
                    user_votes = {v['comment_id']: v['vote_type'] for v in (votes_result.data or [])}
        
        formatted_comments = []
        for comment in comments:
            post = posts_map.get(comment.get('post_id')) or {}
            formatted_comments.append({
                'id': comment['id'],
                'content': comment['content'],
                'created_at': comment['created_at'],
                'like_count': comment.get('like_count', 0),
                'dislike_count': comment.get('dislike_count', 0),
                'post': {
                    'id': comment.get('post_id'),
                    'title': post.get('title')
                },
                'author': {
                    'id': profile['id'],
                    'username': profile.get('username'),
                    'display_name': profile.get('display_name'),
                    'avatar_url': profile.get('avatar_url')
                },
                'user_vote': user_votes.get(comment['id'])
            })
        
        return jsonify({
            'success': True,
            'comments': formatted_comments,
            'page': page,
            'limit': limit,
            'has_more': len(comments) == limit
        })
    except Exception as e:
        print(f"Error fetching user comments: {e}")
        return jsonify({'error': 'Failed to fetch comments'}), 500


@app.route('/api/mod/users/<user_id>/ban', methods=['POST'])
@require_auth
def ban_user(user_id):
    """Ban a user via Supabase admin API."""
    user = request.user
    if not is_moderator(user):
        return jsonify({'error': 'Moderator access required'}), 403
    data = request.json or {}
    reason = (data.get('reason') or 'Not provided').strip()

    try:
        # Request body can include {"reason": "..."} but is optional
        payload = {'ban_duration': '8760h'}  # 1 year ban; adjust as needed
        ban_api_ok = False
        try:
            res = requests.patch(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={
                    'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
                    'apikey': SUPABASE_ANON_KEY,
                    'Content-Type': 'application/json'
                },
                json=payload,
                timeout=10
            )
            ban_api_ok = res.status_code < 400
            if not ban_api_ok:
                print(f"Ban API failed: {res.status_code} {res.text}")
        except Exception as e:
            print(f"Ban API exception: {e}")

        # Mark banned in our DB regardless to enforce app-level ban
        try:
            supabase.table('usernames').update({'banned': True}).eq('user_id', user_id).execute()
        except Exception as e:
            print(f"Could not mark user as banned in usernames table: {e}")

        LOCAL_BANNED_IDS.add(user_id)
        save_banned_ids(LOCAL_BANNED_IDS)

        actor_username = get_username_from_db(user.get('id')) or user.get('email')
        target_username = get_username_from_db(user_id)
        deleted_count = soft_delete_posts_for_user(
            target_user_id=user_id,
            actor_id=user.get('id'),
            actor_username=actor_username,
            reason=f"User banned: {reason}"
        )
        append_action_log({
            'type': 'ban_user',
            'timestamp': datetime.utcnow().isoformat(),
            'target_user_id': user_id,
            'target_username': target_username,
            'reason': reason,
            'actor_id': user.get('id'),
            'actor_username': actor_username,
            'ban_api': ban_api_ok,
            'posts_deleted': deleted_count
        })

        return jsonify({'success': True, 'ban_api': ban_api_ok, 'posts_deleted': deleted_count})
    except Exception as e:
        print(f"Error banning user: {e}")
        return jsonify({'error': 'Failed to ban user'}), 500


@app.route('/api/mod/users/<user_id>/unban', methods=['POST'])
@require_auth
def unban_user(user_id):
    """Unban a user (app-level) by removing from local bans and clearing DB flag if present."""
    user = request.user
    if not is_moderator(user):
        return jsonify({'error': 'Moderator access required'}), 403
    data = request.json or {}
    reason = (data.get('reason') or 'Not provided').strip()
    try:
        LOCAL_BANNED_IDS.discard(user_id)
        save_banned_ids(LOCAL_BANNED_IDS)
        try:
            supabase.table('usernames').update({'banned': False}).eq('user_id', user_id).execute()
        except Exception as e:
            print(f"Could not clear banned flag in DB: {e}")

        actor_username = get_username_from_db(user.get('id')) or user.get('email')
        target_username = get_username_from_db(user_id)
        append_action_log({
            'type': 'unban_user',
            'timestamp': datetime.utcnow().isoformat(),
            'target_user_id': user_id,
            'target_username': target_username,
            'reason': reason,
            'actor_id': user.get('id'),
            'actor_username': actor_username
        })
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error unbanning user: {e}")
        return jsonify({'error': 'Failed to unban user'}), 500


@app.route('/api/posts/<post_id>', methods=['GET'])
def get_post(post_id):
    """Get a single post by ID."""
    try:
        result = supabase.table('posts') \
            .select('*, usernames!inner(username, display_name, avatar_url), post_images(id, image_path, display_order), post_tags(tags(id, name))') \
            .eq('id', post_id) \
            .is_('deleted_at', 'null') \
            .single() \
            .execute()
        
        post = result.data
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        author_data = post.get('usernames') or {}
        avatar_url = None
        if author_data.get('avatar_url'):
            avatar_url = supabase.storage.from_('avatars').get_public_url(author_data['avatar_url'])
        
        images = []
        for img in sorted(post.get('post_images', []), key=lambda x: x.get('display_order', 0)):
            img_url = supabase.storage.from_('post-images').get_public_url(img['image_path'])
            images.append({'id': img['id'], 'url': img_url})
        
        tags = [pt.get('tags', {}).get('name') for pt in post.get('post_tags', []) if pt.get('tags')]
        
        user_vote = None
        user_reposted = False
        access_token = session.get('supabase_access_token')
        if access_token:
            user = get_user_from_token(access_token)
            if user:
                vote_result = supabase.table('post_votes') \
                    .select('vote_type') \
                    .eq('user_id', user['id']) \
                    .eq('post_id', post_id) \
                    .execute()
                if vote_result.data:
                    user_vote = vote_result.data[0]['vote_type']
                repost_target_id = post.get('original_post_id') or post_id
                repost_result = supabase.table('reposts') \
                    .select('original_post_id') \
                    .eq('user_id', user['id']) \
                    .eq('original_post_id', repost_target_id) \
                    .execute()
                user_reposted = bool(repost_result.data)
        
        formatted_post = {
            'id': post['id'],
            'title': post.get('title'),
            'content': post['content'],
            'created_at': post['created_at'],
            'like_count': post.get('like_count', 0),
            'dislike_count': post.get('dislike_count', 0),
            'comment_count': post.get('comment_count', 0),
            'repost_count': post.get('repost_count', 0),
            'is_repost': post.get('is_repost', False),
            'original_post_id': post.get('original_post_id'),
            'author': {
                'id': post['user_id'],
                'username': author_data.get('username') or author_data.get('display_name'),
                'display_name': author_data.get('display_name'),
                'avatar_url': avatar_url
            },
            'images': images,
            'tags': tags,
            'user_vote': user_vote,
            'user_reposted': user_reposted
        }
        
        return jsonify({'success': True, 'post': formatted_post})
    except Exception as e:
        print(f"Error fetching post: {e}")
        return jsonify({'error': 'Failed to fetch post'}), 500


@app.route('/api/posts', methods=['POST'])
@require_auth
def create_post():
    """Create a new post."""
    user = request.user
    user_id = user['id']
    
    if request.content_type and 'multipart/form-data' in request.content_type:
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        tags_raw = request.form.get('tags', '')
        images = request.files.getlist('images')
    else:
        data = request.json or {}
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        tags_raw = data.get('tags', '')
        images = []
    
    if title and len(title) > MAX_TITLE_LENGTH:
        return jsonify({'error': f'Title must be {MAX_TITLE_LENGTH} characters or less'}), 400
    
    valid, error = validate_post_content(content)
    if not valid:
        return jsonify({'error': error}), 400
    
    content = sanitize_content(content)
    title = sanitize_content(title) if title else None
    
    tags = []
    if tags_raw:
        if isinstance(tags_raw, str):
            tags_raw = [t.strip() for t in tags_raw.split(',')]
        for tag in tags_raw[:MAX_TAGS_PER_POST]:
            sanitized = sanitize_tag(tag)
            if sanitized and sanitized not in tags:
                tags.append(sanitized)
    
    try:
        post_result = supabase.table('posts').insert({
            'user_id': user_id,
            'title': title,
            'content': content
        }).execute()
        
        post = post_result.data[0]
        post_id = post['id']
        
        uploaded_images = []
        if images:
            for i, image_file in enumerate(images[:MAX_IMAGES_PER_POST]):
                if image_file and image_file.filename:
                    if not image_file.content_type.startswith('image/'):
                        continue
                    ext = os.path.splitext(image_file.filename)[1] or '.jpg'
                    filename = f"{post_id}/{uuid.uuid4()}{ext}"
                    content_bytes = image_file.read()
                    supabase.storage.from_('post-images').upload(
                        filename, content_bytes,
                        {'content-type': image_file.content_type}
                    )
                    img_result = supabase.table('post_images').insert({
                        'post_id': post_id,
                        'image_path': filename,
                        'display_order': i
                    }).execute()
                    uploaded_images.append({
                        'id': img_result.data[0]['id'],
                        'url': supabase.storage.from_('post-images').get_public_url(filename)
                    })
        
        saved_tags = []
        for tag_name in tags:
            tag_result = supabase.table('tags') \
                .select('id, name') \
                .eq('name', tag_name) \
                .execute()
            if tag_result.data:
                tag_id = tag_result.data[0]['id']
            else:
                new_tag = supabase.table('tags').insert({'name': tag_name}).execute()
                tag_id = new_tag.data[0]['id']
            supabase.table('post_tags').insert({
                'post_id': post_id,
                'tag_id': tag_id
            }).execute()
            saved_tags.append(tag_name)
        
        return jsonify({
            'success': True,
            'post': {
                'id': post_id,
                'title': title,
                'content': content,
                'created_at': post['created_at'],
                'images': uploaded_images,
                'tags': saved_tags
            }
        }), 201
    except Exception as e:
        print(f"Error creating post: {e}")
        return jsonify({'error': 'Failed to create post'}), 500


@app.route('/api/posts/<post_id>', methods=['DELETE'])
@require_auth
def delete_post(post_id):
    """Soft delete a post (only by author)."""
    user = request.user
    user_id = user['id']
    
    existing = supabase.table('posts').select('user_id').eq('id', post_id).single().execute()
    if not existing.data:
        return jsonify({'error': 'Post not found'}), 404
    if existing.data['user_id'] != user_id:
        return jsonify({'error': 'Not authorized to delete this post'}), 403
    
    try:
        supabase.table('posts').update({'deleted_at': datetime.utcnow().isoformat()}).eq('id', post_id).execute()
        cleanup_post_tags(post_id, None)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting post: {e}")
        return jsonify({'error': 'Failed to delete post'}), 500


@app.route('/api/posts/<post_id>/vote', methods=['POST'])
@require_auth
def vote_post(post_id):
    """Vote on a post (like/dislike)."""
    user = request.user
    user_id = user['id']
    data = request.json or {}
    vote_type = data.get('vote_type')
    
    if vote_type not in [1, -1, 0]:
        return jsonify({'error': 'Invalid vote type'}), 400
    
    try:
        if vote_type == 0:
            supabase.table('post_votes').delete().eq('user_id', user_id).eq('post_id', post_id).execute()
        else:
            existing = supabase.table('post_votes').select('vote_type').eq('user_id', user_id).eq('post_id', post_id).execute()
            if existing.data:
                supabase.table('post_votes').update({'vote_type': vote_type}).eq('user_id', user_id).eq('post_id', post_id).execute()
            else:
                supabase.table('post_votes').insert({'user_id': user_id, 'post_id': post_id, 'vote_type': vote_type}).execute()
        
        post = supabase.table('posts').select('like_count, dislike_count').eq('id', post_id).single().execute()
        return jsonify({
            'success': True,
            'like_count': post.data['like_count'],
            'dislike_count': post.data['dislike_count'],
            'user_vote': vote_type if vote_type != 0 else None
        })
    except Exception as e:
        print(f"Error voting on post: {e}")
        return jsonify({'error': 'Failed to vote'}), 500


@app.route('/api/mod/posts/<post_id>/delete', methods=['POST'])
@require_auth
def moderator_delete_post(post_id):
    """Moderator soft-deletes a post (regardless of owner)."""
    user = request.user
    if not is_moderator(user):
        return jsonify({'error': 'Moderator access required'}), 403
    data = request.json or {}
    reason = (data.get('reason') or 'Not provided').strip()

    try:
        existing = supabase.table('posts').select('id, user_id, post_tags(tags(id, name))').eq('id', post_id).single().execute()
        if not existing.data:
            return jsonify({'error': 'Post not found'}), 404

        supabase.table('posts').update({'deleted_at': datetime.utcnow().isoformat()}).eq('id', post_id).execute()

        cleanup_post_tags(post_id, existing.data)

        actor_username = get_username_from_db(user.get('id')) or user.get('email')
        append_action_log({
            'type': 'delete_post',
            'timestamp': datetime.utcnow().isoformat(),
            'post_id': post_id,
            'reason': reason,
            'actor_id': user.get('id'),
            'actor_username': actor_username,
            'target_user_id': existing.data.get('user_id')
        })
        return jsonify({'success': True})
    except Exception as e:
        print(f"Moderator delete failed: {e}")
        return jsonify({'error': 'Failed to delete post'}), 500


@app.route('/api/posts/<post_id>/comments', methods=['GET'])
def get_comments(post_id):
    """Get comments for a post."""
    try:
        result = supabase.table('comments') \
            .select('*, usernames!inner(username, display_name, avatar_url)') \
            .eq('post_id', post_id) \
            .is_('deleted_at', 'null') \
            .is_('parent_comment_id', 'null') \
            .order('created_at', desc=False) \
            .execute()
        
        comments = result.data or []
        user_votes = {}
        access_token = session.get('supabase_access_token')
        if access_token:
            user = get_user_from_token(access_token)
            if user:
                comment_ids = [c['id'] for c in comments]
                if comment_ids:
                    votes_result = supabase.table('comment_votes') \
                        .select('comment_id, vote_type') \
                        .eq('user_id', user['id']) \
                        .in_('comment_id', comment_ids) \
                        .execute()
                    user_votes = {v['comment_id']: v['vote_type'] for v in (votes_result.data or [])}
        
        formatted_comments = []
        for comment in comments:
            author_data = comment.get('usernames') or {}
            avatar_url = None
            if author_data.get('avatar_url'):
                avatar_url = supabase.storage.from_('avatars').get_public_url(author_data['avatar_url'])
            formatted_comments.append({
                'id': comment['id'],
                'content': comment['content'],
                'created_at': comment['created_at'],
                'like_count': comment.get('like_count', 0),
                'dislike_count': comment.get('dislike_count', 0),
                'reply_count': comment.get('reply_count', 0),
                'author': {
                    'id': comment['user_id'],
                    'username': author_data.get('username') or author_data.get('display_name'),
                    'display_name': author_data.get('display_name'),
                    'avatar_url': avatar_url
                },
                'user_vote': user_votes.get(comment['id'])
            })
        return jsonify({'success': True, 'comments': formatted_comments})
    except Exception as e:
        print(f"Error fetching comments: {e}")
        return jsonify({'error': 'Failed to fetch comments'}), 500


@app.route('/api/posts/<post_id>/comments', methods=['POST'])
@require_auth
def create_comment(post_id):
    """Create a comment on a post."""
    user = request.user
    user_id = user['id']
    data = request.json or {}
    content = data.get('content', '').strip()
    parent_comment_id = data.get('parent_comment_id')
    
    if not content:
        return jsonify({'error': 'Comment content is required'}), 400
    if len(content) > MAX_COMMENT_LENGTH:
        return jsonify({'error': f'Comment must be {MAX_COMMENT_LENGTH} characters or less'}), 400
    
    try:
        result = supabase.table('comments').insert({
            'post_id': post_id,
            'user_id': user_id,
            'content': sanitize_content(content),
            'parent_comment_id': parent_comment_id
        }).execute()
        comment = result.data[0]
        
        author_result = supabase.table('usernames').select('username, display_name, avatar_url').eq('user_id', user_id).single().execute()
        author_data = author_result.data or {}
        avatar_url = None
        if author_data.get('avatar_url'):
            avatar_url = supabase.storage.from_('avatars').get_public_url(author_data['avatar_url'])
        
        return jsonify({
            'success': True,
            'comment': {
                'id': comment['id'],
                'content': comment['content'],
                'created_at': comment['created_at'],
                'like_count': 0,
                'dislike_count': 0,
                'reply_count': 0,
                'author': {
                    'id': user_id,
                    'username': author_data.get('username') or author_data.get('display_name'),
                    'display_name': author_data.get('display_name'),
                    'avatar_url': avatar_url
                }
            }
        }), 201
    except Exception as e:
        print(f"Error creating comment: {e}")
        return jsonify({'error': 'Failed to create comment'}), 500


@app.route('/api/comments/<comment_id>/vote', methods=['POST'])
@require_auth
def vote_comment(comment_id):
    """Vote on a comment."""
    user = request.user
    user_id = user['id']
    data = request.json or {}
    vote_type = data.get('vote_type')
    
    if vote_type not in [1, -1, 0]:
        return jsonify({'error': 'Invalid vote type'}), 400
    
    try:
        if vote_type == 0:
            supabase.table('comment_votes').delete().eq('user_id', user_id).eq('comment_id', comment_id).execute()
        else:
            existing = supabase.table('comment_votes').select('vote_type').eq('user_id', user_id).eq('comment_id', comment_id).execute()
            if existing.data:
                supabase.table('comment_votes').update({'vote_type': vote_type}).eq('user_id', user_id).eq('comment_id', comment_id).execute()
            else:
                supabase.table('comment_votes').insert({'user_id': user_id, 'comment_id': comment_id, 'vote_type': vote_type}).execute()
        
        # Recalculate counts in case database triggers are not present
        like_result = supabase.table('comment_votes') \
            .select('vote_type', count='exact', head=True) \
            .eq('comment_id', comment_id) \
            .eq('vote_type', 1) \
            .execute()
        dislike_result = supabase.table('comment_votes') \
            .select('vote_type', count='exact', head=True) \
            .eq('comment_id', comment_id) \
            .eq('vote_type', -1) \
            .execute()

        like_count = like_result.count if like_result.count is not None else len(like_result.data or [])
        dislike_count = dislike_result.count if dislike_result.count is not None else len(dislike_result.data or [])

        # Persist counts so subsequent fetches show updated numbers
        supabase.table('comments') \
            .update({'like_count': like_count, 'dislike_count': dislike_count}) \
            .eq('id', comment_id) \
            .execute()

        return jsonify({
            'success': True,
            'like_count': like_count,
            'dislike_count': dislike_count,
            'user_vote': vote_type if vote_type != 0 else None
        })
    except Exception as e:
        print(f"Error voting on comment: {e}")
        return jsonify({'error': 'Failed to vote'}), 500


@app.route('/api/posts/<post_id>/repost', methods=['POST', 'DELETE'])
@require_auth
def repost(post_id):
    """Repost a post."""
    user = request.user
    user_id = user['id']
    
    try:
        existing = supabase.table('reposts').select('repost_id').eq('user_id', user_id).eq('original_post_id', post_id).execute()
        if request.method == 'DELETE':
            if not existing.data:
                return jsonify({'success': True, 'repost_count': 0})
            repost_ids = [row['repost_id'] for row in existing.data if row.get('repost_id')]
            if repost_ids:
                supabase.table('posts').delete().in_('id', repost_ids).execute()
            supabase.table('reposts').delete().eq('user_id', user_id).eq('original_post_id', post_id).execute()
            repost_count_result = supabase.table('reposts') \
                .select('repost_id', count='exact') \
                .eq('original_post_id', post_id) \
                .execute()
            repost_count = repost_count_result.count
            if repost_count is None:
                repost_count = len(repost_count_result.data or [])
            supabase.table('posts').update({'repost_count': repost_count}).eq('id', post_id).execute()
            return jsonify({'success': True, 'repost_count': repost_count})

        if existing.data:
            return jsonify({'error': 'You have already reposted this'}), 409
        
        original = supabase.table('posts').select('*').eq('id', post_id).is_('deleted_at', 'null').single().execute()
        if not original.data:
            return jsonify({'error': 'Original post not found'}), 404
        
        repost_result = supabase.table('posts').insert({
            'user_id': user_id,
            'title': original.data.get('title'),
            'content': original.data['content'],
            'is_repost': True,
            'original_post_id': post_id
        }).execute()
        repost_post = repost_result.data[0]
        
        supabase.table('reposts').insert({
            'user_id': user_id,
            'original_post_id': post_id,
            'repost_id': repost_post['id']
        }).execute()

        repost_count_result = supabase.table('reposts') \
            .select('repost_id', count='exact') \
            .eq('original_post_id', post_id) \
            .execute()
        repost_count = repost_count_result.count
        if repost_count is None:
            repost_count = len(repost_count_result.data or [])
        supabase.table('posts') \
            .update({'repost_count': repost_count}) \
            .eq('id', post_id) \
            .execute()
        
        return jsonify({'success': True, 'repost_id': repost_post['id'], 'repost_count': repost_count}), 201
    except Exception as e:
        print(f"Error reposting: {e}")
        return jsonify({'error': 'Failed to repost'}), 500


@app.route('/api/tags', methods=['GET'])
def get_tags():
    """Get popular tags."""
    limit = min(request.args.get('limit', 20, type=int), 50)
    try:
        result = supabase.table('tags') \
            .select('id, name, post_count') \
            .gt('post_count', 0) \
            .order('post_count', desc=True) \
            .limit(limit) \
            .execute()
        tags = [t for t in (result.data or []) if (t.get('post_count') or 0) > 0]
        return jsonify({'success': True, 'tags': tags})
    except Exception as e:
        print(f"Error fetching tags: {e}")
        return jsonify({'error': 'Failed to fetch tags'}), 500


@app.route('/api/price-history/<ticker>')
def price_history(ticker):
    """Return historical closing prices for a ticker for charting.
    
    Supports:
    - range: 1d, 5d, 1m, 6m, ytd, 1y, 5y, max
    - before: ISO date string to fetch data before this date (for infinite scroll)
    - count: number of data points to fetch when using 'before'
    """
    import yfinance as yf
    from datetime import datetime, timedelta
    
    range_key = request.args.get('range', '6m')
    before_date = request.args.get('before')  # For infinite scroll
    count = request.args.get('count', 100, type=int)
    ticker = (ticker or '').upper().strip()
    
    if not ticker:
        return jsonify({'error': 'Ticker required'}), 400

    try:
        # Determine if this is intraday data (needs Unix timestamps)
        is_intraday = range_key in ('1d', '5d')
        
        # If 'before' is specified, we're doing infinite scroll
        if before_date:
            try:
                end_dt = datetime.fromisoformat(before_date.replace('Z', '+00:00').split('T')[0])
                # Fetch a generous window before the visible edge so horizontal
                # panning can populate history in one smooth prepend instead
                # of many small, jumpy fetches.
                lookback_days = max(220, min(3650, count * 3))
                start_dt = end_dt - timedelta(days=lookback_days)
                
                df = yf.download(
                    ticker, 
                    start=start_dt.strftime('%Y-%m-%d'),
                    end=end_dt.strftime('%Y-%m-%d'),
                    progress=False, 
                    interval='1d'
                )
                
                if df is None or df.empty:
                    return jsonify({'success': True, 'prices': []})
                
                df = df.tail(count).sort_index()
                is_intraday = False  # Infinite scroll always uses daily data
                
            except Exception as e:
                print(f"Error parsing before date: {e}")
                return jsonify({'error': 'Invalid before date'}), 400
        else:
            # Normal range-based query
            period = None
            start = None
            interval = '1d'
            
            if range_key == '1d':
                period = '5d'
                interval = '15m'  # Changed to 15m for better granularity
            elif range_key == '5d':
                period = '10d'
                interval = '30m'  # Changed to 30m
            elif range_key == '1m':
                period = '1mo'
                interval = '1d'
            elif range_key == '6m':
                period = '6mo'
                interval = '1d'
            elif range_key == '1y':
                period = '1y'
                interval = '1d'
            elif range_key == '5y':
                period = '5y'
                interval = '1wk'
            elif range_key == 'max':
                period = 'max'
                interval = '1wk'
            elif range_key == 'ytd':
                start = datetime(datetime.utcnow().year, 1, 1)
            else:
                period = '6mo'

            if start:
                df = yf.download(ticker, start=start, progress=False, interval=interval)
            else:
                df = yf.download(ticker, period=period, progress=False, interval=interval)

            if df is None or df.empty:
                return jsonify({'error': 'No data found'}), 404

            df = df.tail(400).sort_index()

        # yfinance returns MultiIndex columns like ('Close', 'AAPL') even for a
        # single ticker — flatten to just 'Close' so row['Close'] is a scalar.
        if getattr(df.columns, 'nlevels', 1) > 1:
            df.columns = df.columns.get_level_values(0)

        prices = []
        for ts, row in df.iterrows():
            try:
                dt = ts.to_pydatetime()
            except Exception:
                dt = ts
            
            # For intraday data, use Unix timestamp
            # For daily data, use ISO date string (YYYY-MM-DD)
            if is_intraday:
                # Convert to Unix timestamp (seconds since epoch)
                timestamp = int(dt.timestamp())
                prices.append({
                    'date': timestamp,  # Unix timestamp for intraday
                    'close': float(row['Close']),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'volume': float(row.get('Volume', 0))
                })
            else:
                prices.append({
                    'date': dt.date().isoformat(),  # YYYY-MM-DD for daily
                    'close': float(row['Close']),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'volume': float(row.get('Volume', 0))
                })

        return jsonify({'success': True, 'prices': prices, 'intraday': is_intraday})
        
    except Exception as e:
        print(f"Price history error for {ticker}: {e}")
        return jsonify({'error': 'Failed to fetch price history', 'detail': f'{type(e).__name__}: {e}'}), 500
@app.route('/api/mod/logs')
@require_auth
def get_mod_logs():
    user = request.user
    if not (is_moderator(user) or is_admin(user)):
        return jsonify({'error': 'Moderator or admin access required'}), 403
    limit = min(request.args.get('limit', 50, type=int), 200)
    logs = load_action_logs()
    return jsonify({'success': True, 'logs': list(reversed(logs[-limit:]))})


# Community page routes (was /blog — kept as redirects below for back-compat)
@app.route('/community')
@require_auth_page
def community_feed():
    return render_template('blog.html')

@app.route('/community/new')
@require_auth_page
def new_post_page():
    return render_template('blog_new.html')

@app.route('/community/post/<post_id>')
@require_auth_page
def view_post_page(post_id):
    return render_template('blog_post.html', post_id=post_id)

@app.route('/community/tag/<tag>')
@require_auth_page
def tag_posts_page(tag):
    return render_template('blog.html')

@app.route('/community/user/<username>')
@require_auth_page
def user_posts_page(username):
    return render_template('blog.html')

# Backwards-compat: redirect old /blog/* URLs to /community/*.
@app.route('/blog')
def blog_redirect_root():
    return redirect('/community', code=301)

@app.route('/blog/<path:rest>')
def blog_redirect(rest):
    return redirect(f'/community/{rest}', code=301)

@app.route('/admin')
@require_auth_page
def admin_dashboard():
    if not is_admin(request.user):
        return redirect('/')
    if request.host.split(':', 1)[0].lower().endswith('vsnanalysis.com'):
        return redirect('https://admin.vsnanalysis.com/', code=301)
    return render_template('admin_dashboard.html')

@app.route('/moderator')
@require_auth_page
def moderator_dashboard():
    if not is_moderator(request.user):
        return redirect('/')
    return render_template('moderator_dashboard.html')


# ============================================
# MAIN
# ============================================
def _prewarm_caches():
    """Background warm-up so the first user request to /api/search-tickers
    doesn't pay the Yahoo round-trip. Re-runs periodically so the cache
    never expires for a logged-in user mid-session."""
    while True:
        try:
            _fetch_most_active(limit=200)
        except Exception as e:
            print(f"prewarm failed: {e}")
        # Refresh slightly before the TTL expires
        time.sleep(max(60, _VOLUME_CACHE_TTL - 30))


import threading as _threading
_threading.Thread(target=_prewarm_caches, daemon=True).start()


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
