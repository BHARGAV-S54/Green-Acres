import os
import uuid
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

SECRET_KEY = os.environ.get("AGRICONNECT_SECRET", "agri-jwt-secret-2024-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 24  # token lives for 24 hours
COOKIE_NAME = "ac_token"  # HTTP-only cookie name

# ──────────────────────────────────────────────
#  Database helpers
# ──────────────────────────────────────────────
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "root",
    "database": "agriconnect_db",
    "charset": "utf8mb4",
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
    "id": 0,
    "full_name": "Demo Farmer",
    "username": "demo",
    "email": "demo@agriconnect.in",
    "title": "Organic Farmer & Agri-Tech Enthusiast",
    "location": "Andhra Pradesh, India",
    "connections": 342,
    "avatar_url": "https://ui-avatars.com/api/?name=D+F&background=1b873f&color=fff&rounded=true",
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
    {
        "id": 4,
        "name": "Amjad Khan",
        "title": "Paddy & Rice Specialist",
        "avatar_url": "https://ui-avatars.com/api/?name=AK&background=e8f5e9&color=2e7d32&rounded=true",
    },
    {
        "id": 5,
        "name": "Sunita Devi",
        "title": "Dairy & Cattle Farmer",
        "avatar_url": "https://ui-avatars.com/api/?name=SD&background=fce4ec&color=880e4f&rounded=true",
    },
    {
        "id": 6,
        "name": "Vikram Singh",
        "title": "Sugarcane Grower",
        "avatar_url": "https://ui-avatars.com/api/?name=VS&background=e3f2fd&color=1565c0&rounded=true",
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
    {
        "name": "Shalini Patel",
        "title": "Spice Farmer, Gujarat",
        "avatar_url": "https://ui-avatars.com/api/?name=SP&background=fce4ec&color=c62828&rounded=true",
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

    # No DB → accept demo credentials for dev
    if user is None:
        if (
            email_or_user in ("demo@agriconnect.in", "demo_farmer")
            and password == "farmer123"
        ):
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

    if result == -2:
        return render_template(
            "register.html", error="Email or username already registered."
        )
    if result < 0:
        # DB not ready – still issue a token for demo purposes
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
            execute(
                "INSERT IGNORE INTO revoked_tokens (jti) VALUES (%s)", (payload["jti"],)
            )

    resp = make_response(jsonify({"success": True, "message": "Logged out"}))
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
    return render_template(
        "index.html", user=user, posts=posts, suggestions=DEMO_SUGGESTIONS
    )


@app.route("/network")
@login_required
def network(user):
    user = normalise_user(user)
    # Fetch accepted connections – fallback to demo list
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
    friends = conn_rows if conn_rows else DEMO_FRIENDS
    for f in friends:
        if not f.get("avatar_url"):
            f["avatar_url"] = (
                f"https://ui-avatars.com/api/?name={f['name'][0]}&background=random&rounded=true"
            )
    return render_template("network.html", user=user, friends=friends)


@app.route("/market")
@login_required
def market(user):
    user = normalise_user(user)
    return render_template("market.html", user=user)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
