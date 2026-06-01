import importlib
import os
import shutil
import sqlite3
import tempfile
import unittest


class AttendanceAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="attendance-app-")
        cls.db_path = os.path.join(cls.temp_dir, "test_users.db")
        os.environ["ATTENDANCE_DB_PATH"] = cls.db_path
        os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

        import app as attendance_app

        cls.app_module = importlib.reload(attendance_app)
        cls.app = cls.app_module.app
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.client = self.app.test_client()
        self.reset_database()

    def reset_database(self):
        if os.path.exists(self.db_path):
            with sqlite3.connect(self.db_path) as con:
                tables = con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (table_name,) in tables:
                    con.execute(f"DROP TABLE IF EXISTS {table_name}")
        self.app_module.initialize_database()

    def insert_student(self, username="student1", rollno=1):
        with self.app_module.db() as con:
            con.execute(
                """
                INSERT INTO users(rollno, username, password, gender, mobile, address, photo, enroll, blood, school, birthdate, class, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rollno,
                    username,
                    self.app_module.generate_password_hash("pass1234"),
                    "Male",
                    "9999999999",
                    "Test Address",
                    "",
                    "ENR001",
                    "O+",
                    "Test School",
                    "2005-01-01",
                    "10",
                    "student",
                ),
            )
            return con.execute(
                "SELECT id FROM users WHERE username=?",
                (username,)
            ).fetchone()["id"]

    def login_admin(self):
        return self.client.post(
            "/admin_login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )

    def login_teacher(self):
        return self.client.post(
            "/teacher_login",
            data={"username": "atmiya", "password": "atmiya123"},
            follow_redirects=False,
        )

    def login_student(self, username="student1", password="pass1234"):
        return self.client.post(
            "/student_login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )

    def insert_teacher(self, name, username, course="BCA", subject="Python"):
        with self.app_module.db() as con:
            con.execute(
                """
                INSERT INTO teachers(name, email, mobile, username, course, subject)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, f"{username}@example.com", "8888888888", username, course, subject),
            )
            return con.execute(
                "SELECT id FROM teachers WHERE username=?",
                (username,)
            ).fetchone()["id"]

    def test_public_pages_load(self):
        for path in ["/", "/login", "/login?role=admin", "/login?role=teacher", "/login?role=student", "/signup?role=admin", "/signup?role=teacher", "/student_login", "/admin_login", "/teacher_login", "/forgot_password", "/forgot_password?role=admin", "/forgot_password?role=teacher", "/forgot_password?role=student"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

    def test_public_admin_signup_creates_admin_account(self):
        response = self.client.post(
            "/signup?role=admin",
            data={
                "name": "Panel Admin",
                "username": "paneladmin",
                "password": "pass1234",
                "confirm_password": "pass1234",
                "mobile": "9876543210",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin", response.headers["Location"])

        with self.app_module.db() as con:
            user = con.execute(
                "SELECT username, role FROM users WHERE username=?",
                ("paneladmin",)
            ).fetchone()

        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "admin")

        dashboard_response = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(dashboard_response.status_code, 200)

    def test_public_teacher_signup_creates_teacher_account(self):
        response = self.client.post(
            "/signup?role=teacher",
            data={
                "name": "Faculty Signup",
                "email": "faculty@example.com",
                "mobile": "9876543211",
                "course": "BCA",
                "subject": "Python",
                "username": "facultysignup",
                "password": "pass1234",
                "confirm_password": "pass1234",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/teacher", response.headers["Location"])

        with self.app_module.db() as con:
            user = con.execute(
                "SELECT username, role FROM users WHERE username=?",
                ("facultysignup",)
            ).fetchone()
            teacher = con.execute(
                "SELECT name, subject FROM teachers WHERE username=?",
                ("facultysignup",)
            ).fetchone()

        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "teacher")
        self.assertIsNotNone(teacher)
        self.assertEqual(teacher["name"], "Faculty Signup")

        dashboard_response = self.client.get("/teacher", follow_redirects=False)
        self.assertEqual(dashboard_response.status_code, 200)

    def test_public_student_signup_creates_student_and_logs_in(self):
        response = self.client.post(
            "/signup?role=student",
            data={
                "rollno": "22",
                "username": "studentsignup",
                "password": "pass1234",
                "confirm_password": "pass1234",
                "gender": "Male",
                "mobile": "9876543212",
                "address": "Demo Address",
                "enroll": "ENR022",
                "blood": "A+",
                "school": "Demo School",
                "birthdate": "2005-01-01",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/home", response.headers["Location"])

        with self.app_module.db() as con:
            user = con.execute(
                "SELECT username, role FROM users WHERE username=?",
                ("studentsignup",)
            ).fetchone()

        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "student")

        dashboard_response = self.client.get("/home", follow_redirects=False)
        self.assertEqual(dashboard_response.status_code, 200)

    def test_role_specific_login_is_enforced(self):
        response = self.client.post(
            "/student_login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid student login", response.data)

        response = self.login_admin()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin", response.headers["Location"])

    def test_single_login_opens_selected_role_desk(self):
        self.insert_student(username="singleloginstudent", rollno=14)

        response = self.client.post(
            "/login",
            data={"role": "admin", "username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin", response.headers["Location"])

        self.client.get("/logout", follow_redirects=False)
        response = self.client.post(
            "/login",
            data={"role": "teacher", "username": "atmiya", "password": "atmiya123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/teacher", response.headers["Location"])

        self.client.get("/logout", follow_redirects=False)
        response = self.client.post(
            "/login",
            data={"role": "student", "username": "singleloginstudent", "password": "pass1234"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/home", response.headers["Location"])

    def test_single_login_rejects_wrong_selected_role(self):
        response = self.client.post(
            "/login",
            data={"role": "teacher", "username": "admin", "password": "admin123"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid teacher login", response.data)

    def test_student_login_does_not_show_signup_link(self):
        response = self.client.get("/student_login")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Create Account", response.data)

    def test_role_specific_forgot_password_rejects_wrong_role(self):
        response = self.client.post(
            "/forgot_password?role=teacher",
            data={
                "username": "admin",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
                "role": "teacher",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not registered as a teacher", response.data)

    def test_role_specific_forgot_password_updates_matching_user(self):
        self.insert_student(username="resetstudent", rollno=12)

        response = self.client.post(
            "/forgot_password?role=student",
            data={
                "username": "resetstudent",
                "new_password": "freshpass123",
                "confirm_password": "freshpass123",
                "role": "student",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Password reset successfully", response.data)

        login_response = self.client.post(
            "/student_login",
            data={"username": "resetstudent", "password": "freshpass123"},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertIn("/home", login_response.headers["Location"])

    def test_admin_can_delete_student(self):
        student_id = self.insert_student(username="delete_me", rollno=10)
        self.login_admin()

        response = self.client.get(f"/delete/{student_id}", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/list", response.headers["Location"])

        with self.app_module.db() as con:
            student = con.execute("SELECT id FROM users WHERE id=?", (student_id,)).fetchone()
        self.assertIsNone(student)

    def test_teacher_attendance_post_redirects_back_to_attendance(self):
        student_id = self.insert_student(username="daily_student", rollno=7)
        self.login_teacher()

        response = self.client.post(
            "/attendance",
            data={
                "date": "2026-03-25",
                f"status_{student_id}": "Present",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/attendance?saved=1", response.headers["Location"])

        with self.app_module.db() as con:
            row = con.execute(
                "SELECT status FROM attendance WHERE student_id=? AND date=?",
                (student_id, "2026-03-25"),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Present")

    def test_student_report_percentage_uses_present_vs_absent_counts(self):
        student_id = self.insert_student(username="percent_student", rollno=8)

        with self.app_module.db() as con:
            statuses = [
                ("2026-03-25", 1, "Present"),
                ("2026-03-25", 2, "Absent"),
                ("2026-03-24", 1, "Present"),
                ("2026-03-24", 2, "Absent"),
                ("2026-03-23", 1, "Present"),
                ("2026-03-23", 2, "Absent"),
                ("2026-03-22", 1, "Absent"),
                ("2026-03-22", 2, "Absent"),
            ]
            for attendance_date, lecture_no, status in statuses:
                con.execute(
                    """
                    INSERT INTO lecture_attendance(student_id, date, lecture_no, status, lecture_day, lecture_name, lecture_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (student_id, attendance_date, lecture_no, status, "Monday", f"Lecture {lecture_no}", "09:00"),
                )

        report = self.app_module.get_student_attendance_report(student_id)

        self.assertEqual(report["present"], 3)
        self.assertEqual(report["absent"], 5)
        self.assertEqual(report["percent"], 38)

    def test_student_result_is_visible_after_admin_declares_it(self):
        student_id = self.insert_student(username="result_student", rollno=18)

        with self.app_module.db() as con:
            con.execute(
                """
                INSERT INTO exam_cia_marks(student_id, class_num, subject, marks, total_marks, exam_term, entered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (student_id, "10", "PHP", 20, 25, "CIA", "admin"),
            )
            con.execute(
                """
                INSERT INTO exam_cia_marks(student_id, class_num, subject, marks, total_marks, exam_term, entered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (student_id, "10", "PHP", 40, 50, "SEE", "admin"),
            )

        self.login_student("result_student")
        pending_response = self.client.get("/student_result", follow_redirects=False)
        self.assertEqual(pending_response.status_code, 200)
        self.assertIn(b"Result Not Declared", pending_response.data)

        self.client.get("/logout", follow_redirects=False)
        self.login_admin()
        declare_response = self.client.post(
            "/admin_results",
            data={"class_num": "10", "action": "declare"},
            follow_redirects=False,
        )
        self.assertEqual(declare_response.status_code, 200)

        self.client.get("/logout", follow_redirects=False)
        self.login_student("result_student")
        result_response = self.client.get("/student_result", follow_redirects=False)
        self.assertEqual(result_response.status_code, 200)
        self.assertIn(b"ATMIYA UNIVERSITY", result_response.data)
        self.assertIn(b"PHP", result_response.data)
        self.assertIn(b"60.0 / 75", result_response.data)

    def test_admin_dashboard_requires_admin_session(self):
        response = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/", response.headers["Location"])


    def test_admin_dashboard_shows_student_report_view_action(self):
        self.insert_student(username="report_student", rollno=3)
        self.login_admin()

        response = self.client.get("/admin", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Report", response.data)
        self.assertIn(b">View<", response.data)

    def test_teacher_dashboard_shows_student_report_view_action(self):
        self.insert_student(username="teacher_side_student", rollno=4)
        self.login_teacher()

        response = self.client.get("/teacher", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Student overview table", response.data)
        self.assertIn(b">View<", response.data)


    def test_admin_dashboard_shows_teacher_overview_table(self):
        self.insert_teacher("Faculty Admin View", "facultyadminview")
        self.login_admin()

        response = self.client.get("/admin", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Teacher overview table", response.data)
        self.assertIn(b"/teacher_report/", response.data)


    def test_teacher_can_open_own_teacher_attendance_report(self):
        atmiya_teacher_id = self.insert_teacher("Atmiya Sir", "atmiya")
        other_teacher_id = self.insert_teacher("Other Teacher", "otherteacher")

        with self.app_module.db() as con:
            con.execute(
                "INSERT INTO teacher_attendance(teacher_id, date, status) VALUES (?, ?, ?)",
                (atmiya_teacher_id, "2026-03-25", "Present"),
            )
            con.execute(
                "INSERT INTO teacher_attendance(teacher_id, date, status) VALUES (?, ?, ?)",
                (other_teacher_id, "2026-03-25", "Absent"),
            )

        self.login_teacher()
        response = self.client.get("/teacher_attendance_report", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Atmiya Sir", response.data)
        self.assertNotIn(b"Other Teacher", response.data)

    def test_teacher_attendance_download_is_filtered_for_logged_in_teacher(self):
        atmiya_teacher_id = self.insert_teacher("Atmiya Sir", "atmiya")
        other_teacher_id = self.insert_teacher("Other Teacher", "otherteacher")

        with self.app_module.db() as con:
            con.execute(
                "INSERT INTO teacher_attendance(teacher_id, date, status) VALUES (?, ?, ?)",
                (atmiya_teacher_id, "2026-03-25", "Present"),
            )
            con.execute(
                "INSERT INTO teacher_attendance(teacher_id, date, status) VALUES (?, ?, ?)",
                (other_teacher_id, "2026-03-25", "Absent"),
            )

        self.login_teacher()
        response = self.client.get("/teacher_attendance_download", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Atmiya Sir", response.data)
        self.assertNotIn(b"Other Teacher", response.data)


    def test_admin_teachers_list_shows_report_view_action(self):
        self.insert_teacher("Faculty One", "facultyone")
        self.login_admin()

        response = self.client.get("/teachers", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Report", response.data)
        self.assertIn(b">View<", response.data)

    def test_admin_can_open_single_teacher_report(self):
        teacher_one_id = self.insert_teacher("Faculty One", "facultyone")
        teacher_two_id = self.insert_teacher("Faculty Two", "facultytwo")

        with self.app_module.db() as con:
            con.execute(
                "INSERT INTO teacher_attendance(teacher_id, date, status) VALUES (?, ?, ?)",
                (teacher_one_id, "2026-03-26", "Present"),
            )
            con.execute(
                "INSERT INTO teacher_attendance(teacher_id, date, status) VALUES (?, ?, ?)",
                (teacher_two_id, "2026-03-26", "Absent"),
            )

        self.login_admin()
        response = self.client.get(f"/teacher_report/{teacher_one_id}", follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Faculty One", response.data)
        self.assertNotIn(b"Faculty Two", response.data)

    def test_manage_timetable_requires_admin_session(self):
        self.login_teacher()

        response = self.client.get("/manage_timetable", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/timetable", response.headers["Location"])

    def test_admin_can_save_new_timetable(self):
        self.login_admin()

        response = self.client.post(
            "/manage_timetable",
            data={
                "start_date": "2026-03-30",
                "total_days": "7",
                "row_count": "2",
                "row_type_0": "lecture",
                "period_number_0": "1",
                "start_time_0": "08:00",
                "end_time_0": "08:45",
                "lecture_0_monday": "Python Advanced",
                "lecture_0_tuesday": "AI Lab",
                "lecture_0_wednesday": "",
                "lecture_0_thursday": "",
                "lecture_0_friday": "",
                "lecture_0_saturday": "",
                "row_type_1": "break",
                "period_number_1": "",
                "start_time_1": "08:45",
                "end_time_1": "09:00",
                "lecture_1_monday": "",
                "lecture_1_tuesday": "",
                "lecture_1_wednesday": "",
                "lecture_1_thursday": "",
                "lecture_1_friday": "",
                "lecture_1_saturday": "",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/manage_timetable?saved=1", response.headers["Location"])

        with self.app_module.db() as con:
            settings = con.execute(
                "SELECT start_date, total_days FROM timetable_settings WHERE id=1"
            ).fetchone()
            monday_row = con.execute(
                """
                SELECT lecture_name, start_time, end_time
                FROM timetable_schedule
                WHERE row_order=1 AND day_name='Monday'
                """
            ).fetchone()
            break_row = con.execute(
                """
                SELECT is_break, start_time, end_time
                FROM timetable_schedule
                WHERE row_order=2
                LIMIT 1
                """
            ).fetchone()
            lecture_row = con.execute(
                """
                SELECT lecture_name, time
                FROM lectures
                WHERE lecture_date='2026-03-30'
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()

        self.assertEqual(settings["start_date"], "2026-03-30")
        self.assertEqual(settings["total_days"], 7)
        self.assertEqual(monday_row["lecture_name"], "Python Advanced")
        self.assertEqual(monday_row["start_time"], "08:00")
        self.assertEqual(monday_row["end_time"], "08:45")
        self.assertEqual(break_row["is_break"], 1)
        self.assertEqual(lecture_row["lecture_name"], "Python Advanced")
        self.assertEqual(lecture_row["time"], "08:00 to 08:45")


if __name__ == "__main__":
    unittest.main()
