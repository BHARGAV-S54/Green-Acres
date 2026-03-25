import os
import time
import uuid
import hashlib
import hashlib
from datetime import datetime, timezone, timedelta
from functools import wraps

import jwt
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    make_response,
    jsonify,
)
import mysql.connector

# ──────────────────────────────────────────────
#  App Config
# ──────────────────────────────────────────────
app = Flask(__name__)

SECRET_KEY    = os.environ.get('GREENACRES_SECRET', 'greenacres-jwt-secret-2026-change-me')
JWT_ALGORITHM = 'HS256'
JWT_EXP_HOURS = 24          # token lives for 24 hours
COOKIE_NAME   = 'ga_token'  # HTTP-only cookie name

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
os.makedirs(os.path.join(UPLOAD_FOLDER, 'posts'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'messages'), exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
        print(f"[DB] Connection error: {e}")
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
        print(f"[DB] Query error: {e}")
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
        print(f"[DB] Integrity error: {e}")
        return -2  # unique constraint violation
    except Exception as e:
        print(f"[DB] Execute error: {e}")
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
        "sub": user_id,
        "user": username,
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
    }
    encoded = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    # Ensure it's a string, not bytes (v1.x vs v2.x of PyJWT)
    if isinstance(encoded, bytes):
        return encoded.decode('utf-8')
    return encoded


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
        "SELECT 1 FROM revoked_tokens WHERE jti=%s", (payload["jti"],), one=True
    )
    if is_revoked:
        return None
    user = query(
        "SELECT * FROM users WHERE id=%s AND is_active=1", (payload["sub"],), one=True
    )
    return user


# ──────────────────────────────────────────────
#  Auth decorator
# ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("login_page"))
        return f(*args, user=user, **kwargs)

    return decorated


# ──────────────────────────────────────────────
#  Fallback data  (used when DB is unavailable)
# ──────────────────────────────────────────────
DEMO_USER = {
    'id': 0, 'full_name': 'Demo Farmer', 'username': 'demo',
    'email': 'demo@greenacres.in',
    'title': 'Organic Farmer & Agri-Tech Enthusiast',
    'location': 'Andhra Pradesh, India', 'connections': 342,
    'avatar_url': 'https://ui-avatars.com/api/?name=D+F&background=1b873f&color=fff&rounded=true',
}

DEMO_POSTS = [
    {
        "author_name": "Rajesh Kumar",
        "author_title": "Traditional Wheat Farmer",
        "time_ago": "2 hours ago",
        "content": "Just finished testing the new drip irrigation system on the north field. The water savings are incredible! 🌾💧",
        "likes": 124,
        "comments": 18,
        "avatar_url": "https://ui-avatars.com/api/?name=RK&background=d4edda&color=1b5e20&rounded=true",
    },
    {
        "author_name": "Priya Verma",
        "author_title": "Organic Vegetable Grower",
        "time_ago": "5 hours ago",
        "content": "Started using neem oil spray instead of chemical pesticides. Pests are down 70%! 🌿✨",
        "likes": 89,
        "comments": 12,
        "avatar_url": "https://ui-avatars.com/api/?name=PV&background=fff3e0&color=e65100&rounded=true",
    },
]

DEMO_FRIENDS = [
    {
        "id": 2,
        "name": "Rajesh Kumar",
        "title": "Traditional Wheat Farmer",
        "avatar_url": "https://ui-avatars.com/api/?name=RK&background=d4edda&color=1b5e20&rounded=true",
    },
    {
        "id": 3,
        "name": "Priya Verma",
        "title": "Organic Vegetable Grower",
        "avatar_url": "https://ui-avatars.com/api/?name=PV&background=fff3e0&color=e65100&rounded=true",
    },
]

DEMO_SUGGESTIONS = [
    {
        "name": "Kiran Bhat",
        "title": "Coconut Farmer, Kerala",
        "avatar_url": "https://ui-avatars.com/api/?name=KB&background=e8f5e9&color=1b5e20&rounded=true",
    },
    {
        "name": "Mohan Das",
        "title": "Basmati Rice Grower, UP",
        "avatar_url": "https://ui-avatars.com/api/?name=MD&background=fff8e1&color=f57f17&rounded=true",
    },
]


