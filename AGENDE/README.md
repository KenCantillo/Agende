# AGENDE
### A Web-Based Multi-Appointment System for Scheduling, Managing, and Monitoring Appointments

AGENDE is a centralized appointment system built with **Python (Flask)**, **MySQL (PyMySQL)**,
and **HTML/CSS/JavaScript (Bootstrap 5 + Chart.js)**. It supports three account types
(Client, Provider, Administrator) and covers appointment booking, conflict detection,
schedule management, notifications, and descriptive analytics.

This project was written at a **beginner-to-intermediate level** on purpose, so that a
4th-year BSIT student can read, explain, modify, and debug every part of it. There is
no ORM, no design patterns, no class hierarchy — just Flask routes, PyMySQL queries,
and Jinja templates.

---

## 1. Features

- **Authentication** — register, login, logout, hashed passwords (Werkzeug)
- **Client role** — book, reschedule, cancel appointments; view own history, calendar,
  and notifications; update profile
- **Provider role** — confirm/complete/cancel appointments; manage weekly availability;
  view own dashboard and notifications
- **Admin role** — manage all appointments, clients, providers, users, and schedules;
  view descriptive analytics (Chart.js)
- **Conflict detection** — prevents double-booking a provider or a client for the
  same date/time
- **Notifications** — stored in the database and shown per-user
- **Appointment history** — every status change is logged
- **Role protection** — every route checks the logged-in user's role and appointment
  ownership on the **server side** (not just hidden buttons)

---

## 2. Technologies

| Layer      | Technology                     |
|------------|---------------------------------|
| Backend    | Python 3, Flask                 |
| Database   | MySQL, accessed with PyMySQL    |
| Frontend   | HTML, CSS, JavaScript, Bootstrap 5, Bootstrap Icons |
| Charts     | Chart.js (loaded via CDN)       |
| Passwords  | Werkzeug security (hashing)     |

---

## 3. Folder Structure

```
agende/
├── app.py              <- all Flask routes (the whole application logic)
├── database.py         <- one function: get_connection()
├── config.py            <- database settings
├── requirements.txt
├── schema.sql           <- creates the database and tables
├── seed.sql              <- sample/test data
├── templates/            <- Jinja2 HTML pages
│   ├── base.html          <- shared layout + sidebar
│   ├── login.html
│   ├── register.html
│   ├── user/               <- client pages
│   ├── provider/            <- provider pages
│   └── admin/                <- admin pages
└── static/
    ├── css/style.css
    └── js/script.js
```

---

## 4. Prerequisites

- Python 3.9 or newer
- MySQL Server 5.7+/8.0 (or MariaDB) running locally
- pip (comes with Python)

---

## 5. Installation Steps

### Step 1 — Install Python
Download and install Python from https://www.python.org/downloads/.
Confirm it is installed:
```bash
python --version
```

### Step 2 — Create a virtual environment
From inside the `agende` folder:
```bash
python -m venv venv
```
Activate it:
- Windows: `venv\Scripts\activate`
- macOS/Linux: `source venv/bin/activate`

### Step 3 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 4 — Create the MySQL database
Open your MySQL client (MySQL Workbench, phpMyAdmin, or the terminal) and run:
```bash
mysql -u root -p < schema.sql
```
This creates the `agende_db` database and all required tables.

### Step 5 — Import the seed (test) data
```bash
mysql -u root -p agende_db < seed.sql
```
This adds sample clients, providers, services, schedules, and appointments so
the system is not empty on first run.

### Step 6 — Configure the database connection
Open `config.py` and update the values to match your MySQL setup:
```python
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""        # put your MySQL password here
DB_NAME = "agende_db"
```

### Step 7 — Run the application
```bash
python app.py
```
The app will start at **http://127.0.0.1:5000**

---

## 6. Test Accounts

| Role     | Email                   | Password     |
|----------|--------------------------|--------------|
| Admin    | admin@agende.com          | admin123     |
| Provider | provider@agende.com        | provider123  |
| Client   | user@agende.com             | user123      |

