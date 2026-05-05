# Manual Testing Checklist

## 1. Login Pages
- Open `/`
- Open `/student_login`
- Open `/teacher_login`
- Open `/admin_login`
- Check that all pages load properly
- Try wrong username/password and confirm error message appears
- Try correct login for student, teacher, and admin

## 2. Student Flow
- Login as student
- Open dashboard `/home`
- Check attendance percentage is visible
- Check present, absent, leave, penalty, and recovery values
- Open `/my_attendance`
- Confirm attendance rows and percentage are shown correctly
- Open `/student_leave`
- Submit a leave request
- Confirm leave request appears in history
- Confirm leave request status is visible

## 3. Admin Leave Approval Flow
- Login as admin
- Open `/admin`
- Go to leave request table
- Approve one student leave request
- Reject one student leave request
- Confirm status changes properly
- Confirm `From` and `To` dates appear in one line

## 4. Teacher Leave Approval Flow
- Login as teacher
- Open `/teacher`
- Check student leave request table
- Approve or reject a leave request
- Confirm status changes properly
- Confirm date columns look correct

## 5. Daily Attendance Flow
- Login as admin or teacher
- Open `/attendance`
- Select a date
- Mark one student `Present`
- Mark one student `Absent`
- For approved leave student, confirm `Leave` is shown
- Confirm approved leave student cannot be marked `Present`
- Save attendance
- Confirm success message appears with selected date
- Confirm same date stays selected after save

## 6. Lecture Attendance Flow
- Open `/lecture_attendance`
- Select date and lecture
- Mark attendance
- Confirm approved leave student shows `Leave`
- Confirm leave student cannot be marked `Present`
- Save attendance
- Confirm same date and lecture remain selected after save

## 7. Percentage Logic
- Give one student approved leave entry and save attendance
- Confirm percentage reduces by 10%
- Mark one student absent without leave
- Confirm percentage reduces by 20%
- Next day mark that same student present
- Confirm recovery adds 5%
- Open `/home`
- Open `/my_attendance`
- Open `/report/<student_id>`
- Confirm percentage is same everywhere

## 8. Teacher Attendance Flow
- Login as admin
- Open `/teacher_attendance`
- Select date
- Mark one teacher present and one absent
- Save attendance
- Confirm success message appears with formatted date
- Confirm recent teacher attendance table updates

## 9. Reports
- Open `/weekly_attendance`
- Confirm summary table loads
- Confirm lecture details load
- Open student report `/report/<student_id>`
- Confirm present, absent, leave, penalty, recovery, and percentage are shown
- Open teacher report `/teacher_attendance_report`
- Confirm report table and percentage load properly

## 10. Export Checks
- Open student CSV export `/excel/<student_id>`
- Confirm CSV contains Present, Absent, Leave, Penalty %, Recovery %, Attendance %
- Open weekly report download `/weekly_attendance_download`
- Open teacher report download `/teacher_attendance_download`

## 11. Access Control
- Logout
- Try opening `/admin`
- Try opening `/teacher`
- Try opening `/attendance`
- Try opening `/student_leave`
- Confirm protected routes redirect when not logged in

## 12. Final Smoke Check
- Start app with `python app.py`
- Confirm server starts on `http://127.0.0.1:5000`
- Open main flows once:
- Student login
- Teacher login
- Admin login
- Attendance save
- Leave approval
- Report view
