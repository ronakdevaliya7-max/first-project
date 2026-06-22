import io
import sqlite3, os, time
import csv
from datetime import date, timedelta

from flask import Flask, render_template, request, redirect, session, send_from_directory, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "attendance-dev-secret")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config["DATABASE_PATH"] = os.environ.get(
    "ATTENDANCE_DB_PATH",
    os.path.join(BASE_DIR, "users.db")
)
app.jinja_env.filters["display_date"] = lambda value: format_display_date(value)

TIMETABLE_META = {
    "title": "DS3 - [B.C.A & B.Sc.I.T. Sem-4]",
    "subtitle": "Classroom no. 208, Computer Lab. 6&8 Ground Floor",
}
TIMETABLE_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
TIMETABLE_ROWS = [
    {
        "number": "1",
        "time": "07:30 to 08:25",
        "courses": {
            "Monday": "",
            "Tuesday": "PHP",
            "Wednesday": "Java",
            "Thursday": "",
            "Friday": "",
            "Saturday": "DBMS",
        },
    },
    {
        "number": "2",
        "time": "08:25 to 09:20",
        "courses": {
            "Monday": "",
            "Tuesday": "Python",
            "Wednesday": "AI",
            "Thursday": "Math",
            "Friday": "",
            "Saturday": "PHP",
        },
    },
    {
        "number": "",
        "time": "09:20 to 09:50",
        "courses": {},
        "is_break": True,
    },
    {
        "number": "3",
        "time": "09:50 to 10:45",
        "courses": {
            "Monday": "DBMS",
            "Tuesday": "Java",
            "Wednesday": "PHP",
            "Thursday": "Python",
            "Friday": "AI",
            "Saturday": "Math",
        },
    },
    {
        "number": "4",
        "time": "10:45 to 11:40",
        "courses": {
            "Monday": "Math",
            "Tuesday": "AI",
            "Wednesday": "",
            "Thursday": "Java",
            "Friday": "DBMS",
            "Saturday": "",
        },
    },
    {
        "number": "",
        "time": "11:40 to 11:50",
        "courses": {},
        "is_break": True,
    },
    {
        "number": "5",
        "time": "11:50 to 12:45",
        "courses": {
            "Monday": "PHP",
            "Tuesday": "Python",
            "Wednesday": "",
            "Thursday": "Math",
            "Friday": "AI",
            "Saturday": "",
        },
    },
    {
        "number": "6",
        "time": "12:45 to 01:40",
        "courses": {
            "Monday": "Java",
            "Tuesday": "",
            "Wednesday": "",
            "Thursday": "",
            "Friday": "DBMS",
            "Saturday": "",
        },
    },
]
EXAM_PAGES = {
    "course_selection": {
        "title": "Course Selection",
        "description": "Select your exam courses for the current term.",
        "kind": "course",
    },
    "regular_form": {
        "title": "Regular Exam Form",
        "description": "Fill your regular exam form details before submission.",
        "kind": "form",
    },
    "schedule_hall_ticket": {
        "title": "Exam Schedule / Hall Ticket",
        "description": "Check your exam schedule and hall ticket information.",
        "kind": "schedule",
    },
    "cia_marks": {
        "title": "CIA Marks",
        "description": "Review internal assessment marks for selected subjects.",
        "kind": "marks",
    },
    "repeater_form": {
        "title": "Repeater Exam Form",
        "description": "Apply for repeater exam subjects and keep the form ready.",
        "kind": "form",
    },
    "result_reassessment": {
        "title": "Result and Reassessment",
        "description": "View result status and apply for reassessment when available.",
        "kind": "result",
    },
    "online_login": {
        "title": "Online Exam Login Detail",
        "description": "Find online exam login details and exam portal instructions.",
        "kind": "login",
    },
}
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# DATABASE
def db():
    con = sqlite3.connect(app.config["DATABASE_PATH"])
    con.row_factory = sqlite3.Row
    return con


def redirect_for_role(role):
    if role == "admin":
        return redirect("/admin")
    if role == "teacher":
        return redirect("/teacher")
    return redirect("/home")


def normalize_login_role(role):
    role = (role or "").strip().lower()
    return role if role in {"admin", "teacher", "student"} else ""


def authenticate_user(username, password):
    with db() as con:
        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

    if user and check_password_hash(user["password"], password):
        return user

    return None


def current_user():
    if "user" not in session:
        return None

    with db() as con:
        return con.execute(
            "SELECT * FROM users WHERE username=?",
            (session["user"],)
        ).fetchone()


def current_teacher_record(con=None):
    username = session.get("user")
    if not username:
        return None

    owns_connection = con is None
    if owns_connection:
        con = db()

    try:
        return con.execute(
            """
            SELECT *
            FROM teachers
            WHERE username=?
            ORDER BY id
            LIMIT 1
            """,
            (username,)
        ).fetchone()
    finally:
        if owns_connection:
            con.close()


def get_student_leave_requests(con, status_filter="", limit=None):
    query = """
        SELECT
            student_leaves.id,
            student_leaves.student_id,
            student_leaves.leave_kind,
            student_leaves.leave_type,
            student_leaves.from_date,
            student_leaves.to_date,
            student_leaves.remarks,
            student_leaves.status,
            student_leaves.created_at,
            users.username,
            users.rollno,
            users.enroll
        FROM student_leaves
        JOIN users ON users.id = student_leaves.student_id
        WHERE users.role='student'
    """
    params = []

    if status_filter:
        query += " AND student_leaves.status=?"
        params.append(status_filter)

    query += " ORDER BY student_leaves.from_date DESC, student_leaves.id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    return con.execute(query, tuple(params)).fetchall()


def get_attendance_day_name(attendance_date):
    try:
        return date.fromisoformat(attendance_date).strftime("%A")
    except (TypeError, ValueError):
        return ""


def format_display_date(value):
    try:
        return date.fromisoformat(value).strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        return value or "-"


def format_timetable_range(start_time, end_time):
    if start_time and end_time:
        return f"{start_time} to {end_time}"
    return start_time or end_time or ""


