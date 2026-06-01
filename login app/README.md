# Student Attendance System

Flask-based attendance management project with:

- Admin dashboard
- Teacher dashboard
- Student attendance portal
- Daily and lecture attendance
- Weekly reports
- Timetable and festival calendar

## Run

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Start the project:

```bash
python app.py
```

3. Open in browser:

```text
http://127.0.0.1:5000/
```

## Login

Use the single login screen:

```text
http://127.0.0.1:5000/login
```

Choose Admin Desk, Teacher Desk, or Student Desk. The app redirects each successful login to its own dashboard.

- Admin Desk:
  - Username: `admin`
  - Password: `admin123`
- Teacher Desk:
  - Username: `atmiya`
  - Password: `atmiya123`
- Student Desk:
  - Username: `student`
  - Password: `student123`

## Test

```bash
python -m unittest discover -s tests -v
```

## Database

- Main SQLite database: `users.db`
- Uploads folder: `uploads/`
- Optional env vars:
  - `ATTENDANCE_DB_PATH`
  - `FLASK_SECRET_KEY`
