import datetime

from dateutil.relativedelta import relativedelta
from django.contrib.messages import get_messages
from django.utils import timezone
from freezegun import freeze_time

from homeschool.courses.models import Course
from homeschool.courses.tests.factories import (
    CourseFactory,
    CourseTaskFactory,
    GradedWorkFactory,
)
from homeschool.schools.models import SchoolYear
from homeschool.schools.tests.factories import (
    GradeLevelFactory,
    SchoolBreakFactory,
    SchoolYearFactory,
)
from homeschool.students.models import Coursework, Enrollment, Grade, Student
from homeschool.students.tests.factories import (
    CourseworkFactory,
    EnrollmentFactory,
    GradeFactory,
    StudentFactory,
)
from homeschool.test import TestCase


class TestStudentsIndexView(TestCase):
    def test_unauthenticated_access(self):
        self.assertLoginRequired("students:index")

    def test_get(self):
        user = self.make_user()

        with self.login(user):
            self.get_check_200("students:index")

        assert self.get_context("nav_link") == "students"

    def test_has_school_year(self):
        """The current school year is in the context."""
        user = self.make_user()
        school_year = SchoolYearFactory(school=user.school)

        with self.login(user):
            self.get_check_200("students:index")

        assert self.get_context("school_year") == school_year

    def test_has_roster(self):
        """The user's students are available in the context."""
        user = self.make_user()
        StudentFactory()
        student = StudentFactory(school=user.school)
        enrollment = EnrollmentFactory(
            student=student, grade_level__school_year__school=user.school
        )

        with self.login(user):
            self.get_check_200("students:index")

        roster = self.get_context("roster")
        assert roster == [{"student": student, "enrollment": enrollment}]

    def test_unenrolled_student(self):
        """A student is unenrolled in the current school year."""
        user = self.make_user()
        StudentFactory()
        student = StudentFactory(school=user.school)

        with self.login(user):
            self.get_check_200("students:index")

        roster = self.get_context("roster")
        assert roster == [{"student": student, "enrollment": None}]


class TestStudentsCreateView(TestCase):
    def test_unauthenticated_access(self):
        self.assertLoginRequired("students:create")

    def test_get(self):
        user = self.make_user()

        with self.login(user):
            self.get_check_200("students:create")

        assert self.get_context("create")

    def test_post(self):
        user = self.make_user()
        data = {"first_name": "Johnny", "last_name": "Smith"}

        with self.login(user):
            response = self.post("students:create", data=data)

        self.response_302(response)
        assert self.reverse("students:index") in response.get("Location")
        student = Student.objects.get(school=user.school)
        assert student.first_name == "Johnny"
        assert student.last_name == "Smith"