def normalise_user(u: dict) -> dict:
    """Ensure avatar_url is always set."""
    if not u.get("avatar_url"):
        u["avatar_url"] = (
            f"https://ui-avatars.com/api/?name="
            f"{(u.get('full_name') or 'U')[0]}&background=1b873f&color=fff&rounded=true"
        )
    return u


def load_posts_db():
    rows = query("""
        SELECT p.*, u.full_name AS author_name, u.title AS author_title,
               u.avatar_url, p.created_at
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 20
    """)
    if not rows:
        return DEMO_POSTS
    for p in rows:
        p["time_ago"] = "2 hours ago"
        if not p.get("avatar_url"):
            p["avatar_url"] = (
                f"https://ui-avatars.com/api/?name={p['author_name'][0]}&background=random&rounded=true"
            )
    return rows


# ══════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════


@app.route("/login", methods=["GET"])
def login_page():
    if get_current_user():
        return redirect("/")
    return render_template("login.html", error=None)


@app.route("/login", methods=["POST"])
def login_post():
    email_or_user = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email_or_user or not password:
        return render_template("login.html", error="Please fill in all fields.")

    # Try finding user by email or username
    user = query(
        "SELECT * FROM users WHERE (email=%s OR username=%s) AND is_active=1",
        (email_or_user, email_or_user),
        one=True,
    )

    if user is None:
        if email_or_user in ('demo@greenacres.in', 'demo_farmer') and password == 'farmer123':
            user = DEMO_USER.copy()
            token = create_token(0, "demo_farmer")
            resp = make_response(redirect("/"))
            resp.set_cookie(
                COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600
            )
            return resp
        return render_template("login.html", error="Invalid credentials.")

    if not check_password(password, user["password_hash"]):
        return render_template("login.html", error="Invalid email or password.")

    # Update last_login
    execute("UPDATE users SET last_login=%s WHERE id=%s", (datetime.now(), user["id"]))

    token = create_token(user["id"], user["username"])
    resp = make_response(redirect("/"))
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite="Lax"
    )
    return resp


@app.route("/register", methods=["GET"])
def register_page():
    if get_current_user():
        return redirect("/")
    return render_template("register.html", error=None)


@app.route("/register", methods=["POST"])
def register_post():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    email = request.form.get("email", "").strip().lower()
    title = request.form.get("title", "").strip()
    location = request.form.get("location", "").strip()
    password = request.form.get("password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not all([full_name, username, email, password]):
        return render_template(
            "register.html", error="Please fill in all required fields."
        )
    if len(password) < 6:
        return render_template(
            "register.html", error="Password must be at least 6 characters."
        )
    if password != confirm_pw:
        return render_template("register.html", error="Passwords do not match.")

    avatar_url = (
        f"https://ui-avatars.com/api/?name={full_name.replace(' ', '+')}"
        f"&background=1b873f&color=fff&rounded=true"
    )
    pw_hash = hash_password(password)

    result = execute(
        """INSERT INTO users
           (full_name, username, email, password_hash, title, location, avatar_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (full_name, username, email, pw_hash, title, location, avatar_url),
    )

    print(f"[Register] DB result: {result}") # DEBUG

    if result == -2:
        return render_template(
            "register.html", error="Email or username already registered."
        )
    if result < 0:
        # DB not ready – still issue a token for demo purposes (id=0)
        print("[Register] DB Error detected, falling back to demo login")
        token = create_token(0, username)
        resp = make_response(redirect("/"))
        resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600)
        return resp

    token = create_token(result, username)
    resp = make_response(redirect("/"))
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite="Lax"
    )
    return resp


@app.route("/logout")
def logout():
    """Revoke token and clear cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_token(token)
        if payload:
            execute(
                "INSERT IGNORE INTO revoked_tokens (jti) VALUES (%s)", (payload["jti"],)
            )
    resp = make_response(redirect("/login"))
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ══════════════════════════════════════════════
#  API ROUTES (Real-time Authentication)
# ══════════════════════════════════════════════


@app.route("/api/check-username")
def api_check_username():
    """Check if username is available."""
    username = request.args.get("username", "").strip().lower()
    if not username:
        return jsonify({"available": False, "message": "Username required"})

    if len(username) < 3:
        return jsonify(
            {"available": False, "message": "Username must be at least 3 characters"}
        )

    existing = query("SELECT id FROM users WHERE username=%s", (username,), one=True)
    return jsonify(
        {
            "available": existing is None,
            "message": "Username available"
            if existing is None
            else "Username already taken",
        }
    )


@app.route("/api/check-email")
def api_check_email():
    """Check if email is available."""
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"available": False, "message": "Email required"})

    if "@" not in email or "." not in email:
        return jsonify({"available": False, "message": "Invalid email format"})

    existing = query("SELECT id FROM users WHERE email=%s", (email,), one=True)
    return jsonify(
        {
            "available": existing is None,
            "message": "Email available"
            if existing is None
            else "Email already registered",
        }
    )


