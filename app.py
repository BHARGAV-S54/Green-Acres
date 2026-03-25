import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from functools import wraps

import jwt
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, jsonify)
import mysql.connector
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Firebase Admin SDK (optional - only if service account file exists)
firebase_initialized = False
try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth
    firebase_cred_path = os.environ.get('FIREBASE_CREDENTIALS', 'firebase-service-account.json')
    if os.path.exists(firebase_cred_path):
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred)
        firebase_initialized = True
        print('[Firebase] Initialized successfully')
except Exception as e:
    print(f'[Firebase] Not initialized: {e}')

# ──────────────────────────────────────────────
#  App Config
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('AGRICONNECT_SECRET', 'agri-jwt-secret-2024-change-me')

SECRET_KEY    = app.secret_key
JWT_ALGORITHM = 'HS256'
JWT_EXP_HOURS = 24          # token lives for 24 hours
COOKIE_NAME   = 'ac_token'  # HTTP-only cookie name

# ──────────────────────────────────────────────
#  OAuth Configuration
# ──────────────────────────────────────────────
oauth = OAuth(app)

# Google OAuth
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# GitHub OAuth
github = oauth.register(
    name='github',
    client_id=os.environ.get('GITHUB_CLIENT_ID'),
    client_secret=os.environ.get('GITHUB_CLIENT_SECRET'),
    authorize_url='https://github.com/login/oauth/authorize',
    access_token_url='https://github.com/login/oauth/access_token',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'}
)

# ──────────────────────────────────────────────
#  Database helpers
# ──────────────────────────────────────────────
DB_CONFIG = {
    'host':     '127.0.0.1',
    'user':     'root',
    'password': '',
    'database': 'agriconnect_db',
    'charset':  'utf8mb4',
}

def get_db():
    """Return a new MySQL connection, or None if unavailable."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f'[DB] Connection error: {e}')
        return None

def query(sql, params=(), one=False):
    """Execute a SELECT and return dict rows."""
    conn = get_db()
    if not conn:
        return None if one else []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()
    except Exception as e:
        print(f'[DB] Query error: {e}')
        return None if one else []
    finally:
        conn.close()

def execute(sql, params=()):
    """Execute INSERT/UPDATE/DELETE; return lastrowid or -1 on error."""
    conn = get_db()
    if not conn:
        return -1
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    except mysql.connector.IntegrityError as e:
        print(f'[DB] Integrity error: {e}')
        return -2          # unique constraint violation
    except Exception as e:
        print(f'[DB] Execute error: {e}')
        return -1
    finally:
        conn.close()

# ──────────────────────────────────────────────
#  Password helpers  (SHA-256, works with no extras)
# ──────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()

def check_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed

# ──────────────────────────────────────────────
#  JWT helpers
# ──────────────────────────────────────────────
def create_token(user_id: int, username: str) -> str:
    payload = {
        'sub':  user_id,
        'user': username,
        'jti':  str(uuid.uuid4()),
        'iat':  datetime.now(timezone.utc),
        'exp':  datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str):
    """Return decoded payload or None."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    """Read JWT from cookie and return user dict, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    # Check if token has been revoked (logout)
    is_revoked = query(
        'SELECT 1 FROM revoked_tokens WHERE jti=%s', (payload['jti'],), one=True
    )
    if is_revoked:
        return None
    user = query('SELECT * FROM users WHERE id=%s AND is_active=1',
                 (payload['sub'],), one=True)
    return user

# ──────────────────────────────────────────────
#  Auth decorator
# ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('login_page'))
        return f(*args, user=user, **kwargs)
    return decorated

# ──────────────────────────────────────────────
#  Fallback data  (used when DB is unavailable)
# ──────────────────────────────────────────────
DEMO_USER = {
    'id': 0, 'full_name': 'Demo Farmer', 'username': 'demo',
    'email': 'demo@agriconnect.in',
    'title': 'Organic Farmer & Agri-Tech Enthusiast',
    'location': 'Andhra Pradesh, India', 'connections': 342,
    'avatar_url': 'https://ui-avatars.com/api/?name=D+F&background=1b873f&color=fff&rounded=true',
}

DEMO_POSTS = [
    {'author_name': 'Rajesh Kumar', 'author_title': 'Traditional Wheat Farmer',
     'time_ago': '2 hours ago',
     'content': 'Just finished testing the new drip irrigation system on the north field. The water savings are incredible! 🌾💧',
     'likes': 124, 'comments': 18,
     'avatar_url': 'https://ui-avatars.com/api/?name=RK&background=d4edda&color=1b5e20&rounded=true'},
    {'author_name': 'Priya Verma', 'author_title': 'Organic Vegetable Grower',
     'time_ago': '5 hours ago',
     'content': 'Started using neem oil spray instead of chemical pesticides. Pests are down 70%! 🌿✨',
     'likes': 89, 'comments': 12,
     'avatar_url': 'https://ui-avatars.com/api/?name=PV&background=fff3e0&color=e65100&rounded=true'},
]

