# =========================================================
# APP.PY
# Main Flask application for AGENDE.
# All routes are kept in this single file so the logic for
# any feature (login, booking, conflict checking, admin
# management, etc.) is easy to find and read top to bottom.
# =========================================================

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date as date_cls
from functools import wraps

from database import get_connection
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STATUS_LIST = ["pending", "confirmed", "completed", "cancelled", "rejected", "no_show"]


# =========================================================
# SMALL HELPER FUNCTIONS
# (used by many routes below)
# =========================================================

def login_required(view_function):
    """Make sure the user is logged in before running the route."""
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "danger")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)
    return wrapper


def role_required(role_name):
    """Make sure the logged-in user has the correct role.
    Usage: @role_required("admin")
    """
    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "danger")
                return redirect(url_for("login"))
            if session.get("role") != role_name:
                # A user tried to access a page that does not belong
                # to their role (for example a client typing /admin/clients).
                # We NEVER trust the frontend, so we block it here on the server.
                abort(403)
            return view_function(*args, **kwargs)
        return wrapper
    return decorator


def create_notification(user_id, message, notif_type="info"):
    """Insert one row into the notifications table."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO notifications (user_id, message, type) VALUES (%s, %s, %s)",
            (user_id, message, notif_type)
        )
        connection.commit()
        cursor.close()
    except Exception:
        connection.rollback()
    finally:
        connection.close()


def log_history(appointment_id, action, old_status, new_status, performed_by):
    """Insert one row into the appointment_history table."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """INSERT INTO appointment_history
               (appointment_id, action, old_status, new_status, performed_by)
               VALUES (%s, %s, %s, %s, %s)""",
            (appointment_id, action, old_status, new_status, performed_by)
        )
        connection.commit()
        cursor.close()
    except Exception:
        connection.rollback()
    finally:
        connection.close()


def get_provider_id_for_user(user_id):
    """Given a logged-in provider's user_id, find their providers.id row."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM providers WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    connection.close()
    return row["id"] if row else None


def parse_date(date_string):
    """Convert a 'YYYY-MM-DD' string into a Python date object, or None."""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def parse_time(time_string):
    """Convert a 'HH:MM' string into a Python time object, or None."""
    try:
        return datetime.strptime(time_string, "%H:%M").time()
    except (ValueError, TypeError):
        return None


def check_provider_schedule(provider_id, appointment_date, start_time, duration=30):
    """Return True if the provider is scheduled to work on this day/time."""
    day_of_week = appointment_date.weekday()  # 0 = Monday ... 6 = Sunday
    requested_end = (datetime.combine(appointment_date, start_time) + timedelta(minutes=int(duration))).time()

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT * FROM provider_schedules
           WHERE provider_id = %s AND day_of_week = %s AND is_available = 1
           AND start_time <= %s AND end_time >= %s""",
        (provider_id, day_of_week, start_time, requested_end)
    )
    schedule_row = cursor.fetchone()
    cursor.close()
    connection.close()

    return schedule_row is not None



def check_blocked_period(provider_id, appointment_date, start_time, duration):
    """Return True when the requested appointment overlaps a blocked period."""
    start_dt = datetime.combine(appointment_date, start_time)
    end_dt = start_dt + timedelta(minutes=int(duration))
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT id FROM blocked_periods
               WHERE provider_id = %s AND start_datetime < %s AND end_datetime > %s LIMIT 1""",
            (provider_id, end_dt, start_dt)
        )
        return cursor.fetchone() is not None
    finally:
        connection.close()


def check_provider_conflict(provider_id, appointment_date, start_time, exclude_appointment_id=None, duration=30):
    """Check interval overlap, not just identical start times."""
    requested_start = datetime.combine(appointment_date, start_time)
    requested_end = requested_start + timedelta(minutes=int(duration))
    connection = get_connection()
    try:
        cursor = connection.cursor()
        query = """SELECT id FROM appointments
                   WHERE provider_id = %s AND appointment_date = %s
                   AND status IN ('pending','confirmed')
                   AND start_time < %s AND end_time > %s"""
        params = [provider_id, appointment_date, requested_end.time(), requested_start.time()]
        if exclude_appointment_id:
            query += " AND id != %s"
            params.append(exclude_appointment_id)
        cursor.execute(query, params)
        return cursor.fetchone() is not None
    finally:
        connection.close()


def check_user_conflict(user_id, appointment_date, start_time, exclude_appointment_id=None, duration=30):
    """Prevent a client from booking overlapping appointments."""
    requested_start = datetime.combine(appointment_date, start_time)
    requested_end = requested_start + timedelta(minutes=int(duration))
    connection = get_connection()
    try:
        cursor = connection.cursor()
        query = """SELECT id FROM appointments
                   WHERE user_id = %s AND appointment_date = %s
                   AND status IN ('pending','confirmed')
                   AND start_time < %s AND end_time > %s"""
        params = [user_id, appointment_date, requested_end.time(), requested_start.time()]
        if exclude_appointment_id:
            query += " AND id != %s"
            params.append(exclude_appointment_id)
        cursor.execute(query, params)
        return cursor.fetchone() is not None
    finally:
        connection.close()


