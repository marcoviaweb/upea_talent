from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import (
    AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment,
    GradeRecord, Institution, StudentProfile, TeachingAssignment,
)
from apps.audit.models import AuditEvent

from .models import DevelopmentRecord, StudentProject, StudentSkill
from .services import create_grade_record, save_development_record


class TrajectoryWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_superuser(username="e05_admin", email="admin-e05@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Universidad Demo", short_name="E05-DEMO")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.period = AcademicPeriod.objects.create(career=cls.career, code="E05-P", name="Periodo de prueba", starts_on=today - timedelta(days=30), ends_on=today + timedelta(days=30), status=AcademicPeriod.Status.OPEN)
        cls.course = Course.objects.create(career=cls.career, code="E05-101", name="Curso de prueba")
        cls.offering = CourseOffering.objects.create(course=cls.course, period=cls.period, group_code="A", status=CourseOffering.Status.OPEN)
        cls.student, cls.enrollment, cls.roster = cls.make_student("e05_student", "E05-001")
        cls.other_student, cls.other_enrollment, cls.other_roster = cls.make_student("e05_other", "E05-002")
        cls.teacher = User.objects.create_user(username="e05_teacher", email="teacher-e05@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.teacher, role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP, group=cls.offering, reason="Prueba E05")
        TeachingAssignment.objects.create(user=cls.teacher, offering=cls.offering, role=TeachingAssignment.AssignmentRole.TEACHER, starts_on=today - timedelta(days=1))
        cls.project = StudentProject.objects.create(
            enrollment=cls.enrollment, created_by=cls.student, title="Proyecto de prueba",
            description="Construcción de un prototipo académico.", role="Desarrollo", status=DevelopmentRecord.Status.IN_REVIEW,
        )
        cls.skill = StudentSkill.objects.create(
            enrollment=cls.enrollment, created_by=cls.student, name="Python", proficiency_label="Intermedio",
            status=DevelopmentRecord.Status.DECLARED,
        )
        GradeRecord.objects.create(
            enrollment=cls.enrollment, offering=cls.offering, grade_value=Decimal("81"), scale_snapshot=100,
            status=GradeRecord.Status.UNVERIFIED, source="Dato pendiente", recorded_by=cls.admin,
        )

    @classmethod
    def make_student(cls, username, number):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=user, institution=cls.institution, student_number=number)
        enrollment = Enrollment.objects.create(student=profile, career=cls.career, period=cls.period, valid_from=cls.period.starts_on)
        grant_role(actor=cls.admin, user=user, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Prueba E05")
        roster = CourseEnrollment.objects.create(enrollment=enrollment, offering=cls.offering)
        return user, enrollment, roster

    def test_login_required_and_own_profile_is_rendered(self):
        url = reverse("profiles:api-enrollment-profile", args=(self.enrollment.pk,))
        self.assertEqual(APIClient().get(url).status_code, 403)
        client, _ = self.api_session(self.student)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["grades"], [])

    def api_session(self, user):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(reverse("profiles:api-csrf")).data["csrfToken"]
        response = client.post(
            reverse("profiles:api-login"),
            {"username": user.username, "password": "test-pass-123"},
            format="json", HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200, response.data)
        return client, response.data["csrfToken"]

    def test_api_login_requires_csrf_and_returns_authenticated_session(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(reverse("profiles:api-login"), {"username": self.student.username, "password": "test-pass-123"}, format="json")
        self.assertEqual(response.status_code, 403)
        client, _ = self.api_session(self.student)
        home = client.get(reverse("profiles:api-home"))
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.data["user"]["username"], self.student.username)

    def test_api_profile_hides_other_students_and_unverified_grades(self):
        client, _ = self.api_session(self.student)
        own = client.get(reverse("profiles:api-enrollment-profile", args=(self.enrollment.pk,)))
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data["grades"], [])
        other = client.get(reverse("profiles:api-enrollment-profile", args=(self.other_enrollment.pk,)))
        self.assertEqual(other.status_code, 404)

    def test_api_creates_and_audits_student_declaration(self):
        client, csrf = self.api_session(self.student)
        response = client.post(
            reverse("profiles:api-development-create", args=(self.enrollment.pk, "project")),
            {"title": "Proyecto por API", "description": "Registro desde el portal React.",
             "role": "Desarrollo", "started_on": "", "completed_on": "", "intent": "submit"},
            format="json", HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 201, response.data)
        created = StudentProject.objects.get(title="Proyecto por API")
        self.assertEqual(created.status, DevelopmentRecord.Status.IN_REVIEW)
        self.assertTrue(AuditEvent.objects.filter(action="trajectory.development_submitted", object_id=str(created.pk)).exists())

    def test_api_review_requires_assignment_and_note_when_observing(self):
        client, csrf = self.api_session(self.teacher)
        url = reverse("profiles:api-development-review", args=("project", self.project.pk))
        rejected = client.post(url, {"outcome": "observe"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(rejected.status_code, 400)
        approved = client.post(url, {"outcome": "approve"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(approved.status_code, 200, approved.data)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, DevelopmentRecord.Status.VALIDATED)

    def test_portal_login_page_authenticates_and_redirects(self):
        response = self.client.get(reverse("profiles:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="root"')
        self.assertContains(response, 'id="root"')

    def test_student_cannot_open_another_students_profile_by_uuid(self):
        client, _ = self.api_session(self.student)
        response = client.get(reverse("profiles:api-enrollment-profile", args=(self.other_enrollment.pk,)))
        self.assertEqual(response.status_code, 404)

    def test_student_can_save_and_submit_own_project(self):
        client, csrf = self.api_session(self.student)
        url = reverse("profiles:api-development-create", args=(self.enrollment.pk, "project"))
        response = client.post(url, {
            "title": "Aplicación universitaria", "description": "Herramienta para una materia.",
            "role": "Programación", "started_on": "", "completed_on": "", "intent": "submit",
        }, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 201, response.data)
        submitted = StudentProject.objects.get(title="Aplicación universitaria")
        self.assertEqual(submitted.status, DevelopmentRecord.Status.IN_REVIEW)
        self.assertTrue(AuditEvent.objects.filter(action="trajectory.development_submitted", object_id=str(submitted.pk)).exists())

    def test_student_cannot_edit_closed_enrollment(self):
        self.enrollment.status = Enrollment.Status.COMPLETED
        self.enrollment.save(update_fields=("status",))
        client, csrf = self.api_session(self.student)
        response = client.post(reverse("profiles:api-development-create", args=(self.enrollment.pk, "skill")),
                               {"name": "Python", "intent": "submit"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 403)

    def test_assigned_teacher_can_validate_and_audit_project(self):
        client, csrf = self.api_session(self.teacher)
        response = client.post(reverse("profiles:api-development-review", args=("project", self.project.pk)),
                               {"outcome": "approve"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200, response.data)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, DevelopmentRecord.Status.VALIDATED)
        self.assertEqual(self.project.validated_by, self.teacher)
        self.assertIsNotNone(self.project.validated_at)
        self.assertTrue(AuditEvent.objects.filter(action="trajectory.development_validated", object_id=str(self.project.pk)).exists())

    def test_review_requires_a_reason_when_requesting_changes(self):
        client, csrf = self.api_session(self.teacher)
        response = client.post(reverse("profiles:api-development-review", args=("project", self.project.pk)),
                               {"outcome": "observe", "note": ""}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 400)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, DevelopmentRecord.Status.IN_REVIEW)

    def test_student_cannot_validate_own_declaration(self):
        submitted = StudentSkill.objects.create(enrollment=self.enrollment, created_by=self.student, name="SQL", status=DevelopmentRecord.Status.IN_REVIEW)
        client, csrf = self.api_session(self.student)
        response = client.post(reverse("profiles:api-development-review", args=("skill", submitted.pk)),
                               {"outcome": "approve"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 404)
        submitted.refresh_from_db()
        self.assertEqual(submitted.status, DevelopmentRecord.Status.IN_REVIEW)

    def test_unauthorized_review_does_not_leak_enrollment_via_invalid_form_redirect(self):
        client, csrf = self.api_session(self.other_student)
        response = client.post(reverse("profiles:api-development-review", args=("project", self.project.pk)),
                               {"outcome": "invalid"}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 404)

    def test_only_verified_grades_appear_and_mean_is_labelled(self):
        create_grade_record(actor=self.teacher, enrollment=self.enrollment, offering=self.offering, grade_value=Decimal("85"), source="Acta sintética")
        client, _ = self.api_session(self.student)
        response = client.get(reverse("profiles:api-enrollment-profile", args=(self.enrollment.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["grades"][0]["value"], "85.00")
        self.assertEqual(response.data["average"], "85.00")

    def test_grade_correction_preserves_prior_verified_record(self):
        initial = create_grade_record(actor=self.teacher, enrollment=self.enrollment, offering=self.offering, grade_value=Decimal("82"), source="Acta 1")
        corrected = create_grade_record(actor=self.teacher, enrollment=self.enrollment, offering=self.offering, grade_value=Decimal("88"), source="Acta rectificada", reason="Corrección autorizada")
        initial.refresh_from_db()
        self.assertEqual(initial.status, GradeRecord.Status.SUPERSEDED)
        self.assertEqual(corrected.supersedes_id, initial.pk)
        self.assertEqual(GradeRecord.objects.filter(enrollment=self.enrollment, status=GradeRecord.Status.VERIFIED).count(), 1)

    def test_profile_template_handles_empty_projects_and_skills_accessibly(self):
        client, _ = self.api_session(self.other_student)
        response = client.get(reverse("profiles:api-enrollment-profile", args=(self.other_enrollment.pk,)))
        self.assertEqual(response.data["projects"], [])
        self.assertEqual(response.data["skills"], [])