DEMO_FRIENDS = [
    {'id': 2, 'name': 'Rajesh Kumar',  'title': 'Traditional Wheat Farmer',
     'avatar_url': 'https://ui-avatars.com/api/?name=RK&background=d4edda&color=1b5e20&rounded=true'},
    {'id': 3, 'name': 'Priya Verma',   'title': 'Organic Vegetable Grower',
     'avatar_url': 'https://ui-avatars.com/api/?name=PV&background=fff3e0&color=e65100&rounded=true'},
    {'id': 4, 'name': 'Amjad Khan',    'title': 'Paddy & Rice Specialist',
     'avatar_url': 'https://ui-avatars.com/api/?name=AK&background=e8f5e9&color=2e7d32&rounded=true'},
    {'id': 5, 'name': 'Sunita Devi',   'title': 'Dairy & Cattle Farmer',
     'avatar_url': 'https://ui-avatars.com/api/?name=SD&background=fce4ec&color=880e4f&rounded=true'},
    {'id': 6, 'name': 'Vikram Singh',  'title': 'Sugarcane Grower',
     'avatar_url': 'https://ui-avatars.com/api/?name=VS&background=e3f2fd&color=1565c0&rounded=true'},
]

DEMO_SUGGESTIONS = [
    {'name': 'Kiran Bhat',   'title': 'Coconut Farmer, Kerala',
     'avatar_url': 'https://ui-avatars.com/api/?name=KB&background=e8f5e9&color=1b5e20&rounded=true'},
    {'name': 'Mohan Das',    'title': 'Basmati Rice Grower, UP',
     'avatar_url': 'https://ui-avatars.com/api/?name=MD&background=fff8e1&color=f57f17&rounded=true'},
    {'name': 'Shalini Patel','title': 'Spice Farmer, Gujarat',
     'avatar_url': 'https://ui-avatars.com/api/?name=SP&background=fce4ec&color=c62828&rounded=true'},
]

def normalise_user(u: dict) -> dict:
    """Ensure avatar_url is always set."""
    if not u.get('avatar_url'):
        u['avatar_url'] = (
            f"https://ui-avatars.com/api/?name="
            f"{(u.get('full_name') or 'U')[0]}&background=1b873f&color=fff&rounded=true"
        )
    return u

def load_posts_db():
    rows = query('''
        SELECT p.*, u.full_name AS author_name, u.title AS author_title,
               u.avatar_url, p.created_at
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 20
    ''')
    if not rows:
        return DEMO_POSTS
    for p in rows:
        p['time_ago'] = '2 hours ago'
        if not p.get('avatar_url'):
            p['avatar_url'] = f"https://ui-avatars.com/api/?name={p['author_name'][0]}&background=random&rounded=true"
    return rows

# ══════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════

@app.route('/login', methods=['GET'])
def login_page():
    if get_current_user():
        return redirect('/')
    return render_template('login.html', error=None)

@app.route('/login', methods=['POST'])
def login_post():
    email_or_user = request.form.get('email', '').strip()
    password      = request.form.get('password', '')

    if not email_or_user or not password:
        return render_template('login.html', error='Please fill in all fields.')

    # Try finding user by email or username
    user = query(
        'SELECT * FROM users WHERE (email=%s OR username=%s) AND is_active=1',
        (email_or_user, email_or_user), one=True
    )

    # No DB → accept demo credentials for dev
    if user is None:
        if email_or_user in ('demo@agriconnect.in', 'demo_farmer') and password == 'farmer123':
            user = DEMO_USER.copy()
            token = create_token(0, 'demo_farmer')
            resp = make_response(redirect('/'))
            resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600)
            return resp
        return render_template('login.html', error='Invalid credentials.')

    if not check_password(password, user['password_hash']):
        return render_template('login.html', error='Invalid email or password.')

    # Update last_login
    execute('UPDATE users SET last_login=%s WHERE id=%s',
            (datetime.now(), user['id']))

    token = create_token(user['id'], user['username'])
    resp = make_response(redirect('/'))
    resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite='Lax')
    return resp


@app.route('/register', methods=['GET'])
def register_page():
    if get_current_user():
        return redirect('/')
    return render_template('register.html', error=None)