@app.route("/api/login", methods=["POST"])
def api_login():
    """JSON API for login - returns JSON response."""
    data = request.get_json() or {}
    email_or_user = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    remember = data.get("remember", False)

    if not email_or_user or not password:
        return jsonify(
            {"success": False, "message": "Email/username and password are required"}
        ), 400

    user = query(
        "SELECT * FROM users WHERE (email=%s OR username=%s) AND is_active=1",
        (email_or_user, email_or_user),
        one=True,
    )

    if user is None:
        if email_or_user in ('demo@greenacres.in', 'demo_farmer') and password == 'farmer123':
             user = DEMO_USER.copy()
             token = create_token(0, "demo_farmer")
             resp = make_response(jsonify({"success": True, "message": "Login successful"}))
             resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600)
             return resp
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    if not check_password(password, user["password_hash"]):
        return jsonify({"success": False, "message": "Invalid password"}), 401

    execute("UPDATE users SET last_login=%s WHERE id=%s", (datetime.now(), user["id"]))

    token = create_token(user["id"], user["username"])
    max_age = JWT_EXP_HOURS * 3600 if remember else JWT_EXP_HOURS * 3600

    resp = make_response(
        jsonify(
            {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": user["id"],
                    "full_name": user["full_name"],
                    "username": user["username"],
                    "email": user["email"],
                    "avatar_url": user.get("avatar_url", ""),
                },
            }
        )
    )
    resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=max_age, samesite="Lax")
    return resp