def write_audit(user_id, action, entity_name, entity_id=None, details=None):
    """Record important administrative or appointment actions."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (user_id, action, entity_name, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            (user_id, action, entity_name, entity_id, details)
        )
        connection.commit()
    except Exception:
        connection.rollback()
    finally:
        connection.close()


# =========================================================
# HOME / AUTH ROUTES
# =========================================================

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    elif session["role"] == "provider":
        return redirect(url_for("provider_dashboard"))
    else:
        return redirect(url_for("user_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """SELECT u.*, r.name AS role_name FROM users u
               JOIN roles r ON u.role_id = r.id
               WHERE u.email = %s""",
            (email,)
        )
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user is None or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        if not user["is_active"]:
            flash("This account has been deactivated. Please contact the administrator.", "danger")
            return redirect(url_for("login"))

        # Save the essentials in the session
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role_name"]

        flash(f"Welcome back, {user['name']}!", "success")

        if user["role_name"] == "admin":
            return redirect(url_for("admin_dashboard"))
        elif user["role_name"] == "provider":
            return redirect(url_for("provider_dashboard"))
        else:
            return redirect(url_for("user_dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill out all required fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        connection = get_connection()
        try:
            cursor = connection.cursor()

            # Check if email is already used
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash("An account with this email already exists.", "danger")
                cursor.close()
                connection.close()
                return redirect(url_for("register"))

            hashed_password = generate_password_hash(password)

            # role_id = 1 is always "user" for public self-registration
            cursor.execute(
                """INSERT INTO users (role_id, name, email, password, phone)
                   VALUES (1, %s, %s, %s, %s)""",
                (name, email, hashed_password, phone)
            )
            connection.commit()
            cursor.close()

            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for("login"))

        except Exception:
            connection.rollback()
            flash("Unable to create account. Please try again.", "danger")
            return redirect(url_for("register"))
        finally:
            connection.close()

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# =========================================================
# USER / CLIENT ROUTES
# =========================================================

@app.route("/user/dashboard")
@role_required("user")
def user_dashboard():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    # KPI CARDS - counts for the logged-in user only
    cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE user_id = %s", (user_id,))
    total_appointments = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE user_id = %s AND appointment_date = CURDATE() AND status != 'cancelled'",
        (user_id,)
    )
    today_appointments = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE user_id = %s AND status = 'pending'",
        (user_id,)
    )
    pending_appointments = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE user_id = %s AND status = 'completed'",
        (user_id,)
    )
    completed_appointments = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE user_id = %s AND appointment_date >= CURDATE() AND status IN ('pending','confirmed')",
        (user_id,)
    )
    upcoming_appointments = cursor.fetchone()["total"]

    # Upcoming appointments list (next 5)
    cursor.execute(
        """SELECT a.*, s.name AS service_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.user_id = %s AND a.appointment_date >= CURDATE() AND a.status IN ('pending','confirmed')
           ORDER BY a.appointment_date ASC, a.start_time ASC
           LIMIT 5""",
        (user_id,)
    )
    upcoming_list = cursor.fetchall()

    # Recent activity (last 5 history entries for this user's appointments)
    cursor.execute(
        """SELECT h.*, a.appointment_date, s.name AS service_name
           FROM appointment_history h
           JOIN appointments a ON h.appointment_id = a.id
           JOIN services s ON a.service_id = s.id
           WHERE a.user_id = %s
           ORDER BY h.created_at DESC
           LIMIT 5""",
        (user_id,)
    )
    recent_activity = cursor.fetchall()

    # Notifications (last 5, unread first)
    cursor.execute(
        """SELECT * FROM notifications WHERE user_id = %s
           ORDER BY is_read ASC, created_at DESC LIMIT 5""",
        (user_id,)
    )
    notifications = cursor.fetchall()

    # Chart data: My Appointment Activity for the last 6 months
    cursor.execute(
        """SELECT DATE_FORMAT(appointment_date, '%%Y-%%m') AS ym, COUNT(*) AS total
           FROM appointments
           WHERE user_id = %s AND appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
           GROUP BY ym ORDER BY ym""",
        (user_id,)
    )
    chart_rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "user/dashboard.html",
        total_appointments=total_appointments,
        today_appointments=today_appointments,
        pending_appointments=pending_appointments,
        completed_appointments=completed_appointments,
        upcoming_appointments=upcoming_appointments,
        upcoming_list=upcoming_list,
        recent_activity=recent_activity,
        notifications=notifications,
        chart_rows=chart_rows
    )


@app.route("/user/appointments")
@role_required("user")
def user_appointments():
    user_id = session["user_id"]

    status_filter = request.args.get("status", "")
    date_filter = request.args.get("date", "")
    search_query = request.args.get("q", "")

    connection = get_connection()
    cursor = connection.cursor()

    query = """SELECT a.*, s.name AS service_name, pu.name AS provider_name
               FROM appointments a
               JOIN services s ON a.service_id = s.id
               JOIN providers p ON a.provider_id = p.id
               JOIN users pu ON p.user_id = pu.id
               WHERE a.user_id = %s"""
    params = [user_id]

    if status_filter:
        query += " AND a.status = %s"
        params.append(status_filter)

    if date_filter:
        query += " AND a.appointment_date = %s"
        params.append(date_filter)

    if search_query:
        query += " AND (s.name LIKE %s OR pu.name LIKE %s)"
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term])

    query += " ORDER BY a.appointment_date DESC, a.start_time DESC"

    cursor.execute(query, params)
    appointments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "user/appointments.html",
        appointments=appointments,
        status_filter=status_filter,
        date_filter=date_filter,
        search_query=search_query
    )


@app.route("/user/appointment/<int:appointment_id>")
@role_required("user")
def user_view_appointment(appointment_id):
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """SELECT a.*, s.name AS service_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.id = %s""",
        (appointment_id,)
    )
    appointment = cursor.fetchone()

    if appointment is None or appointment["user_id"] != user_id:
        # Ownership check: a user may only view their OWN appointment.
        cursor.close()
        connection.close()
        abort(403)

    cursor.execute(
        "SELECT * FROM appointment_history WHERE appointment_id = %s ORDER BY created_at DESC",
        (appointment_id,)
    )
    history = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("user/appointment_view.html", appointment=appointment, history=history)


@app.route("/user/book", methods=["GET", "POST"])
@role_required("user")
def book_appointment():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY name")
    services = cursor.fetchall()

    cursor.execute(
        """SELECT p.id, pu.name AS provider_name, p.service_id
           FROM providers p JOIN users pu ON p.user_id = pu.id
           WHERE p.is_active = 1 ORDER BY pu.name"""
    )
    providers = cursor.fetchall()

    if request.method == "POST":
        service_id = request.form.get("service_id")
        provider_id = request.form.get("provider_id")
        date_string = request.form.get("appointment_date")
        time_string = request.form.get("start_time")
        notes = request.form.get("notes", "").strip()

        appointment_date = parse_date(date_string)
        start_time = parse_time(time_string)

        # ---- VALIDATION CHECKS ----

        # 1. Date must not be in the past
        if appointment_date is None or appointment_date < date_cls.today():
            flash("Invalid date.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # 2. Time must be valid
        if start_time is None:
            flash("Invalid date.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # 3. Provider must exist and be active
        cursor.execute(
            "SELECT * FROM providers WHERE id = %s AND is_active = 1", (provider_id,)
        )
        provider = cursor.fetchone()
        if provider is None:
            flash("Selected provider is unavailable.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # 4. Service must exist and must match the provider's assigned service
        cursor.execute("SELECT * FROM services WHERE id = %s AND is_active = 1", (service_id,))
        service = cursor.fetchone()
        if service is None:
            flash("Unable to book appointment.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        if str(provider["service_id"]) != str(service_id):
            flash("Selected provider is unavailable.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # Calculate end_time using the service duration
        start_datetime = datetime.combine(appointment_date, start_time)
        end_datetime = start_datetime + timedelta(minutes=service["duration"])
        end_time = end_datetime.time()

        # 5. Provider must be scheduled to work at this day/time
        if not check_provider_schedule(provider_id, appointment_date, start_time, service["duration"]):
            flash("Selected provider is unavailable.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # 6. Provider must not already have an appointment at this time
        if check_blocked_period(provider_id, appointment_date, start_time, service["duration"]):
            flash("The selected time is blocked by the provider. Please choose another time.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        if check_provider_conflict(provider_id, appointment_date, start_time, duration=service['duration']):
            flash("Schedule conflict detected. Please choose another time.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # 7. The user must not already have another appointment at this time
        if check_user_conflict(user_id, appointment_date, start_time, duration=service['duration']):
            flash("Schedule conflict detected. Please choose another time.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("book_appointment"))

        # ---- SAVE THE APPOINTMENT ----
        try:
            cursor.execute(
                """INSERT INTO appointments
                   (user_id, provider_id, service_id, appointment_date, start_time, end_time, status, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)""",
                (user_id, provider_id, service_id, appointment_date, start_time, end_time, notes)
            )
            connection.commit()
            new_appointment_id = cursor.lastrowid
            cursor.close()
            connection.close()

            log_history(new_appointment_id, "created", None, "pending", user_id)
            create_notification(
                user_id,
                f"Your appointment for {service['name']} on {appointment_date} has been booked and is pending confirmation.",
                "info"
            )
            create_notification(
                provider["user_id"],
                f"New appointment request for {service['name']} on {appointment_date}.",
                "info"
            )

            flash("Appointment booked successfully.", "success")
            return redirect(url_for("user_appointments"))

        except Exception:
            connection.rollback()
            cursor.close()
            connection.close()
            flash("Unable to book appointment.", "danger")
            return redirect(url_for("book_appointment"))

    cursor.close()
    connection.close()
    return render_template("user/book.html", services=services, providers=providers)


@app.route("/user/appointment/<int:appointment_id>/reschedule", methods=["GET", "POST"])
@role_required("user")
def reschedule_appointment(appointment_id):
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """SELECT a.*, s.name AS service_name, s.duration, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.id = %s""",
        (appointment_id,)
    )
    appointment = cursor.fetchone()

    if appointment is None or appointment["user_id"] != user_id:
        cursor.close()
        connection.close()
        abort(403)

    if appointment["status"] not in ("pending", "confirmed"):
        cursor.close()
        connection.close()
        flash("This appointment can no longer be rescheduled.", "danger")
        return redirect(url_for("user_appointments"))

    if request.method == "POST":
        date_string = request.form.get("appointment_date")
        time_string = request.form.get("start_time")

        new_date = parse_date(date_string)
        new_time = parse_time(time_string)

        if new_date is None or new_date < date_cls.today() or new_time is None:
            flash("Invalid date.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("reschedule_appointment", appointment_id=appointment_id))

        provider_id = appointment["provider_id"]

        if not check_provider_schedule(provider_id, new_date, new_time, appointment["duration"]):
            flash("Selected provider is unavailable.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("reschedule_appointment", appointment_id=appointment_id))

        if check_blocked_period(provider_id, new_date, new_time, appointment["duration"]):
            flash("The selected time is blocked by the provider.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("reschedule_appointment", appointment_id=appointment_id))

        if check_provider_conflict(provider_id, new_date, new_time, exclude_appointment_id=appointment_id, duration=appointment['duration']):
            flash("Schedule conflict detected. Please choose another time.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("reschedule_appointment", appointment_id=appointment_id))

        if check_user_conflict(user_id, new_date, new_time, exclude_appointment_id=appointment_id, duration=appointment['duration']):
            flash("Schedule conflict detected. Please choose another time.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("reschedule_appointment", appointment_id=appointment_id))

        start_datetime = datetime.combine(new_date, new_time)
        end_datetime = start_datetime + timedelta(minutes=appointment["duration"])
        new_end_time = end_datetime.time()

        try:
            cursor.execute(
                """UPDATE appointments SET appointment_date = %s, start_time = %s, end_time = %s,
                   status = 'pending' WHERE id = %s""",
                (new_date, new_time, new_end_time, appointment_id)
            )
            connection.commit()
            cursor.close()
            connection.close()

            log_history(appointment_id, "rescheduled", appointment["status"], "pending", user_id)
            create_notification(user_id, f"Your appointment for {appointment['service_name']} has been rescheduled to {new_date}.", "info")

            flash("Appointment rescheduled successfully.", "success")
            return redirect(url_for("user_appointments"))

        except Exception:
            connection.rollback()
            cursor.close()
            connection.close()
            flash("Unable to reschedule appointment.", "danger")
            return redirect(url_for("reschedule_appointment", appointment_id=appointment_id))

    cursor.close()
    connection.close()
    return render_template("user/reschedule.html", appointment=appointment)


@app.route("/user/appointment/<int:appointment_id>/cancel", methods=["POST"])
@role_required("user")
def cancel_appointment(appointment_id):
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appointment = cursor.fetchone()

    if appointment is None or appointment["user_id"] != user_id:
        cursor.close()
        connection.close()
        abort(403)

    if appointment["status"] not in ("pending", "confirmed"):
        cursor.close()
        connection.close()
        flash("Unable to cancel appointment.", "danger")
        return redirect(url_for("user_appointments"))

    try:
        cursor.execute("UPDATE appointments SET status = 'cancelled' WHERE id = %s", (appointment_id,))
        connection.commit()
        cursor.close()
        connection.close()

        log_history(appointment_id, "cancelled", appointment["status"], "cancelled", user_id)
        create_notification(user_id, "Your appointment has been cancelled.", "warning")

        flash("Appointment cancelled successfully.", "success")
    except Exception:
        connection.rollback()
        cursor.close()
        connection.close()
        flash("Unable to cancel appointment.", "danger")

    return redirect(url_for("user_appointments"))


@app.route("/user/calendar")
@role_required("user")
def user_calendar():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT a.*, s.name AS service_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.user_id = %s AND a.status != 'cancelled'
           ORDER BY a.appointment_date ASC""",
        (user_id,)
    )
    appointments = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("user/calendar.html", appointments=appointments)