class TestStudentCourseView(TestCase):
    def test_unauthenticated_access(self):
        student = StudentFactory()
        course = CourseFactory()
        self.assertLoginRequired(
            "students:course", uuid=student.uuid, course_uuid=course.uuid
        )

    def test_get(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])

        with self.login(user):
            self.get_check_200(
                "students:course", uuid=student.uuid, course_uuid=course.uuid
            )

        assert self.get_context("student") == student
        assert self.get_context("course") == course

    def test_other_user(self):
        user = self.make_user()
        student = StudentFactory()
        course = CourseFactory()

        with self.login(user):
            response = self.get(
                "students:course", uuid=student.uuid, course_uuid=course.uuid
            )

        self.response_404(response)

    @freeze_time("2020-02-10")  # Monday
    def test_has_tasks_today(self):
        """A course that runs today shows its tasks."""
        user = self.make_user()
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year__school=user.school
        )
        student = enrollment.student
        grade_level = enrollment.grade_level
        course = CourseFactory(grade_levels=[grade_level])
        task = CourseTaskFactory(course=course)
        today = timezone.now().date()

        with self.login(user):
            self.get("students:course", uuid=student.uuid, course_uuid=course.uuid)

        assert self.get_context("task_items") == [
            {"course_task": task, "planned_date": today, "has_graded_work": False}
        ]

    @freeze_time("2020-02-10")  # Monday
    def test_has_tasks(self):
        user = self.make_user()
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year__school=user.school
        )
        student = enrollment.student
        grade_level = enrollment.grade_level
        course = CourseFactory(
            grade_levels=[grade_level], days_of_week=Course.WEDNESDAY + Course.THURSDAY
        )
        task_1 = CourseTaskFactory(course=course)
        CourseworkFactory(course_task=task_1, student=student)
        task_2 = CourseTaskFactory(course=course)
        GradedWorkFactory(course_task=task_2)
        today = timezone.now().date() + datetime.timedelta(days=2)

        with self.login(user):
            self.get_check_200(
                "students:course", uuid=student.uuid, course_uuid=course.uuid
            )

        self.assertContext(
            "task_items",
            [{"course_task": task_2, "planned_date": today, "has_graded_work": True}],
        )

    @freeze_time("2020-02-10")  # Monday
    def test_has_tasks_with_completed(self):
        """Completed tasks appear in the context when the query flag is present."""
        user = self.make_user()
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year__school=user.school
        )
        student = enrollment.student
        grade_level = enrollment.grade_level
        course = CourseFactory(grade_levels=[grade_level])
        task_1 = CourseTaskFactory(course=course)
        coursework = CourseworkFactory(course_task=task_1, student=student)
        task_2 = CourseTaskFactory(course=course)
        GradedWorkFactory(course_task=task_2)
        tuesday = timezone.localdate() + datetime.timedelta(days=1)

        with self.login(user):
            self.get_check_200(
                "students:course",
                uuid=student.uuid,
                course_uuid=course.uuid,
                data={"completed_tasks": "1"},
            )

        assert coursework.completed_date == timezone.localdate()
        assert self.get_context("task_items") == [
            {"course_task": task_1, "coursework": coursework, "has_graded_work": False},
            {"course_task": task_2, "planned_date": tuesday, "has_graded_work": True},
        ]

    def test_only_task_for_grade_level(self):
        """Only general tasks and tasks for the student's grade level appear."""
        user = self.make_user()
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year__school=user.school
        )
        course = CourseFactory(grade_levels=[enrollment.grade_level])
        general_task = CourseTaskFactory(course=course)
        grade_level_task = CourseTaskFactory(
            course=course, grade_level=enrollment.grade_level
        )
        CourseTaskFactory(course=course, grade_level=GradeLevelFactory())

        with self.login(user):
            self.get_check_200(
                "students:course", uuid=enrollment.student.uuid, course_uuid=course.uuid
            )

        task_items = self.get_context("task_items")
        assert len(task_items) == 2
        assert task_items[0]["course_task"] == general_task
        assert task_items[1]["course_task"] == grade_level_task

    def test_planned_dates_for_future_school_years(self):
        """The planned dates for a future school year match with the year."""
        today = timezone.localdate()
        user = self.make_user()
        school_year = SchoolYearFactory(
            school=user.school,
            start_date=today + relativedelta(years=1, month=1, day=1),
            end_date=today + relativedelta(years=1, month=12, day=31),
            days_of_week=SchoolYear.ALL_DAYS,
        )
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year=school_year
        )
        course = CourseFactory(
            grade_levels=[enrollment.grade_level], days_of_week=Course.ALL_DAYS
        )
        CourseTaskFactory(course=course)

        with self.login(user):
            self.get_check_200(
                "students:course", uuid=enrollment.student.uuid, course_uuid=course.uuid
            )

        task_item = self.get_context("task_items")[0]
        assert task_item["planned_date"] == school_year.start_date

    def test_planned_date_accounts_for_breaks(self):
        """A planned date for a task will skip break days."""
        today = timezone.localdate()
        user = self.make_user()
        school_year = SchoolYearFactory(
            school=user.school,
            start_date=today + relativedelta(years=1, month=1, day=1),
            end_date=today + relativedelta(years=1, month=12, day=31),
            days_of_week=SchoolYear.ALL_DAYS,
        )
        SchoolBreakFactory(
            school_year=school_year,
            start_date=school_year.start_date,
            end_date=school_year.start_date,
        )
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year=school_year
        )
        course = CourseFactory(
            grade_levels=[enrollment.grade_level], days_of_week=Course.ALL_DAYS
        )
        CourseTaskFactory(course=course)

        with self.login(user):
            self.get_check_200(
                "students:course", uuid=enrollment.student.uuid, course_uuid=course.uuid
            )

        task_item = self.get_context("task_items")[0]
        assert task_item["planned_date"] == school_year.start_date + datetime.timedelta(
            days=1
        )

    def test_no_forecast_course_not_running(self):
        """A course that isn't running will not forecast dates."""
        today = timezone.localdate()
        user = self.make_user()
        school_year = SchoolYearFactory(
            school=user.school,
            start_date=today + relativedelta(years=1, month=1, day=1),
            end_date=today + relativedelta(years=1, month=12, day=31),
            days_of_week=SchoolYear.ALL_DAYS,
        )
        enrollment = EnrollmentFactory(
            student__school=user.school, grade_level__school_year=school_year
        )
        course = CourseFactory(
            grade_levels=[enrollment.grade_level], days_of_week=Course.NO_DAYS
        )
        CourseTaskFactory(course=course)

        with self.login(user):
            self.get_check_200(
                "students:course", uuid=enrollment.student.uuid, course_uuid=course.uuid
            )

        task_item = self.get_context("task_items")[0]
        assert "planned_date" not in task_item