Additional sample clients and providers were also created by `seed.sql`
using the password **password123** (see the comments inside `seed.sql`
for their email addresses).

---

## 7. Role Permissions

| Action                         | Client | Provider | Admin |
|---------------------------------|:------:|:--------:|:-----:|
| Book / reschedule / cancel own appointment | \u2713 |   |   |
| View own appointments only      | \u2713 | \u2713 |   |
| Confirm / complete a provider's own appointments |   | \u2713 |   |
| Manage own weekly availability  |   | \u2713 |   |
| View / manage ALL appointments  |   |   | \u2713 |
| View / manage Clients page      |   |   | \u2713 |
| View / manage Providers page    |   |   | \u2713 |
| View / manage Users & Roles     |   |   | \u2713 |
| View system-wide analytics      |   |   | \u2713 |

Every one of these rules is enforced **on the Flask server**, using the
`role_required()` decorator and explicit ownership checks
(e.g. `if appointment["user_id"] != session["user_id"]: abort(403)`),
so typing a restricted URL directly will not bypass the rule.

---

## 8. How Key Features Work (Beginner-Friendly Explanation)

**Booking an appointment** (`/user/book` in `app.py`):
1. The client selects a service, provider, date, time, and optional notes.
2. Flask checks the date is not in the past and the time is valid.
3. `check_provider_schedule()` confirms the provider works on that day/time using
   the `provider_schedules` table.
4. `check_provider_conflict()` and `check_user_conflict()` run simple `SELECT`
   queries to make sure neither the provider nor the client already has a
   booking at that exact time.
5. If everything passes, one `INSERT` adds the row to `appointments` with
   status `pending`, a row is added to `appointment_history`, and two
   notifications are created (for the client and the provider).

**Conflict detection** is intentionally simple: it is one `SELECT` query that
looks for an existing, non-cancelled appointment at the same
`provider_id + appointment_date + start_time`.

**Role protection** uses one small decorator function, `role_required(role_name)`,
defined near the top of `app.py`. Any route that should only be available to
one role is simply marked with `@role_required("admin")` (or `"user"` /
`"provider"`).

---

## 9. Notes for Students

- All SQL queries use **parameterized placeholders (`%s`)** to prevent SQL
  injection — never string-concatenate user input into a query.
- Every database write is wrapped in `try/except`, with `connection.rollback()`
  on failure, so a broken INSERT never silently reports success.
- If you want to add a new feature, search `app.py` for the closest existing
  route (e.g. copy `cancel_appointment()` to build a similar action) — the file
  is long, but every route is self-contained and easy to find with Ctrl+F.


## Additional requirements implemented

This version adds blocked periods, interval-overlap conflict detection, rejection/“Did not attend” status handling,
service management, weekly aggregate linear-regression forecasts, appointment CSV export, and audit logs.

### Updating an existing database
1. Back up `agende_db` first.
2. Open MySQL Workbench/phpMyAdmin.
3. Select the `agende_db` database and run `upgrade_existing_database.sql`.
4. Restart the Flask application.

For a fresh installation, run `schema.sql` followed by `seed.sql`.

### New admin pages
- Services: `/admin/services`
- Forecast: `/admin/forecast`
- Reports: `/admin/reports`
- Audit logs: `/admin/audit-logs`

### New provider page
- Block Time: `/provider/blocked-periods`

Forecasting requires at least 8 historical weeks with appointment records. It forecasts aggregate weekly
appointment and did-not-attend counts; it does not predict the behavior of individual clients. Forecast evaluation
uses a chronological 80/20 split and reports MAE, RMSE, and R² when calculable.

### Security and deployment note
Before deployment, change `SECRET_KEY` in `config.py` to a long random secret and set database credentials
for your environment. Run with debug mode disabled outside development.


## Account profile and logout

All signed-in roles (user, provider, and admin) can open **My Profile** from the sidebar to update their name, phone number, and password. **Log Out** remains available at the bottom of the sidebar. The Help & Support sidebar item has been removed.