@app.route("/user/history")
@role_required("user")
def user_history():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT a.*, s.name AS service_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.user_id = %s AND a.status IN ('completed', 'cancelled', 'rejected', 'no_show')
           ORDER BY a.appointment_date DESC""",
        (user_id,)
    )
    appointments = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("user/history.html", appointments=appointments)


@app.route("/user/notifications")
@role_required("user")
def user_notifications():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
    )
    notifications = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("user/notifications.html", notifications=notifications)


@app.route("/user/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM notifications WHERE id = %s", (notification_id,))
    notification = cursor.fetchone()

    if notification is None or notification["user_id"] != user_id:
        cursor.close()
        connection.close()
        abort(403)

    try:
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = %s", (notification_id,))
        connection.commit()
        flash("Notification marked as read.", "success")
    except Exception:
        connection.rollback()
        flash("Unable to update notification.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(request.referrer or url_for("index"))


@app.route("/user/profile", methods=["GET", "POST"])
@login_required
def user_profile():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        new_password = request.form.get("new_password", "")

        try:
            if new_password:
                hashed_password = generate_password_hash(new_password)
                cursor.execute(
                    "UPDATE users SET name = %s, phone = %s, password = %s WHERE id = %s",
                    (name, phone, hashed_password, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET name = %s, phone = %s WHERE id = %s",
                    (name, phone, user_id)
                )
            connection.commit()
            session["name"] = name
            flash("Profile updated successfully.", "success")
        except Exception:
            connection.rollback()
            flash("Unable to update profile.", "danger")

    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()

    return render_template("user/profile.html", user=user)


# =========================================================
# PROVIDER / STAFF ROUTES
# =========================================================

@app.route("/provider/dashboard")
@role_required("provider")
def provider_dashboard():
    provider_id = get_provider_id_for_user(session["user_id"])
    if provider_id is None:
        abort(403)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE provider_id = %s AND appointment_date = CURDATE() AND status != 'cancelled'",
        (provider_id,)
    )
    today_count = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE provider_id = %s AND status = 'pending'",
        (provider_id,)
    )
    pending_count = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE provider_id = %s AND status = 'confirmed'",
        (provider_id,)
    )
    confirmed_count = cursor.fetchone()["total"]

    cursor.execute(
        "SELECT COUNT(*) AS total FROM appointments WHERE provider_id = %s AND status = 'completed'",
        (provider_id,)
    )
    completed_count = cursor.fetchone()["total"]

    # Simple conflict detector: two non-cancelled appointments sharing the same date/time
    cursor.execute(
        """SELECT appointment_date, start_time, COUNT(*) AS total
           FROM appointments
           WHERE provider_id = %s AND status != 'cancelled'
           GROUP BY appointment_date, start_time
           HAVING COUNT(*) > 1""",
        (provider_id,)
    )
    conflicts = cursor.fetchall()

    cursor.execute(
        """SELECT a.*, s.name AS service_name, u.name AS client_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN users u ON a.user_id = u.id
           WHERE a.provider_id = %s AND a.appointment_date = CURDATE() AND a.status != 'cancelled'
           ORDER BY a.start_time ASC""",
        (provider_id,)
    )
    todays_schedule = cursor.fetchall()

    cursor.execute(
        """SELECT a.*, s.name AS service_name, u.name AS client_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN users u ON a.user_id = u.id
           WHERE a.provider_id = %s AND a.appointment_date > CURDATE() AND a.status IN ('pending','confirmed')
           ORDER BY a.appointment_date ASC, a.start_time ASC
           LIMIT 5""",
        (provider_id,)
    )
    upcoming = cursor.fetchall()

    cursor.execute(
        """SELECT h.*, a.appointment_date, s.name AS service_name
           FROM appointment_history h
           JOIN appointments a ON h.appointment_id = a.id
           JOIN services s ON a.service_id = s.id
           WHERE a.provider_id = %s
           ORDER BY h.created_at DESC LIMIT 5""",
        (provider_id,)
    )
    recent_activity = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM provider_schedules WHERE provider_id = %s ORDER BY day_of_week", (provider_id,)
    )
    availability = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "provider/dashboard.html",
        today_count=today_count,
        pending_count=pending_count,
        confirmed_count=confirmed_count,
        completed_count=completed_count,
        conflicts=conflicts,
        todays_schedule=todays_schedule,
        upcoming=upcoming,
        recent_activity=recent_activity,
        availability=availability,
        day_names=DAY_NAMES
    )


@app.route("/provider/appointments")
@role_required("provider")
def provider_appointments():
    provider_id = get_provider_id_for_user(session["user_id"])
    if provider_id is None:
        abort(403)

    status_filter = request.args.get("status", "")
    date_filter = request.args.get("date", "")
    search_query = request.args.get("q", "")

    connection = get_connection()
    cursor = connection.cursor()

    query = """SELECT a.*, s.name AS service_name, u.name AS client_name
               FROM appointments a
               JOIN services s ON a.service_id = s.id
               JOIN users u ON a.user_id = u.id
               WHERE a.provider_id = %s"""
    params = [provider_id]

    if status_filter:
        query += " AND a.status = %s"
        params.append(status_filter)
    if date_filter:
        query += " AND a.appointment_date = %s"
        params.append(date_filter)
    if search_query:
        query += " AND u.name LIKE %s"
        params.append(f"%{search_query}%")

    query += " ORDER BY a.appointment_date DESC, a.start_time DESC"
    cursor.execute(query, params)
    appointments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "provider/appointments.html",
        appointments=appointments,
        status_filter=status_filter,
        date_filter=date_filter,
        search_query=search_query
    )


def _provider_update_status(appointment_id, new_status, allowed_old_statuses, success_message):
    """Shared logic for provider confirm/complete/cancel actions."""
    provider_id = get_provider_id_for_user(session["user_id"])
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appointment = cursor.fetchone()

    if appointment is None or appointment["provider_id"] != provider_id:
        cursor.close()
        connection.close()
        abort(403)

    if appointment["status"] not in allowed_old_statuses:
        cursor.close()
        connection.close()
        flash(f"Unable to update appointment.", "danger")
        return redirect(url_for("provider_appointments"))

    try:
        cursor.execute("UPDATE appointments SET status = %s WHERE id = %s", (new_status, appointment_id))
        connection.commit()
        cursor.close()
        connection.close()

        log_history(appointment_id, new_status, appointment["status"], new_status, session["user_id"])
        create_notification(appointment["user_id"], success_message, "success" if new_status != "cancelled" else "warning")

        flash(success_message, "success")
    except Exception:
        connection.rollback()
        cursor.close()
        connection.close()
        flash("Unable to update appointment.", "danger")

    return redirect(url_for("provider_appointments"))


@app.route("/provider/appointment/<int:appointment_id>/confirm", methods=["POST"])
@role_required("provider")
def provider_confirm_appointment(appointment_id):
    return _provider_update_status(
        appointment_id, "confirmed", ["pending"],
        "Appointment confirmed successfully."
    )


@app.route("/provider/appointment/<int:appointment_id>/reject", methods=["POST"])
@role_required("provider")
def provider_reject_appointment(appointment_id):
    return _provider_update_status(
        appointment_id, "rejected", ["pending"],
        "Appointment request rejected."
    )


@app.route("/provider/appointment/<int:appointment_id>/complete", methods=["POST"])
@role_required("provider")
def provider_complete_appointment(appointment_id):
    return _provider_update_status(
        appointment_id, "completed", ["confirmed"],
        "Appointment marked as completed."
    )


@app.route("/provider/appointment/<int:appointment_id>/cancel", methods=["POST"])
@role_required("provider")
def provider_cancel_appointment(appointment_id):
    return _provider_update_status(
        appointment_id, "cancelled", ["pending", "confirmed"],
        "Appointment cancelled successfully."
    )


@app.route("/provider/appointment/<int:appointment_id>/no-show", methods=["POST"])
@role_required("provider")
def provider_mark_no_show(appointment_id):
    return _provider_update_status(
        appointment_id, "no_show", ["confirmed"],
        "Appointment marked as did not attend."
    )


@app.route("/provider/schedule", methods=["GET", "POST"])
@role_required("provider")
def provider_schedule():
    provider_id = get_provider_id_for_user(session["user_id"])
    if provider_id is None:
        abort(403)

    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "POST":
        day_of_week = request.form.get("day_of_week")
        start_time = parse_time(request.form.get("start_time"))
        end_time = parse_time(request.form.get("end_time"))

        if start_time is None or end_time is None or start_time >= end_time:
            flash("Invalid date.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("provider_schedule"))

        try:
            cursor.execute(
                """INSERT INTO provider_schedules (provider_id, day_of_week, start_time, end_time, is_available)
                   VALUES (%s, %s, %s, %s, 1)""",
                (provider_id, day_of_week, start_time, end_time)
            )
            connection.commit()
            flash("Profile updated successfully.", "success")
        except Exception:
            connection.rollback()
            flash("Unable to update profile.", "danger")

    cursor.execute("SELECT * FROM provider_schedules WHERE provider_id = %s ORDER BY day_of_week", (provider_id,))
    schedules = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template("provider/schedule.html", schedules=schedules, day_names=DAY_NAMES)


@app.route("/provider/schedule/<int:schedule_id>/toggle", methods=["POST"])
@role_required("provider")
def provider_toggle_schedule(schedule_id):
    provider_id = get_provider_id_for_user(session["user_id"])
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM provider_schedules WHERE id = %s", (schedule_id,))
    schedule_row = cursor.fetchone()

    if schedule_row is None or schedule_row["provider_id"] != provider_id:
        cursor.close()
        connection.close()
        abort(403)

    new_value = 0 if schedule_row["is_available"] else 1
    try:
        cursor.execute("UPDATE provider_schedules SET is_available = %s WHERE id = %s", (new_value, schedule_id))
        connection.commit()
        flash("Profile updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Unable to update profile.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("provider_schedule"))


@app.route("/provider/notifications")
@role_required("provider")
def provider_notifications():
    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    notifications = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("provider/notifications.html", notifications=notifications)


# =========================================================
# ADMIN ROUTES
# =========================================================

@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM appointments")
    total_appointments = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE appointment_date = CURDATE() AND status != 'cancelled'")
    today_appointments = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE status = 'pending'")
    pending_appointments = cursor.fetchone()["total"]

    cursor.execute(
        """SELECT COUNT(*) AS total FROM appointments
           WHERE status = 'completed' AND MONTH(appointment_date) = MONTH(CURDATE())
           AND YEAR(appointment_date) = YEAR(CURDATE())"""
    )
    completed_this_month = cursor.fetchone()["total"]

    cursor.execute(
        """SELECT appointment_date, start_time, provider_id, COUNT(*) AS total
           FROM appointments WHERE status != 'cancelled'
           GROUP BY appointment_date, start_time, provider_id
           HAVING COUNT(*) > 1"""
    )
    conflict_rows = cursor.fetchall()
    conflict_count = len(conflict_rows)

    # Appointment trends - last 6 months
    cursor.execute(
        """SELECT DATE_FORMAT(appointment_date, '%%Y-%%m') AS ym, COUNT(*) AS total
           FROM appointments
           WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
           GROUP BY ym ORDER BY ym"""
    )
    trend_rows = cursor.fetchall()

    cursor.execute(
        """SELECT a.*, s.name AS service_name, u.name AS client_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN users u ON a.user_id = u.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.appointment_date >= CURDATE() AND a.status IN ('pending','confirmed')
           ORDER BY a.appointment_date ASC, a.start_time ASC
           LIMIT 6"""
    )
    upcoming = cursor.fetchall()

    cursor.execute(
        """SELECT a.*, s.name AS service_name, u.name AS client_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN users u ON a.user_id = u.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.appointment_date = CURDATE() AND a.status != 'cancelled'
           ORDER BY a.start_time ASC"""
    )
    todays_appointments = cursor.fetchall()

    cursor.execute(
        """SELECT p.id, pu.name AS provider_name, s.name AS service_name,
                  COUNT(a.id) AS total_appointments
           FROM providers p
           JOIN users pu ON p.user_id = pu.id
           JOIN services s ON p.service_id = s.id
           LEFT JOIN appointments a ON a.provider_id = p.id AND a.status != 'cancelled'
           GROUP BY p.id, pu.name, s.name
           ORDER BY total_appointments DESC"""
    )
    staff_overview = cursor.fetchall()

    cursor.execute(
        """SELECT h.*, a.appointment_date, s.name AS service_name, u.name AS client_name, perf.name AS performed_by_name
           FROM appointment_history h
           JOIN appointments a ON h.appointment_id = a.id
           JOIN services s ON a.service_id = s.id
           JOIN users u ON a.user_id = u.id
           JOIN users perf ON h.performed_by = perf.id
           ORDER BY h.created_at DESC LIMIT 8"""
    )
    recent_activity = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/dashboard.html",
        total_appointments=total_appointments,
        today_appointments=today_appointments,
        pending_appointments=pending_appointments,
        completed_this_month=completed_this_month,
        conflict_count=conflict_count,
        conflict_rows=conflict_rows,
        trend_rows=trend_rows,
        upcoming=upcoming,
        todays_appointments=todays_appointments,
        staff_overview=staff_overview,
        recent_activity=recent_activity
    )


@app.route("/admin/appointments")
@role_required("admin")
def admin_appointments():
    status_filter = request.args.get("status", "")
    date_filter = request.args.get("date", "")
    provider_filter = request.args.get("provider_id", "")
    service_filter = request.args.get("service_id", "")
    search_query = request.args.get("q", "")

    connection = get_connection()
    cursor = connection.cursor()

    query = """SELECT a.*, s.name AS service_name, u.name AS client_name, pu.name AS provider_name
               FROM appointments a
               JOIN services s ON a.service_id = s.id
               JOIN users u ON a.user_id = u.id
               JOIN providers p ON a.provider_id = p.id
               JOIN users pu ON p.user_id = pu.id
               WHERE 1=1"""
    params = []

    if status_filter:
        query += " AND a.status = %s"
        params.append(status_filter)
    if date_filter:
        query += " AND a.appointment_date = %s"
        params.append(date_filter)
    if provider_filter:
        query += " AND a.provider_id = %s"
        params.append(provider_filter)
    if service_filter:
        query += " AND a.service_id = %s"
        params.append(service_filter)
    if search_query:
        query += " AND (u.name LIKE %s OR pu.name LIKE %s OR s.name LIKE %s)"
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term, like_term])

    query += " ORDER BY a.appointment_date DESC, a.start_time DESC"
    cursor.execute(query, params)
    appointments = cursor.fetchall()

    cursor.execute(
        """SELECT p.id, pu.name AS provider_name FROM providers p
           JOIN users pu ON p.user_id = pu.id ORDER BY pu.name"""
    )
    providers = cursor.fetchall()

    cursor.execute("SELECT * FROM services ORDER BY name")
    services = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/appointments.html",
        appointments=appointments,
        providers=providers,
        services=services,
        status_filter=status_filter,
        date_filter=date_filter,
        provider_filter=provider_filter,
        service_filter=service_filter,
        search_query=search_query
    )


@app.route("/admin/appointment/<int:appointment_id>/status", methods=["POST"])
@role_required("admin")
def admin_update_status(appointment_id):
    new_status = request.form.get("status")
    if new_status not in STATUS_LIST:
        flash("Unable to update appointment.", "danger")
        return redirect(url_for("admin_appointments"))

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appointment = cursor.fetchone()

    if appointment is None:
        cursor.close()
        connection.close()
        abort(404)

    try:
        cursor.execute("UPDATE appointments SET status = %s WHERE id = %s", (new_status, appointment_id))
        connection.commit()
        cursor.close()
        connection.close()

        log_history(appointment_id, new_status, appointment["status"], new_status, session["user_id"])
        write_audit(session["user_id"], new_status, "appointment", appointment_id,
                    f"Status changed from {appointment['status']} to {new_status}")
        create_notification(appointment["user_id"], f"Your appointment status was updated to {new_status}.", "info")

        flash("Appointment updated successfully.", "success")
    except Exception:
        connection.rollback()
        cursor.close()
        connection.close()
        flash("Unable to update appointment.", "danger")

    return redirect(url_for("admin_appointments"))


@app.route("/admin/clients")
@role_required("admin")
def admin_clients():
    search_query = request.args.get("q", "")

    connection = get_connection()
    cursor = connection.cursor()

    query = """SELECT u.*,
               (SELECT COUNT(*) FROM appointments WHERE user_id = u.id) AS total_appointments
               FROM users u WHERE u.role_id = 1"""
    params = []

    if search_query:
        query += " AND (u.name LIKE %s OR u.email LIKE %s)"
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term])

    query += " ORDER BY u.name"
    cursor.execute(query, params)
    clients = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("admin/clients.html", clients=clients, search_query=search_query)


@app.route("/admin/clients/<int:client_id>")
@role_required("admin")
def admin_view_client(client_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM users WHERE id = %s AND role_id = 1", (client_id,))
    client = cursor.fetchone()
    if client is None:
        cursor.close()
        connection.close()
        abort(404)

    cursor.execute(
        """SELECT a.*, s.name AS service_name, pu.name AS provider_name
           FROM appointments a
           JOIN services s ON a.service_id = s.id
           JOIN providers p ON a.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           WHERE a.user_id = %s ORDER BY a.appointment_date DESC""",
        (client_id,)
    )
    appointments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("admin/client_view.html", client=client, appointments=appointments)


@app.route("/admin/clients/<int:client_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_client(client_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s AND role_id = 1", (client_id,))
    client = cursor.fetchone()

    if client is None:
        cursor.close()
        connection.close()
        abort(404)

    new_value = 0 if client["is_active"] else 1
    try:
        cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_value, client_id))
        connection.commit()
        flash("Profile updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Database error occurred.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_clients"))


@app.route("/admin/providers")
@role_required("admin")
def admin_providers():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT p.*, pu.name AS provider_name, pu.email, pu.phone, s.name AS service_name,
                  (SELECT COUNT(*) FROM appointments WHERE provider_id = p.id) AS total_appointments
           FROM providers p
           JOIN users pu ON p.user_id = pu.id
           JOIN services s ON p.service_id = s.id
           ORDER BY pu.name"""
    )
    providers = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("admin/providers.html", providers=providers)


