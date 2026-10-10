from datetime import timedelta
from tempfile import TemporaryDirectory

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment, Institution, StudentProfile, TeachingAssignment
from apps.audit.models import AuditEvent
from .models import Activity, ActivityCategory, EvidenceFile, PointsMovement, Regulation
from .services import resubmit_activity, review_activity, revoke_activity, submit_activity


class E06EvidenceAndPointsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_superuser(username="e06_admin", email="e06-admin@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Institución E06", short_name="E06-U")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.period = AcademicPeriod.objects.create(career=cls.career, code="E06-P", name="Periodo E06", starts_on=today - timedelta(days=20), ends_on=today + timedelta(days=60))
        cls.course = Course.objects.create(career=cls.career, code="E06-101", name="Curso E06")
        cls.offering = CourseOffering.objects.create(course=cls.course, period=cls.period, group_code="A")
        cls.student = User.objects.create_user(username="e06_student", email="student-e06@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=cls.student, institution=cls.institution, student_number="E06-001")
        cls.enrollment = Enrollment.objects.create(student=profile, career=cls.career, period=cls.period, valid_from=cls.period.starts_on)
        grant_role(actor=cls.admin, user=cls.student, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Prueba E06")
        cls.roster = CourseEnrollment.objects.create(enrollment=cls.enrollment, offering=cls.offering)
        cls.teacher = User.objects.create_user(username="e06_teacher", email="teacher-e06@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.teacher, role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP, group=cls.offering, reason="Prueba E06")
        TeachingAssignment.objects.create(user=cls.teacher, offering=cls.offering, role=TeachingAssignment.AssignmentRole.TEACHER, starts_on=today - timedelta(days=1))
        cls.regulation = Regulation.objects.create(career=cls.career, version=1, title="Reglamento E06 v1", effective_from=today - timedelta(days=1), created_by=cls.admin)
        cls.category = ActivityCategory.objects.create(regulation=cls.regulation, code="course", name="Curso certificado", criterion="Certificado verificable.", points=10)
        cls.regulation.published = True
        cls.regulation.published_by = cls.admin
        cls.regulation.published_at = timezone.now()
        cls.regulation.save()

    def setUp(self):
        self.tempdir = TemporaryDirectory()
        EvidenceFile._meta.get_field("file").storage.location = self.tempdir.name

    def tearDown(self):
        self.tempdir.cleanup()

    def upload(self, name="certificado.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.7\nprueba", content_type="application/pdf")

    def submit(self, title="Certificación de prueba"):
        return submit_activity(user=self.student, enrollment=self.enrollment, category=self.category, title=title, description="Actividad ficticia verificable", occurred_on=timezone.localdate(), source="Entidad de demostración", uploaded_file=self.upload(), course_enrollment=self.roster)

    def test_approval_awards_exactly_once_and_reversal_is_compensating(self):
        activity = self.submit()
        review_activity(actor=self.teacher, activity=activity, outcome="approve", note="Certificado verificado.")
        self.assertEqual(PointsMovement.objects.filter(activity=activity).count(), 1)
        with self.assertRaises(ValidationError):
            review_activity(actor=self.teacher, activity=activity, outcome="approve", note="Reintento duplicado")
        revoke_activity(actor=self.admin, activity=activity, reason="Documento duplicado en revisión administrativa.")
        movement_rows = list(PointsMovement.objects.filter(activity=activity).order_by("points"))
        self.assertEqual([row.points for row in movement_rows], [-10, 10])
        self.assertEqual(sum(row.points for row in movement_rows), 0)
        self.assertEqual(activity.reviews.count(), 2)
        self.assertTrue(AuditEvent.objects.filter(object_id=str(activity.pk), action="evidence.revoked").exists())

    def test_observation_requires_note_and_resubmission_keeps_file_history(self):
        activity = self.submit()
        with self.assertRaises(ValidationError):
            review_activity(actor=self.teacher, activity=activity, outcome="observe", note=" ")
        review_activity(actor=self.teacher, activity=activity, outcome="observe", note="Falta identificación del organizador.")
        resubmit_activity(actor=self.student, activity=activity, uploaded_file=self.upload("certificado-corregido.pdf"))
        self.assertEqual(activity.files.count(), 2)
        self.assertEqual(list(activity.files.order_by("version").values_list("version", flat=True)), [1, 2])
        self.assertEqual(activity.status, Activity.Status.IN_REVIEW)
        self.assertEqual(activity.reviews.count(), 1)

    def test_only_assigned_reviewer_can_approve_and_only_owner_can_submit(self):
        stranger = User.objects.create_user(username="e06_stranger", email="stranger-e06@example.test", password="test-pass-123")
        activity = self.submit()
        with self.assertRaises(PermissionDenied):
            review_activity(actor=stranger, activity=activity, outcome="approve", note="")
        with self.assertRaises(PermissionDenied):
            submit_activity(user=self.teacher, enrollment=self.enrollment, category=self.category, title="No autorizado", description="x", occurred_on=timezone.localdate(), source="", uploaded_file=self.upload(), course_enrollment=self.roster)

    def test_same_student_cannot_receive_duplicate_for_same_fact(self):
        self.submit("Certificación de prueba")
        with self.assertRaises(ValidationError):
            self.submit("Certificación de prueba")

    def test_published_regulation_and_categories_are_immutable(self):
        self.regulation.title = "Versión modificada"
        with self.assertRaises(ValidationError):
            self.regulation.save()
        self.category.points = 99
        with self.assertRaises(ValidationError):
            self.category.save()

    def test_multipart_api_upload_and_private_download_authorization(self):
        student_client = APIClient()
        student_client.force_authenticate(user=self.student)
        response = student_client.post(reverse("api-evidence"), {
            "enrollment": str(self.enrollment.pk), "category": str(self.category.pk),
            "title": "Certificado enviado por API", "description": "Comprobación del flujo multipart.",
            "occurredOn": timezone.localdate().isoformat(), "source": "Organización ficticia",
            "courseEnrollment": str(self.roster.pk), "file": self.upload(),
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        file_id = response.data["activity"]["files"][0]["id"]
        teacher_client = APIClient()
        teacher_client.force_authenticate(user=self.teacher)
        download = teacher_client.get(reverse("api-evidence-file", args=(file_id,)))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(download["Content-Type"], "application/octet-stream")
        self.assertTrue(b"%PDF-1.7" in b"".join(download.streaming_content))
        stranger = User.objects.create_user(username="e06_stranger_file", email="stranger-file-e06@example.test", password="test-pass-123")
        stranger_client = APIClient()
        stranger_client.force_authenticate(user=stranger)
        self.assertEqual(stranger_client.get(reverse("api-evidence-file", args=(file_id,))).status_code, 404)

    def test_career_coordinator_can_open_portal_to_revoke_records(self):
        coordinator = User.objects.create_user(username="e06_coordinator", email="coordinator-e06@example.test", password="test-pass-123")
        grant_role(actor=self.admin, user=coordinator, role=RoleAssignment.Role.COORDINATOR, scope=RoleAssignment.Scope.CAREER, career=self.career, reason="Prueba de coordinación E06")
        client = APIClient()
        client.force_authenticate(user=coordinator)
        response = client.get(reverse("profiles:api-home"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["enrollments"], [])
        candidates = client.get(reverse("api-evidence-candidates"))
        self.assertEqual(candidates.status_code, 200)
        self.assertEqual(candidates.data["enrollments"][0]["id"], str(self.enrollment.pk))
        response = client.post(reverse("api-evidence-verified"), {
            "enrollment": str(self.enrollment.pk), "category": str(self.category.pk),
            "title": "Reconocimiento de feria", "description": "Participación registrada por coordinación.",
            "occurredOn": timezone.localdate().isoformat(), "source": "Acta ficticia E06-01",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        activity = Activity.objects.get(pk=response.data["activity"]["id"])
        self.assertEqual(activity.status, Activity.Status.APPROVED)
        self.assertTrue(response.data["activity"]["canRevoke"])
        self.assertEqual(PointsMovement.objects.get(activity=activity).points, 10)
        self.assertTrue(AuditEvent.objects.filter(object_id=str(activity.pk), action="evidence.admin_recorded").exists())
        revoked = client.post(reverse("api-evidence-revoke", args=(activity.pk,)), {"reason": "Corrección administrativa documentada."}, format="json")
        self.assertEqual(revoked.status_code, 200, revoked.data)
        self.assertEqual(sum(PointsMovement.objects.filter(activity=activity).values_list("points", flat=True)), 0)