def split_timetable_range(value):
    parts = [part.strip() for part in (value or "").split("to", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return value or "", ""


def get_seed_timetable_subjects():
    return sorted({
        course
        for row in TIMETABLE_ROWS
        if not row.get("is_break")
        for course in row["courses"].values()
        if course
    })


def seed_timetable_schedule(con):
    existing_rows = con.execute("SELECT COUNT(*) FROM timetable_schedule").fetchone()[0]
    if existing_rows:
        return

    for row_order, row in enumerate(TIMETABLE_ROWS, start=1):
        start_time, end_time = split_timetable_range(row.get("time"))

        if row.get("is_break"):
            con.execute(
                """
                INSERT INTO timetable_schedule(
                    row_order, period_number, day_name, start_time, end_time, lecture_name, is_break
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                (row_order, row.get("number", ""), "", start_time, end_time, "", 1)
            )
            continue

        for day_name in TIMETABLE_DAYS:
            con.execute(
                """
                INSERT INTO timetable_schedule(
                    row_order, period_number, day_name, start_time, end_time, lecture_name, is_break
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    row_order,
                    row.get("number", ""),
                    day_name,
                    start_time,
                    end_time,
                    row.get("courses", {}).get(day_name, ""),
                    0,
                )
            )


def fetch_timetable_rows(con):
    rows = con.execute(
        """
        SELECT row_order, period_number, day_name, start_time, end_time, lecture_name, is_break
        FROM timetable_schedule
        ORDER BY row_order,
            CASE day_name
                WHEN 'Monday' THEN 1
                WHEN 'Tuesday' THEN 2
                WHEN 'Wednesday' THEN 3
                WHEN 'Thursday' THEN 4
                WHEN 'Friday' THEN 5
                WHEN 'Saturday' THEN 6
                ELSE 7
            END,
            id
        """
    ).fetchall()

    grouped_rows = []
    current = None
    current_row_order = None

    for row in rows:
        if row["row_order"] != current_row_order:
            current_row_order = row["row_order"]
            current = {
                "number": row["period_number"] or "",
                "start_time": row["start_time"] or "",
                "end_time": row["end_time"] or "",
                "time": format_timetable_range(row["start_time"], row["end_time"]),
                "courses": {day: "" for day in TIMETABLE_DAYS},
                "is_break": bool(row["is_break"]),
            }
            grouped_rows.append(current)

        if row["is_break"]:
            current["is_break"] = True
            continue

        day_name = row["day_name"] or ""
        if day_name in current["courses"]:
            current["courses"][day_name] = row["lecture_name"] or ""

    return grouped_rows


def save_timetable_rows(con, rows):
    con.execute("DELETE FROM timetable_schedule")

    for row_order, row in enumerate(rows, start=1):
        start_time = (row.get("start_time") or "").strip()
        end_time = (row.get("end_time") or "").strip()
        period_number = (row.get("number") or "").strip()

        if row.get("is_break"):
            con.execute(
                """
                INSERT INTO timetable_schedule(
                    row_order, period_number, day_name, start_time, end_time, lecture_name, is_break
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                (row_order, period_number, "", start_time, end_time, "", 1)
            )
            continue

        for day_name in TIMETABLE_DAYS:
            con.execute(
                """
                INSERT INTO timetable_schedule(
                    row_order, period_number, day_name, start_time, end_time, lecture_name, is_break
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    row_order,
                    period_number,
                    day_name,
                    start_time,
                    end_time,
                    (row.get("courses", {}).get(day_name) or "").strip(),
                    0,
                )
            )


def get_weekly_timetable(con=None):
    owns_connection = con is None
    if owns_connection:
        con = db()

    try:
        rows = fetch_timetable_rows(con)
    finally:
        if owns_connection:
            con.close()

    return {
        "meta": TIMETABLE_META,
        "days": TIMETABLE_DAYS,
        "rows": rows or TIMETABLE_ROWS,
    }


def get_day_timetable_slots(day_name, con=None):
    owns_connection = con is None
    if owns_connection:
        con = db()

    try:
        rows = fetch_timetable_rows(con)
    finally:
        if owns_connection:
            con.close()

    slots = []
    for row in rows or TIMETABLE_ROWS:
        if row.get("is_break"):
            continue
        lecture_name = row["courses"].get(day_name, "")
        if lecture_name:
            slots.append({
                "lecture_name": lecture_name,
                "time": row["time"],
            })
    return slots


def expected_timetable_lecture_count(start_date, total_days, con=None):
    total_lectures = 0
    for day_offset in range(total_days):
        current_date = start_date + timedelta(days=day_offset)
        day_name = current_date.strftime("%A")
        if day_name == "Sunday":
            continue
        total_lectures += len(get_day_timetable_slots(day_name, con))
    return total_lectures


def build_timetable_editor_rows(rows):
    editor_rows = []
    source_rows = rows or TIMETABLE_ROWS

    for row in source_rows:
        start_time = (row.get("start_time") or "").strip()
        end_time = (row.get("end_time") or "").strip()
        if not start_time and not end_time:
            start_time, end_time = split_timetable_range(row.get("time"))

        editor_rows.append({
            "number": row.get("number", ""),
            "start_time": start_time,
            "end_time": end_time,
            "is_break": bool(row.get("is_break")),
            "courses": {day: (row.get("courses", {}).get(day, "") if not row.get("is_break") else "") for day in TIMETABLE_DAYS},
        })

    return editor_rows


def get_students_on_approved_leave(con, target_date):
    if not target_date:
        return {}

    rows = con.execute(
        """
        SELECT
            student_id,
            leave_kind,
            leave_type,
            from_date,
            to_date
        FROM student_leaves
        WHERE status='Approved'
          AND from_date <= ?
          AND to_date >= ?
        """,
        (target_date, target_date)
    ).fetchall()

    return {
        row["student_id"]: {
            "leave_kind": row["leave_kind"],
            "leave_type": row["leave_type"],
            "from_date": row["from_date"],
            "to_date": row["to_date"],
        }
        for row in rows
    }


def calculate_student_percentage(data):
    def row_value(row, key):
        if isinstance(row, dict):
            return row.get(key)
        return row[key] if key in row.keys() else None

    present = sum(1 for row in data if row["status"] == "Present")
    absent = sum(1 for row in data if row["status"] == "Absent")
    leave = sum(1 for row in data if row["status"] == "Leave")
    eligible_total = present + absent
    base_percent = round((present / eligible_total) * 100) if eligible_total else 0

    return {
        "present": present,
        "absent": absent,
        "leave": leave,
        "eligible_total": eligible_total,
        "base_percent": base_percent,
        "penalty": 0,
        "recovery": 0,
        "percent": base_percent,
    }


def safe_percent(part, total):
    return round((part * 100 / total), 0) if total else 0


def get_recent_attendance_chart(con, limit=5):
    rows = con.execute(
        """
        SELECT
            lecture_attendance.date,
            SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
            SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
        FROM lecture_attendance
        GROUP BY lecture_attendance.date
        ORDER BY lecture_attendance.date DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    chart_rows = []
    for row in reversed(rows):
        chart_rows.append({
            "label": format_display_date(row["date"]),
            "value": int(safe_percent(row["present_count"] or 0, row["total_count"] or 0)),
        })

    return chart_rows


def get_teacher_snapshot_chart(con):
    all_rows = get_recent_attendance_chart(con, limit=3)
    week_start = (date.today() - timedelta(days=6)).isoformat()
    week_rows = con.execute(
        """
        SELECT
            lecture_attendance.date,
            SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
            SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
        FROM lecture_attendance
        WHERE lecture_attendance.date >= ?
        GROUP BY lecture_attendance.date
        ORDER BY lecture_attendance.date DESC
        LIMIT 3
        """,
        (week_start,)
    ).fetchall()

    week_chart = []
    for row in reversed(week_rows):
        week_chart.append({
            "label": format_display_date(row["date"]),
            "value": int(safe_percent(row["present_count"] or 0, row["total_count"] or 0)),
        })

    return {
        "all": all_rows,
        "week": week_chart or all_rows,
    }


def normalize_teacher_username(username):
    cleaned = (username or "").strip().lower()
    if cleaned in {"", "-", "none", "null", "n/a", "na"}:
        return ""
    return cleaned


def build_unique_teacher_username(con, name, preferred_username=""):
    base_username = normalize_teacher_username(preferred_username)
    if not base_username:
        base_username = "".join(ch.lower() for ch in (name or "") if ch.isalnum())
    if not base_username:
        base_username = "teacher"

    candidate = base_username
    suffix = 1
    while con.execute(
        "SELECT 1 FROM users WHERE username=? UNION SELECT 1 FROM teachers WHERE username=?",
        (candidate, candidate)
    ).fetchone():
        candidate = f"{base_username}{suffix}"
        suffix += 1
    return candidate


def build_teacher_username(name, explicit_username=""):
    username = normalize_teacher_username(explicit_username)
    if username:
        return username

    base_username = "".join(ch.lower() for ch in (name or "") if ch.isalnum())
    return base_username or f"teacher{int(time.time())}"


def normalize_teacher_records(con):
    teachers = con.execute(
        "SELECT id, name, username, mobile FROM teachers ORDER BY id"
    ).fetchall()

    for teacher in teachers:
        raw_username = teacher["username"]
        normalized_username = normalize_teacher_username(raw_username)
        linked_user = None

        if raw_username:
            linked_user = con.execute(
                "SELECT id, username FROM users WHERE username=? AND role='teacher'",
                (raw_username,)
            ).fetchone()

        if linked_user and not normalized_username:
            new_username = build_unique_teacher_username(con, teacher["name"])
            con.execute(
                "UPDATE teachers SET username=? WHERE id=?",
                (new_username, teacher["id"])
            )
            con.execute(
                "UPDATE users SET username=? WHERE id=?",
                (new_username, linked_user["id"])
            )
            continue

        if normalized_username and normalized_username != raw_username:
            con.execute(
                "UPDATE teachers SET username=? WHERE id=?",
                (normalized_username, teacher["id"])
            )
            if linked_user:
                con.execute(
                    "UPDATE users SET username=? WHERE id=?",
                    (normalized_username, linked_user["id"])
                )
            continue

        if not normalized_username and teacher["mobile"]:
            mobile_user = con.execute(
                """
                SELECT id, username
                FROM users
                WHERE mobile=? AND role='teacher'
                ORDER BY id
                """,
                (teacher["mobile"],)
            ).fetchone()
            if mobile_user and normalize_teacher_username(mobile_user["username"]):
                con.execute(
                    "UPDATE teachers SET username=? WHERE id=?",
                    (mobile_user["username"], teacher["id"])
                )
                continue

        if not normalized_username:
            con.execute(
                "UPDATE teachers SET username=? WHERE id=?",
                (build_unique_teacher_username(con, teacher["name"]), teacher["id"])
            )


def initialize_database():
    with db() as con:

        # Ensure role exists in users table for admin vs student
        try:
            con.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'")
        except sqlite3.OperationalError:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rollno INTEGER,
            username TEXT UNIQUE,
            password TEXT,
            gender TEXT,
            mobile TEXT,
            address TEXT,
            photo TEXT,
            enroll TEXT,
            blood TEXT,
            school TEXT,
            birthdate TEXT,
            class TEXT,
            role TEXT DEFAULT 'student'
        )
        """)

        try:
            con.execute("ALTER TABLE users ADD COLUMN class TEXT")
        except sqlite3.OperationalError:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            status TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS lectures(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lecture_date TEXT,
            day TEXT,
            lecture_name TEXT,
            time TEXT
        )
        """)

        try:
            con.execute("ALTER TABLE lectures ADD COLUMN lecture_date TEXT")
        except sqlite3.OperationalError:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS lecture_attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            lecture_no INTEGER,
            status TEXT
        )
        """)

        try:
            con.execute("ALTER TABLE lecture_attendance ADD COLUMN lecture_day TEXT")
        except sqlite3.OperationalError:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS student_leaves(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            leave_kind TEXT,
            leave_type TEXT,
            from_date TEXT,
            to_date TEXT,
            remarks TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        try:
            con.execute("ALTER TABLE lecture_attendance ADD COLUMN lecture_name TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            con.execute("ALTER TABLE lecture_attendance ADD COLUMN lecture_time TEXT")
        except sqlite3.OperationalError:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS teachers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            mobile TEXT,
            username TEXT,
            course TEXT,
            subject TEXT
        )
        """)

        try:
            con.execute("ALTER TABLE teachers ADD COLUMN username TEXT")
        except sqlite3.OperationalError:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS teacher_attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            date TEXT,
            status TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS courses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS subjects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            course TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS lecture_slots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT,
            end_time TEXT,
            slot_order INTEGER
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS timetable_settings(
            id INTEGER PRIMARY KEY CHECK (id = 1),
            start_date TEXT,
            total_days INTEGER
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS timetable_schedule(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_order INTEGER NOT NULL,
            period_number TEXT,
            day_name TEXT,
            start_time TEXT,
            end_time TEXT,
            lecture_name TEXT,
            is_break INTEGER NOT NULL DEFAULT 0
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS festivals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            festival_date TEXT,
            day TEXT,
            name TEXT,
            holiday_type TEXT,
            note TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS class_subjects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_num INTEGER,
            subject_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS class_notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_num INTEGER,
            subject TEXT,
            message TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS class_timetable(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_num INTEGER,
            day_name TEXT,
            period_number INTEGER,
            start_time TEXT,
            end_time TEXT,
            subject_name TEXT,
            teacher_name TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS teacher_notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_num INTEGER,
            subject TEXT,
            message TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS fee_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            class_num TEXT,
            fee_type TEXT,
            amount REAL,
            payment_method TEXT,
            remarks TEXT,
            status TEXT DEFAULT 'Pending',
            receipt_no TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS student_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject TEXT,
            message TEXT,
            message_type TEXT DEFAULT 'General',
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS exam_cia_marks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            class_num TEXT,
            subject TEXT,
            marks REAL,
            total_marks REAL DEFAULT 25,
            exam_term TEXT DEFAULT 'CIA',
            entered_by TEXT,
            remarks TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, subject, exam_term)
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS exam_result_declarations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_num TEXT,
            exam_term TEXT DEFAULT 'Sem - III',
            examination TEXT DEFAULT 'November - 2025',
            programme TEXT DEFAULT 'Bachelor of Computer Application',
            is_declared INTEGER DEFAULT 0,
            declared_by TEXT,
            declared_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(class_num, exam_term)
        )
        """)

        admin_user = con.execute("SELECT * FROM users WHERE username=?", ("admin",)).fetchone()
        if not admin_user:
            con.execute("""
            INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,role)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                0,
                "admin",
                generate_password_hash("admin123"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "admin"
            ))

        atmiya_user = con.execute("SELECT * FROM users WHERE username=?", ("atmiya",)).fetchone()
        if not atmiya_user:
            con.execute("""
            INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,role)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                0,
                "atmiya",
                generate_password_hash("atmiya123"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "teacher"
            ))

        demo_student = con.execute("SELECT * FROM users WHERE username=?", ("student",)).fetchone()
        if not demo_student:
            con.execute("""
            INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,class,role)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                1,
                "student",
                generate_password_hash("student123"),
                "",
                "",
                "",
                "",
                "ENR-DEMO-001",
                "",
                "Demo School",
                "",
                "10",
                "student"
            ))

        default_course = "BCA"
        seed_timetable_schedule(con)

        default_subjects = get_seed_timetable_subjects()

        existing_course = con.execute(
            "SELECT id FROM courses WHERE name=?",
            (default_course,)
        ).fetchone()
        if not existing_course:
            con.execute(
                "INSERT INTO courses(name,description) VALUES (?,?)",
                (default_course, "Default course")
            )

        for subject_name in default_subjects:
            existing_subject = con.execute(
                "SELECT id FROM subjects WHERE name=? AND course=?",
                (subject_name, default_course)
            ).fetchone()
            if not existing_subject:
                con.execute(
                    "INSERT INTO subjects(name,course) VALUES (?,?)",
                    (subject_name, default_course)
                )

        default_slots = [
            ("07:30", "08:25", 1),
            ("08:25", "09:20", 2),
            ("09:50", "10:45", 3),
            ("10:45", "11:40", 4),
            ("11:50", "12:45", 5),
            ("12:45", "01:40", 6),
        ]
        slot_count = con.execute("SELECT COUNT(*) FROM lecture_slots").fetchone()[0]
        if slot_count == 0:
            con.executemany(
                "INSERT INTO lecture_slots(start_time,end_time,slot_order) VALUES (?,?,?)",
                default_slots
            )

        settings = con.execute("SELECT id FROM timetable_settings WHERE id=1").fetchone()
        if not settings:
            con.execute(
                "INSERT INTO timetable_settings(id,start_date,total_days) VALUES (1,?,?)",
                (date.today().isoformat(), 180)
            )

        con.execute("""
        UPDATE lecture_attendance
        SET
            lecture_day = COALESCE(
                NULLIF(lecture_day, ''),
                (SELECT day FROM lectures WHERE lectures.id = lecture_attendance.lecture_no)
            ),
            lecture_name = COALESCE(
                NULLIF(lecture_name, ''),
                (SELECT lecture_name FROM lectures WHERE lectures.id = lecture_attendance.lecture_no)
            ),
            lecture_time = COALESCE(
                NULLIF(lecture_time, ''),
                (SELECT time FROM lectures WHERE lectures.id = lecture_attendance.lecture_no)
            )
        WHERE
            COALESCE(lecture_day, '') = ''
            OR COALESCE(lecture_name, '') = ''
            OR COALESCE(lecture_time, '') = ''
        """)

        normalize_teacher_records(con)


def get_lecture_attendance_rows(con, where_clause="", params=()):
    query = f"""
    WITH dated_lectures AS (
        SELECT
            id,
            lecture_date,
            day,
            lecture_name,
            time,
            ROW_NUMBER() OVER (
                PARTITION BY lecture_date
                ORDER BY id
            ) AS slot_no
        FROM lectures
    ),
    attendance_slots AS (
        SELECT
            date,
            lecture_no,
            DENSE_RANK() OVER (
                PARTITION BY date
                ORDER BY lecture_no
            ) AS slot_no
        FROM (
                SELECT DISTINCT date, lecture_no
                FROM lecture_attendance
            )
        )
        SELECT
        lecture_attendance.date,
        COALESCE(
            NULLIF(lecture_attendance.lecture_day, ''),
            exact_lecture.day,
            slot_lecture.day,
            CASE strftime('%w', lecture_attendance.date)
                WHEN '0' THEN 'Sunday'
                WHEN '1' THEN 'Monday'
                WHEN '2' THEN 'Tuesday'
                WHEN '3' THEN 'Wednesday'
                WHEN '4' THEN 'Thursday'
                WHEN '5' THEN 'Friday'
                WHEN '6' THEN 'Saturday'
            END
        ) AS day,
        COALESCE(
            NULLIF(lecture_attendance.lecture_name, ''),
            exact_lecture.lecture_name,
            slot_lecture.lecture_name,
            CASE
                WHEN attendance_slots.slot_no IS NOT NULL THEN 'Lecture ' || attendance_slots.slot_no
            END
        ) AS lecture_name,
        COALESCE(
            NULLIF(lecture_attendance.lecture_time, ''),
            exact_lecture.time,
            slot_lecture.time,
            CASE
                WHEN lecture_slot.start_time IS NOT NULL AND lecture_slot.end_time IS NOT NULL
                THEN lecture_slot.start_time || ' - ' || lecture_slot.end_time
            END
        ) AS time,
        users.username,
        lecture_attendance.status
    FROM lecture_attendance
    JOIN users ON users.id = lecture_attendance.student_id
    LEFT JOIN dated_lectures AS exact_lecture
        ON exact_lecture.id = lecture_attendance.lecture_no
    LEFT JOIN attendance_slots
        ON attendance_slots.date = lecture_attendance.date
        AND attendance_slots.lecture_no = lecture_attendance.lecture_no
    LEFT JOIN dated_lectures AS slot_lecture
        ON slot_lecture.lecture_date = lecture_attendance.date
        AND slot_lecture.slot_no = attendance_slots.slot_no
        AND exact_lecture.id IS NULL
    LEFT JOIN lecture_slots AS lecture_slot
        ON lecture_slot.slot_order = attendance_slots.slot_no
    {where_clause}
    ORDER BY
        lecture_attendance.date DESC,
        COALESCE(
            NULLIF(lecture_attendance.lecture_time, ''),
            exact_lecture.time,
            slot_lecture.time,
            lecture_slot.start_time
        ),
        lecture_attendance.lecture_no,
        users.username
    """
    return con.execute(query, params).fetchall()


def get_student_attendance_report(student_id):
    with db() as con:
        student = con.execute(
            "SELECT id, username, rollno FROM users WHERE id=?",
            (student_id,)
        ).fetchone()

        lecture_data = get_lecture_attendance_rows(
            con,
            "WHERE lecture_attendance.student_id=?",
            (student_id,)
        )

        if lecture_data:
            data = [
                {
                    "date": row["date"],
                    "day": row["day"],
                    "lecture_name": row["lecture_name"],
                    "time": row["time"],
                    "status": row["status"],
                }
                for row in lecture_data
            ]
            report_type = "lecture"
        else:
            data = con.execute("""
            SELECT
                date,
                '' AS day,
                '' AS lecture_name,
                '' AS time,
                status
            FROM attendance
            WHERE student_id=?
            ORDER BY date DESC
            """, (student_id,)).fetchall()
            report_type = "daily"

    score = calculate_student_percentage(data)

    return {
        "student": student,
        "data": data,
        "present": score["present"],
        "absent": score["absent"],
        "leave": score["leave"],
        "base_percent": score["base_percent"],
        "penalty": score["penalty"],
        "recovery": score["recovery"],
        "percent": score["percent"],
        "report_type": report_type,
    }


def get_teacher_attendance_report(selected_date="", teacher_username="", teacher_id=None):
    with db() as con:
        teacher_filter = normalize_teacher_username(teacher_username)
        join_clause = "LEFT JOIN teacher_attendance ON teacher_attendance.teacher_id = teachers.id"
        summary_params = []
        if selected_date:
            join_clause = """
            LEFT JOIN teacher_attendance
                ON teacher_attendance.teacher_id = teachers.id
                AND teacher_attendance.date=?
            """
            summary_params.append(selected_date)

        summary_query = f"""
        SELECT
            teachers.id,
            TRIM(teachers.name) AS name,
            teachers.username,
            teachers.course,
            teachers.subject,
            SUM(CASE WHEN teacher_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
            SUM(CASE WHEN teacher_attendance.status='Absent' THEN 1 ELSE 0 END) AS absent_count,
            COUNT(teacher_attendance.id) AS total_count
        FROM teachers
        {join_clause}
        """
        detail_query = """
        SELECT
            teacher_attendance.date,
            teachers.id AS teacher_id,
            TRIM(teachers.name) AS name,
            teachers.username,
            teachers.course,
            teachers.subject,
            teacher_attendance.status
        FROM teacher_attendance
        JOIN teachers ON teachers.id = teacher_attendance.teacher_id
        """

        summary_where_parts = []
        detail_where_parts = []
        detail_params = []

        if teacher_filter:
            summary_where_parts.append("teachers.username=?")
            summary_params.append(teacher_filter)
            detail_where_parts.append("teachers.username=?")
            detail_params.append(teacher_filter)

        if teacher_id is not None:
            summary_where_parts.append("teachers.id=?")
            summary_params.append(teacher_id)
            detail_where_parts.append("teachers.id=?")
            detail_params.append(teacher_id)

        if selected_date:
            detail_where_parts.append("teacher_attendance.date=?")
            detail_params.append(selected_date)

        if summary_where_parts:
            summary_query += " WHERE " + " AND ".join(summary_where_parts)

        where_clause = ""
        if detail_where_parts:
            where_clause = " WHERE " + " AND ".join(detail_where_parts)

        summary = con.execute(
            summary_query + """
            GROUP BY teachers.id, teachers.name, teachers.username, teachers.course, teachers.subject
            ORDER BY TRIM(teachers.name), teachers.id
            """,
            tuple(summary_params)
        ).fetchall()

        details = con.execute(
            detail_query + where_clause + """
            ORDER BY teacher_attendance.date DESC, TRIM(teachers.name), teachers.id
            """,
            tuple(detail_params)
        ).fetchall()

    total_present = sum((row["present_count"] or 0) for row in summary)
    total_absent = sum((row["absent_count"] or 0) for row in summary)
    total_records = sum((row["total_count"] or 0) for row in summary)
    overall_percent = round((total_present / total_records) * 100) if total_records else 0

    chart_labels = [row["name"] or row["username"] or f"Teacher {row['id']}" for row in summary]
    chart_present = [row["present_count"] or 0 for row in summary]
    chart_absent = [row["absent_count"] or 0 for row in summary]

    return {
        "selected_date": selected_date,
        "summary": summary,
        "details": details,
        "total_present": total_present,
        "total_absent": total_absent,
        "total_records": total_records,
        "overall_percent": overall_percent,
        "chart_labels": chart_labels,
        "chart_present": chart_present,
        "chart_absent": chart_absent,
    }


def can_access_teacher_report(target_teacher_id):
    if "user" not in session:
        return False

    role = session.get("role")
    if role == "admin":
        return True

    if role != "teacher":
        return False

    with db() as con:
        teacher = current_teacher_record(con)
        return bool(teacher and teacher["id"] == target_teacher_id)


initialize_database()


# IMAGE VIEW
@app.route("/uploads/<filename>")
def uploaded(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


def get_timetable_settings(con):
    settings = con.execute(
        "SELECT start_date, total_days FROM timetable_settings WHERE id=1"
    ).fetchone()
    if not settings:
        return date.today().isoformat(), 180
    start_date = settings["start_date"] or date.today().isoformat()
    total_days = settings["total_days"] or 180
    try:
        date.fromisoformat(start_date)
    except ValueError:
        start_date = date.today().isoformat()
    if total_days < 1:
        total_days = 180
    return start_date, total_days


def parse_timetable_builder_form(form):
    try:
        row_count = int((form.get("row_count") or "0").strip())
    except ValueError:
        return [], "Please provide a valid timetable layout."

    rows = []
    for index in range(row_count):
        row_type = (form.get(f"row_type_{index}") or "lecture").strip().lower()
        start_time = (form.get(f"start_time_{index}") or "").strip()
        end_time = (form.get(f"end_time_{index}") or "").strip()
        period_number = (form.get(f"period_number_{index}") or "").strip()

        if row_type not in ("lecture", "break"):
            continue

        if not start_time or not end_time:
            return [], f"Row {index + 1} needs both start and end time."

        row = {
            "number": period_number,
            "start_time": start_time,
            "end_time": end_time,
            "is_break": row_type == "break",
            "courses": {day: "" for day in TIMETABLE_DAYS},
        }

        if row_type == "lecture":
            if not period_number:
                return [], f"Lecture row {index + 1} needs a period number."

            has_subject = False
            for day in TIMETABLE_DAYS:
                value = (form.get(f"lecture_{index}_{day.lower()}") or "").strip()
                row["courses"][day] = value
                has_subject = has_subject or bool(value)

            if not has_subject:
                return [], f"Lecture row {index + 1} needs at least one subject."

        rows.append(row)

    if not rows:
        return [], "Add at least one timetable row before saving."

    start_date = (form.get("start_date") or "").strip()
    total_days_value = (form.get("total_days") or "").strip()

    try:
        date.fromisoformat(start_date)
    except ValueError:
        return [], "Please choose a valid timetable start date."

    try:
        total_days = int(total_days_value)
    except ValueError:
        return [], "Please enter a valid total day count."

    if total_days < 1:
        return [], "Total days must be at least 1."

    return rows, ""


def build_timetable_editor_rows_from_form(form):
    try:
        row_count = int((form.get("row_count") or "0").strip())
    except ValueError:
        row_count = 0

    rows = []
    for index in range(row_count):
        row_type = (form.get(f"row_type_{index}") or "lecture").strip().lower()
        rows.append({
            "number": (form.get(f"period_number_{index}") or "").strip(),
            "start_time": (form.get(f"start_time_{index}") or "").strip(),
            "end_time": (form.get(f"end_time_{index}") or "").strip(),
            "is_break": row_type == "break",
            "courses": {
                day: (form.get(f"lecture_{index}_{day.lower()}") or "").strip()
                for day in TIMETABLE_DAYS
            },
        })
    return rows


def ensure_six_month_timetable(con, reset=False):
    start_date_text, total_days = get_timetable_settings(con)
    start_date = date.fromisoformat(start_date_text)
    expected_lecture_count = expected_timetable_lecture_count(start_date, total_days, con)
    lecture_count = con.execute("SELECT COUNT(*) FROM lectures").fetchone()[0]
    valid_dates_count = con.execute(
        "SELECT COUNT(*) FROM lectures WHERE lecture_date IS NOT NULL AND lecture_date != ''"
    ).fetchone()[0]
    first_lecture = con.execute(
        """
        SELECT lecture_name, time
        FROM lectures
        ORDER BY lecture_date, id
        LIMIT 1
        """
    ).fetchone()
    expected_first_lecture = None

    for day_offset in range(total_days):
        current_date = start_date + timedelta(days=day_offset)
        slots = get_day_timetable_slots(current_date.strftime("%A"), con)
        if slots:
            expected_first_lecture = slots[0]
            break

    if (
        not reset
        and lecture_count == expected_lecture_count
        and valid_dates_count == expected_lecture_count
        and first_lecture
        and expected_first_lecture
        and first_lecture["lecture_name"] == expected_first_lecture["lecture_name"]
        and first_lecture["time"] == expected_first_lecture["time"]
    ):
        return

    con.execute("DELETE FROM lectures")

    for day_offset in range(total_days):
        current_date = start_date + timedelta(days=day_offset)
        day_name = current_date.strftime("%A")
        if day_name == "Sunday":
            continue

        for slot in get_day_timetable_slots(day_name, con):
            con.execute("""
            INSERT INTO lectures(lecture_date,day,lecture_name,time)
            VALUES (?,?,?,?)
            """, (current_date.isoformat(), day_name, slot["lecture_name"], slot["time"]))


def ensure_festival_calendar(con, reset=False):
    festival_rows = con.execute("""
        SELECT id, festival_date
        FROM festivals
        WHERE festival_date IS NOT NULL AND festival_date != ''
    """).fetchall()

    for row in festival_rows:
        day = date.fromisoformat(row["festival_date"]).strftime("%A")
        con.execute("UPDATE festivals SET day=? WHERE id=?", (day, row["id"]))


# LANDING PAGE
@app.route("/", methods=["GET", "POST"])
def index():
    if "user" in session:
        return redirect_for_role(session.get("role"))
    return handle_login()


# LOGIN
def handle_login(expected_role=""):
    msg = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = authenticate_user(username, password)
        user_role = normalize_login_role(user["role"] if user else "")

        if user and user_role:
            session["user"] = user["username"]
            session["role"] = user_role
            return redirect_for_role(session["role"])

        msg = "Invalid username or password"

    return render_template("shared/login.html", msg=msg)


@app.route("/login", methods=["GET", "POST"])
def login():
    return handle_login()


@app.route("/student_login", methods=["GET", "POST"])
def student_login():
    return handle_login("student")


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    return handle_login("admin")


@app.route("/teacher_login", methods=["GET", "POST"])
def teacher_login():
    return handle_login("teacher")


@app.route("/teacher")
def teacher_dashboard():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "teacher":
        return redirect("/")
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE username=?", (session["user"],)).fetchone()
        selected_date = request.args.get("date", "").strip() or date.today().isoformat()
        end_date = selected_date
        week_start = (date.fromisoformat(selected_date) - timedelta(days=6)).isoformat()
        today_text = date.today().isoformat()
        students = con.execute("""
            SELECT
                users.*,
                users.username AS name,
                SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
            FROM users
            LEFT JOIN lecture_attendance ON lecture_attendance.student_id = users.id
            WHERE role='student'
            GROUP BY users.id
            ORDER BY rollno, name
            LIMIT 50
        """).fetchall()
        lectures = con.execute("""
            SELECT id, lecture_date, lecture_name, time
            FROM lectures
            ORDER BY lecture_date DESC, id DESC
            LIMIT 20
        """).fetchall()
        leave_requests = get_student_leave_requests(con, limit=10)
        pending_leave_count = con.execute(
            "SELECT COUNT(*) FROM student_leaves WHERE status='Pending'"
        ).fetchone()[0]
        today_classes = con.execute(
            "SELECT COUNT(*) FROM lectures WHERE lecture_date=?",
            (selected_date,)
        ).fetchone()[0]
        today_lectures = con.execute(
            """
            SELECT lecture_name, time
            FROM lectures
            WHERE lecture_date=?
            ORDER BY id
            LIMIT 5
            """,
            (selected_date,)
        ).fetchall()
        student_count = con.execute(
            "SELECT COUNT(*) FROM users WHERE role='student'"
        ).fetchone()[0]
        lecture_records_today = con.execute(
            """
            SELECT COUNT(*)
            FROM lecture_attendance
            WHERE date=? AND status IN ('Present', 'Absent', 'Leave')
            """,
            (selected_date,)
        ).fetchone()[0]
        expected_today_records = student_count * today_classes
        lecture_flow_percent = int(safe_percent(lecture_records_today, expected_today_records)) if expected_today_records else 0
        weekly_rows = con.execute(
            """
            SELECT COUNT(*)
            FROM lecture_attendance
            WHERE date >= ? AND date <= ?
            """,
            (week_start, end_date)
        ).fetchone()[0]
        teacher_chart = get_teacher_snapshot_chart(con)
        ensure_festival_calendar(con)
        upcoming_festival_count = con.execute(
            "SELECT COUNT(*) FROM festivals WHERE festival_date >= ?",
            (today_text,)
        ).fetchone()[0]
        next_festival = con.execute(
            """
            SELECT festival_date, name
            FROM festivals
            WHERE festival_date >= ?
            ORDER BY festival_date, id
            LIMIT 1
            """,
            (today_text,)
        ).fetchone()

    search_items = [
        {"label": "Daily Attendance", "meta": "Open attendance sheet", "url": "/attendance"},
        {"label": "Lecture Attendance", "meta": "Mark lecture-wise attendance", "url": "/lecture_attendance"},
        {"label": "Timetable", "meta": "Open lecture timetable", "url": "/timetable"},
        {"label": "Weekly Report", "meta": "Open weekly attendance report", "url": "/weekly_attendance"},
        {"label": "Teacher Attendance Report", "meta": "Open teacher attendance summary", "url": "/teacher_attendance_report"},
        {"label": "Festival Calendar", "meta": "View festival dates", "url": "/festivals"},
    ]

    for student in students:
        student_name = student["name"] or student["username"] or f"Student {student['id']}"
        search_items.append({
            "label": student_name,
            "meta": f"Student report | Roll No: {student['rollno'] or '-'}",
            "url": f"/report/{student['id']}"
        })

    for lecture in lectures:
        lecture_date = lecture["lecture_date"] or "No date"
        lecture_name = lecture["lecture_name"] or f"Lecture {lecture['id']}"
        lecture_time = lecture["time"] or "Time pending"
        search_items.append({
            "label": lecture_name,
            "meta": f"{lecture_date} | {lecture_time}",
            "url": "/lecture_attendance"
        })

    return render_template(
        "teacher/teacher.html",
        user=user,
        students=students,
        search_items=search_items,
        leave_requests=leave_requests,
        pending_leave_count=pending_leave_count,
        today_classes=today_classes,
        today_lectures=today_lectures,
        student_count=student_count,
        lecture_flow_percent=lecture_flow_percent,
        weekly_rows=weekly_rows,
        upcoming_festival_count=upcoming_festival_count,
        next_festival=next_festival,
        teacher_chart=teacher_chart,
        selected_date=selected_date,
        weekly_timetable=get_weekly_timetable(),
    )


@app.route("/teacher_students")
def teacher_students():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "teacher":
        return redirect("/")

    with db() as con:
        users = con.execute(
            """
            SELECT *
            FROM users
            WHERE role='student'
            ORDER BY class, rollno, username
            """
        ).fetchall()

    return render_template("teacher/teacher_students.html", users=users)


@app.route("/teacher_students_by_class")
def teacher_students_by_class():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "teacher":
        return redirect("/")

    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            count = con.execute(
                "SELECT COUNT(*) FROM users WHERE role='student' AND class=?",
                (str(class_num),)
            ).fetchone()[0]
            classes_data.append({
                "class_num": class_num,
                "count": count
            })

    return render_template("teacher/teacher_students_by_class.html", classes_data=classes_data)


@app.route("/teacher_students_by_class/<class_num>")
def teacher_students_in_class(class_num):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "teacher":
        return redirect("/")

    with db() as con:
        students = con.execute(
            """
            SELECT *
            FROM users
            WHERE role='student' AND class=?
            ORDER BY rollno, username
            """,
            (class_num,)
        ).fetchall()
        total_students = con.execute(
            "SELECT COUNT(*) FROM users WHERE role='student'"
        ).fetchone()[0]

    return render_template(
        "teacher/teacher_students_in_class.html",
        students=students,
        class_num=class_num,
        total_students=total_students
    )


# FORGOT PASSWORD
@app.route("/forgot_password", methods=["GET","POST"])
def forgot_password():
    msg = ""
    success = ""
    role = (request.values.get("role") or "").strip().lower()

    if role not in {"admin", "teacher", "student"}:
        role = ""
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        
        if not username or not new_password or not confirm_password:
            msg = "All fields are required"
        elif new_password != confirm_password:
            msg = "Passwords do not match"
        elif len(new_password) < 4:
            msg = "Password must be at least 4 characters"
        else:
            with db() as con:
                user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
                if not user:
                    msg = "Username not found"
                elif role and (user["role"] or "") != role:
                    msg = f"This username is not registered as a {role}"
                else:
                    hashed_password = generate_password_hash(new_password)
                    con.execute("UPDATE users SET password=? WHERE username=?", (hashed_password, username))
                    success = "Password reset successfully! Please login with your new password."
    
    return render_template("shared/forgot_password.html", msg=msg, success=success, role=role)


# SIGNUP
@app.route("/signup", methods=["GET","POST"])
def signup():
    requested_role = (request.values.get("role") or "").strip().lower()
    session_role = session.get("role", "")
    is_admin_session = session_role == "admin"

    if requested_role not in {"admin", "teacher", "student"}:
        requested_role = "student" if is_admin_session else ""

    if requested_role in {"admin", "teacher"} and "user" in session:
        return redirect_for_role(session_role)

    signup_role = requested_role or ("student" if is_admin_session else "")
    if not signup_role:
        return redirect("/")

    is_admin_student_signup = signup_role == "student" and is_admin_session

    if request.method == "POST":
        f = request.form
        file = request.files.get("photo")
        password = f.get("password", "")
        confirm_password = f.get("confirm_password", "")
        username = (f.get("username") or "").strip()
        rollno = (f.get("rollno") or "").strip()

        if not username or not password:
            return render_template(
                "shared/signup.html",
                msg="Username and password are required",
                signup_role=signup_role
            )

        if password != confirm_password:
            return render_template(
                "shared/signup.html",
                msg="Password and confirm password must match",
                signup_role=signup_role
            )

        filename = ""

        if signup_role == "student" and file and file.filename != "":
            filename = str(time.time()) + "_" + secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        with db() as con:
            check = con.execute(
                "SELECT * FROM users WHERE username=?",
                (username,)
            ).fetchone()

            if check:
                return render_template(
                    "shared/signup.html",
                    msg="Username already exists",
                    signup_role=signup_role
                )

            if signup_role == "teacher":
                teacher_name = (f.get("name") or "").strip()
                if not teacher_name:
                    return render_template(
                        "shared/signup.html",
                        msg="Teacher name is required",
                        signup_role=signup_role
                    )
                con.execute(
                    "INSERT INTO teachers(name,email,mobile,username,course,subject) VALUES (?,?,?,?,?,?)",
                    (
                        teacher_name,
                        f.get("email", ""),
                        f.get("mobile", ""),
                        username,
                        f.get("course", ""),
                        f.get("subject", "")
                    )
                )
                con.execute("""
                INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,role)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    0,
                    username,
                    generate_password_hash(password),
                    "",
                    f.get("mobile", ""),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "teacher"
                ))
                session["user"] = username
                session["role"] = "teacher"
                return redirect("/teacher")

            if signup_role == "admin":
                admin_name = (f.get("name") or "").strip()
                con.execute("""
                INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,role)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    0,
                    username,
                    generate_password_hash(password),
                    "",
                    f.get("mobile", ""),
                    admin_name,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "admin"
                ))
                session["user"] = username
                session["role"] = "admin"
                return redirect("/admin")

            con.execute("""
            INSERT INTO users
            (rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,class,role)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,(
                int(rollno) if rollno.isdigit() else None,
                username,
                generate_password_hash(password),
                f.get("gender", ""),
                f.get("mobile", ""),
                f.get("address", ""),
                filename,
                f.get("enroll", ""),
                f.get("blood", ""),
                f.get("school", ""),
                f.get("birthdate", ""),
                f.get("class", ""),
                "student"
            ))

        if is_admin_student_signup:
            return redirect("/list")
        session["user"] = username
        session["role"] = "student"
        return redirect("/home")

    return render_template("shared/signup.html", msg="", signup_role=signup_role)