@app.route("/api/register", methods=["POST"])
def api_register():
    """JSON API for registration - returns JSON response."""
    data = request.get_json() or {}
    full_name = (data.get("full_name") or "").strip()
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    title = (data.get("title") or "").strip()
    location = (data.get("location") or "").strip()
    password = (data.get("password") or "").strip()
    confirm_pw = (data.get("confirm_password") or "").strip()

    if not all([full_name, username, email, password]):
        return jsonify(
            {"success": False, "message": "All required fields must be filled"}
        ), 400

    if len(username) < 3:
        return jsonify(
            {"success": False, "message": "Username must be at least 3 characters"}
        ), 400

    if len(password) < 6:
        return jsonify(
            {"success": False, "message": "Password must be at least 6 characters"}
        ), 400

    if password != confirm_pw:
        return jsonify({"success": False, "message": "Passwords do not match"}), 400

    existing_user = query(
        "SELECT id FROM users WHERE email=%s OR username=%s",
        (email, username),
        one=True,
    )
    if existing_user:
        return jsonify(
            {"success": False, "message": "Email or username already exists"}
        ), 400

    avatar_url = (
        f"https://ui-avatars.com/api/?name={full_name.replace(' ', '+')}"
        f"&background=1b873f&color=fff&rounded=true"
    )
    pw_hash = hash_password(password)

    result = execute(
        """INSERT INTO users
           (full_name, username, email, password_hash, title, location, avatar_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (full_name, username, email, pw_hash, title, location, avatar_url),
    )

    if result < 0:
        return jsonify(
            {"success": False, "message": "Registration failed. Please try again."}
        ), 500

    token = create_token(result, username)
    resp = make_response(
        jsonify(
            {
                "success": True,
                "message": "Registration successful",
                "user": {
                    "id": result,
                    "full_name": full_name,
                    "username": username,
                    "email": email,
                    "avatar_url": avatar_url,
                },
            }
        )
    )
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_HOURS * 3600, samesite="Lax"
    )
    return resp


@app.route("/api/me")
def api_me():
    """Get current user info."""
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401

    return jsonify(
        {
            "authenticated": True,
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "username": user["username"],
                "email": user.get("email", ""),
                "title": user.get("title", ""),
                "location": user.get("location", ""),
                "avatar_url": user.get("avatar_url", ""),
                "connections": user.get("connections", 0),
            },
        }
    )


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """JSON API for logout."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_token(token)
        if payload:
            execute("INSERT IGNORE INTO revoked_tokens (jti) VALUES (%s)", (payload["jti"],))

    resp = make_response(jsonify({"success": True, "message": "Logged out"}))
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.route("/api/account/delete", methods=["POST"])
@login_required
def api_delete_account(user):
    """Deactivate current user account and logout."""
    user = normalise_user(user)
    # Revoke current token
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_token(token)
        if payload:
            execute("INSERT IGNORE INTO revoked_tokens (jti) VALUES (%s)", (payload["jti"],))
            
    # Mark as inactive
    execute("UPDATE users SET is_active=0 WHERE id=%s", (user['id'],))
    
    # Clear cookies
    resp = make_response(jsonify({"success": True, "message": "Account deactivated"}))
    resp.delete_cookie(COOKIE_NAME)
    return resp
    

# ══════════════════════════════════════════════
#  PROTECTED PAGE ROUTES
# ══════════════════════════════════════════════


@app.route("/")
@login_required
def index(user):
    user = normalise_user(user)
    posts = load_posts_db()
    
    # 1. Fetch current friends (accepted connections)
    friends = query(
        '''SELECT u.id, u.full_name AS name, u.title, u.avatar_url 
           FROM users u
           JOIN connections c ON (c.requester_id = u.id OR c.receiver_id = u.id)
           WHERE (c.requester_id = %s OR c.receiver_id = %s)
             AND u.id != %s
             AND c.status = "accepted"''',
        (user['id'], user['id'], user['id'])
    )
    
    # 2. Fetch suggestions (not the user, and not already connected)
    suggestions = query(
        '''SELECT id, full_name AS name, title, avatar_url 
           FROM users 
           WHERE id != %s 
             AND id NOT IN (
                 SELECT requester_id FROM connections WHERE receiver_id = %s
                 UNION
                 SELECT receiver_id FROM connections WHERE requester_id = %s
             )
           LIMIT 3''',
        (user['id'], user['id'], user['id'])
    )
    
    # 2. Fetch total users
    stats = query('SELECT COUNT(*) AS total FROM users WHERE is_active=1', one=True)
    total_users = stats['total'] if stats else 0
    
    return render_template(
        "index.html",
        user=user,
        posts=posts,
        friends=friends,
        suggestions=suggestions,
        total_users=total_users
    )


@app.route('/api/post/create', methods=['POST'])
@login_required
def api_create_post(user):
    print(f"[API] Create Post attempt by {user.get('username')}")
    user = normalise_user(user)
    content = request.form.get('content', '').strip()
    image = request.files.get('image')
    
    print(f"[API] Content: {content[:30]}..., Has Image: {image is not None}")

    if not content and not image:
        return jsonify({'status': 'error', 'message': 'Post content cannot be empty'}), 400
        
    media_url = None
    if image:
        try:
            # Preserve original extension or fallback to jpg
            ext = 'jpg'
            if '.' in image.filename:
                ext = image.filename.rsplit('.', 1)[1].lower()
            
            filename = f"post_{user['id']}_{int(time.time())}.{ext}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'posts', filename)
            image.save(save_path)
            media_url = f"/static/uploads/posts/{filename}"
            print(f"[API] Media saved: {media_url}")
        except Exception as e:
            print(f"[API] Media SAVE ERROR: {e}")
            return jsonify({'status': 'error', 'message': f'Media upload failed: {str(e)}'}), 500
        
    print(f"[API] Executing DB Insert...")
    res = execute(
        'INSERT INTO posts (user_id, content, media_url) VALUES (%s, %s, %s)',
        (user['id'], content, media_url)
    )
    
    print(f"[API] DB Result: {res}")
    if res > 0:
        return jsonify({'status': 'success', 'post_id': res})
    return jsonify({'status': 'error', 'message': 'Database error'}), 500


@app.route("/api/post/delete/<int:post_id>", methods=["POST"])
@login_required
def api_delete_post(user, post_id):
    """Delete a post (author only)."""
    user = normalise_user(user)
    # Check ownership
    rows = query('SELECT user_id FROM posts WHERE id=%s', (post_id,))
    if not rows:
        return jsonify({'status': 'error', 'message': 'Post not found'}), 404
    if rows[0]['user_id'] != user['id']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
        
    execute('DELETE FROM posts WHERE id=%s', (post_id,))
    print(f"[API] Post deleted: {post_id} by {user['id']}")
    return jsonify({'status': 'success'})


@app.route("/api/post/report/<int:post_id>", methods=["POST"])
@login_required
def api_report_post(user, post_id):
    """Report an inappropriate post."""
    user = normalise_user(user)
    data = request.json or {}
    reason = data.get('reason', 'Unspecified post misconduct').strip()
    
    # Store in reporting system
    try:
        execute(
            'INSERT INTO reports (reporter_id, target_id, reason) VALUES (%s, %s, %s)',
            (user['id'], -post_id, f"POST_REPORT: {reason}")
        )
        print(f"[REPORT] Post {post_id} reported by {user['id']}: {reason}")
    except: pass
    
    return jsonify({'status': 'success', 'message': 'Post report submitted.'})


@app.route('/api/post/like/<int:post_id>', methods=['POST'])
@login_required
def api_like_post(user, post_id):
    user = normalise_user(user)
    liked = query('SELECT * FROM post_likes WHERE user_id=%s AND post_id=%s', (user['id'], post_id), one=True)
    
    if liked:
        execute('DELETE FROM post_likes WHERE user_id=%s AND post_id=%s', (user['id'], post_id))
        execute('UPDATE posts SET likes = GREATEST(0, CAST(likes AS SIGNED) - 1) WHERE id=%s', (post_id,))
        is_liked = False
    else:
        execute('INSERT IGNORE INTO post_likes (user_id, post_id) VALUES (%s, %s)', (user['id'], post_id))
        execute('UPDATE posts SET likes = likes + 1 WHERE id=%s', (post_id,))
        is_liked = True
        
    new_count = query('SELECT likes FROM posts WHERE id=%s', (post_id,), one=True)
    return jsonify({'status': 'success', 'is_liked': is_liked, 'likes_count': new_count['likes'] if new_count else 0})


@app.route('/api/post/comment/<int:post_id>', methods=['POST'])
@login_required
def api_comment_post(user, post_id):
    user = normalise_user(user)
    content = (request.json or {}).get('content', '').strip()
    if not content: return jsonify({'status': 'error', 'message': 'Comment cannot be empty'}), 400
    
    res = execute('INSERT INTO post_comments (post_id, user_id, content) VALUES (%s, %s, %s)', (post_id, user['id'], content))
    if res > 0:
        execute('UPDATE posts SET comments = comments + 1 WHERE id=%s', (post_id,))
        return jsonify({'status': 'success', 'comment': {'author_name': user['full_name'], 'avatar_url': user['avatar_url'], 'content': content}})
    return jsonify({'status': 'error', 'message': 'Database error'}), 500


@app.route("/network")
@login_required
def network(user):
    user = normalise_user(user)
    # Fetch accepted connections
    conn_rows = query(
        """SELECT u.id, u.full_name AS name, u.title, u.avatar_url
           FROM connections c
           JOIN users u ON (
               CASE WHEN c.requester_id=%s THEN c.receiver_id ELSE c.requester_id END = u.id
           )
           WHERE (c.requester_id=%s OR c.receiver_id=%s) AND c.status='accepted'
           LIMIT 30""",
        (user["id"], user["id"], user["id"]),
    )
    friends = conn_rows if conn_rows else []
    
    # Fetch suggestions (users not connected)
    suggestions = query(
        '''SELECT id, full_name AS name, title, avatar_url 
           FROM users 
           WHERE id != %s AND id NOT IN (
               SELECT CASE WHEN requester_id=%s THEN receiver_id ELSE requester_id END
               FROM connections 
               WHERE requester_id=%s OR receiver_id=%s
           )
           LIMIT 5''',
        (user['id'], user['id'], user['id'], user['id'])
    )
    
    for f in (friends + suggestions):
        # Ensure name exists for first-letter fallback
        display_name = (f.get('name') or f.get('username') or 'User')
        if not f.get('avatar_url'):
            initial = display_name[0] if display_name else 'U'
            f['avatar_url'] = f"https://ui-avatars.com/api/?name={initial}&background=random&rounded=true"
            
    return render_template('network.html', user=user, friends=friends, suggestions=suggestions)


@app.route("/api/connect/<int:target_id>", methods=["POST"])
@login_required
def api_connect(user, target_id):
    """Create a new connection request."""
    user = normalise_user(user)
    # Check if already exists
    existing = query('SELECT * FROM connections WHERE (requester_id=%s AND receiver_id=%s) OR (requester_id=%s AND receiver_id=%s)', 
                     (user['id'], target_id, target_id, user['id']), one=True)
    if existing:
        return jsonify({'status': 'error', 'message': 'Connection already exists'}), 400
    
    res = execute('INSERT INTO connections (requester_id, receiver_id, status) VALUES (%s, %s, "accepted")', 
                  (user['id'], target_id))
    if res > 0:
        return jsonify({'status': 'success', 'message': 'Connected!'})
    return jsonify({'status': 'error', 'message': 'Database error'}), 500


@app.route("/api/disconnect/<int:target_id>", methods=["POST"])
@login_required
def api_disconnect(user, target_id):
    """Remove a connection."""
    res = execute(
        '''DELETE FROM connections 
           WHERE (requester_id=%s AND receiver_id=%s) 
              OR (requester_id=%s AND receiver_id=%s)''',
        (user['id'], target_id, target_id, user['id'])
    )
    if res >= 0:
        return jsonify({'status': 'success', 'message': 'Connection removed.'})
    return jsonify({'status': 'error', 'message': 'Database error'}), 500


@app.route("/api/messages/<int:other_id>", methods=["GET"])
@login_required
def api_get_messages(user, other_id):
    """Fetch chat history with a specific user."""
    user = normalise_user(user)
    rows = query(
        '''SELECT id, sender_id, content, media_url, created_at 
           FROM messages 
           WHERE (sender_id=%s AND receiver_id=%s) 
              OR (sender_id=%s AND receiver_id=%s)
           ORDER BY created_at ASC 
           LIMIT 50''',
        (user['id'], other_id, other_id, user['id'])
    )
    return jsonify({'status': 'success', 'messages': rows if rows else []})


@app.route("/api/messages/send", methods=["POST"])
@login_required
def api_send_message(user):
    """Send a private message."""
    user = normalise_user(user)
    
    # Can be multipart (with file) or json
    if request.is_json:
        data = request.json or {}
        receiver_id = data.get('receiver_id')
        content = data.get('content', '').strip()
        media_file = None
    else:
        receiver_id = request.form.get('receiver_id')
        content = request.form.get('content', '').strip()
        media_file = request.files.get('file')

    if not receiver_id or (not content and not media_file):
        return jsonify({'status': 'error', 'message': 'Missing recipient or content'}), 400
        
    media_url = None
    if media_file:
        try:
            ext = 'jpg'
            if '.' in media_file.filename:
                ext = media_file.filename.rsplit('.', 1)[1].lower()
            fname = f"msg_{user['id']}_{int(time.time())}.{ext}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'messages', fname)
            media_file.save(save_path)
            media_url = f"/static/uploads/messages/{fname}"
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'File upload failed: {e}'}), 500

    res = execute(
        'INSERT INTO messages (sender_id, receiver_id, content, media_url) VALUES (%s, %s, %s, %s)',
        (user['id'], receiver_id, content, media_url)
    )
    if res > 0:
        return jsonify({'status': 'success', 'message_id': res, 'media_url': media_url})
    return jsonify({'status': 'error', 'message': 'Database error'}), 500


@app.route("/api/report/<int:other_id>", methods=["POST"])
@login_required
def api_report_user(user, other_id):
    """Report a user for misconduct."""
    user = normalise_user(user)
    data = request.json or {}
    reason = data.get('reason', 'No specific reason given.').strip()
    
    # Just log for now if table isn't created, but let's try execute it
    try:
        execute(
            'INSERT INTO reports (reporter_id, target_id, reason) VALUES (%s, %s, %s)',
            (user['id'], other_id, reason)
        )
        print(f"[REPORT] User {user['id']} reported {other_id} for: {reason}")
        return jsonify({'status': 'success', 'message': 'User reported.'})
    except Exception as e:
        print(f"[REPORT ERROR] {e}")
        return jsonify({'status': 'success', 'message': 'Report submitted for review.'})


@app.route("/market")
@login_required
def market(user):
    user = normalise_user(user)
    return render_template("market.html", user=user)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
