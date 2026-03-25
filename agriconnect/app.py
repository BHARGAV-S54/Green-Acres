import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from functools import wraps

import jwt
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, jsonify)
import mysql.connector

# ──────────────────────────────────────────────
#  App Config
# ──────────────────────────────────────────────
app = Flask(__name__)

SECRET_KEY    = os.environ.get('AGRICONNECT_SECRET', 'agri-jwt-secret-2024-change-me')
JWT_ALGORITHM = 'HS256'
JWT_EXP_HOURS = 24          # token lives for 24 hours
COOKIE_NAME   = 'ac_token'  # HTTP-only cookie name
UPLOAD_FOLDER = 'static/uploads/posts'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ──────────────────────────────────────────────
#  Database helpers
# ──────────────────────────────────────────────
DB_CONFIG = {
    'host':     '127.0.0.1',
    'user':     'root',
    'password': 'root',
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
        
    # If using the demo farmer login fallback (id=0), return the fallback user directly 
    # so authentication works even if the DB is uninitialized.
    if payload.get('sub') == 0:
        return DEMO_USER.copy()
        
    # Check if token has been revoked (logout)
    try:
        is_revoked = query(
            'SELECT 1 FROM revoked_tokens WHERE jti=%s', (payload['jti'],), one=True
        )
        if is_revoked:
            return None
        user = query('SELECT * FROM users WHERE id=%s AND is_active=1',
                     (payload['sub'],), one=True)
        return user
    except Exception:
        # Fallback to demo user if DB query crashes entirely
        return None

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
    return render_template('auth.html', mode='login', error=None)

@app.route('/login', methods=['POST'])
def login_post():
    email_or_user = request.form.get('email', '').strip()
    password      = request.form.get('password', '')

    if not email_or_user or not password:
        return render_template('auth.html', mode='login', error='Please fill in all fields.')

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
        return render_template('auth.html', mode='login', error='Invalid credentials.')

    if not check_password(password, user['password_hash']):
        return render_template('auth.html', mode='login', error='Invalid email or password.')

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
    return render_template('auth.html', mode='register', error=None)

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
        return render_template('auth.html', mode='register', error='Please fill in all required fields.')
    if len(password) < 6:
        return render_template('auth.html', mode='register', error='Password must be at least 6 characters.')
    if password != confirm_pw:
        return render_template('auth.html', mode='register', error='Passwords do not match.')

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
        return render_template('auth.html', mode='register', error='Email or username already registered.')
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
#  PROTECTED PAGE ROUTES
# ══════════════════════════════════════════════

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit(user):
    user = normalise_user(user)

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        title     = request.form.get('title', '').strip()
        location  = request.form.get('location', '').strip()
        bio       = request.form.get('bio', '').strip()

        if not full_name:
            return render_template('edit_profile.html', user=user, error="Full Name is required.")

        # Update the database
        res = execute(
            'UPDATE users SET full_name=%s, title=%s, location=%s, bio=%s WHERE id=%s',
            (full_name, title, location, bio, user['id'])
        )

        if res >= 0:
            # Re-fetch user to reflect changes immediately
            updated_user = query('SELECT * FROM users WHERE id=%s', (user['id'],), one=True)
            if updated_user:
                user = normalise_user(updated_user)
            return render_template('edit_profile.html', user=user, msg="Profile updated successfully!")
        else:
            return render_template('edit_profile.html', user=user, error="Failed to update profile. Are you using the demo account without a database?")

    return render_template('edit_profile.html', user=user)

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
    
    # 1. Fetch accepted friends
    conn_rows = query(
        '''SELECT u.id, u.full_name AS name, u.title, u.avatar_url
           FROM connections c
           JOIN users u ON (
               CASE WHEN c.requester_id=%s THEN c.receiver_id ELSE c.requester_id END = u.id
           )
           WHERE (c.requester_id=%s OR c.receiver_id=%s) AND c.status='accepted'
           LIMIT 50''',
        (user['id'], user['id'], user['id'])
    )
    friends = conn_rows if conn_rows else (DEMO_FRIENDS if user['id'] == 0 else [])
    
    # 2. Fetch suggestions (Users not connected and not themselves)
    sug_rows = query(
        '''SELECT id, full_name AS name, title, avatar_url
           FROM users
           WHERE id != %s
           AND id NOT IN (
               SELECT receiver_id FROM connections WHERE requester_id = %s
               UNION
               SELECT requester_id FROM connections WHERE receiver_id = %s
           )
           LIMIT 20''',
        (user['id'], user['id'], user['id'])
    )
    suggestions = sug_rows if sug_rows else (DEMO_SUGGESTIONS if user['id'] == 0 else [])

    # Unified avatar processing
    for person in (friends + suggestions):
        if not person.get('avatar_url'):
            person['avatar_url'] = f"https://ui-avatars.com/api/?name={person['name'][0]}&background=random&rounded=true"
            
    return render_template('network.html', user=user, friends=friends, suggestions=suggestions)


@app.route('/api/connect/<int:target_id>', methods=['POST'])
@login_required
def api_connect(user, target_id):
    user = normalise_user(user)
    
    # 1. Prevent connecting to self
    if user['id'] == target_id:
        return jsonify({'status': 'error', 'message': 'Cannot connect to yourself'}), 400
    
    # 2. Check if connection already exists
    existing = query(
        'SELECT id FROM connections WHERE (requester_id=%s AND receiver_id=%s) OR (requester_id=%s AND receiver_id=%s)',
        (user['id'], target_id, target_id, user['id']),
        one=True
    )
    if existing:
        return jsonify({'status': 'error', 'message': 'Connection already exists or is pending'}), 400
    
    # 3. Create connection (auto-accepted for demo purposes)
    res = execute(
        'INSERT INTO connections (requester_id, receiver_id, status) VALUES (%s, %s, "accepted")',
        (user['id'], target_id)
    )
    
    if res > 0:
        return jsonify({'status': 'success', 'message': 'Successfully connected!'})
    elif res == -2:
        return jsonify({'status': 'error', 'message': 'Connection already exists'}), 400
    else:
        return jsonify({'status': 'error', 'message': 'Database error. Ensure you have the local MySQL running.'}), 500



@app.route('/api/post/create', methods=['POST'])
@login_required
def api_create_post(user):
    user = normalise_user(user)
    
    # Use request.form for content when sending as FormData
    content = request.form.get('content', '').strip()
    media_file = request.files.get('media')
    
    media_url = ''
    if media_file and media_file.filename:
        # Save file with unique ID
        ext = media_file.filename.split('.')[-1]
        fname = f"{uuid.uuid4()}.{ext}"
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        media_file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        media_url = f"/static/uploads/posts/{fname}"
    
    if not content and not media_url:
        return jsonify({'status': 'error', 'message': 'Post content or media is required'}), 400
        
    res = execute(
        'INSERT INTO posts (user_id, content, media_url) VALUES (%s, %s, %s)',
        (user['id'], content, media_url)
    )
    
    if res > 0:
        new_post = {
            'id': res,
            'author_name': user['full_name'],
            'author_title': user.get('title', 'Farmer'),
            'avatar_url': user.get('avatar_url') or f"https://ui-avatars.com/api/?name={user['full_name'][0]}&background=random",
            'content': content,
            'media_url': media_url,
            'time_ago': 'Just now',
            'likes': 0,
            'comments': 0
        }
        return jsonify({'status': 'success', 'post': new_post})
    else:
        return jsonify({'status': 'error', 'message': 'Database error or demo mode active'}), 500


@app.route('/api/post/like/<int:post_id>', methods=['POST'])
@login_required
def api_like_post(user, post_id):
    user = normalise_user(user)
    
    # Check if liked
    liked = query('SELECT * FROM post_likes WHERE user_id=%s AND post_id=%s', (user['id'], post_id), one=True)
    
    if liked:
        # Unlike
        execute('DELETE FROM post_likes WHERE user_id=%s AND post_id=%s', (user['id'], post_id))
        execute('UPDATE posts SET likes = GREATEST(0, CAST(likes AS SIGNED) - 1) WHERE id=%s', (post_id,))
        is_liked = False
    else:
        # Like
        execute('INSERT IGNORE INTO post_likes (user_id, post_id) VALUES (%s, %s)', (user['id'], post_id))
        execute('UPDATE posts SET likes = likes + 1 WHERE id=%s', (post_id,))
        is_liked = True
        
    new_count = query('SELECT likes FROM posts WHERE id=%s', (post_id,), one=True)
    return jsonify({
        'status': 'success',
        'is_liked': is_liked,
        'likes_count': new_count['likes'] if new_count else 0
    })


@app.route('/api/post/comment/<int:post_id>', methods=['POST'])
@login_required
def api_comment_post(user, post_id):
    user = normalise_user(user)
    content = request.json.get('content', '').strip()
    
    if not content:
        return jsonify({'status': 'error', 'message': 'Comment cannot be empty'}), 400
        
    res = execute(
        'INSERT INTO post_comments (post_id, user_id, content) VALUES (%s, %s, %s)',
        (post_id, user['id'], content)
    )
    
    if res > 0:
        execute('UPDATE posts SET comments = comments + 1 WHERE id=%s', (post_id,))
        return jsonify({
            'status': 'success',
            'comment': {
                'author_name': user['full_name'],
                'avatar_url': user['avatar_url'],
                'content': content,
                'time_ago': 'Just now'
            }
        })
    return jsonify({'status': 'error', 'message': 'Database error'}), 500


@app.route('/market')
@login_required
def market(user):
    user = normalise_user(user)
    return render_template('market.html', user=user)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