@app.route('/register', methods=['POST'])
def register_post():
    full_name  = request.form.get('full_name', '').strip()
    username   = request.form.get('username',  '').strip().lower()
    email      = request.form.get('email',     '').strip().lower()
    title      = request.form.get('title',     '').strip()
    location   = request.form.get('location',  '').strip()
    password   = request.form.get('password',  '')
    confirm_pw = request.form.get('confirm_password', '')

    if not all([full_name, username, email, password]):
        return render_template('register.html', error='Please fill in all required fields.')
    if len(password) < 6:
        return render_template('register.html', error='Password must be at least 6 characters.')
    if password != confirm_pw:
        return render_template('register.html', error='Passwords do not match.')

    avatar_url = (
        f"https://ui-avatars.com/api/?name={full_name.replace(' ', '+')}"
        f"&background=1b873f&color=fff&rounded=true"
    )
    pw_hash = hash_password(password)

    result = execute(
        '''INSERT INTO users
           (full_name, username, email, password_hash, title, location, avatar_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
        (full_name, username, email, pw_hash, title, location, avatar_url)
    )

    if result == -2:
        return render_template('register.html', error='Email or username already registered.')
    if result < 0:
        # DB not ready – still issue a token for demo purposes
        token = create_token(0, username)
        resp = make_response(redirect('/'))
        resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600)
        return resp

    token = create_token(result, username)
    resp = make_response(redirect('/'))
    resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite='Lax')
    return resp


@app.route('/logout')
def logout():
    """Revoke token and clear cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_token(token)
        if payload:
            execute('INSERT IGNORE INTO revoked_tokens (jti) VALUES (%s)',
                    (payload['jti'],))
    resp = make_response(redirect('/login'))
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ══════════════════════════════════════════════
#  OAUTH ROUTES
# ══════════════════════════════════════════════

def find_or_create_oauth_user(provider, oauth_id, email, full_name, avatar_url=None):
    """Find existing user by OAuth credentials or create a new one."""
    # First, try to find by OAuth provider + ID
    user = query(
        'SELECT * FROM users WHERE oauth_provider=%s AND oauth_id=%s AND is_active=1',
        (provider, oauth_id), one=True
    )
    if user:
        return user

    # Check if user exists with same email (link accounts)
    if email:
        user = query('SELECT * FROM users WHERE email=%s AND is_active=1', (email,), one=True)
        if user:
            # Update existing user with OAuth info
            execute('UPDATE users SET oauth_provider=%s, oauth_id=%s WHERE id=%s',
                    (provider, oauth_id, user['id']))
            return user

    # Create new user
    username = email.split('@')[0] if email else f'{provider}_{oauth_id[:8]}'
    # Ensure username is unique
    base_username = username
    counter = 1
    while query('SELECT 1 FROM users WHERE username=%s', (username,), one=True):
        username = f'{base_username}_{counter}'
        counter += 1

    default_avatar = avatar_url or f"https://ui-avatars.com/api/?name={full_name.replace(' ', '+')}&background=1b873f&color=fff&rounded=true"

    result = execute(
        '''INSERT INTO users (full_name, username, email, oauth_provider, oauth_id, avatar_url)
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (full_name, username, email, provider, oauth_id, default_avatar)
    )

    if result > 0:
        return query('SELECT * FROM users WHERE id=%s', (result,), one=True)
    return None


# ── Google OAuth ────────────────────────────────

@app.route('/auth/google')
def auth_google():
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        return render_template('login.html', error='Google OAuth not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.')
    redirect_uri = url_for('auth_google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def auth_google_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            return render_template('login.html', error='Failed to get user info from Google.')

        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0] if email else 'Google User')
        google_id = user_info.get('sub')
        picture = user_info.get('picture')

        user = find_or_create_oauth_user('google', google_id, email, name, picture)
        if not user:
            return render_template('login.html', error='Failed to create account. Please try again.')

        # Update last login
        execute('UPDATE users SET last_login=%s WHERE id=%s', (datetime.now(), user['id']))

        # Issue JWT and redirect
        jwt_token = create_token(user['id'], user['username'])
        resp = make_response(redirect('/'))
        resp.set_cookie(COOKIE_NAME, jwt_token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite='Lax')
        return resp

    except Exception as e:
        print(f'[Google OAuth] Error: {e}')
        return render_template('login.html', error='Google authentication failed. Please try again.')


# ── GitHub OAuth ────────────────────────────────

@app.route('/auth/github')
def auth_github():
    if not os.environ.get('GITHUB_CLIENT_ID'):
        return render_template('login.html', error='GitHub OAuth not configured. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.')
    redirect_uri = url_for('auth_github_callback', _external=True)
    return github.authorize_redirect(redirect_uri)