@app.route("/admin/providers/add", methods=["GET", "POST"])
@role_required("admin")
def admin_add_provider():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY name")
    services = cursor.fetchall()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        service_id = request.form.get("service_id")

        if not name or not email or not password or not service_id:
            flash("Please fill out all required fields.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("admin_add_provider"))

        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash("An account with this email already exists.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for("admin_add_provider"))

        try:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (role_id, name, email, password, phone) VALUES (2, %s, %s, %s, %s)",
                (name, email, hashed_password, phone)
            )
            new_user_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO providers (user_id, service_id, is_active) VALUES (%s, %s, 1)",
                (new_user_id, service_id)
            )
            connection.commit()
            cursor.close()
            connection.close()

            flash("Provider added successfully.", "success")
            return redirect(url_for("admin_providers"))
        except Exception:
            connection.rollback()
            cursor.close()
            connection.close()
            flash("Database error occurred.", "danger")
            return redirect(url_for("admin_add_provider"))

    cursor.close()
    connection.close()
    return render_template("admin/provider_form.html", services=services, provider=None)


@app.route("/admin/providers/<int:provider_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_edit_provider(provider_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """SELECT p.*, pu.name, pu.email, pu.phone FROM providers p
           JOIN users pu ON p.user_id = pu.id WHERE p.id = %s""",
        (provider_id,)
    )
    provider = cursor.fetchone()
    if provider is None:
        cursor.close()
        connection.close()
        abort(404)

    cursor.execute("SELECT * FROM services WHERE is_active = 1 ORDER BY name")
    services = cursor.fetchall()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        service_id = request.form.get("service_id")

        try:
            cursor.execute("UPDATE users SET name = %s, phone = %s WHERE id = %s", (name, phone, provider["user_id"]))
            cursor.execute("UPDATE providers SET service_id = %s WHERE id = %s", (service_id, provider_id))
            connection.commit()
            cursor.close()
            connection.close()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("admin_providers"))
        except Exception:
            connection.rollback()
            cursor.close()
            connection.close()
            flash("Unable to update profile.", "danger")
            return redirect(url_for("admin_edit_provider", provider_id=provider_id))

    cursor.close()
    connection.close()
    return render_template("admin/provider_form.html", services=services, provider=provider)


@app.route("/admin/providers/<int:provider_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_provider(provider_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM providers WHERE id = %s", (provider_id,))
    provider = cursor.fetchone()

    if provider is None:
        cursor.close()
        connection.close()
        abort(404)

    new_value = 0 if provider["is_active"] else 1
    try:
        cursor.execute("UPDATE providers SET is_active = %s WHERE id = %s", (new_value, provider_id))
        connection.commit()
        flash("Profile updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Database error occurred.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_providers"))


@app.route("/admin/providers/<int:provider_id>/schedule")
@role_required("admin")
def admin_view_provider_schedule(provider_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """SELECT p.*, pu.name FROM providers p JOIN users pu ON p.user_id = pu.id WHERE p.id = %s""",
        (provider_id,)
    )
    provider = cursor.fetchone()
    if provider is None:
        cursor.close()
        connection.close()
        abort(404)

    cursor.execute("SELECT * FROM provider_schedules WHERE provider_id = %s ORDER BY day_of_week", (provider_id,))
    schedules = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("admin/provider_schedule_view.html", provider=provider, schedules=schedules, day_names=DAY_NAMES)


@app.route("/admin/users")
@role_required("admin")
def admin_users():
    search_query = request.args.get("q", "")
    role_filter = request.args.get("role", "")

    connection = get_connection()
    cursor = connection.cursor()

    query = """SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE 1=1"""
    params = []

    if role_filter:
        query += " AND r.name = %s"
        params.append(role_filter)
    if search_query:
        query += " AND (u.name LIKE %s OR u.email LIKE %s)"
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term])

    query += " ORDER BY u.created_at DESC"
    cursor.execute(query, params)
    users = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("admin/users.html", users=users, search_query=search_query, role_filter=role_filter)


@app.route("/admin/users/<int:target_user_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_user(target_user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (target_user_id,))
    target_user = cursor.fetchone()

    if target_user is None:
        cursor.close()
        connection.close()
        abort(404)

    new_value = 0 if target_user["is_active"] else 1
    try:
        cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_value, target_user_id))
        connection.commit()
        flash("Profile updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Database error occurred.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_users"))


@app.route("/admin/schedules")
@role_required("admin")
def admin_schedules():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT ps.*, pu.name AS provider_name FROM provider_schedules ps
           JOIN providers p ON ps.provider_id = p.id
           JOIN users pu ON p.user_id = pu.id
           ORDER BY pu.name, ps.day_of_week"""
    )
    schedules = cursor.fetchall()

    cursor.execute(
        """SELECT p.id, pu.name AS provider_name FROM providers p
           JOIN users pu ON p.user_id = pu.id ORDER BY pu.name"""
    )
    providers = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("admin/schedules.html", schedules=schedules, providers=providers, day_names=DAY_NAMES)