# HOME
@app.route("/home")
def home():
    if "user" not in session:
        return redirect("/")

    if session.get("role") == "admin":
        return redirect("/admin")
    if session.get("role") == "teacher":
        return redirect("/teacher")

    with db() as con:
        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (session["user"],)
        ).fetchone()
        if user is None:
            session.clear()
            return redirect("/")

        ensure_pending_fee_message(con, user)
        fee_messages = con.execute(
            """
            SELECT *
            FROM student_messages
            WHERE student_id=? AND message_type='Fee Reminder'
            ORDER BY created_at DESC, id DESC
            LIMIT 3
            """,
            (user["id"],)
        ).fetchall()
        has_pending_fee = not student_has_paid_fee(con, user["id"], "Academic Fee")

        total = con.execute(
            "SELECT COUNT(*) FROM users WHERE role='student'"
        ).fetchone()[0]
        recent_leaves = con.execute(
            """
            SELECT leave_kind, leave_type, from_date, to_date, status
            FROM student_leaves
            WHERE student_id=?
            ORDER BY from_date DESC, id DESC
            LIMIT 3
            """,
            (user["id"],)
        ).fetchall()

        ensure_six_month_timetable(con)
        upcoming_lectures = con.execute(
            """
            SELECT lecture_date, lecture_name, time
            FROM lectures
            WHERE lecture_date >= ?
            ORDER BY lecture_date, id
            LIMIT 3
            """,
            (date.today().isoformat(),)
        ).fetchall()

    report_data = get_student_attendance_report(user["id"])
    leave_request_count = len(recent_leaves)
    latest_leave_status = recent_leaves[0]["status"] if recent_leaves else "No Request"

    return render_template(
        "student/home.html",
        user=user,
        total=total,
        attendance_percent=report_data["percent"],
        present_count=report_data["present"],
        absent_count=report_data["absent"],
        leave_count=report_data["leave"],
        leave_request_count=leave_request_count,
        attendance_penalty=report_data["penalty"],
        attendance_recovery=report_data["recovery"],
        latest_leave_status=latest_leave_status,
        recent_leaves=recent_leaves,
        upcoming_lectures=upcoming_lectures,
        fee_messages=fee_messages,
        has_pending_fee=has_pending_fee,
        weekly_timetable=get_weekly_timetable(),
    )