class TestCourseworkFormView(TestCase):
    def test_unauthenticated_access(self):
        student = StudentFactory()
        course_task = CourseTaskFactory()
        self.assertLoginRequired(
            "students:coursework", uuid=student.uuid, course_task_uuid=course_task.uuid
        )

    def test_get(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)

        with self.login(user):
            self.get_check_200(
                "students:coursework",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
            )

        assert self.get_context("student") == student
        assert self.get_context("course_task") == course_task

    def test_post(self):
        """A POST creates a coursework."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        EnrollmentFactory(student=student, grade_level=grade_level)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)
        data = {"completed_date": str(grade_level.school_year.start_date)}

        with self.login(user):
            response = self.post(
                "students:coursework",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
                data=data,
            )

        self.response_302(response)
        assert (
            Coursework.objects.filter(student=student, course_task=course_task).count()
            == 1
        )

    def test_other_user_student(self):
        """A student belonging to another user is a 404."""
        user = self.make_user()
        student = StudentFactory()
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)

        with self.login(user):
            response = self.get(
                "students:coursework",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
            )

        self.response_404(response)

    def test_other_user_task(self):
        """A task belonging to another user is a 404."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        course_task = CourseTaskFactory()

        with self.login(user):
            response = self.get(
                "students:coursework",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
            )

        self.response_404(response)

    def test_multiple_grade_levels(self):
        """A task that belongs to multiple grade levels can be displayed.

        This is a regression test for https://rollbar.com/SchoolDesk/schooldesk/items/6/
        """
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        other_grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level, other_grade_level])
        course_task = CourseTaskFactory(course=course)

        with self.login(user):
            self.get_check_200(
                "students:coursework",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
            )

        assert self.get_context("course_task") == course_task


class TestGradeFormView(TestCase):
    def test_unauthenticated_access(self):
        student = StudentFactory()
        course_task = CourseTaskFactory()
        self.assertLoginRequired(
            "students:grade_task", uuid=student.uuid, course_task_uuid=course_task.uuid
        )

    def test_get(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)
        GradedWorkFactory(course_task=course_task)

        with self.login(user):
            self.get_check_200(
                "students:grade_task",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
            )

        assert self.get_context("student") == student
        assert self.get_context("course_task") == course_task

    def test_post(self):
        """A POST creates a grade."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        EnrollmentFactory(student=student, grade_level=grade_level)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)
        graded_work = GradedWorkFactory(course_task=course_task)
        data = {"score": "100"}

        with self.login(user):
            response = self.post(
                "students:grade_task",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
                data=data,
            )

        self.response_302(response)
        assert (
            Grade.objects.filter(student=student, graded_work=graded_work).count() == 1
        )

    def test_no_graded_work(self):
        """A course task that has no graded work returns a 404."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)

        with self.login(user):
            response = self.get(
                "students:grade_task",
                uuid=student.uuid,
                course_task_uuid=course_task.uuid,
            )

        self.response_404(response)

    def test_redirect_next(self):
        next_url = "/another/location/"
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        EnrollmentFactory(student=student, grade_level=grade_level)
        course = CourseFactory(grade_levels=[grade_level])
        course_task = CourseTaskFactory(course=course)
        GradedWorkFactory(course_task=course_task)
        data = {"score": "100"}
        url = self.reverse(
            "students:grade_task", uuid=student.uuid, course_task_uuid=course_task.uuid
        )
        url += f"?next={next_url}"

        with self.login(user):
            response = self.post(url, data=data)

        self.response_302(response)
        assert next_url in response.get("Location")