@app.route("/admin/schedules/add", methods=["POST"])
@role_required("admin")
def admin_add_schedule():
    provider_id = request.form.get("provider_id")
    day_of_week = request.form.get("day_of_week")
    start_time = parse_time(request.form.get("start_time"))
    end_time = parse_time(request.form.get("end_time"))

    if not provider_id or start_time is None or end_time is None or start_time >= end_time:
        flash("Invalid date.", "danger")
        return redirect(url_for("admin_schedules"))

    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """INSERT INTO provider_schedules (provider_id, day_of_week, start_time, end_time, is_available)
               VALUES (%s, %s, %s, %s, 1)""",
            (provider_id, day_of_week, start_time, end_time)
        )
        connection.commit()
        flash("Profile updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Database error occurred.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_schedules"))


@app.route("/admin/schedules/<int:schedule_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_schedule(schedule_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM provider_schedules WHERE id = %s", (schedule_id,))
    schedule_row = cursor.fetchone()

    if schedule_row is None:
        cursor.close()
        connection.close()
        abort(404)

    new_value = 0 if schedule_row["is_available"] else 1
    try:
        cursor.execute("UPDATE provider_schedules SET is_available = %s WHERE id = %s", (new_value, schedule_id))
        connection.commit()
        flash("Profile updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Database error occurred.", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_schedules"))


@app.route("/admin/analytics")
@role_required("admin")
def admin_analytics():
    connection = get_connection()
    cursor = connection.cursor()

    # 1. Appointment trends (last 6 months)
    cursor.execute(
        """SELECT DATE_FORMAT(appointment_date, '%%Y-%%m') AS ym, COUNT(*) AS total
           FROM appointments
           WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
           GROUP BY ym ORDER BY ym"""
    )
    trend_rows = cursor.fetchall()

    # 2. Status distribution
    cursor.execute("SELECT status, COUNT(*) AS total FROM appointments GROUP BY status")
    status_rows = cursor.fetchall()

    # 3. Appointments by provider
    cursor.execute(
        """SELECT pu.name AS provider_name, COUNT(a.id) AS total
           FROM providers p
           JOIN users pu ON p.user_id = pu.id
           LEFT JOIN appointments a ON a.provider_id = p.id
           GROUP BY pu.name ORDER BY total DESC"""
    )
    provider_rows = cursor.fetchall()

    # 4. Appointments by service
    cursor.execute(
        """SELECT s.name AS service_name, COUNT(a.id) AS total
           FROM services s
           LEFT JOIN appointments a ON a.service_id = s.id
           GROUP BY s.name ORDER BY total DESC"""
    )
    service_rows = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE status = 'completed'")
    completed_total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE status = 'cancelled'")
    cancelled_total = cursor.fetchone()["total"]

    cursor.close()
    connection.close()

    return render_template(
        "admin/analytics.html",
        trend_rows=trend_rows,
        status_rows=status_rows,
        provider_rows=provider_rows,
        service_rows=service_rows,
        completed_total=completed_total,
        cancelled_total=cancelled_total
    )



# =========================================================
# EXTRA BLUEPRINT REQUIREMENTS: SERVICES, BLOCKED TIME,
# FORECASTING, REPORT EXPORT, AND AUDIT LOGS
# =========================================================

@app.route("/admin/services", methods=["GET", "POST"])
@role_required("admin")
def admin_services():
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        duration = request.form.get("duration", "30")
        try:
            duration = int(duration)
            if not name or duration < 1:
                raise ValueError()
            service_id = request.form.get("service_id")
            if service_id:
                cursor.execute("UPDATE services SET name=%s, description=%s, duration=%s WHERE id=%s",
                               (name, description, duration, service_id))
                action = "Updated service"
            else:
                cursor.execute("INSERT INTO services (name, description, duration) VALUES (%s,%s,%s)",
                               (name, description, duration))
                action = "Created service"
            connection.commit()
            write_audit(session["user_id"], action, "service", service_id, name)
            flash("Service saved successfully.", "success")
        except (ValueError, TypeError):
            connection.rollback()
            flash("Enter a service name and a positive duration.", "danger")
        except Exception:
            connection.rollback()
            flash("Unable to save service. Check whether the name is valid.", "danger")
        finally:
            cursor.close()
            connection.close()
        return redirect(url_for("admin_services"))

    cursor.execute("SELECT * FROM services ORDER BY name")
    services = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("admin/services.html", services=services)


@app.route("/admin/services/<int:service_id>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_service(service_id):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT is_active FROM services WHERE id=%s", (service_id,))
        row = cursor.fetchone()
        if not row:
            abort(404)
        new_status = 0 if row["is_active"] else 1
        cursor.execute("UPDATE services SET is_active=%s WHERE id=%s", (new_status, service_id))
        connection.commit()
        write_audit(session["user_id"], "Activated" if new_status else "Deactivated",
                    "service", service_id, None)
        flash("Service status updated successfully.", "success")
    except Exception:
        connection.rollback()
        flash("Unable to update service status.", "danger")
    finally:
        cursor.close()
        connection.close()
    return redirect(url_for("admin_services"))


@app.route("/provider/blocked-periods", methods=["GET", "POST"])
@role_required("provider")
def provider_blocked_periods():
    provider_id = get_provider_id_for_user(session["user_id"])
    if not provider_id:
        abort(403)
    connection = get_connection()
    cursor = connection.cursor()
    if request.method == "POST":
        start_value = request.form.get("start_datetime", "")
        end_value = request.form.get("end_datetime", "")
        reason = request.form.get("reason", "").strip()
        try:
            start_dt = datetime.strptime(start_value, "%Y-%m-%dT%H:%M")
            end_dt = datetime.strptime(end_value, "%Y-%m-%dT%H:%M")
            if start_dt <= datetime.now() or end_dt <= start_dt:
                raise ValueError()
            cursor.execute(
                """INSERT INTO blocked_periods (provider_id,start_datetime,end_datetime,reason,created_by)
                   VALUES (%s,%s,%s,%s,%s)""",
                (provider_id, start_dt, end_dt, reason, session["user_id"])
            )
            connection.commit()
            write_audit(session["user_id"], "Blocked time", "blocked_period", cursor.lastrowid, reason)
            flash("Unavailable period added successfully.", "success")
        except ValueError:
            connection.rollback()
            flash("Enter a valid future period; end must be after start.", "danger")
        except Exception:
            connection.rollback()
            flash("Unable to add unavailable period.", "danger")
        finally:
            cursor.close()
            connection.close()
        return redirect(url_for("provider_blocked_periods"))
    cursor.execute("SELECT * FROM blocked_periods WHERE provider_id=%s ORDER BY start_datetime DESC", (provider_id,))
    periods = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("provider/blocked_periods.html", periods=periods)


@app.route("/provider/blocked-periods/<int:period_id>/delete", methods=["POST"])
@role_required("provider")
def provider_delete_blocked_period(period_id):
    provider_id = get_provider_id_for_user(session["user_id"])
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM blocked_periods WHERE id=%s AND provider_id=%s", (period_id, provider_id))
        if cursor.rowcount == 0:
            abort(404)
        connection.commit()
        write_audit(session["user_id"], "Removed blocked time", "blocked_period", period_id)
        flash("Unavailable period removed.", "success")
    except Exception:
        connection.rollback()
        flash("Unable to remove unavailable period.", "danger")
    finally:
        cursor.close()
        connection.close()
    return redirect(url_for("provider_blocked_periods"))


def build_weekly_forecast():
    """Small, transparent ordinary least-squares model; no extra ML package required."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT DATE_SUB(appointment_date, INTERVAL WEEKDAY(appointment_date) DAY) AS week_start,
               COUNT(*) AS appointment_count,
               SUM(status='no_show') AS no_show_count
        FROM appointments
        WHERE status IN ('pending','confirmed','completed','cancelled','rejected','no_show')
        GROUP BY week_start ORDER BY week_start
    """)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    if len(rows) < 8:
        return {"available": False, "message": "Insufficient historical data for forecasting. At least 8 weeks with appointment records are required.", "rows": rows}

    def model(values):
        n = len(values)
        xs = list(range(1, n + 1))
        split = max(2, int(n * 0.8))
        train_x, train_y = xs[:split], values[:split]
        mean_x = sum(train_x) / len(train_x)
        mean_y = sum(train_y) / len(train_y)
        denominator = sum((x - mean_x) ** 2 for x in train_x)
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(train_x, train_y)) / denominator if denominator else 0
        intercept = mean_y - slope * mean_x
        test_actual = values[split:]
        test_pred = [max(0, intercept + slope * x) for x in xs[split:]]
        errors = [actual - pred for actual, pred in zip(test_actual, test_pred)]
        mae = sum(abs(e) for e in errors) / len(errors) if errors else None
        rmse = (sum(e * e for e in errors) / len(errors)) ** 0.5 if errors else None
        mean_test = sum(test_actual) / len(test_actual) if test_actual else 0
        ss_tot = sum((y - mean_test) ** 2 for y in test_actual)
        r2 = 1 - sum(e * e for e in errors) / ss_tot if errors and ss_tot else None
        full_mean_x = sum(xs) / n
        full_mean_y = sum(values) / n
        full_den = sum((x - full_mean_x) ** 2 for x in xs)
        full_slope = sum((x-full_mean_x)*(y-full_mean_y) for x,y in zip(xs,values))/full_den if full_den else 0
        full_intercept = full_mean_y-full_slope*full_mean_x
        return {"mae": mae, "rmse": rmse, "r2": r2,
                "forecast": [max(0, round(full_intercept + full_slope * (n + i))) for i in range(1, 5)]}

    appointment_model = model([int(row["appointment_count"] or 0) for row in rows])
    no_show_model = model([int(row["no_show_count"] or 0) for row in rows])
    last_monday = rows[-1]["week_start"]
    future = [{"week_start": last_monday + timedelta(days=7*i),
               "appointments": appointment_model["forecast"][i-1],
               "no_shows": no_show_model["forecast"][i-1]} for i in range(1,5)]
    return {"available": True, "rows": rows, "future": future,
            "appointment_model": appointment_model, "no_show_model": no_show_model}


