from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import AcademicPeriod, Career, Course, CourseOffering, Enrollment, GradeRecord, Institution, StudentProfile
from .models import SupportAlert, SupportCase, SupportRuleVersion
from .services import evaluate_active_rules


class E10SupportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_superuser(username="e10_admin", email="e10-admin@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Institución E10", short_name="E10-U")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.periods = []
        for idx, code in enumerate(("E10-P1", "E10-P2")):
            period = AcademicPeriod.objects.create(career=cls.career, code=code, name=f"Periodo {idx + 1}",
                starts_on=today-timedelta(days=240-idx*120), ends_on=today-timedelta(days=121-idx*120), status=AcademicPeriod.Status.CLOSED)
            cls.periods.append(period)
        cls.courses = []
        for idx in range(3):
            course = Course.objects.create(career=cls.career, code=f"E10-{idx}", name=f"Asignatura {idx}")
            cls.courses.append(course)
        cls.coordinator = User.objects.create_user(username="e10_coord", email="e10-coord@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.coordinator, role=RoleAssignment.Role.COORDINATOR,
            scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Coordinación de pruebas E10")
        cls.student = User.objects.create_user(username="e10_student", first_name="Estudiante", email="e10-student@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=cls.student, institution=cls.institution, student_number="E10-001")
        cls.enrollments = []
        for period in cls.periods:
            cls.enrollments.append(Enrollment.objects.create(student=profile, career=cls.career, period=period,
                valid_from=period.starts_on, valid_to=period.ends_on, status=Enrollment.Status.COMPLETED))
        cls.grades = []
        for enrollment, values in zip(cls.enrollments, ((95, 94, 92), (70, 72, 68))):
            for course, value in zip(cls.courses, values):
                offering = CourseOffering.objects.create(course=course, period=enrollment.period, group_code="A", status=CourseOffering.Status.CLOSED)
                grade = GradeRecord.objects.create(enrollment=enrollment, offering=offering, grade_value=value, scale_snapshot=100,
                    status=GradeRecord.Status.VERIFIED, source="Fuente oficial ficticia", recorded_by=cls.admin,
                    verified_by=cls.admin, verified_at=timezone.now())
                cls.grades.append(grade)
        cls.rule = SupportRuleVersion.objects.create(career=cls.career, valid_from=cls.periods[0], version=1,
            indicator=SupportRuleVersion.Indicator.VERIFIED_AVERAGE_DECLINE, threshold_points=10,
            minimum_verified_courses=3, active=True, created_by=cls.coordinator, published_at=timezone.now())
        grant_role(actor=cls.admin, user=cls.student, role=RoleAssignment.Role.STUDENT,
            scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Estudiante de pruebas E10")

    def test_alert_uses_verified_grades_in_consecutive_closed_periods_and_is_idempotent(self):
        alerts = evaluate_active_rules(actor=self.coordinator, career=self.career)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].enrollment, self.enrollments[1])
        self.assertEqual(alerts[0].evidence_snapshot["previousAverage"], "93.67")
        self.assertEqual(alerts[0].evidence_snapshot["currentAverage"], "70.00")
        self.assertEqual(evaluate_active_rules(actor=self.coordinator, career=self.career), [])

    def test_missing_and_unverified_data_never_create_adverse_alerts(self):
        for grade in self.grades[3:]:
            grade.status = GradeRecord.Status.UNVERIFIED
            grade.verified_by = None
            grade.verified_at = None
            grade.save()
        self.assertEqual(evaluate_active_rules(actor=self.coordinator, career=self.career), [])
        self.assertEqual(SupportAlert.objects.count(), 0)

    def test_student_sees_only_own_case_and_other_student_is_denied(self):
        alert = evaluate_active_rules(actor=self.coordinator, career=self.career)[0]
        case = SupportCase.objects.create(alert=alert, assigned_to=self.coordinator, created_by=self.coordinator)
        student = APIClient(); student.force_authenticate(self.student)
        response = student.get(reverse("support:api-support"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["alerts"]], [str(alert.pk)])
        outsider = User.objects.create_user(username="e10_outsider", email="e10-outsider@example.test", password="test-pass-123")
        client = APIClient(); client.force_authenticate(outsider)
        denied = client.post(reverse("support:api-support-case-action", args=[case.pk]),
            {"kind": "student_response", "description": "Solicito hablar con coordinación.", "status": "completed"}, format="json")
        self.assertEqual(denied.status_code, 403)

    def test_incomplete_open_period_does_not_make_comparison(self):
        self.periods[1].status = AcademicPeriod.Status.OPEN
        self.periods[1].save(update_fields=("status",))
        self.assertEqual(evaluate_active_rules(actor=self.coordinator, career=self.career), [])

    def test_coordinator_can_open_follow_up_and_close_case_with_outcome(self):
        alert = evaluate_active_rules(actor=self.coordinator, career=self.career)[0]
        client = APIClient(); client.force_authenticate(self.coordinator)
        created = client.post(reverse("support:api-support-create-case"), {"alertId": str(alert.pk)}, format="json")
        self.assertEqual(created.status_code, 201)
        case_id = created.data["id"]
        action = client.post(reverse("support:api-support-case-action", args=[case_id]), {
            "kind": "tutoring", "description": "Sesión de apoyo acordada para revisar ejercicios de programación.",
            "dueDate": (timezone.localdate()+timedelta(days=7)).isoformat(), "status": "planned",
        }, format="json")
        self.assertEqual(action.status_code, 201)
        closed = client.post(reverse("support:api-support-close-case", args=[case_id]),
            {"outcome": "Se completaron dos sesiones y se acordó mantener asesoría opcional."}, format="json")
        self.assertEqual(closed.status_code, 200)
        case = SupportCase.objects.get(pk=case_id)
        self.assertEqual(case.status, SupportCase.Status.CLOSED)
        self.assertTrue(case.closed_at)
        self.assertEqual(case.actions.count(), 1)
        dashboard = client.get(reverse("support:api-support"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertTrue(dashboard.data["canManage"])
        self.assertGreaterEqual(len(dashboard.data["managedIndicators"]), 2)

    def test_coordinator_can_discard_with_reason_and_published_rule_is_immutable(self):
        alert = evaluate_active_rules(actor=self.coordinator, career=self.career)[0]
        client = APIClient(); client.force_authenticate(self.coordinator)
        created = client.post(reverse("support:api-support-create-case"), {"alertId": str(alert.pk)}, format="json")
        self.assertEqual(created.status_code, 201)
        discarded = client.post(reverse("support:api-support-discard-case", args=[created.data["id"]]),
            {"reason": "La revisión confirmó que no se requiere acompañamiento."}, format="json")
        self.assertEqual(discarded.status_code, 200)
        case = SupportCase.objects.get(pk=created.data["id"])
        self.assertEqual(case.status, SupportCase.Status.DISCARDED)
        self.assertEqual(case.alert.status, SupportAlert.Status.DISMISSED)
        with self.assertRaises(ValidationError):
            self.rule.threshold_points = Decimal("25")
            self.rule.save()