def get_student_or_redirect():
    if "user" not in session:
        return None, redirect("/")
    if session.get("role") != "student":
        return None, redirect_for_role(session.get("role"))

    user = current_user()
    if user is None:
        session.clear()
        return None, redirect("/")

    return user, None


def build_receipt_no(payment_id):
    return f"FEE-{date.today().strftime('%Y%m%d')}-{payment_id:04d}"


def normalize_gender_group(gender):
    value = (gender or "").strip().lower()
    if value in {"male", "boy", "boys"}:
        return "boys"
    if value in {"female", "girl", "girls"}:
        return "girls"
    return "other"


def student_has_paid_fee(con, student_id, fee_type="Academic Fee"):
    return con.execute(
        """
        SELECT 1
        FROM fee_payments
        WHERE student_id=? AND fee_type=?
        LIMIT 1
        """,
        (student_id, fee_type)
    ).fetchone() is not None


def clear_fee_reminders(con, student_id):
    con.execute(
        """
        DELETE FROM student_messages
        WHERE student_id=? AND message_type='Fee Reminder'
        """,
        (student_id,)
    )


def ensure_pending_fee_message(con, student):
    if not student:
        return None

    if student_has_paid_fee(con, student["id"], "Academic Fee"):
        clear_fee_reminders(con, student["id"])
        return None

    existing = con.execute(
        """
        SELECT *
        FROM student_messages
        WHERE student_id=?
          AND message_type='Fee Reminder'
        ORDER BY id DESC
        LIMIT 1
        """,
        (student["id"],)
    ).fetchone()
    if existing:
        return existing

    subject = "Fee Pending Reminder"
    message = (
        f"Dear {student['username']}, your Academic Fee for Class {student['class'] or '-'} "
        "is still pending. Please pay it from the Fee section as soon as possible."
    )
    cursor = con.execute(
        """
        INSERT INTO student_messages(student_id, subject, message, message_type)
        VALUES (?, ?, ?, ?)
        """,
        (student["id"], subject, message, "Fee Reminder")
    )
    return con.execute(
        "SELECT * FROM student_messages WHERE id=?",
        (cursor.lastrowid,)
    ).fetchone()


def get_cia_marks_rows(con, student_id=None, class_num=None, exam_term=None):
    filters = []
    params = []
    if student_id is not None:
        filters.append("users.id=?")
        params.append(student_id)
    if class_num:
        filters.append("users.class=?")
        params.append(str(class_num))
    if exam_term:
        filters.append("exam_cia_marks.exam_term=?")
        params.append(exam_term)

    where_sql = " AND " + " AND ".join(filters) if filters else ""
    return con.execute(
        f"""
        SELECT
            exam_cia_marks.*,
            users.username,
            users.rollno,
            users.enroll,
            users.class
        FROM exam_cia_marks
        JOIN users ON users.id = exam_cia_marks.student_id
        WHERE users.role='student'
        {where_sql}
        ORDER BY CAST(users.class AS INTEGER), users.class, users.rollno, users.username, exam_cia_marks.subject, exam_cia_marks.exam_term
        """,
        tuple(params)
    ).fetchall()


def get_result_declaration(con, class_num, exam_term="Sem - III"):
    row = con.execute(
        """
        SELECT *
        FROM exam_result_declarations
        WHERE class_num=? AND exam_term=?
        """,
        (str(class_num or ""), exam_term)
    ).fetchone()
    if row:
        return row

    con.execute(
        """
        INSERT OR IGNORE INTO exam_result_declarations(class_num, exam_term)
        VALUES (?, ?)
        """,
        (str(class_num or ""), exam_term)
    )
    return con.execute(
        """
        SELECT *
        FROM exam_result_declarations
        WHERE class_num=? AND exam_term=?
        """,
        (str(class_num or ""), exam_term)
    ).fetchone()


def build_student_result(con, student, exam_term="Sem - III"):
    marks = get_cia_marks_rows(con, student_id=student["id"])
    marks_by_subject = {}
    for row in marks:
        subject_bucket = marks_by_subject.setdefault(row["subject"], {})
        subject_bucket[row["exam_term"]] = row

    result_rows = []

    for index, subject in enumerate(sorted(marks_by_subject), start=1):
        subject_marks = marks_by_subject[subject]
        cia_row = subject_marks.get("CIA")
        see_row = subject_marks.get("SEE")
        cia_marks = float(cia_row["marks"] or 0) if cia_row else None
        cia_total = float(cia_row["total_marks"] or 25) if cia_row else 25
        see_marks = float(see_row["marks"] or 0) if see_row else None
        see_total = float(see_row["total_marks"] or 50) if see_row else 50
        total_marks = (cia_marks or 0) + (see_marks or 0)
        max_marks = (cia_total if cia_row else 0) + (see_total if see_row else 0)
        result_rows.append({
            "course_code": f"24UGCA{300 + index}",
            "subject": subject,
            "cia_marks": cia_marks if cia_row else "-",
            "cia_total": cia_total,
            "see_marks": see_marks if see_row else "-",
            "see_total": see_total,
            "total_marks": total_marks,
            "max_marks": max_marks,
            "result": "P" if max_marks and total_marks >= (max_marks * 0.35) else "RA",
        })

    earned = sum(row["total_marks"] for row in result_rows)
    maximum = sum(row["max_marks"] for row in result_rows)
    percentage = round((earned * 100 / maximum), 2) if maximum else 0
    sgpa = round(percentage / 10, 2) if percentage else 0

    return {
        "rows": result_rows,
        "earned": earned,
        "maximum": maximum,
        "percentage": percentage,
        "sgpa": sgpa,
        "status": "PASS" if result_rows and all(row["result"] == "P" for row in result_rows) else "PENDING",
        "declaration": get_result_declaration(con, student["class"], exam_term),
    }


def get_fee_status_data(con, fee_type="all", class_num=None):
    fee_type = (fee_type or "all").strip()
    payment_filter = ""
    params = []

    if fee_type != "all":
        payment_filter = " AND fee_type=?"
        params.append(fee_type)

    class_filter = ""
    if class_num:
        class_filter = " AND users.class=?"
        params.append(str(class_num))

    students = con.execute(
        f"""
        SELECT
            users.id,
            users.rollno,
            users.username,
            users.gender,
            users.class,
            COALESCE(SUM(fee_payments.amount), 0) AS paid_amount,
            COUNT(fee_payments.id) AS payment_count,
            MAX(fee_payments.created_at) AS latest_payment,
            MAX(fee_payments.receipt_no) AS latest_receipt
        FROM users
        LEFT JOIN fee_payments
            ON fee_payments.student_id = users.id
            {payment_filter}
        WHERE users.role='student'
        {class_filter}
        GROUP BY users.id
        ORDER BY CAST(users.class AS INTEGER), users.class, users.rollno, users.username
        """,
        tuple(params)
    ).fetchall()

    summary_map = {}
    totals = {
        "students": 0,
        "paid": 0,
        "pending": 0,
        "boys": 0,
        "girls": 0,
        "boys_paid": 0,
        "girls_paid": 0,
        "boys_pending": 0,
        "girls_pending": 0,
        "amount": 0,
    }

    detail_rows = []
    for student in students:
        student_class = student["class"] or "-"
        gender_group = normalize_gender_group(student["gender"])
        is_paid = (student["payment_count"] or 0) > 0

        if student_class not in summary_map:
            summary_map[student_class] = {
                "class_num": student_class,
                "students": 0,
                "paid": 0,
                "pending": 0,
                "boys": 0,
                "girls": 0,
                "boys_paid": 0,
                "girls_paid": 0,
                "boys_pending": 0,
                "girls_pending": 0,
                "amount": 0,
            }

        bucket = summary_map[student_class]
        for target in (bucket, totals):
            target["students"] += 1
            target["amount"] += student["paid_amount"] or 0
            if is_paid:
                target["paid"] += 1
            else:
                target["pending"] += 1

            if gender_group == "boys":
                target["boys"] += 1
                target["boys_paid" if is_paid else "boys_pending"] += 1
            elif gender_group == "girls":
                target["girls"] += 1
                target["girls_paid" if is_paid else "girls_pending"] += 1

        detail_rows.append({
            "id": student["id"],
            "rollno": student["rollno"],
            "username": student["username"],
            "gender": student["gender"] or "-",
            "class": student_class,
            "paid_amount": student["paid_amount"] or 0,
            "payment_count": student["payment_count"] or 0,
            "latest_payment": student["latest_payment"] or "-",
            "latest_receipt": student["latest_receipt"] or "-",
            "status": "Fee Paid" if is_paid else "Pending",
            "is_paid": is_paid,
        })

    def class_sort_key(item):
        value = item["class_num"]
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            return (1, str(value))

    return sorted(summary_map.values(), key=class_sort_key), detail_rows, totals


@app.route("/fee_status")
@app.route("/fee_status/<class_num>")
def fee_status(class_num=None):
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect_for_role(session.get("role"))

    fee_type = request.args.get("fee_type", "all").strip() or "all"
    valid_fee_types = ["all", "Academic Fee", "Transport Fee"]
    if fee_type not in valid_fee_types:
        fee_type = "all"

    with db() as con:
        summary_rows, student_rows, totals = get_fee_status_data(con, fee_type, class_num)

    return render_template(
        "shared/fee_status.html",
        role=session.get("role"),
        fee_type=fee_type,
        fee_type_options=valid_fee_types,
        selected_class=class_num,
        summary_rows=summary_rows,
        student_rows=student_rows,
        totals=totals,
    )


@app.route("/pay_fee", methods=["GET", "POST"])
def pay_fee():
    user, redirect_response = get_student_or_redirect()
    if redirect_response:
        return redirect_response

    message = ""
    error = ""

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0"))
        except ValueError:
            amount = 0

        payment_method = request.form.get("payment_method", "").strip()
        remarks = request.form.get("remarks", "").strip()

        if amount <= 0:
            error = "Please enter a valid fee amount."
        elif not payment_method:
            error = "Please select a payment method."
        else:
            with db() as con:
                cur = con.execute(
                    """
                    INSERT INTO fee_payments(
                        student_id, class_num, fee_type, amount, payment_method, remarks, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user["id"], user["class"] or "", "Academic Fee", amount, payment_method, remarks, "Submitted")
                )
                receipt_no = build_receipt_no(cur.lastrowid)
                con.execute(
                    "UPDATE fee_payments SET receipt_no=? WHERE id=?",
                    (receipt_no, cur.lastrowid)
                )
                clear_fee_reminders(con, user["id"])

            return redirect(f"/fee_receipt?submitted=1&receipt={receipt_no}")

    return render_template(
        "student/pay_fee.html",
        user=user,
        message=message,
        error=error,
        fee_type="Academic Fee",
        form_action="/pay_fee",
    )


@app.route("/pay_transport_fee", methods=["GET", "POST"])
def pay_transport_fee():
    user, redirect_response = get_student_or_redirect()
    if redirect_response:
        return redirect_response

    error = ""

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0"))
        except ValueError:
            amount = 0

        payment_method = request.form.get("payment_method", "").strip()
        remarks = request.form.get("remarks", "").strip()

        if amount <= 0:
            error = "Please enter a valid transport fee amount."
        elif not payment_method:
            error = "Please select a payment method."
        else:
            with db() as con:
                cur = con.execute(
                    """
                    INSERT INTO fee_payments(
                        student_id, class_num, fee_type, amount, payment_method, remarks, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user["id"], user["class"] or "", "Transport Fee", amount, payment_method, remarks, "Submitted")
                )
                receipt_no = build_receipt_no(cur.lastrowid)
                con.execute(
                    "UPDATE fee_payments SET receipt_no=? WHERE id=?",
                    (receipt_no, cur.lastrowid)
                )

            return redirect(f"/fee_receipt?submitted=1&receipt={receipt_no}")

    return render_template(
        "student/pay_fee.html",
        user=user,
        message="",
        error=error,
        fee_type="Transport Fee",
        form_action="/pay_transport_fee",
    )


@app.route("/fee_receipt")
def fee_receipt():
    user, redirect_response = get_student_or_redirect()
    if redirect_response:
        return redirect_response

    with db() as con:
        receipts = con.execute(
            """
            SELECT *
            FROM fee_payments
            WHERE student_id=?
            ORDER BY created_at DESC, id DESC
            """,
            (user["id"],)
        ).fetchall()

    return render_template(
        "student/fee_receipt.html",
        user=user,
        receipts=receipts,
        submitted=request.args.get("submitted") == "1",
        submitted_receipt=request.args.get("receipt", ""),
    )


@app.route("/fee_circular")
def fee_circular():
    user, redirect_response = get_student_or_redirect()
    if redirect_response:
        return redirect_response

    class_num = user["class"] or ""
    with db() as con:
        ensure_pending_fee_message(con, user)
        fee_messages = con.execute(
            """
            SELECT *
            FROM student_messages
            WHERE student_id=? AND message_type='Fee Reminder'
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """,
            (user["id"],)
        ).fetchall()
        circulars = con.execute(
            """
            SELECT *
            FROM class_notifications
            WHERE CAST(class_num AS TEXT)=?
              AND (
                    LOWER(subject) LIKE '%fee%'
                    OR LOWER(subject) LIKE '%fees%'
                    OR LOWER(subject) LIKE '%circular%'
                    OR LOWER(message) LIKE '%fee%'
                    OR LOWER(message) LIKE '%fees%'
                  )
            ORDER BY created_at DESC
            """,
            (str(class_num),)
        ).fetchall()

    return render_template(
        "student/fee_circular.html",
        user=user,
        circulars=circulars,
        fee_messages=fee_messages,
        class_num=class_num,
    )


def render_student_result_page(user, page=None):
    with db() as con:
        result_data = build_student_result(con, user)

    if not result_data["declaration"] or not result_data["declaration"]["is_declared"]:
        return render_template(
            "student/result_pending.html",
            user=user,
            page=page or EXAM_PAGES["result_reassessment"],
            declaration=result_data["declaration"],
        )
    return render_template(
        "shared/result_marksheet.html",
        role="student",
        user=user,
        student=user,
        result_data=result_data,
        declaration=result_data["declaration"],
    )


@app.route("/student_result")
def student_result():
    user, redirect_response = get_student_or_redirect()
    if redirect_response:
        return redirect_response

    return render_student_result_page(user)


