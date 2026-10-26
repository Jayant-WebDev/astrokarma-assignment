# AstroKarma Assignment — Wallet-Based Per-Minute Session Billing

Django + Django REST Framework backend for prepaid wallet balance, mock recharge, consultation session state machine, and per-minute billing.

**Stack:** Django 6 · DRF · SimpleJWT · SQLite (local)

---

## Features

- Prepaid **wallet** (view balance, mock recharge + idempotent callback)
- **USER / PROVIDER** roles via `Profile`
- Consultation **session lifecycle** (unassigned → assigned → accepted → in_progress → completed)
- **Per-minute billing** with idempotent minute tracking
- Auto-end when wallet cannot cover the next minute (`ended_by=system`)
- JWT authentication
- Automated tests for all six assignment scenarios

---

## Setup

### 1. Prerequisites

- Python 3.12+ (3.14 works with this repo)
- `pip` / venv

### 2. Clone and create virtualenv

```bash
cd astrokarma-assignment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

### 3. Migrate database

```bash
python manage.py migrate
```

### 4. Create users

```bash
python manage.py createsuperuser
```

Promote a user to provider (optional, for manual API testing):

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from consultations.models import Profile

User = get_user_model()
p = User.objects.get(username='PROVIDER_USERNAME')
p.profile.role = Profile.Role.PROVIDER
p.profile.save()
```

### 5. Run the server

```bash
python manage.py runserver
```

API base: `http://127.0.0.1:8000/api/`

---

## Authentication (JWT)

```bash
# Obtain tokens
curl -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USER","password":"YOUR_PASSWORD"}'

# Use access token on protected endpoints
curl http://127.0.0.1:8000/api/wallet/ \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

- `POST /api/auth/token/` — username/password → `access` + `refresh`
- `POST /api/auth/token/refresh/` — refresh → new `access`

Session auth is also enabled for DRF browsable API login during local development.

---

## Main API endpoints

### Wallet

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/wallet/` | Yes | Current balance |
| POST | `/api/wallet/recharge/` | Yes | Start mock recharge (`amount`) |
| POST | `/api/wallet/recharge/callback/` | No (mock webhook) | Complete recharge (`reference`, `status`) |

### Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/sessions/` | Yes | Create (`per_minute_cost`) |
| POST | `/api/sessions/<id>/assign/` | Yes | Assign provider (`provider_id`) |
| POST | `/api/sessions/<id>/accept/` | Yes | Provider accepts |
| POST | `/api/sessions/<id>/start/` | Yes | User starts (needs ≥ 5× cost) |
| POST | `/api/sessions/<id>/bill/` | Yes | Bill until `minutes` total (idempotent) |
| POST | `/api/sessions/<id>/end/` | Yes | User or provider ends |

Happy-path sketch:

1. Recharge wallet → callback `success`
2. Create session → assign → accept → start
3. `POST .../bill/` with `{"minutes": 2}`
4. End session

---

## Running tests

All six assignment scenarios live in `consultations/tests.py`.

```bash
source .venv/bin/activate
python manage.py test consultations.tests -v 2
```

Expected: **6 tests, OK**.

Scenarios covered:

1. Insufficient balance cannot start  
2. Happy path (recharge → session → bill 2 minutes → end)  
3. Balance runs out → system ends session  
4. Invalid state transition → HTTP 400  
5. Duplicate recharge callback credits once  
6. Duplicate billing does not double-charge  

---

## Diagrams & design notes

- [State machine & ER diagram](docs/DIAGRAMS.md)
- [Important implementation decisions](docs/DESIGN_DECISIONS.md)

---

## Project layout

```text
config/           # Django project (settings, root URLs, JWT routes)
wallet/           # Wallet + mock recharge
consultations/    # Profile roles + sessions + billing + tests
docs/             # Diagrams and design decisions
requirements.txt
manage.py
```

---

## Out of scope (per assignment)

Real payment gateways, chat/WebRTC, frontend, admin customization, Celery/background workers, multi-currency.