class TestGradeView(TestCase):
    def test_unauthenticated_access(self):
        self.assertLoginRequired("students:grade")

    def test_get(self):
        user = self.make_user()

        with self.login(user):
            self.get_check_200("students:grade")

    def test_fetch_students(self):
        user = self.make_user()
        student_1 = StudentFactory(school=user.school)
        student_2 = StudentFactory(school=user.school)

        with self.login(user):
            self.get("students:grade")

        self.assertContext(
            "work_to_grade",
            [
                {"student": student_1, "graded_work": []},
                {"student": student_2, "graded_work": []},
            ],
        )
        assert not self.get_context("has_work_to_grade")

    def test_not_other_students(self):
        user = self.make_user()
        StudentFactory()

        with self.login(user):
            self.get("students:grade")

        self.assertContext("work_to_grade", [])

    def test_fetch_graded_work(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        graded_work_1 = GradedWorkFactory(course_task__course=course)
        CourseworkFactory(student=student, course_task=graded_work_1.course_task)
        GradeFactory(student=student, graded_work=graded_work_1)
        graded_work_2 = GradedWorkFactory(course_task__course=course)
        CourseworkFactory(student=student, course_task=graded_work_2.course_task)

        with self.login(user):
            self.get("students:grade")

        assert self.get_context("work_to_grade") == [
            {"student": student, "graded_work": [graded_work_2]}
        ]
        assert self.get_context("has_work_to_grade")

    def test_not_graded_work_from_other_school(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        graded_work_1 = GradedWorkFactory(course_task__course=course)
        CourseworkFactory(student=student, course_task=graded_work_1.course_task)
        graded_work_2 = GradedWorkFactory()
        CourseworkFactory(course_task=graded_work_2.course_task)

        with self.login(user):
            self.get("students:grade")

        self.assertContext(
            "work_to_grade", [{"student": student, "graded_work": [graded_work_1]}]
        )

    def test_grade(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        course = CourseFactory(grade_levels=[grade_level])
        graded_work = GradedWorkFactory(course_task__course=course)
        graded_work_2 = GradedWorkFactory(course_task__course=course)
        data = {
            f"graded_work-{student.id}-{graded_work.id}": "100",
            f"graded_work-{student.id}-{graded_work_2.id}": "",
        }

        with self.login(user):
            response = self.post("students:grade", data=data)

        self.response_302(response)
        assert response.get("Location") == self.reverse("core:daily")
        grade = Grade.objects.get(student=student, graded_work=graded_work)
        assert grade.score == 100


class TestEnrollmentCreateView(TestCase):
    def test_unauthenticated_access(self):
        school_year = SchoolYearFactory()

        self.assertLoginRequired(
            "students:enrollment_create", school_year_uuid=school_year.uuid
        )

    def test_get(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        school_year = SchoolYearFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year=school_year)
        enrolled_student = StudentFactory(school=user.school)
        EnrollmentFactory(student=enrolled_student, grade_level=grade_level)

        with self.login(user):
            self.get_check_200(
                "students:enrollment_create", school_year_uuid=school_year.uuid
            )

        assert list(self.get_context("grade_levels")) == [grade_level]
        assert list(self.get_context("students")) == [student]

    def test_post(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        data = {"student": str(student.id), "grade_level": str(grade_level.id)}

        with self.login(user):
            response = self.post(
                "students:enrollment_create",
                school_year_uuid=grade_level.school_year.uuid,
                data=data,
            )

        assert Enrollment.objects.filter(
            student=student, grade_level=grade_level
        ).exists()
        assert response.get("Location") == self.reverse(
            "schools:school_year_detail", uuid=grade_level.school_year.uuid
        )

    def test_no_students(self):
        """With no students, redirect to the student index page."""
        user = self.make_user()
        school_year = SchoolYearFactory(school=user.school)
        GradeLevelFactory(school_year=school_year)

        with self.login(user):
            response = self.get(
                "students:enrollment_create", school_year_uuid=school_year.uuid
            )

        assert response.get("Location") == self.reverse("students:index")
        message = list(get_messages(response.wsgi_request))[0]
        assert str(message) == "You need to add a student to enroll."

    def test_no_enrollable_students(self):
        """When all students are enrolled, redirect back to the school year."""
        user = self.make_user()
        school_year = SchoolYearFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year=school_year)
        EnrollmentFactory(student__school=user.school, grade_level=grade_level)

        with self.login(user):
            response = self.get(
                "students:enrollment_create", school_year_uuid=school_year.uuid
            )

        assert response.get("Location") == self.reverse(
            "schools:school_year_detail", uuid=school_year.uuid
        )
        message = list(get_messages(response.wsgi_request))[0]
        assert str(message) == "All students are enrolled in the school year."

    def test_no_grade_levels(self):
        """When no grade levels are available, redirect to create a grade level."""
        user = self.make_user()
        school_year = SchoolYearFactory(school=user.school)

        with self.login(user):
            response = self.get(
                "students:enrollment_create", school_year_uuid=school_year.uuid
            )

        assert response.get("Location") == self.reverse(
            "schools:grade_level_create", uuid=school_year.uuid
        )
        message = list(get_messages(response.wsgi_request))[0]
        assert (
            str(message)
            == "You need to create a grade level for a student to enroll in."
        )

    def test_user_access_their_school_years(self):
        """The user can only access their school years."""
        user = self.make_user()
        grade_level = GradeLevelFactory()

        with self.login(user):
            response = self.get(
                "students:enrollment_create",
                school_year_uuid=grade_level.school_year.uuid,
            )

        self.response_404(response)


class TestStudentEnrollmentCreateView(TestCase):
    def test_unauthenticated_access(self):
        student = StudentFactory()
        school_year = SchoolYearFactory()

        self.assertLoginRequired(
            "students:student_enrollment_create",
            uuid=student.uuid,
            school_year_uuid=school_year.uuid,
        )

    def test_get(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        school_year = SchoolYearFactory(school=user.school)

        with self.login(user):
            self.get_check_200(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=school_year.uuid,
            )

    def test_post(self):
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        data = {"student": str(student.id), "grade_level": str(grade_level.id)}

        with self.login(user):
            self.post(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
                data=data,
            )

        assert Enrollment.objects.filter(
            student=student, grade_level=grade_level
        ).exists()

    def test_invalid_student_submission(self):
        """An invalid POST for a student is rejected."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        other_student = StudentFactory()
        grade_level = GradeLevelFactory(school_year__school=user.school)
        data = {"student": str(other_student.id), "grade_level": str(grade_level.id)}

        with self.login(user):
            self.post(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
                data=data,
            )

        form = self.get_context("form")
        assert "You may not enroll that student." in form.errors["__all__"][0]

    def test_invalid_grade_level_submission(self):
        """An invalid POST for a grade level is rejected."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)
        other_grade_level = GradeLevelFactory()
        data = {"student": str(student.id), "grade_level": str(other_grade_level.id)}

        with self.login(user):
            self.post(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
                data=data,
            )

        form = self.get_context("form")
        assert "You may not enroll to that grade level." in form.errors["__all__"][0]

    def test_has_student(self):
        """The student is in the context."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)

        with self.login(user):
            self.get(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
            )

        assert self.get_context("student") == student

    def test_not_other_students(self):
        """Another student is not viewable."""
        user = self.make_user()
        student = StudentFactory()
        grade_level = GradeLevelFactory(school_year__school=user.school)

        with self.login(user):
            response = self.get(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
            )

        self.response_404(response)

    def test_has_school_year(self):
        """The school year is in the context."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)

        with self.login(user):
            self.get(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
            )

        assert self.get_context("school_year") == grade_level.school_year

    def test_has_grade_levels(self):
        """The grade levels for the school year are in the context."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory(school_year__school=user.school)

        with self.login(user):
            self.get(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
            )

        grade_levels = self.get_context("grade_levels")
        assert list(grade_levels) == [grade_level]

    def test_user_access_their_school_years(self):
        """The user can only access their school years."""
        user = self.make_user()
        student = StudentFactory(school=user.school)
        grade_level = GradeLevelFactory()

        with self.login(user):
            response = self.get(
                "students:student_enrollment_create",
                uuid=student.uuid,
                school_year_uuid=grade_level.school_year.uuid,
            )

        self.response_404(response)
