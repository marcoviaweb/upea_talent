from datetime import date

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.academics.models import (
    AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment,
    Institution, StudentProfile, TeachingAssignment,
)
from apps.audit.models import AuditEvent
from .models import RoleAssignment, User
from .permissions import can_access_course_enrollment, visible_course_enrollments
from .services import grant_role, revoke_role


class ScopedAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="technical", email="technical@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Universidad Demo", short_name="UDEMO")
        cls.systems = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.electronics = Career.objects.create(institution=cls.institution, code="ELC", name="Ingeniería Electrónica")
        cls.period_sis = AcademicPeriod.objects.create(career=cls.systems, code="2026-1", name="I/2026", starts_on=date(2026, 2, 1), ends_on=date(2026, 7, 31))
        cls.period_elc = AcademicPeriod.objects.create(career=cls.electronics, code="2026-1", name="I/2026", starts_on=date(2026, 2, 1), ends_on=date(2026, 7, 31))
        cls.course_sis = Course.objects.create(career=cls.systems, code="INF101", name="Programación I")
        cls.course_elc = Course.objects.create(career=cls.electronics, code="ELC101", name="Circuitos I")
        cls.group_sis = CourseOffering.objects.create(course=cls.course_sis, period=cls.period_sis, group_code="A")
        cls.group_elc = CourseOffering.objects.create(course=cls.course_elc, period=cls.period_elc, group_code="A")
        cls.student_sis = cls.make_student("student_sis", cls.systems, cls.period_sis, "SIS-001")
        cls.student_elc = cls.make_student("student_elc", cls.electronics, cls.period_elc, "ELC-001")
        cls.roster_sis = CourseEnrollment.objects.create(enrollment=cls.student_sis, offering=cls.group_sis)
        cls.roster_elc = CourseEnrollment.objects.create(enrollment=cls.student_elc, offering=cls.group_elc)

    @classmethod
    def make_student(cls, username, career, period, number):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=user, institution=career.institution, student_number=number)
        enrollment = Enrollment.objects.create(student=profile, career=career, period=period, valid_from=period.starts_on)
        grant_role(actor=cls.admin, user=user, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER, career=career, reason="Fixture sintético")
        return enrollment

    def test_student_sees_only_own_roster_row(self):
        user = self.student_sis.student.user
        self.assertQuerySetEqual(visible_course_enrollments(user), [self.roster_sis], transform=lambda row: row)
        self.assertTrue(can_access_course_enrollment(user, self.roster_sis.pk))
        self.assertFalse(can_access_course_enrollment(user, self.roster_elc.pk))

    def test_career_coordinator_is_isolated_from_other_careers(self):
        coordinator = User.objects.create_user(username="coord_sis", email="coord@example.test", password="test-pass-123")
        grant_role(actor=self.admin, user=coordinator, role=RoleAssignment.Role.COORDINATOR, scope=RoleAssignment.Scope.CAREER, career=self.systems, reason="Fixture sintético")
        self.assertQuerySetEqual(visible_course_enrollments(coordinator), [self.roster_sis], transform=lambda row: row)
        self.assertFalse(can_access_course_enrollment(coordinator, self.roster_elc.pk))

    def test_teacher_access_requires_matching_role_and_assignment(self):
        teacher = User.objects.create_user(username="teacher", email="teacher@example.test", password="test-pass-123")
        grant_role(actor=self.admin, user=teacher, role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP, group=self.group_sis, reason="Asignación de prueba")
        TeachingAssignment.objects.create(user=teacher, offering=self.group_sis, role="teacher", starts_on=date(2026, 1, 1))
        self.assertQuerySetEqual(visible_course_enrollments(teacher), [self.roster_sis], transform=lambda row: row)
        self.assertFalse(can_access_course_enrollment(teacher, self.roster_elc.pk))

    def test_institution_admin_does_not_receive_student_rosters(self):
        institutional_admin = User.objects.create_user(username="institution_admin", email="ia@example.test", password="test-pass-123")
        grant_role(actor=self.admin, user=institutional_admin, role=RoleAssignment.Role.INSTITUTION_ADMIN, scope=RoleAssignment.Scope.INSTITUTION, institution=self.institution, reason="Fixture sintético")
        self.assertFalse(visible_course_enrollments(institutional_admin).exists())

    def test_disabled_account_cannot_log_in_or_keep_scope(self):
        user = self.student_sis.student.user
        user.is_active = False
        user.save(update_fields=("is_active",))
        self.assertFalse(self.client.login(username=user.username, password="test-pass-123"))
        self.assertFalse(visible_course_enrollments(user).exists())

    def test_enabled_account_can_log_in(self):
        user = self.student_sis.student.user
        self.assertTrue(self.client.login(username=user.username, password="test-pass-123"))

    def test_actor_cannot_grant_role_to_self(self):
        with self.assertRaises(PermissionDenied):
            grant_role(actor=self.admin, user=self.admin, role=RoleAssignment.Role.INSTITUTION_ADMIN,
                       scope=RoleAssignment.Scope.INSTITUTION, institution=self.institution, reason="No permitido")

    def test_unassigned_user_cannot_grant_roles(self):
        unauthorized = User.objects.create_user(username="unassigned", email="unassigned@example.test", password="test-pass-123")
        target = User.objects.create_user(username="target", email="target@example.test", password="test-pass-123")
        with self.assertRaises(PermissionDenied):
            grant_role(actor=unauthorized, user=target, role=RoleAssignment.Role.STUDENT,
                       scope=RoleAssignment.Scope.CAREER, career=self.systems, reason="No autorizado")

    def test_revocation_is_audited_and_deactivates_access(self):
        user = self.student_sis.student.user
        assignment = user.role_assignments.get(role=RoleAssignment.Role.STUDENT)
        revoke_role(actor=self.admin, assignment=assignment, reason="Fin de prueba")
        self.assertFalse(can_access_course_enrollment(user, self.roster_sis.pk))
        self.assertTrue(AuditEvent.objects.filter(action="role.revoked", object_id=str(assignment.pk)).exists())

    def test_audit_events_are_append_only(self):
        event = AuditEvent.objects.first()
        self.assertIsNotNone(event)
        event.reason = "mutación"
        with self.assertRaises(PermissionDenied):
            event.save()
        with self.assertRaises(PermissionDenied):
            event.delete()
