# GreenAcres

A community platform connecting farmers across India — share updates, network with fellow growers, and trade agricultural products.

## Features

### Community Feed
- Post farming updates, weather reports, and crop insights
- Like and interact with posts from other farmers
- Real-time local weather display
- Connect with farmers through the suggestion engine

### Networking
- Connection management with farmers in your region
- Real-time chat with connected farmers
- Profile viewing with shared interests tags
- Search through your connections

### Marketplace
- Buy and sell tractors, fertilizers, grains, ghee, and crops
- Post new listings with category filtering
- Support for both sale and rent listings
- Price display in Indian Rupees (₹)

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask 3.0.2 |
| Database | MySQL 8.x with utf8mb4 |
| Authentication | JWT (PyJWT 2.8.0) via HTTP-only cookies |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Icons | Font Awesome 6.4 |
| Fonts | Google Fonts (Inter) |

## Project Structure

```
greenacres/
├── app.py                 # Flask application with all routes
├── schema.sql             # MySQL database schema & seed data
├── requirements.txt      # Python dependencies
├── templates/
│   ├── index.html        # Home / Community Feed
│   ├── network.html      # Networking & Chat
│   ├── market.html       # Marketplace
│   ├── login.html        # Login page
│   ├── register.html    # Registration page
│   └── partials/
│       └── navbar.html   # Shared navigation
└── static/
    ├── css/
    │   ├── style.css     # Main styles
    │   └── auth.css      # Auth page styles
    └── js/
        └── script.js     # Client-side interactions
```

## Setup Instructions

### Prerequisites

- Python 3.10+
- MySQL 8.0+
- pip (Python package manager)

### 1. Clone & Navigate

```bash
cd greenacres
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Database

Create a MySQL database named `greenacres_db`:

```sql
CREATE DATABASE IF NOT EXISTS greenacres_db
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

Run the schema to create tables and seed data:

```bash
mysql -u root -p greenacres_db < schema.sql
```

Or import `schema.sql` via MySQL Workbench/phpmyadmin.

### 5. Configure Environment Variables

Set the secret key for JWT tokens:

```bash
# Windows (Command Prompt)
set GREENACRES_SECRET=your-secure-secret-key-here

# Windows (PowerShell)
$env:GREENACRES_SECRET="your-secure-secret-key-here"

# macOS/Linux
export GREENACRES_SECRET="your-secure-secret-key-here"
```

### 6. Update Database Credentials

Edit the `DB_CONFIG` in `app.py` (lines 25-31) if your MySQL credentials differ:

```python
DB_CONFIG = {
    'host':     '127.0.0.1',
    'user':     'root',
    'password': 'your_password',  # Update if needed
    'database': 'greenacres_db',
    'charset':  'utf8mb4',
}
```

### 7. Run the Application

```bash
python app.py
```

The application will start at `http://localhost:5000`

## Demo Credentials

A demo account is seeded in `schema.sql`:

| Field | Value |
|-------|-------|
| Email | demo@greenacres.in |
| Username | demo_farmer |
| Password | farmer123 |

## Routes Overview

### Page Routes
| Route | Description |
|-------|-------------|
| `/` | Home — Community feed (login required) |
| `/login` | Login page |
| `/register` | Registration page |
| `/logout` | Clear session and redirect |
| `/network` | Connections list and chat |
| `/market` | Marketplace with listings |

### API Routes (Real-time Authentication)
| Route | Method | Description |
|-------|--------|-------------|
| `/api/me` | GET | Get current authenticated user |
| `/api/login` | POST | Login with JSON response |
| `/api/register` | POST | Register with JSON response |
| `/api/logout` | POST | Logout via API |
| `/api/check-username` | GET | Check username availability |
| `/api/check-email` | GET | Check email availability |

## Database Schema

- **users** — Farmer profiles with auth credentials
- **connections** — Friend/connection requests (pending/accepted/blocked)
- **posts** — Community feed posts with likes/comments
- **post_likes** — Like records for posts
- **post_comments** — Comment records for posts
- **messages** — Direct messages between farmers
- **market_listings** — Buy/sell/rent agricultural products
- **revoked_tokens** — JWT token blocklist for logout

## Security Features

- Password hashing with SHA-256
- JWT tokens stored in HTTP-only cookies
- Token revocation on logout
- SQL injection protection via parameterized queries
- Real-time validation for username/email availability
- Protected API endpoints with session verification

## License

MIT License