@app.route("/exam/<page_key>", methods=["GET", "POST"])
def student_exam_page(page_key):
    user, redirect_response = get_student_or_redirect()
    if redirect_response:
        return redirect_response

    page = EXAM_PAGES.get(page_key)
    if page is None:
        return redirect("/exam/course_selection")

    message = ""
    selected_subjects = request.form.getlist("subjects")
    if request.method == "POST":
        if page["kind"] == "form":
            message = f"{page['title']} submitted successfully."
        elif page["kind"] == "course":
            message = "Course selection saved successfully."
        elif page["kind"] == "result":
            message = "Reassessment request saved successfully."

    subjects = get_seed_timetable_subjects() or ["PHP", "Python", "Java", "DBMS", "AI", "Math"]
    exam_rows = [
        {"date": "20-05-2026", "time": "10:00 AM to 12:00 PM", "subject": subjects[0] if len(subjects) > 0 else "Subject 1"},
        {"date": "22-05-2026", "time": "10:00 AM to 12:00 PM", "subject": subjects[1] if len(subjects) > 1 else "Subject 2"},
        {"date": "24-05-2026", "time": "10:00 AM to 12:00 PM", "subject": subjects[2] if len(subjects) > 2 else "Subject 3"},
    ]
    with db() as con:
        marks_rows = get_cia_marks_rows(con, student_id=user["id"], exam_term="CIA")

    if page_key == "result_reassessment":
        return render_student_result_page(user, page)

    return render_template(
        "student/exam_page.html",
        user=user,
        page_key=page_key,
        page=page,
        subjects=subjects,
        selected_subjects=selected_subjects,
        exam_rows=exam_rows,
        marks_rows=marks_rows,
        message=message,
    )