@app.route("/admin/forecast")
@role_required("admin")
def admin_forecast():
    return render_template("admin/forecast.html", forecast=build_weekly_forecast())


@app.route("/admin/reports")
@role_required("admin")
def admin_reports():
    return render_template("admin/reports.html")


@app.route("/admin/reports/appointments.csv")
@role_required("admin")
def export_appointments_csv():
    import csv, io
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT a.id, u.name AS client, pu.name AS provider, s.name AS service,
               a.appointment_date, a.start_time, a.end_time, a.status, a.created_at
        FROM appointments a JOIN users u ON a.user_id=u.id
        JOIN providers p ON a.provider_id=p.id JOIN users pu ON p.user_id=pu.id
        JOIN services s ON a.service_id=s.id
        ORDER BY a.appointment_date DESC, a.start_time DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Appointment ID","Client","Provider","Service","Date","Start","End","Status","Created"])
    for row in rows:
        writer.writerow([row["id"], row["client"], row["provider"], row["service"],
                         row["appointment_date"], row["start_time"], row["end_time"], row["status"], row["created_at"]])
    from flask import Response
    return Response("\\ufeff" + output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=agende_appointments.csv"})


@app.route("/admin/audit-logs")
@role_required("admin")
def admin_audit_logs():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT a.*, u.name AS user_name FROM audit_logs a
        LEFT JOIN users u ON a.user_id=u.id
        ORDER BY a.created_at DESC LIMIT 300
    """)
    logs = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template("admin/audit_logs.html", logs=logs)


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(403)
def forbidden(e):
    return render_template("error_403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error_404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