@app.route('/auth/github/callback')
def auth_github_callback():
    try:
        token = github.authorize_access_token()
        resp = github.get('user', token=token)
        user_info = resp.json()

        github_id = str(user_info.get('id'))
        name = user_info.get('name') or user_info.get('login')
        email = user_info.get('email')
        avatar = user_info.get('avatar_url')

        # If email is private, try to fetch from emails endpoint
        if not email:
            emails_resp = github.get('user/emails', token=token)
            emails = emails_resp.json()
            for e in emails:
                if e.get('primary') and e.get('verified'):
                    email = e.get('email')
                    break

        user = find_or_create_oauth_user('github', github_id, email, name, avatar)
        if not user:
            return render_template('login.html', error='Failed to create account. Please try again.')

        # Update last login
        execute('UPDATE users SET last_login=%s WHERE id=%s', (datetime.now(), user['id']))

        # Issue JWT and redirect
        jwt_token = create_token(user['id'], user['username'])
        resp = make_response(redirect('/'))
        resp.set_cookie(COOKIE_NAME, jwt_token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite='Lax')
        return resp

    except Exception as e:
        print(f'[GitHub OAuth] Error: {e}')
        return render_template('login.html', error='GitHub authentication failed. Please try again.')


# ── Phone OTP (Firebase) ────────────────────────

@app.route('/auth/phone/verify', methods=['POST'])
def auth_phone_verify():
    """Verify Firebase ID token and create/login user."""
    if not firebase_initialized:
        return jsonify({'success': False, 'error': 'Phone authentication not configured.'}), 400

    data = request.get_json()
    id_token = data.get('idToken')

    if not id_token:
        return jsonify({'success': False, 'error': 'No ID token provided.'}), 400

    try:
        decoded = firebase_auth.verify_id_token(id_token)
        phone = decoded.get('phone_number')

        if not phone:
            return jsonify({'success': False, 'error': 'Phone number not found in token.'}), 400

        # Find or create user by phone
        user = query('SELECT * FROM users WHERE phone=%s AND is_active=1', (phone,), one=True)

        if not user:
            # Create new user with phone
            username = f'user_{phone[-4:]}'
            counter = 1
            while query('SELECT 1 FROM users WHERE username=%s', (username,), one=True):
                username = f'user_{phone[-4:]}_{counter}'
                counter += 1

            full_name = f'Farmer {phone[-4:]}'
            avatar_url = f"https://ui-avatars.com/api/?name=F&background=1b873f&color=fff&rounded=true"

            result = execute(
                '''INSERT INTO users (full_name, username, phone, oauth_provider, avatar_url)
                   VALUES (%s, %s, %s, %s, %s)''',
                (full_name, username, phone, 'phone', avatar_url)
            )

            if result > 0:
                user = query('SELECT * FROM users WHERE id=%s', (result,), one=True)
            else:
                return jsonify({'success': False, 'error': 'Failed to create account.'}), 500

        # Update last login
        execute('UPDATE users SET last_login=%s WHERE id=%s', (datetime.now(), user['id']))

        # Issue JWT
        jwt_token = create_token(user['id'], user['username'])

        return jsonify({
            'success': True,
            'token': jwt_token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name']
            }
        })

    except Exception as e:
        print(f'[Phone Auth] Error: {e}')
        return jsonify({'success': False, 'error': 'Phone verification failed.'}), 400


@app.route('/auth/phone/config')
def auth_phone_config():
    """Return Firebase config for frontend (safe to expose)."""
    config = {
        'apiKey': os.environ.get('FIREBASE_API_KEY', ''),
        'authDomain': os.environ.get('FIREBASE_AUTH_DOMAIN', ''),
        'projectId': os.environ.get('FIREBASE_PROJECT_ID', ''),
    }
    return jsonify(config)


# ══════════════════════════════════════════════
#  PROTECTED PAGE ROUTES
# ══════════════════════════════════════════════

@app.route('/')
@login_required
def index(user):
    user = normalise_user(user)
    posts = load_posts_db()
    return render_template('index.html', user=user, posts=posts, suggestions=DEMO_SUGGESTIONS)


@app.route('/network')
@login_required
def network(user):
    user = normalise_user(user)
    # Fetch accepted connections – fallback to demo list
    conn_rows = query(
        '''SELECT u.id, u.full_name AS name, u.title, u.avatar_url
           FROM connections c
           JOIN users u ON (
               CASE WHEN c.requester_id=%s THEN c.receiver_id ELSE c.requester_id END = u.id
           )
           WHERE (c.requester_id=%s OR c.receiver_id=%s) AND c.status='accepted'
           LIMIT 30''',
        (user['id'], user['id'], user['id'])
    )
    friends = conn_rows if conn_rows else DEMO_FRIENDS
    for f in friends:
        if not f.get('avatar_url'):
            f['avatar_url'] = f"https://ui-avatars.com/api/?name={f['name'][0]}&background=random&rounded=true"
    return render_template('network.html', user=user, friends=friends)


@app.route('/market')
@login_required
def market(user):
    user = normalise_user(user)
    return render_template('market.html', user=user)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