@app.route("/teacher_cia_marks", methods=["GET", "POST"])
@app.route("/teacher_see_marks", methods=["GET", "POST"])
def teacher_cia_marks():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "teacher":
        return redirect_for_role(session.get("role"))

    selected_class = request.form.get("class_num") or request.args.get("class_num") or "1"
    selected_subject = request.form.get("subject") or request.args.get("subject") or "PHP"
    selected_mark_type = request.form.get("mark_type") or request.args.get("mark_type")
    if not selected_mark_type:
        selected_mark_type = "SEE" if request.path == "/teacher_see_marks" else "CIA"
    selected_mark_type = "SEE" if selected_mark_type == "SEE" else "CIA"
    total_marks = 50 if selected_mark_type == "SEE" else 25
    message = ""

    with db() as con:
        if request.method == "POST":
            student_ids = request.form.getlist("student_id")
            for student_id in student_ids:
                raw_marks = request.form.get(f"marks_{student_id}", "").strip()
                remarks = request.form.get(f"remarks_{student_id}", "").strip()
                if raw_marks == "":
                    continue
                try:
                    marks = float(raw_marks)
                except ValueError:
                    continue
                marks = max(0, min(marks, total_marks))
                con.execute(
                    """
                    INSERT INTO exam_cia_marks(
                        student_id, class_num, subject, marks, total_marks, exam_term, entered_by, remarks, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(student_id, subject, exam_term)
                    DO UPDATE SET
                        class_num=excluded.class_num,
                        marks=excluded.marks,
                        total_marks=excluded.total_marks,
                        entered_by=excluded.entered_by,
                        remarks=excluded.remarks,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (student_id, selected_class, selected_subject, marks, total_marks, selected_mark_type, session.get("user"), remarks)
                )
            message = f"{selected_mark_type} marks saved successfully."

        students = con.execute(
            """
            SELECT users.*, exam_cia_marks.marks, exam_cia_marks.remarks
            FROM users
            LEFT JOIN exam_cia_marks
              ON exam_cia_marks.student_id = users.id
             AND exam_cia_marks.subject=?
             AND exam_cia_marks.exam_term=?
            WHERE users.role='student' AND users.class=?
            ORDER BY users.rollno, users.username
            """,
            (selected_subject, selected_mark_type, str(selected_class))
        ).fetchall()
        classes = con.execute(
            "SELECT DISTINCT class FROM users WHERE role='student' AND class IS NOT NULL AND class!='' ORDER BY CAST(class AS INTEGER), class"
        ).fetchall()
        all_marks = get_cia_marks_rows(con, exam_term=selected_mark_type)

    return render_template(
        "shared/cia_marks_manage.html",
        role="teacher",
        user=current_user(),
        selected_class=selected_class,
        selected_subject=selected_subject,
        selected_mark_type=selected_mark_type,
        total_marks=total_marks,
        subjects=get_seed_timetable_subjects() or ["PHP", "Python", "Java", "DBMS", "AI", "Math"],
        classes=[row["class"] for row in classes] or [str(i) for i in range(1, 13)],
        students=students,
        all_marks=all_marks,
        message=message,
    )


@app.route("/admin_cia_marks", methods=["GET", "POST"])
@app.route("/admin_see_marks", methods=["GET", "POST"])
def admin_cia_marks():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect_for_role(session.get("role"))

    selected_class = request.form.get("class_num") or request.args.get("class_num") or "1"
    selected_subject = request.form.get("subject") or request.args.get("subject") or "PHP"
    selected_mark_type = request.form.get("mark_type") or request.args.get("mark_type")
    if not selected_mark_type:
        selected_mark_type = "SEE" if request.path == "/admin_see_marks" else "CIA"
    selected_mark_type = "SEE" if selected_mark_type == "SEE" else "CIA"
    total_marks = 50 if selected_mark_type == "SEE" else 25
    message = ""

    with db() as con:
        if request.method == "POST":
            student_ids = request.form.getlist("student_id")
            for student_id in student_ids:
                raw_marks = request.form.get(f"marks_{student_id}", "").strip()
                remarks = request.form.get(f"remarks_{student_id}", "").strip()
                if raw_marks == "":
                    continue
                try:
                    marks = float(raw_marks)
                except ValueError:
                    continue
                marks = max(0, min(marks, total_marks))
                con.execute(
                    """
                    INSERT INTO exam_cia_marks(
                        student_id, class_num, subject, marks, total_marks, exam_term, entered_by, remarks, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(student_id, subject, exam_term)
                    DO UPDATE SET
                        class_num=excluded.class_num,
                        marks=excluded.marks,
                        total_marks=excluded.total_marks,
                        entered_by=excluded.entered_by,
                        remarks=excluded.remarks,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (student_id, selected_class, selected_subject, marks, total_marks, selected_mark_type, session.get("user"), remarks)
                )
            message = f"{selected_mark_type} marks saved successfully."

        students = con.execute(
            """
            SELECT users.*, exam_cia_marks.marks, exam_cia_marks.remarks
            FROM users
            LEFT JOIN exam_cia_marks
              ON exam_cia_marks.student_id = users.id
             AND exam_cia_marks.subject=?
             AND exam_cia_marks.exam_term=?
            WHERE users.role='student' AND users.class=?
            ORDER BY users.rollno, users.username
            """,
            (selected_subject, selected_mark_type, str(selected_class))
        ).fetchall()
        classes = con.execute(
            "SELECT DISTINCT class FROM users WHERE role='student' AND class IS NOT NULL AND class!='' ORDER BY CAST(class AS INTEGER), class"
        ).fetchall()
        all_marks = get_cia_marks_rows(con, exam_term=selected_mark_type)

    return render_template(
        "shared/cia_marks_manage.html",
        role="admin",
        user=current_user(),
        selected_class=selected_class,
        selected_subject=selected_subject,
        selected_mark_type=selected_mark_type,
        total_marks=total_marks,
        subjects=get_seed_timetable_subjects() or ["PHP", "Python", "Java", "DBMS", "AI", "Math"],
        classes=[row["class"] for row in classes] or [str(i) for i in range(1, 13)],
        students=students,
        all_marks=all_marks,
        message=message,
    )


@app.route("/admin_results", methods=["GET", "POST"])
def admin_results():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect_for_role(session.get("role"))

    selected_class = request.form.get("class_num") or request.args.get("class_num") or "1"
    message = ""

    with db() as con:
        if request.method == "POST":
            action = request.form.get("action", "")
            is_declared = 1 if action == "declare" else 0
            con.execute(
                """
                INSERT INTO exam_result_declarations(
                    class_num, exam_term, is_declared, declared_by, declared_at
                )
                VALUES (?, 'Sem - III', ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(class_num, exam_term)
                DO UPDATE SET
                    is_declared=excluded.is_declared,
                    declared_by=excluded.declared_by,
                    declared_at=CASE WHEN excluded.is_declared=1 THEN CURRENT_TIMESTAMP ELSE NULL END
                """,
                (selected_class, is_declared, session.get("user"))
            )
            message = "Result declared successfully." if is_declared else "Result hidden from students."

        classes = con.execute(
            "SELECT DISTINCT class FROM users WHERE role='student' AND class IS NOT NULL AND class!='' ORDER BY CAST(class AS INTEGER), class"
        ).fetchall()
        students = con.execute(
            """
            SELECT *
            FROM users
            WHERE role='student' AND class=?
            ORDER BY rollno, username
            """,
            (str(selected_class),)
        ).fetchall()
        declaration = get_result_declaration(con, selected_class)
        summaries = []
        for student in students:
            result_data = build_student_result(con, student)
            summaries.append({
                "student": student,
                "earned": result_data["earned"],
                "maximum": result_data["maximum"],
                "percentage": result_data["percentage"],
                "sgpa": result_data["sgpa"],
                "status": result_data["status"],
            })

    return render_template(
        "admin/results.html",
        selected_class=selected_class,
        classes=[row["class"] for row in classes] or [str(i) for i in range(1, 13)],
        declaration=declaration,
        summaries=summaries,
        message=message,
    )


@app.route("/admin_result/<int:student_id>")
def admin_student_result(student_id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect_for_role(session.get("role"))

    with db() as con:
        student = con.execute(
            "SELECT * FROM users WHERE id=? AND role='student'",
            (student_id,)
        ).fetchone()
        if student is None:
            return redirect("/admin_results")
        result_data = build_student_result(con, student)

    return render_template(
        "shared/result_marksheet.html",
        role="admin",
        user=current_user(),
        student=student,
        result_data=result_data,
        declaration=result_data["declaration"],
    )


@app.route("/student_leave", methods=["GET", "POST"])
def student_leave():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "student":
        return redirect_for_role(session.get("role"))

    user = current_user()
    if user is None:
        session.clear()
        return redirect("/")

    message = ""
    error = ""

    leave_kind_options = [
        "Medical Leave",
        "Cultural Leave",
        "Personal Leave",
        "Family Leave",
        "Emergency Leave",
        "Sports Leave",
    ]
    leave_type_options = [
        "Partially Leave",
        "Full Leave",
    ]

    form_data = {
        "leave_kind": "",
        "leave_type": "",
        "from_date": "",
        "to_date": "",
        "remarks": "",
    }

    with db() as con:
        if request.method == "POST":
            form_data = {
                "leave_kind": request.form.get("leave_kind", "").strip(),
                "leave_type": request.form.get("leave_type", "").strip(),
                "from_date": request.form.get("from_date", "").strip(),
                "to_date": request.form.get("to_date", "").strip(),
                "remarks": request.form.get("remarks", "").strip(),
            }

            if not all(form_data.values()):
                error = "All leave details are required."
            elif form_data["leave_kind"] not in leave_kind_options:
                error = "Please select a valid kind of leave."
            elif form_data["leave_type"] not in leave_type_options:
                error = "Please select a valid type of leave."
            else:
                try:
                    from_dt = date.fromisoformat(form_data["from_date"])
                    to_dt = date.fromisoformat(form_data["to_date"])
                except ValueError:
                    error = "Please choose valid leave dates."
                else:
                    if to_dt < from_dt:
                        error = "To date cannot be earlier than from date."

            if not error:
                con.execute(
                    """
                    INSERT INTO student_leaves(
                        student_id, leave_kind, leave_type, from_date, to_date, remarks, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"],
                        form_data["leave_kind"],
                        form_data["leave_type"],
                        form_data["from_date"],
                        form_data["to_date"],
                        form_data["remarks"],
                        "Pending",
                    ),
                )
                message = "Leave application saved successfully."
                form_data = {
                    "leave_kind": "",
                    "leave_type": "",
                    "from_date": "",
                    "to_date": "",
                    "remarks": "",
                }

        leave_rows = con.execute(
            """
            SELECT id, leave_kind, leave_type, from_date, to_date, remarks, status, created_at
            FROM student_leaves
            WHERE student_id=?
            ORDER BY from_date DESC, id DESC
            """,
            (user["id"],)
        ).fetchall()

    leave_history = []
    for row in leave_rows:
        from_iso = row["from_date"] or ""
        to_iso = row["to_date"] or ""
        leave_history.append({
            "id": row["id"],
            "leave_kind": row["leave_kind"],
            "leave_type": row["leave_type"],
            "from_date": from_iso,
            "to_date": to_iso,
            "from_display": date.fromisoformat(from_iso).strftime("%d/%m/%Y") if from_iso else "-",
            "to_display": date.fromisoformat(to_iso).strftime("%d/%m/%Y") if to_iso else "-",
            "remarks": row["remarks"] or "-",
            "status": row["status"] or "Pending",
        })

    return render_template(
        "student/student_leave.html",
        user=user,
        message=message,
        error=error,
        form_data=form_data,
        leave_kind_options=leave_kind_options,
        leave_type_options=leave_type_options,
        leave_history=leave_history,
    )


@app.route("/student_leave/<int:id>/decision", methods=["POST"])
def student_leave_decision(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect_for_role(session.get("role"))

    decision = (request.form.get("decision") or "").strip().lower()
    status_map = {
        "approve": "Approved",
        "reject": "Rejected",
        "pending": "Pending",
    }
    status = status_map.get(decision)
    if not status:
        return redirect("/admin" if session.get("role") == "admin" else "/teacher")

    with db() as con:
        con.execute(
            "UPDATE student_leaves SET status=? WHERE id=?",
            (status, id)
        )

    next_url = request.form.get("next") or ("/admin" if session.get("role") == "admin" else "/teacher")
    return redirect(next_url)


# STUDENT LIST
@app.route("/list")
def list_users():

    if "user" not in session:
        return redirect("/")

    if session.get("role") != "admin":
        return redirect("/admin_login")

    with db() as con:

        users=con.execute("""
            SELECT * FROM users
            WHERE role='student'
            ORDER BY rollno, username
        """).fetchall()

    return render_template("admin/list.html",users=users)


@app.route("/students_by_class")
def students_by_class():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin_login")
    
    with db() as con:
        # Get all classes with student count
        classes_data = []
        for class_num in range(1, 13):
            count = con.execute(
                "SELECT COUNT(*) FROM users WHERE role='student' AND class=?",
                (str(class_num),)
            ).fetchone()[0]
            classes_data.append({
                "class_num": class_num,
                "count": count
            })
    
    return render_template("admin/students_by_class.html", classes_data=classes_data)


@app.route("/students_by_class/<class_num>")
def students_in_class(class_num):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin_login")
    
    with db() as con:
        students = con.execute("""
            SELECT * FROM users
            WHERE role='student' AND class=?
            ORDER BY rollno, username
        """, (class_num,)).fetchall()
        
        class_count = con.execute(
            "SELECT COUNT(*) FROM users WHERE role='student'"
        ).fetchone()[0]
    
    return render_template(
        "admin/students_in_class.html",
        students=students,
        class_num=class_num,
        total_students=class_count
    )


# ADMIN DASHBOARD
@app.route("/admin")
def admin():

    if "user" not in session:
        return redirect("/")

    if session.get("role") != "admin":
        return redirect("/admin_login")

    with db() as con:
        admin_user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (session["user"],)
        ).fetchone()
        today_text = date.today().isoformat()
        users = con.execute("""
            SELECT
                users.*,
                SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
            FROM users
            LEFT JOIN lecture_attendance ON lecture_attendance.student_id = users.id
            WHERE users.role='student'
            GROUP BY users.id
            ORDER BY users.rollno, users.username
        """).fetchall()
        teachers = con.execute("""
            SELECT
                teachers.*,
                SUM(CASE WHEN teacher_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                COUNT(teacher_attendance.id) AS total_count
            FROM teachers
            LEFT JOIN teacher_attendance ON teacher_attendance.teacher_id = teachers.id
            GROUP BY teachers.id
            ORDER BY TRIM(teachers.name), teachers.username
            LIMIT 30
        """).fetchall()
        leave_requests = get_student_leave_requests(con, limit=12)
        student_present_total = sum((row["present_count"] or 0) for row in users)
        student_record_total = sum((row["total_count"] or 0) for row in users)
        attendance_health = int(safe_percent(student_present_total, student_record_total))
        course_count = con.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        subject_count = con.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        lecture_slot_count = con.execute("SELECT COUNT(*) FROM lecture_slots").fetchone()[0]
        lecture_count = con.execute("SELECT COUNT(*) FROM lectures").fetchone()[0]
        pending_leave_count = con.execute(
            "SELECT COUNT(*) FROM student_leaves WHERE status='Pending'"
        ).fetchone()[0]
        paid_fee_count = con.execute(
            """
            SELECT COUNT(DISTINCT student_id)
            FROM fee_payments
            WHERE fee_type='Academic Fee'
            """
        ).fetchone()[0]
        open_modules = course_count + subject_count + lecture_slot_count
        reports_ready = len(users) + len(teachers)
        attendance_trend = get_recent_attendance_chart(con, limit=5)
        ensure_festival_calendar(con)
        festival_count = con.execute(
            "SELECT COUNT(*) FROM festivals WHERE festival_date >= ?",
            (today_text,)
        ).fetchone()[0]
        next_festival = con.execute(
            """
            SELECT festival_date, name
            FROM festivals
            WHERE festival_date >= ?
            ORDER BY festival_date, id
            LIMIT 1
            """,
            (today_text,)
        ).fetchone()

    search_items = [
        {"label": "Student List", "meta": "View all students", "url": "/list"},
        {"label": "Teachers List", "meta": "Manage teacher records", "url": "/teachers"},
        {"label": "Attendance", "meta": "Open daily attendance", "url": "/attendance"},
        {"label": "Lecture Attendance", "meta": "Open lecture attendance", "url": "/lecture_attendance"},
        {"label": "Teacher Attendance", "meta": "Track teacher attendance", "url": "/teacher_attendance"},
        {"label": "Courses", "meta": "Manage courses", "url": "/courses"},
        {"label": "Subjects", "meta": "Manage subjects", "url": "/subjects"},
        {"label": "Manage Timetable", "meta": "Build a new timetable", "url": "/manage_timetable"},
        {"label": "Weekly Report", "meta": "Open weekly attendance report", "url": "/weekly_attendance"},
        {"label": "Timetable", "meta": "Open lecture timetable", "url": "/timetable"},
        {"label": "Fee Status", "meta": "See students who paid class fees", "url": "/fee_status"},
    ]

    for student in users[:50]:
        search_items.append({
            "label": student["username"],
            "meta": f"Student report | Roll No: {student['rollno'] or '-'}",
            "url": f"/report/{student['id']}"
        })

    for teacher in teachers:
        teacher_name = teacher["name"] or teacher["username"] or "Teacher"
        teacher_username = teacher["username"] or "-"
        teacher_subject = teacher["subject"] or "No subject assigned"
        search_items.append({
            "label": teacher_name,
            "meta": f"Teacher | {teacher_subject} | {teacher_username}",
            "url": f"/teacher_report/{teacher['id']}"
        })

    return render_template(
        "admin/admin.html",
        users=users,
        teachers=teachers,
        admin_user=admin_user,
        search_items=search_items,
        leave_requests=leave_requests,
        attendance_health=attendance_health,
        open_modules=open_modules,
        reports_ready=reports_ready,
        course_count=course_count,
        subject_count=subject_count,
        lecture_slot_count=lecture_slot_count,
        lecture_count=lecture_count,
        festival_count=festival_count,
        next_festival=next_festival,
        pending_leave_count=pending_leave_count,
        paid_fee_count=paid_fee_count,
        student_report_count=len(users),
        teacher_report_count=len(teachers),
        attendance_trend=attendance_trend,
        weekly_timetable=get_weekly_timetable(),
    )


# TEACHER CRUD
@app.route("/teachers")
def list_teachers():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    with db() as con:
        normalize_teacher_records(con)
        teachers = con.execute("SELECT * FROM teachers").fetchall()
    return render_template("admin/teachers.html", teachers=teachers)


@app.route("/add_teacher", methods=["GET", "POST"])
def add_teacher():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    msg = ""
    if request.method == "POST":
        f = request.form
        course = f.get("course")
        new_course = f.get("new_course")
        subject = f.get("subject")
        new_subject = f.get("new_subject")
        username = build_teacher_username(f.get("name"), f.get("username"))
        password = (f.get("password") or "").strip()

        with db() as con:
            existing_user = con.execute(
                "SELECT id FROM users WHERE username=?",
                (username,)
            ).fetchone()
            if existing_user:
                msg = "Teacher username already exists."
            elif not password:
                msg = "Password is required for teacher login."
            else:
                if new_course and new_course.strip():
                    course = new_course.strip()
                    existing_course = con.execute("SELECT id FROM courses WHERE name=?", (course,)).fetchone()
                    if not existing_course:
                        con.execute("INSERT INTO courses(name,description) VALUES (?,?)", (course, f.get("course_description", "Added from teacher")))

                if new_subject and new_subject.strip():
                    subject = new_subject.strip()
                    existing_subject = con.execute("SELECT id FROM subjects WHERE name=?", (subject,)).fetchone()
                    if not existing_subject:
                        con.execute("INSERT INTO subjects(name,course) VALUES (?,?)", (subject, course or ""))

                con.execute(
                    "INSERT INTO teachers(name,email,mobile,username,course,subject) VALUES (?,?,?,?,?,?)",
                    (f.get("name"), f.get("email"), f.get("mobile"), username, course, subject)
                )
                con.execute("""
                INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,role)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    0,
                    username,
                    generate_password_hash(password),
                    "",
                    f.get("mobile"),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "teacher"
                ))
                return redirect("/teachers")

    courses = []
    subjects = []
    with db() as con:
        courses = con.execute("SELECT name FROM courses").fetchall()
        subjects = con.execute("SELECT name FROM subjects").fetchall()
    return render_template("admin/add_teacher.html", courses=courses, subjects=subjects, msg=msg)


@app.route("/edit_teacher/<int:id>", methods=["GET", "POST"])
def edit_teacher(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    with db() as con:
        teacher = con.execute("SELECT * FROM teachers WHERE id=?", (id,)).fetchone()
        if teacher is None:
            return redirect("/teachers")

        if request.method == "POST":
            f = request.form
            username = build_teacher_username(f.get("name"), f.get("username"))
            new_password = (f.get("password") or "").strip()
            existing_user = con.execute(
                "SELECT id FROM users WHERE username=? AND username<>?",
                (username, teacher["username"] or "")
            ).fetchone()

            if existing_user:
                courses = con.execute("SELECT name FROM courses").fetchall()
                subjects = con.execute("SELECT name FROM subjects").fetchall()
                return render_template(
                    "admin/edit_teacher.html",
                    teacher=teacher,
                    courses=courses,
                    subjects=subjects,
                    msg="Teacher username already exists."
                )

            con.execute("UPDATE teachers SET name=?, email=?, mobile=?, username=?, course=?, subject=? WHERE id=?", (
                f.get("name"), f.get("email"), f.get("mobile"), username, f.get("course"), f.get("subject"), id
            ))
            teacher_user = con.execute(
                "SELECT id FROM users WHERE (username=? OR username=?) AND role='teacher'",
                (teacher["username"] or "", username)
            ).fetchone()
            if teacher_user:
                con.execute(
                    "UPDATE users SET username=?, mobile=? WHERE id=?",
                    (username, f.get("mobile"), teacher_user["id"])
                )
                if new_password:
                    con.execute(
                        "UPDATE users SET password=? WHERE id=?",
                        (generate_password_hash(new_password), teacher_user["id"])
                    )
            else:
                con.execute("""
                INSERT INTO users(rollno,username,password,gender,mobile,address,photo,enroll,blood,school,birthdate,role)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    0,
                    username,
                    generate_password_hash(new_password or "teacher123"),
                    "",
                    f.get("mobile"),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "teacher"
                ))
            return redirect("/teachers")
        courses = con.execute("SELECT name FROM courses").fetchall()
        subjects = con.execute("SELECT name FROM subjects").fetchall()

    return render_template("admin/edit_teacher.html", teacher=teacher, courses=courses, subjects=subjects, msg="")


@app.route("/delete_teacher/<int:id>")
def delete_teacher(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    with db() as con:
        teacher = con.execute("SELECT username FROM teachers WHERE id=?", (id,)).fetchone()
        con.execute("DELETE FROM teachers WHERE id=?", (id,))
        con.execute("DELETE FROM teacher_attendance WHERE teacher_id=?", (id,))
        if teacher and teacher["username"]:
            con.execute("DELETE FROM users WHERE username=? AND role='teacher'", (teacher["username"],))
    return redirect("/teachers")


@app.route("/delete/<int:id>")
def delete_student(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect("/admin_login")

    with db() as con:
        student = con.execute(
            "SELECT photo FROM users WHERE id=? AND role='student'",
            (id,)
        ).fetchone()
        if student:
            con.execute("DELETE FROM attendance WHERE student_id=?", (id,))
            con.execute("DELETE FROM lecture_attendance WHERE student_id=?", (id,))
            con.execute("DELETE FROM users WHERE id=? AND role='student'", (id,))

            if student["photo"]:
                photo_path = os.path.join(app.config["UPLOAD_FOLDER"], student["photo"])
                if os.path.exists(photo_path):
                    os.remove(photo_path)

    return redirect("/list" if session.get("role") == "admin" else "/teacher")


@app.route("/teacher_attendance", methods=["GET", "POST"])
def teacher_attendance():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    selected_date = request.form.get("date") if request.method == "POST" else request.args.get("date", date.today().isoformat())
    selected_date = selected_date or date.today().isoformat()
    success = request.args.get("saved", "")

    with db() as con:
        teachers = con.execute(
            "SELECT * FROM teachers ORDER BY TRIM(name), id"
        ).fetchall()

        if request.method == "POST":
            for teacher in teachers:
                status = request.form.get(f"status_{teacher['id']}") or "Absent"

                existing = con.execute(
                    "SELECT id FROM teacher_attendance WHERE teacher_id=? AND date=?",
                    (teacher["id"], selected_date)
                ).fetchone()

                if existing:
                    con.execute(
                        "UPDATE teacher_attendance SET status=? WHERE teacher_id=? AND date=?",
                        (status, teacher["id"], selected_date)
                    )
                else:
                    con.execute(
                        "INSERT INTO teacher_attendance(teacher_id,date,status) VALUES (?,?,?)",
                        (teacher["id"], selected_date, status)
                    )
            return redirect(f"/teacher_attendance?date={selected_date}&saved=1")

        attendance_map = {}
        if not success:
            attendance_map = {
                row["teacher_id"]: row["status"]
                for row in con.execute(
                    "SELECT teacher_id, status FROM teacher_attendance WHERE date=?",
                    (selected_date,)
                ).fetchall()
            }
        recent_rows = con.execute("""
        SELECT teacher_attendance.date, teachers.id AS teacher_id, TRIM(teachers.name) AS name, teachers.username, teacher_attendance.status
        FROM teacher_attendance
        JOIN teachers ON teachers.id = teacher_attendance.teacher_id
        ORDER BY teacher_attendance.date DESC, TRIM(teachers.name), teachers.id
        LIMIT 20
        """).fetchall()

    return render_template(
        "admin/teacher_attendance.html",
        teachers=teachers,
        selected_date=selected_date,
        success=success,
        attendance_map=attendance_map,
        recent_rows=recent_rows
    )


@app.route("/teacher_attendance_report")
def teacher_attendance_report():
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect("/attendance")

    selected_date = request.args.get("date", "").strip()
    teacher_username = session.get("user") if session.get("role") == "teacher" else ""
    report_data = get_teacher_attendance_report(selected_date, teacher_username)
    is_teacher_view = session.get("role") == "teacher"

    return render_template(
        "admin/teacher_attendance_report.html",
        selected_date=selected_date,
        summary=report_data["summary"],
        details=report_data["details"],
        total_present=report_data["total_present"],
        total_absent=report_data["total_absent"],
        total_records=report_data["total_records"],
        overall_percent=report_data["overall_percent"],
        chart_labels=report_data["chart_labels"],
        chart_present=report_data["chart_present"],
        chart_absent=report_data["chart_absent"],
        is_teacher_view=is_teacher_view,
        report_teacher_id=None,
    )


@app.route("/teacher_report/<int:id>")
def teacher_report(id):
    if not can_access_teacher_report(id):
        return redirect("/")

    selected_date = request.args.get("date", "").strip()
    report_data = get_teacher_attendance_report(selected_date, teacher_id=id)
    is_teacher_view = session.get("role") == "teacher"

    if not report_data["summary"]:
        return redirect("/teachers" if session.get("role") == "admin" else "/teacher")

    return render_template(
        "admin/teacher_attendance_report.html",
        selected_date=selected_date,
        summary=report_data["summary"],
        details=report_data["details"],
        total_present=report_data["total_present"],
        total_absent=report_data["total_absent"],
        total_records=report_data["total_records"],
        overall_percent=report_data["overall_percent"],
        chart_labels=report_data["chart_labels"],
        chart_present=report_data["chart_present"],
        chart_absent=report_data["chart_absent"],
        is_teacher_view=is_teacher_view,
        report_teacher_id=id,
    )


@app.route("/teacher_attendance_download")
def teacher_attendance_download():
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect("/attendance")

    selected_date = request.args.get("date", "").strip()
    teacher_username = session.get("user") if session.get("role") == "teacher" else ""
    teacher_id = request.args.get("teacher_id", "").strip()
    teacher_id = int(teacher_id) if teacher_id.isdigit() else None
    if teacher_id is not None and not can_access_teacher_report(teacher_id):
        return redirect("/")

    report_data = get_teacher_attendance_report(selected_date, teacher_username, teacher_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Teacher Attendance Report"])
    writer.writerow(["Date Filter", selected_date or "All Dates"])
    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["ID", "Name", "Username", "Course", "Subject", "Present", "Absent", "Total", "Percentage"])

    for row in report_data["summary"]:
        total_count = row["total_count"] or 0
        present_count = row["present_count"] or 0
        absent_count = row["absent_count"] or 0
        percentage = round((present_count * 100 / total_count), 1) if total_count else 0
        writer.writerow([
            row["id"],
            row["name"],
            row["username"] or "-",
            row["course"] or "-",
            row["subject"] or "-",
            present_count,
            absent_count,
            total_count,
            f"{percentage}%"
        ])

    writer.writerow([])
    writer.writerow(["Details"])
    writer.writerow(["Date", "Teacher ID", "Name", "Username", "Course", "Subject", "Status"])

    for row in report_data["details"]:
        writer.writerow([
            row["date"],
            row["teacher_id"],
            row["name"],
            row["username"] or "-",
            row["course"] or "-",
            row["subject"] or "-",
            row["status"]
        ])

    if teacher_id is not None and report_data["summary"]:
        filename_base = f"teacher_attendance_{report_data['summary'][0]['id']}"
    else:
        filename_base = f"teacher_attendance_{teacher_username}" if teacher_username else "teacher_attendance"
    filename = (
        f"{filename_base}_{selected_date}.csv"
        if selected_date
        else f"{filename_base}_all_dates.csv"
    )
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# COURSE CRUD
@app.route("/courses")
def list_courses():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")
    with db() as con:
        courses = con.execute("SELECT * FROM courses").fetchall()
    return render_template("admin/courses.html", courses=courses)


@app.route("/add_course", methods=["GET", "POST"])
def add_course():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")
    if request.method == "POST":
        f = request.form
        with db() as con:
            con.execute("INSERT INTO courses(name,description) VALUES (?,?)", (
                f.get("name"), f.get("description")
            ))
        return redirect("/courses")
    return render_template("admin/add_course.html")


@app.route("/edit_course/<int:id>", methods=["GET", "POST"])
def edit_course(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")
    with db() as con:
        course = con.execute("SELECT * FROM courses WHERE id=?", (id,)).fetchone()
        if request.method == "POST":
            f = request.form
            con.execute("UPDATE courses SET name=?, description=? WHERE id=?", (
                f.get("name"), f.get("description"), id
            ))
            return redirect("/courses")
    return render_template("admin/edit_course.html", course=course)


@app.route("/delete_course/<int:id>")
def delete_course(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    with db() as con:
        con.execute("DELETE FROM courses WHERE id=?", (id,))
    return redirect("/courses")


# SUBJECT CRUD
@app.route("/subjects")
def list_subjects():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")
    with db() as con:
        subjects = con.execute("SELECT * FROM subjects").fetchall()
    return render_template("admin/subjects.html", subjects=subjects)


@app.route("/add_subject", methods=["GET", "POST"])
def add_subject():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")
    if request.method == "POST":
        f = request.form
        course = f.get("course")
        new_course = f.get("new_course")

        with db() as con:
            if new_course and new_course.strip():
                course = new_course.strip()
                # Insert course if not already existing
                existing = con.execute("SELECT id FROM courses WHERE name=?", (course,)).fetchone()
                if not existing:
                    con.execute("INSERT INTO courses(name,description) VALUES (?,?)", (course, f.get("course_description", "Added from subject")))

            con.execute("INSERT INTO subjects(name,course) VALUES (?,?)", (
                f.get("name"), course
            ))

        return redirect("/subjects")
    courses = []
    with db() as con:
        courses = con.execute("SELECT name FROM courses").fetchall()
    return render_template("admin/add_subject.html", courses=courses)


@app.route("/edit_subject/<int:id>", methods=["GET", "POST"])
def edit_subject(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")
    with db() as con:
        subject = con.execute("SELECT * FROM subjects WHERE id=?", (id,)).fetchone()
        if request.method == "POST":
            f = request.form
            con.execute("UPDATE subjects SET name=?, course=? WHERE id=?", (
                f.get("name"), f.get("course"), id
            ))
            return redirect("/subjects")
    courses = con.execute("SELECT name FROM courses").fetchall()
    return render_template("admin/edit_subject.html", subject=subject, courses=courses)


@app.route("/delete_subject/<int:id>")
def delete_subject(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    with db() as con:
        con.execute("DELETE FROM subjects WHERE id=?", (id,))
    return redirect("/subjects")


# VIEW ATTENDANCE (existing)
@app.route("/view_attendance")
def view_attendance():
    return redirect("/attendance")


# UPDATE USER
@app.route("/update/<int:id>", methods=["GET","POST"])
def update(id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect("/attendance")

    with db() as con:

        if request.method=="POST":

            f=request.form
            file=request.files.get("photo")

            old=con.execute(
            "SELECT photo FROM users WHERE id=?",
            (id,)
            ).fetchone()

            duplicate = con.execute(
                "SELECT id FROM users WHERE username=? AND id<>?",
                (f["username"], id)
            ).fetchone()
            if duplicate:
                user = con.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
                return render_template("shared/update.html", user=user, msg="Username already exists")

            filename=old["photo"]

            if file and file.filename!="":

                filename = str(time.time()) + "_" + secure_filename(file.filename)

                path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

                file.save(path)

            con.execute("""
            UPDATE users SET
            username=?,gender=?,mobile=?,address=?,photo=?,enroll=?,blood=?,school=?,birthdate=?,class=?
            WHERE id=?
            """,(f["username"],f["gender"],f["mobile"],f["address"],filename,f["enroll"],f["blood"],f["school"],f["birthdate"],f["class"],id))

            return redirect("/list" if session.get("role") == "admin" else "/teacher")

        user=con.execute("SELECT * FROM users WHERE id=?",(id,)).fetchone()

    return render_template("shared/update.html",user=user, msg="")


# DAILY ATTENDANCE
@app.route("/attendance", methods=["GET","POST"])
def attendance():
    if "user" not in session:
        return redirect("/")
    if session.get("role") == "student":
        return redirect("/my_attendance")

    with db() as con:

        success = request.args.get("saved", "")

        selected_date = request.values.get("date", date.today().isoformat()) or date.today().isoformat()
        leave_students = get_students_on_approved_leave(con, selected_date)

        if request.method=="POST":

            attendance_date = request.form["date"]
            leave_students = get_students_on_approved_leave(con, attendance_date)

            users=con.execute("""
            SELECT * FROM users
            WHERE role='student'
            ORDER BY rollno, username
        """).fetchall()

            for u in users:

                if u["id"] in leave_students:
                    status = "Leave"
                else:
                    status = request.form.get(f"status_{u['id']}") or "Absent"

                check=con.execute(
                "SELECT * FROM attendance WHERE student_id=? AND date=?",
                (u["id"],attendance_date)
                ).fetchone()

                if check:

                    con.execute(
                    "UPDATE attendance SET status=? WHERE student_id=? AND date=?",
                    (status,u["id"],attendance_date)
                    )

                else:

                    con.execute(
                    "INSERT INTO attendance(student_id,date,status) VALUES (?,?,?)",
                    (u["id"],attendance_date,status)
                    )

            return redirect(f"/attendance?saved=1&date={attendance_date}")

        users=con.execute("""
            SELECT * FROM users
            WHERE role='student'
            ORDER BY rollno, username
        """).fetchall()

        attendance_map = {}
        if not success:
            attendance_map = {
                row["student_id"]: row["status"]
                for row in con.execute(
                    "SELECT student_id, status FROM attendance WHERE date=?",
                    (selected_date,)
                ).fetchall()
            }

    return render_template(
        "teacher/attendance.html",
        users=users,
        success=success,
        is_teacher_view=session.get("role") == "teacher",
        selected_date=selected_date,
        leave_students=leave_students,
        attendance_map=attendance_map
    )

# CLASS-WISE ATTENDANCE
@app.route("/attendance_by_class")
def attendance_by_class():
    if "user" not in session:
        return redirect("/")

    if session.get("role") not in {"admin", "teacher"}:
        return redirect("/attendance")

    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            count = con.execute(
                "SELECT COUNT(*) FROM users WHERE role='student' AND class=?",
                (str(class_num),)
            ).fetchone()[0]
            classes_data.append({
                "class_num": class_num,
                "count": count
            })

    template_name = "teacher/teacher_attendance_by_class.html" if session.get("role") == "teacher" else "admin/attendance_by_class.html"
    return render_template(template_name, classes_data=classes_data)


@app.route("/mark_class_attendance/<class_num>", methods=["GET", "POST"])
def mark_class_attendance(class_num):
    if "user" not in session:
        return redirect("/")

    if session.get("role") not in {"admin", "teacher"}:
        return redirect("/attendance")

    with db() as con:
        selected_date = request.values.get("date", date.today().isoformat()) or date.today().isoformat()
        leave_students = get_students_on_approved_leave(con, selected_date)
        
        if request.method == "POST":
            attendance_date = request.form["date"]
            leave_students = get_students_on_approved_leave(con, attendance_date)
            
            students = con.execute(
                "SELECT * FROM users WHERE role='student' AND class=? ORDER BY rollno, username",
                (class_num,)
            ).fetchall()
            
            for student in students:
                if student["id"] in leave_students:
                    status = "Leave"
                else:
                    status = request.form.get(f"status_{student['id']}") or "Absent"
                
                check = con.execute(
                    "SELECT * FROM attendance WHERE student_id=? AND date=?",
                    (student["id"], attendance_date)
                ).fetchone()
                
                if check:
                    con.execute(
                        "UPDATE attendance SET status=? WHERE student_id=? AND date=?",
                        (status, student["id"], attendance_date)
                    )
                else:
                    con.execute(
                        "INSERT INTO attendance(student_id,date,status) VALUES (?,?,?)",
                        (student["id"], attendance_date, status)
                    )
            
            return redirect(f"/mark_class_attendance/{class_num}?saved=1&date={attendance_date}")
        
        students = con.execute(
            "SELECT * FROM users WHERE role='student' AND class=? ORDER BY rollno, username",
            (class_num,)
        ).fetchall()
        
        attendance_map = {}
        success = request.args.get("saved", "")
        if not success:
            attendance_map = {
                row["student_id"]: row["status"]
                for row in con.execute(
                    "SELECT student_id, status FROM attendance WHERE date=?",
                    (selected_date,)
                ).fetchall()
            }

    template_name = "teacher/teacher_mark_class_attendance.html" if session.get("role") == "teacher" else "admin/mark_class_attendance.html"
    return render_template(
        template_name,
        students=students,
        class_num=class_num,
        selected_date=selected_date,
        leave_students=leave_students,
        attendance_map=attendance_map,
        success=request.args.get("saved", "")
    )

# TIMETABLE PAGE
@app.route("/manage_timetable", methods=["GET", "POST"])
def manage_timetable():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/timetable")

    error = ""
    success = request.args.get("saved", "")

    with db() as con:
        start_date, total_days = get_timetable_settings(con)
        schedule_rows = fetch_timetable_rows(con)
        builder_rows = build_timetable_editor_rows(schedule_rows)

        if request.method == "POST":
            start_date = (request.form.get("start_date") or "").strip()
            total_days = (request.form.get("total_days") or "").strip()
            builder_rows = build_timetable_editor_rows_from_form(request.form)
            parsed_rows, error = parse_timetable_builder_form(request.form)

            if not error:
                con.execute(
                    "UPDATE timetable_settings SET start_date=?, total_days=? WHERE id=1",
                    (start_date, int(total_days))
                )
                save_timetable_rows(con, parsed_rows)
                ensure_six_month_timetable(con, reset=True)
                return redirect("/manage_timetable?saved=1")

    return render_template(
        "admin/manage_timetable.html",
        timetable_days=TIMETABLE_DAYS,
        timetable_day_keys=[day.lower() for day in TIMETABLE_DAYS],
        builder_rows=builder_rows,
        start_date=start_date,
        total_days=total_days,
        error=error,
        success=success,
        weekly_timetable=get_weekly_timetable(),
    )


@app.route("/timetable")
def timetable():
    if "user" not in session:
        return redirect("/")

    with db() as con:
        ensure_six_month_timetable(con)
        start_date, total_days = get_timetable_settings(con)
        weekly_timetable = get_weekly_timetable(con)
        active_days = 0
        weekly_slots = 0

        for day_name in weekly_timetable["days"]:
            day_has_lecture = False
            for row in weekly_timetable["rows"]:
                if row.get("is_break"):
                    continue
                if row.get("courses", {}).get(day_name):
                    weekly_slots += 1
                    day_has_lecture = True
            if day_has_lecture:
                active_days += 1

    return render_template(
        "shared/timetable.html",
        weekly_timetable=weekly_timetable,
        is_student_view=session.get("role") == "student",
        is_admin_view=session.get("role") == "admin",
        start_date=start_date,
        total_days=total_days,
        active_days=active_days,
        weekly_slots=weekly_slots,
    )
# GENERATE TIMETABLE
@app.route("/generate_auto_timetable")
def generate_auto_timetable():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "admin":
        return redirect("/attendance")

    with db() as con:
        ensure_six_month_timetable(con, reset=True)

    return redirect("/timetable")
# LECTURE ATTENDANCE
@app.route("/lecture_attendance",methods=["GET","POST"])
def lecture_attendance():
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ("admin", "teacher"):
        return redirect("/my_attendance")

    with db() as con:
        ensure_six_month_timetable(con)

        users=con.execute("""
            SELECT * FROM users
            WHERE role='student'
            ORDER BY rollno, username
        """).fetchall()
        lectures = con.execute("""
        SELECT id, lecture_date, day, lecture_name, time
        FROM lectures
        ORDER BY lecture_date, id
        """).fetchall()
        selected_date = request.values.get("date", date.today().isoformat()) or date.today().isoformat()
        selected_lecture_id = request.values.get("lecture", "")
        success = request.args.get("saved", "")
        leave_students = get_students_on_approved_leave(con, selected_date)

        if request.method=="POST":

            lecture=request.form["lecture"]
            selected_lecture = con.execute(
                "SELECT lecture_date, day, lecture_name, time FROM lectures WHERE id=?",
                (lecture,)
            ).fetchone()
            attendance_date = request.form.get("date") or (selected_lecture["lecture_date"] if selected_lecture else "")
            attendance_day = (
                selected_lecture["day"]
                if selected_lecture and selected_lecture["lecture_date"] == attendance_date
                else get_attendance_day_name(attendance_date)
            )
            lecture_name = selected_lecture["lecture_name"] if selected_lecture else ""
            lecture_time = selected_lecture["time"] if selected_lecture else ""
            leave_students = get_students_on_approved_leave(con, attendance_date)

            for u in users:

                if u["id"] in leave_students:
                    status = "Leave"
                else:
                    status = request.form.get(f"status_{u['id']}") or "Absent"

                check=con.execute("""
                SELECT * FROM lecture_attendance
                WHERE student_id=? AND date=? AND lecture_no=?
                """,(u["id"],attendance_date,lecture)).fetchone()

                if check:

                    con.execute("""
                    UPDATE lecture_attendance
                    SET status=?, lecture_day=?, lecture_name=?, lecture_time=?
                    WHERE student_id=? AND date=? AND lecture_no=?
                    """,(status,attendance_day,lecture_name,lecture_time,u["id"],attendance_date,lecture))

                else:

                    con.execute("""
                    INSERT INTO lecture_attendance(
                        student_id,date,lecture_no,status,lecture_day,lecture_name,lecture_time
                    )
                    VALUES (?,?,?,?,?,?,?)
                    """,(u["id"],attendance_date,lecture,status,attendance_day,lecture_name,lecture_time))

            return redirect(f"/lecture_attendance?date={attendance_date}&lecture={lecture}&saved=1")

        lecture_attendance_map = {}
        if not success and selected_lecture_id:
            lecture_attendance_map = {
                row["student_id"]: row["status"]
                for row in con.execute(
                    """
                    SELECT student_id, status
                    FROM lecture_attendance
                    WHERE date=? AND lecture_no=?
                    """,
                    (selected_date, selected_lecture_id)
                ).fetchall()
            }

    return render_template(
        "teacher/lecture_attendance.html",
        users=users,
        lectures=lectures,
        selected_date=selected_date,
        selected_lecture_id=selected_lecture_id,
        leave_students=leave_students,
        success=success,
        lecture_attendance_map=lecture_attendance_map
    )


@app.route("/festivals")
def festivals():
    if "user" not in session:
        return redirect("/")

    today_text = date.today().isoformat()

    with db() as con:
        ensure_festival_calendar(con)
        data = con.execute("""
        SELECT festival_date, day, name, holiday_type, note
        FROM festivals
        WHERE festival_date >= ?
        ORDER BY festival_date, id
        """, (today_text,)).fetchall()
    total_festivals = len(data)
    holiday_type_count = len({row["holiday_type"] for row in data if row["holiday_type"]})
    next_festival = next((row for row in data if (row["festival_date"] or "") >= today_text), None)

    return render_template(
        "shared/festivals.html",
        data=data,
        is_student_view=session.get("role") == "student",
        total_festivals=total_festivals,
        holiday_type_count=holiday_type_count,
        next_festival=next_festival,
    )


@app.route("/weekly_attendance")
def weekly_attendance():
    if "user" not in session:
        return redirect("/")

    user = current_user()
    if user is None:
        session.clear()
        return redirect("/")

    with db() as con:
        ensure_six_month_timetable(con)
        if session.get("role") == "student":
            summary = con.execute("""
            SELECT
                users.id,
                users.rollno,
                users.username,
                SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN lecture_attendance.status='Absent' THEN 1 ELSE 0 END) AS absent_count,
                SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
            FROM users
            LEFT JOIN lecture_attendance ON lecture_attendance.student_id = users.id
            WHERE users.id=?
            GROUP BY users.id, users.rollno, users.username
            """, (user["id"],)).fetchall()

            lectures = get_lecture_attendance_rows(
                con,
                "WHERE users.id=?",
                (user["id"],)
            )
        else:
            summary = con.execute("""
            SELECT
                users.id,
                users.rollno,
                users.username,
                SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN lecture_attendance.status='Absent' THEN 1 ELSE 0 END) AS absent_count,
                SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
            FROM users
            LEFT JOIN lecture_attendance ON lecture_attendance.student_id = users.id
            WHERE users.role='student'
            GROUP BY users.id, users.rollno, users.username
            ORDER BY users.rollno, users.username
            """).fetchall()

            lectures = get_lecture_attendance_rows(
                con,
                "WHERE users.role='student'"
            )

    return render_template(
        "shared/weekly_attendance.html",
        summary=summary,
        lectures=lectures,
        is_student_view=session.get("role") == "student"
    )


# DATE REPORT
@app.route("/date/<date>")
def date_report(date):
    if "user" not in session:
        return redirect("/")
    if session.get("role") == "student":
        return redirect("/my_attendance")

    with db() as con:

        data=con.execute("""
        SELECT users.rollno,users.username,attendance.status
        FROM attendance
        JOIN users ON users.id=attendance.student_id
        WHERE attendance.date=?
        """,(date,)).fetchall()

    return render_template("shared/day.html",data=data,date=date)


# STUDENT REPORT
@app.route("/report/<int:id>")
def report(id):
    if "user" not in session:
        return redirect("/")

    user = current_user()
    if user is None:
        session.clear()
        return redirect("/")

    if session.get("role") == "student" and user["id"] != id:
        return redirect("/my_attendance")

    report_data = get_student_attendance_report(id)
    if not report_data["student"]:
        return redirect("/attendance")

    return render_template(
    "shared/report.html",
    data=report_data["data"],
    student=report_data["student"],
    present=report_data["present"],
    absent=report_data["absent"],
    leave=report_data["leave"],
    penalty=report_data["penalty"],
    recovery=report_data["recovery"],
    percent=report_data["percent"],
    report_type=report_data["report_type"],
    is_student_view=session.get("role") == "student"
    )


@app.route("/my_attendance")
def my_attendance():
    if "user" not in session:
        return redirect("/")

    user = current_user()
    if user is None:
        session.clear()
        return redirect("/")

    report_data = get_student_attendance_report(user["id"])
    if not report_data["student"]:
        return redirect("/")

    return render_template(
        "shared/report.html",
        data=report_data["data"],
        student=report_data["student"],
        present=report_data["present"],
        absent=report_data["absent"],
        leave=report_data["leave"],
        penalty=report_data["penalty"],
        recovery=report_data["recovery"],
        percent=report_data["percent"],
        report_type=report_data["report_type"],
        is_student_view=True
    )


@app.route("/excel/<int:id>")
def export_attendance(id):
    if "user" not in session:
        return redirect("/")

    user = current_user()
    if user is None:
        session.clear()
        return redirect("/")

    if session.get("role") == "student" and user["id"] != id:
        return redirect("/my_attendance")

    report_data = get_student_attendance_report(id)
    student = report_data["student"]
    data = report_data["data"]
    if not student:
        return redirect("/attendance")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name", student["username"]])
    writer.writerow(["Roll No", student["rollno"]])
    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Present", report_data["present"]])
    writer.writerow(["Absent", report_data["absent"]])
    writer.writerow(["Leave", report_data["leave"]])
    writer.writerow(["Penalty %", report_data["penalty"]])
    writer.writerow(["Recovery %", report_data["recovery"]])
    writer.writerow(["Attendance %", report_data["percent"]])
    writer.writerow([])
    if report_data["report_type"] == "lecture":
        writer.writerow(["Date", "Day", "Subject", "Time", "Status"])
        for row in data:
            writer.writerow([
                row["date"],
                row["day"] or "-",
                row["lecture_name"] or "-",
                row["time"] or "-",
                row["status"]
            ])
    else:
        writer.writerow(["Date", "Status"])
        for row in data:
            writer.writerow([row["date"], row["status"]])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="attendance_report_{student["username"]}.csv"'
    )
    return response


@app.route("/weekly_attendance_download")
def weekly_attendance_download():
    if "user" not in session:
        return redirect("/")

    user = current_user()
    if user is None:
        session.clear()
        return redirect("/")

    with db() as con:
        ensure_six_month_timetable(con)

        if session.get("role") == "student":
            summary = con.execute("""
            SELECT
                users.rollno,
                users.username,
                SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN lecture_attendance.status='Absent' THEN 1 ELSE 0 END) AS absent_count,
                SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
            FROM users
            LEFT JOIN lecture_attendance ON lecture_attendance.student_id = users.id
            WHERE users.id=?
            GROUP BY users.id, users.rollno, users.username
            """, (user["id"],)).fetchall()

            lectures = get_lecture_attendance_rows(
                con,
                "WHERE users.id=?",
                (user["id"],)
            )
        else:
            summary = con.execute("""
            SELECT
                users.rollno,
                users.username,
                SUM(CASE WHEN lecture_attendance.status='Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN lecture_attendance.status='Absent' THEN 1 ELSE 0 END) AS absent_count,
                SUM(CASE WHEN lecture_attendance.status IN ('Present', 'Absent') THEN 1 ELSE 0 END) AS total_count
            FROM users
            LEFT JOIN lecture_attendance ON lecture_attendance.student_id = users.id
            WHERE users.role='student'
            GROUP BY users.id, users.rollno, users.username
            ORDER BY users.rollno, users.username
            """).fetchall()

            lectures = get_lecture_attendance_rows(
                con,
                "WHERE users.role='student'"
            )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Weekly Attendance Summary"])
    writer.writerow([])
    writer.writerow(["Roll No", "Name", "Present", "Absent", "Total Lectures", "Percentage"])

    for row in summary:
        total_count = row["total_count"] or 0
        present_count = row["present_count"] or 0
        absent_count = row["absent_count"] or 0
        percentage = round((present_count * 100 / total_count), 1) if total_count else 0
        writer.writerow([
            row["rollno"],
            row["username"],
            present_count,
            absent_count,
            total_count,
            f"{percentage}%"
        ])

    writer.writerow([])
    writer.writerow(["Lecture Attendance Details"])
    writer.writerow(["Date", "Day", "Subject", "Time", "Name", "Status"])

    for row in lectures:
        writer.writerow([
            row["date"],
            row["day"] or "-",
            row["lecture_name"] or "-",
            row["time"] or "-",
            row["username"],
            row["status"]
        ])

    filename = (
        f'weekly_attendance_{user["username"]}.csv'
        if session.get("role") == "student"
        else "weekly_attendance_all_students.csv"
    )
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# CLASS-WISE REPORTS
@app.route("/class_reports")
def class_reports():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            students = con.execute(
                "SELECT COUNT(*) FROM users WHERE role='student' AND class=?",
                (str(class_num),)
            ).fetchone()[0]
            
            present = con.execute(
                "SELECT COUNT(*) FROM attendance WHERE status='Present' AND student_id IN (SELECT id FROM users WHERE class=?)",
                (str(class_num),)
            ).fetchone()[0]
            
            absent = con.execute(
                "SELECT COUNT(*) FROM attendance WHERE status='Absent' AND student_id IN (SELECT id FROM users WHERE class=?)",
                (str(class_num),)
            ).fetchone()[0]
            
            leave = con.execute(
                "SELECT COUNT(*) FROM attendance WHERE status='Leave' AND student_id IN (SELECT id FROM users WHERE class=?)",
                (str(class_num),)
            ).fetchone()[0]
            
            total = present + absent + leave
            percentage = int((present / total) * 100) if total > 0 else 0
            
            classes_data.append({
                "class_num": class_num,
                "students": students,
                "present": present,
                "absent": absent,
                "leave": leave,
                "total": total,
                "percentage": percentage
            })
    
    return render_template("admin/class_reports.html", classes_data=classes_data)


# CLASS SUBJECTS MANAGEMENT
@app.route("/class_subjects")
def class_subjects():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            subjects = con.execute(
                "SELECT * FROM class_subjects WHERE class_num=? ORDER BY id",
                (class_num,)
            ).fetchall()
            
            classes_data.append({
                "class_num": class_num,
                "subject_count": len(subjects),
                "subjects": [s["subject_name"] for s in subjects]
            })
    
    return render_template("admin/class_subjects.html", classes_data=classes_data)


@app.route("/manage_class_subjects/<class_num>", methods=["GET", "POST"])
def manage_class_subjects(class_num):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        if request.method == "POST":
            subject_name = request.form.get("subject_name", "").strip()
            
            if subject_name:
                con.execute(
                    "INSERT INTO class_subjects(class_num, subject_name) VALUES (?, ?)",
                    (class_num, subject_name)
                )
            
            return redirect(f"/manage_class_subjects/{class_num}")
        
        subjects = con.execute(
            "SELECT * FROM class_subjects WHERE class_num=? ORDER BY id",
            (class_num,)
        ).fetchall()
    
    return render_template(
        "admin/manage_class_subjects.html",
        class_num=class_num,
        subjects=subjects
    )


@app.route("/add_class_subject/<class_num>", methods=["POST"])
def add_class_subject(class_num):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    subject_name = request.form.get("subject_name", "").strip()
    
    if subject_name:
        with db() as con:
            con.execute(
                "INSERT INTO class_subjects(class_num, subject_name) VALUES (?, ?)",
                (class_num, subject_name)
            )
    
    return redirect(f"/manage_class_subjects/{class_num}")


@app.route("/delete_class_subject/<int:subject_id>")
def delete_class_subject(subject_id):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        subject = con.execute("SELECT class_num FROM class_subjects WHERE id=?", (subject_id,)).fetchone()
        class_num = subject["class_num"] if subject else 1
        con.execute("DELETE FROM class_subjects WHERE id=?", (subject_id,))
    
    return redirect(f"/manage_class_subjects/{class_num}")


# CLASS TIMETABLE
@app.route("/class_timetable")
def class_timetable():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            timetable_count = con.execute(
                "SELECT COUNT(*) FROM class_timetable WHERE class_num=?",
                (class_num,)
            ).fetchone()[0]
            
            classes_data.append({
                "class_num": class_num,
                "timetable_count": timetable_count
            })
    
    return render_template("admin/class_timetable.html", classes_data=classes_data)


@app.route("/class_timetable/<class_num>", methods=["GET", "POST"])
def manage_class_timetable(class_num):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        if request.method == "POST":
            day_name = request.form.get("day_name")
            period_number = request.form.get("period_number")
            start_time = request.form.get("start_time")
            end_time = request.form.get("end_time")
            subject_name = request.form.get("subject_name")
            teacher_name = request.form.get("teacher_name")
            
            con.execute(
                """INSERT INTO class_timetable(class_num, day_name, period_number, start_time, end_time, subject_name, teacher_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (class_num, day_name, period_number, start_time, end_time, subject_name, teacher_name)
            )
            
            return redirect(f"/class_timetable/{class_num}")
        
        timetable = con.execute(
            "SELECT * FROM class_timetable WHERE class_num=? ORDER BY period_number",
            (class_num,)
        ).fetchall()
        
        subjects = con.execute(
            "SELECT DISTINCT subject_name FROM class_subjects WHERE class_num=?",
            (class_num,)
        ).fetchall()
    
    return render_template(
        "admin/manage_class_timetable.html",
        class_num=class_num,
        timetable=timetable,
        subjects=[s["subject_name"] for s in subjects],
        days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    )


@app.route("/delete_class_timetable/<int:timetable_id>")
def delete_class_timetable(timetable_id):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        timetable = con.execute("SELECT class_num FROM class_timetable WHERE id=?", (timetable_id,)).fetchone()
        class_num = timetable["class_num"] if timetable else 1
        con.execute("DELETE FROM class_timetable WHERE id=?", (timetable_id,))
    
    return redirect(f"/class_timetable/{class_num}")


# CLASS NOTIFICATIONS
@app.route("/class_notifications")
def class_notifications():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            notifications = con.execute(
                "SELECT COUNT(*) FROM class_notifications WHERE class_num=?",
                (class_num,)
            ).fetchone()[0]
            
            classes_data.append({
                "class_num": class_num,
                "notification_count": notifications
            })
    
    return render_template("admin/class_notifications.html", classes_data=classes_data)


@app.route("/class_notifications/<class_num>", methods=["GET", "POST"])
def manage_class_notifications(class_num):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        if request.method == "POST":
            subject = request.form.get("subject", "").strip()
            message = request.form.get("message", "").strip()
            
            if subject and message:
                con.execute(
                    """INSERT INTO class_notifications(class_num, subject, message, created_by)
                       VALUES (?, ?, ?, ?)""",
                    (class_num, subject, message, session.get("user"))
                )
            
            return redirect(f"/class_notifications/{class_num}")
        
        notifications = con.execute(
            "SELECT * FROM class_notifications WHERE class_num=? ORDER BY created_at DESC",
            (class_num,)
        ).fetchall()
    
    return render_template(
        "admin/manage_class_notifications.html",
        class_num=class_num,
        notifications=notifications
    )


@app.route("/delete_class_notification/<int:notification_id>")
def delete_class_notification(notification_id):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "admin":
        return redirect("/admin")
    
    with db() as con:
        notification = con.execute("SELECT class_num FROM class_notifications WHERE id=?", (notification_id,)).fetchone()
        class_num = notification["class_num"] if notification else 1
        con.execute("DELETE FROM class_notifications WHERE id=?", (notification_id,))
    
    return redirect(f"/class_notifications/{class_num}")


# TEACHER CLASS REPORTS
@app.route("/teacher_class_reports")
def teacher_class_reports():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "teacher":
        return redirect("/teacher")
    
    teacher_name = session.get("user")
    with db() as con:
        # Get all classes where this teacher teaches
        classes_data = []
        for class_num in range(1, 13):
            # Get students in this class
            students = con.execute(
                "SELECT COUNT(*) FROM users WHERE role='student' AND class=?",
                (str(class_num),)
            ).fetchone()[0]
            
            if students == 0:
                continue
            
            # Get attendance stats for this class
            present = con.execute(
                "SELECT COUNT(*) FROM attendance WHERE status='Present' AND student_id IN (SELECT id FROM users WHERE class=?)",
                (str(class_num),)
            ).fetchone()[0]
            
            absent = con.execute(
                "SELECT COUNT(*) FROM attendance WHERE status='Absent' AND student_id IN (SELECT id FROM users WHERE class=?)",
                (str(class_num),)
            ).fetchone()[0]
            
            leave = con.execute(
                "SELECT COUNT(*) FROM attendance WHERE status='Leave' AND student_id IN (SELECT id FROM users WHERE class=?)",
                (str(class_num),)
            ).fetchone()[0]
            
            total = present + absent + leave
            percentage = int((present / total) * 100) if total > 0 else 0
            
            classes_data.append({
                "class_num": class_num,
                "students": students,
                "present": present,
                "absent": absent,
                "leave": leave,
                "total": total,
                "percentage": percentage
            })
    
    return render_template("teacher/teacher_class_reports.html", classes_data=classes_data)


# TEACHER NOTIFICATIONS
@app.route("/teacher_notifications")
def teacher_notifications():
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "teacher":
        return redirect("/teacher")
    
    teacher_name = session.get("user")
    with db() as con:
        classes_data = []
        for class_num in range(1, 13):
            notifications = con.execute(
                "SELECT COUNT(*) FROM teacher_notifications WHERE class_num=? AND created_by=?",
                (class_num, teacher_name)
            ).fetchone()[0]
            
            classes_data.append({
                "class_num": class_num,
                "notification_count": notifications
            })
    
    return render_template("teacher/teacher_notifications.html", classes_data=classes_data)


@app.route("/manage_teacher_notifications/<class_num>", methods=["GET", "POST"])
def manage_teacher_notifications(class_num):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "teacher":
        return redirect("/teacher")
    
    teacher_name = session.get("user")
    with db() as con:
        if request.method == "POST":
            subject = request.form.get("subject", "").strip()
            message = request.form.get("message", "").strip()
            
            if subject and message:
                con.execute(
                    """INSERT INTO teacher_notifications(class_num, subject, message, created_by)
                       VALUES (?, ?, ?, ?)""",
                    (class_num, subject, message, teacher_name)
                )
            
            return redirect(f"/manage_teacher_notifications/{class_num}")
        
        notifications = con.execute(
            "SELECT * FROM teacher_notifications WHERE class_num=? AND created_by=? ORDER BY created_at DESC",
            (class_num, teacher_name)
        ).fetchall()
    
    return render_template(
        "teacher/manage_teacher_notifications.html",
        class_num=class_num,
        notifications=notifications
    )


@app.route("/delete_teacher_notification/<int:notification_id>")
def delete_teacher_notification(notification_id):
    if "user" not in session:
        return redirect("/")
    
    if session.get("role") != "teacher":
        return redirect("/teacher")
    
    teacher_name = session.get("user")
    with db() as con:
        notification = con.execute(
            "SELECT class_num FROM teacher_notifications WHERE id=? AND created_by=?",
            (notification_id, teacher_name)
        ).fetchone()
        class_num = notification["class_num"] if notification else 1
        con.execute("DELETE FROM teacher_notifications WHERE id=? AND created_by=?", (notification_id, teacher_name))
    
    return redirect(f"/manage_teacher_notifications/{class_num}")


# LOGOUT
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


if __name__=="__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=debug_mode)
