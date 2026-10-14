from datetime import date, timedelta

from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment, GradeRecord, Institution, StudentProfile, TeachingAssignment
from apps.audit.models import AuditEvent
from .models import Notification


class E11ReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="e11_admin", email="e11-admin@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Institución E11", short_name="E11-U")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.other_career = Career.objects.create(institution=cls.institution, code="INF", name="Informática")
        today = timezone.localdate()
        cls.period = AcademicPeriod.objects.create(career=cls.career, code="E11-2026", name="Periodo E11",
            starts_on=date(today.year, 1, 1), ends_on=date(today.year, 12, 31), status=AcademicPeriod.Status.OPEN)
        cls.other_period = AcademicPeriod.objects.create(career=cls.other_career, code="E11-INF", name="Periodo ajeno",
            starts_on=date(today.year, 1, 1), ends_on=date(today.year, 12, 31), status=AcademicPeriod.Status.OPEN)
        cls.coordinator = User.objects.create_user(username="e11_coord", first_name="Coord", email="e11-coord@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.coordinator, role=RoleAssignment.Role.COORDINATOR,
            scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Coordinación SIS")
        cls.student = User.objects.create_user(username="e11_student", first_name="Estudiante", email="e11-student@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=cls.student, institution=cls.institution, student_number="E11-001")
        cls.enrollment = Enrollment.objects.create(student=profile, career=cls.career, period=cls.period, valid_from=cls.period.starts_on)
        course = Course.objects.create(career=cls.career, code="E11-101", name="Sistemas de información")
        cls.offering = CourseOffering.objects.create(course=course, period=cls.period, group_code="A")
        CourseEnrollment.objects.create(enrollment=cls.enrollment, offering=cls.offering)
        GradeRecord.objects.create(enrollment=cls.enrollment, offering=cls.offering, grade_value=90, scale_snapshot=120,
            status=GradeRecord.Status.VERIFIED, recorded_by=cls.admin, verified_by=cls.admin, verified_at=timezone.now())
        cls.teacher = User.objects.create_user(username="e11_teacher", first_name="Docente", email="e11-teacher@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.teacher, role=RoleAssignment.Role.TEACHER,
            scope=RoleAssignment.Scope.GROUP, group=cls.offering, reason="Docencia del grupo SIS")
        TeachingAssignment.objects.create(user=cls.teacher, offering=cls.offering,
            role=TeachingAssignment.AssignmentRole.TEACHER, starts_on=today - timedelta(days=1))
        cls.outsider = User.objects.create_user(username="e11_out", email="e11-out@example.test", password="test-pass-123")
        other_profile = StudentProfile.objects.create(user=cls.outsider, institution=cls.institution, student_number="E11-002")
        Enrollment.objects.create(student=other_profile, career=cls.career, period=cls.period, valid_from=cls.period.starts_on)

    def test_coordinator_report_is_scoped_and_rejects_other_career_or_period(self):
        client = APIClient(); client.force_authenticate(self.coordinator)
        response = client.get(reverse("reporting:api-report"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["canManage"])
        self.assertEqual({row["careerCode"] for row in response.data["rows"]}, {"SIS"})
        average = next(row["value"] for row in response.data["rows"] if row["metric"] == "Promedio verificado / 100")
        self.assertEqual(average, 75.0)
        self.assertEqual(client.get(reverse("reporting:api-report"), {"career": str(self.other_career.pk)}).status_code, 404)
        self.assertEqual(client.get(reverse("reporting:api-report"), {"period": str(self.other_period.pk)}).status_code, 404)

    def test_student_cannot_get_career_report_or_audit(self):
        client = APIClient(); client.force_authenticate(self.student)
        response = client.get(reverse("reporting:api-report"))
        self.assertFalse(response.data["canManage"])
        self.assertTrue(response.data["personalView"])
        active = next(row for row in response.data["rows"] if row["metric"] == "Mis matrículas activas")
        self.assertEqual(active["value"], 1)
        self.assertEqual(client.get(reverse("reporting:api-report"), {"career": str(self.career.pk)}).status_code, 404)
        self.assertEqual(client.get(reverse("reporting:api-audit")).status_code, 403)

    def test_teacher_sees_aggregate_report_only_for_assigned_groups(self):
        client = APIClient(); client.force_authenticate(self.teacher)
        response = client.get(reverse("reporting:api-report"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["canManage"])
        self.assertTrue(response.data["groupView"])
        self.assertEqual({row["careerCode"] for row in response.data["rows"]}, {"SIS"})
        average = next(row["value"] for row in response.data["rows"] if row["metric"] == "Promedio verificado / 100")
        self.assertEqual(average, 75.0)
        self.assertEqual(client.get(reverse("reporting:api-audit")).status_code, 403)

    def test_csv_uses_same_authorized_scope_and_exposes_definitions(self):
        client = APIClient(); client.force_authenticate(self.coordinator)
        response = client.get(reverse("reporting:api-report"), {"career": str(self.career.pk), "export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("Denominador", response.content.decode("utf-8-sig"))
        self.assertNotIn("e11-out", response.content.decode("utf-8-sig"))

    def test_report_includes_period_and_status_chart_series(self):
        client = APIClient(); client.force_authenticate(self.coordinator)
        response = client.get(reverse("reporting:api-report"), {"career": str(self.career.pk)})
        self.assertEqual(response.status_code, 200)
        chart = response.data["charts"][0]
        self.assertEqual(chart["activityByPeriod"][0]["label"], self.period.code)
        self.assertEqual(chart["pointsDistribution"][0]["label"], "Explorador")
        self.assertEqual({"evidenceStatuses", "opportunityStatuses", "applicationsByPeriod"} - chart.keys(), set())

    def test_audit_supports_scoped_pages_and_csv_export(self):
        baseline = AuditEvent.objects.filter(scope_type="career", scope_id=str(self.career.pk)).count()
        for number in range(28):
            AuditEvent.objects.create(actor=self.admin, action=f"test.page.{number}", object_type="tests.record",
                object_id=str(number), scope_type="career", scope_id=str(self.career.pk), reason="Registro")
        client = APIClient(); client.force_authenticate(self.coordinator)
        first = client.get(reverse("reporting:api-audit"), {"page": 1, "pageSize": 10})
        second = client.get(reverse("reporting:api-audit"), {"page": 2, "pageSize": 10})
        self.assertEqual(first.data["total"], baseline + 28)
        self.assertEqual(first.data["pages"], (baseline + 28 + 9) // 10)
        self.assertNotEqual(first.data["events"][0]["id"], second.data["events"][0]["id"])
        exported = client.get(reverse("reporting:api-audit"), {"export": "csv"})
        self.assertIn("text/csv", exported["Content-Type"])
        self.assertIn("test.page.0", exported.content.decode("utf-8-sig"))

    def test_career_manager_can_create_scoped_academic_catalogs(self):
        client = APIClient(); client.force_authenticate(self.coordinator)
        response = client.post(reverse("reporting:api-academic-admin"), {
            "kind": "course", "careerId": str(self.career.pk), "code": "E11-202", "name": "Arquitectura de software", "credits": 5,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditEvent.objects.filter(action="admin.course_created", scope_id=str(self.career.pk)).exists())
        student = APIClient(); student.force_authenticate(self.student)
        self.assertEqual(student.get(reverse("reporting:api-academic-admin")).status_code, 403)

    def test_academic_admin_can_register_student_and_verified_grade(self):
        client = APIClient(); client.force_authenticate(self.coordinator)
        student_response = client.post(reverse("reporting:api-academic-admin"), {
            "kind": "student", "careerId": str(self.career.pk), "firstName": "Ana", "lastName": "Ejemplo",
            "username": "e11_new_student", "email": "e11-new-student@example.test", "studentNumber": "E11-003",
            "password": "Complex-Access-952!",
        }, format="json")
        self.assertEqual(student_response.status_code, 201, student_response.data)
        self.assertTrue(RoleAssignment.objects.filter(user__username="e11_new_student", role=RoleAssignment.Role.STUDENT, career=self.career).exists())
        offering = CourseOffering.objects.create(course=Course.objects.get(code="E11-101"), period=self.period, group_code="B")
        grade_response = client.post(reverse("reporting:api-academic-admin"), {
            "kind": "grade", "careerId": str(self.career.pk), "enrollmentId": str(self.enrollment.pk),
            "offeringId": str(offering.pk), "gradeValue": "84", "source": "Acta académica verificada", "reason": "Carga de cierre",
        }, format="json")
        self.assertEqual(grade_response.status_code, 201, grade_response.data)
        self.assertTrue(GradeRecord.objects.filter(enrollment=self.enrollment, offering=offering, status=GradeRecord.Status.VERIFIED).exists())

    def test_audit_is_read_only_and_only_lists_authorized_career(self):
        AuditEvent.objects.create(actor=self.admin, action="test.read", object_type="tests.record", object_id="1",
            scope_type="career", scope_id=str(self.career.pk), reason="Motivo")
        AuditEvent.objects.create(actor=self.admin, action="demo.grade_seeded", object_type="tests.record", object_id="3",
            scope_type="career", scope_id=str(self.career.pk), reason="Carga de nota ficticia para prueba local")
        AuditEvent.objects.create(actor=self.admin, action="test.secret", object_type="tests.record", object_id="2",
            scope_type="career", scope_id=str(self.other_career.pk), reason="No visible")
        client = APIClient(); client.force_authenticate(self.coordinator)
        response = client.get(reverse("reporting:api-audit"))
        self.assertEqual(response.status_code, 200)
        actions = {event["action"] for event in response.data["events"]}
        self.assertIn("test.read", actions)
        self.assertNotIn("demo.grade_seeded", actions)
        self.assertNotIn("test.secret", actions)
        event = next(event for event in response.data["events"] if event["action"] == "test.read")
        self.assertEqual(event["reason"], "Motivo")
        self.assertEqual(client.post(reverse("reporting:api-audit")).status_code, 405)

    def test_notification_is_created_after_commit_for_scoped_review_queue(self):
        client = APIClient(); client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                AuditEvent.objects.create(actor=self.admin, action="evidence.submitted", object_type="activities.activity",
                    object_id="activity-1", scope_type="career", scope_id=str(self.career.pk))
        notice = Notification.objects.get(recipient=self.coordinator)
        self.assertEqual(notice.title, "Evidencia pendiente de revisión")
        self.assertNotIn("file", notice.message.lower())

    def test_notification_inbox_and_read_state_are_private(self):
        notice = Notification.objects.create(recipient=self.student, event_id="10000000-0000-0000-0000-000000000001",
            kind="activity", title="Aviso", message="Actualización", target_path="/trayectoria/evidencias/")
        student = APIClient(); student.force_authenticate(self.student)
        outsider = APIClient(); outsider.force_authenticate(self.outsider)
        self.assertEqual(student.get(reverse("reporting:api-notifications")).data["unreadCount"], 1)
        self.assertEqual(outsider.get(reverse("reporting:api-notifications")).data["items"], [])
        self.assertEqual(outsider.post(reverse("reporting:api-notification-read", args=[notice.pk])).status_code, 404)
        self.assertEqual(student.post(reverse("reporting:api-notification-read", args=[notice.pk])).status_code, 200)
        notice.refresh_from_db(); self.assertIsNotNone(notice.read_at)

    def test_notification_target_must_be_same_origin_trajectory_path(self):
        with self.assertRaises(ValueError):
            Notification.objects.create(recipient=self.student, event_id="10000000-0000-0000-0000-000000000002",
                kind="activity", title="Aviso", message="Actualización", target_path="https://example.org/")
