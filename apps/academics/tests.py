from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.activities.models import Activity, EvidenceFile, PointsMovement
from apps.activities.services import review_activity
from apps.academics.models import Career, Enrollment, StudentProfile
from apps.academics.models import GradeRecord
from apps.audit.models import AuditEvent
from apps.evaluations.models import EvaluationAggregate, EvaluationCampaign, EvaluationSubmission
from apps.opportunities.models import Application, OpportunityVersion
from apps.opportunities.services import evaluate_eligibility
from apps.profiles.models import StudentProject, StudentSkill
from apps.support.models import SupportCase
from apps.transfers.models import TransferMovement, TransferRequest
from apps.transfers.services import create_transfer_request, review_transfer


class JuryWalkthroughSeedTests(TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        EvidenceFile._meta.get_field("file").storage.location = self.tempdir.name

    def tearDown(self):
        self.tempdir.cleanup()

    def test_clean_and_repeated_seed_supports_the_complete_jury_path(self):
        User.objects.create_superuser(username="jury_seed_admin", email="jury-seed@example.test", password="test-pass-123")

        call_command("seed_demo", stdout=StringIO())
        career = Career.objects.get(code="SIS", institution__short_name="UPEA-DEMO")
        valeria = User.objects.get(username="demo.estudiante05")
        profile = StudentProfile.objects.get(user=valeria)
        enrollment = Enrollment.objects.get(student=profile, career=career, period__code="2026-2")
        pending = Activity.objects.get(enrollment=enrollment, title="Curso certificado de investigación aplicada")
        self.assertEqual(pending.status, Activity.Status.IN_REVIEW)
        self.assertEqual(pending.files.count(), 1)
        evidence = pending.files.get()
        self.assertEqual(evidence.original_name, "constancia_curso_investigacion.pdf")
        self.assertEqual(evidence.content_type, "application/pdf")
        self.assertGreater(evidence.size, 0)
        self.assertEqual(points_total(enrollment), 90)

        counts_before = (
            Activity.objects.count(), PointsMovement.objects.count(), EvidenceFile.objects.count(),
            EvaluationSubmission.objects.count(), EvaluationAggregate.objects.count(),
            EvaluationCampaign.objects.count(), StudentProject.objects.count(), AuditEvent.objects.count(),
            TransferRequest.objects.count(), StudentSkill.objects.count(), Application.objects.count(),
        )
        call_command("seed_demo", stdout=StringIO())
        counts_after = (
            Activity.objects.count(), PointsMovement.objects.count(), EvidenceFile.objects.count(),
            EvaluationSubmission.objects.count(), EvaluationAggregate.objects.count(),
            EvaluationCampaign.objects.count(), StudentProject.objects.count(), AuditEvent.objects.count(),
            TransferRequest.objects.count(), StudentSkill.objects.count(), Application.objects.count(),
        )
        self.assertEqual(counts_after, counts_before)

        # Mateo's account should provide a connected example across each student-facing section.
        mateo = User.objects.get(username="demo.estudiante02")
        mateo_enrollment = Enrollment.objects.get(student__user=mateo, career=career, period__code="2026-2")
        self.assertEqual(GradeRecord.objects.filter(enrollment=mateo_enrollment, status=GradeRecord.Status.VERIFIED).count(), 5)
        self.assertEqual(StudentProject.objects.filter(enrollment=mateo_enrollment).count(), 2)
        self.assertTrue(StudentProject.objects.filter(enrollment=mateo_enrollment, status="validated").exists())
        self.assertEqual(StudentSkill.objects.filter(enrollment=mateo_enrollment).count(), 4)
        self.assertTrue(Activity.objects.filter(enrollment=mateo_enrollment, status=Activity.Status.IN_REVIEW, files__isnull=False).exists())
        self.assertTrue(TransferRequest.objects.filter(recipient=mateo_enrollment, status=TransferRequest.Status.APPROVED).exists())
        self.assertTrue(SupportCase.objects.filter(alert__enrollment__student__user=mateo).exists())
        self.assertTrue(Application.objects.filter(enrollment=mateo_enrollment, status=Application.Status.SUBMITTED).exists())
        mateo_client = Client()
        mateo_client.force_login(mateo)
        for endpoint in ("/api/v1/home/", "/api/v1/evidence/", "/api/v1/spd/", "/api/v1/opportunities/",
                         "/api/v1/transfers/", "/api/v1/evaluations/", "/api/v1/support/",
                         "/api/v1/notifications/", "/api/v1/reports/"):
            response = mateo_client.get(endpoint)
            self.assertEqual(response.status_code, 200, f"{endpoint}: {response.content!r}")
            self.assertTrue(response.json(), f"{endpoint} returned an empty response")
        profile_response = mateo_client.get(f"/api/v1/enrollments/{mateo_enrollment.pk}/")
        self.assertEqual(profile_response.status_code, 200, profile_response.content)
        self.assertEqual(len(profile_response.json()["grades"]), 5)
        self.assertEqual(len(profile_response.json()["projects"]), 2)
        self.assertEqual(len(profile_response.json()["skills"]), 4)

        teacher = User.objects.get(username="demo.docente01")
        coordinator = User.objects.get(username="demo.coordinador01")
        review_activity(actor=teacher, activity=pending, outcome="approve", note="Constancia revisada y aceptada.")
        self.assertEqual(points_total(enrollment), 100)

        version = OpportunityVersion.objects.get(title="Beca de Investigación Aplicada", careers=career)
        self.assertIsNone(version.published_at)
        result = evaluate_eligibility(version, enrollment, persist=False)
        self.assertEqual(result.overall_status, "eligible")
        self.assertEqual({row["status"] for row in result.results}, {"meets"})
        client = Client()
        client.force_login(coordinator)
        published = client.post(reverse("opportunities:publish", args=(version.pk,)), data="{}", content_type="application/json")
        self.assertEqual(published.status_code, 200, published.content)
        version.refresh_from_db()
        self.assertIsNotNone(version.published_at)

        collaboration = Activity.objects.get(enrollment=enrollment, title="Colaboración en el proyecto de laboratorio")
        recipient = Enrollment.objects.get(
            student__user__username="demo.estudiante02", career=career, period__code="2026-2",
        )
        request, created = create_transfer_request(
            actor=valeria, sender_id=enrollment.pk, recipient_id=recipient.pk,
            activity_id=collaboration.pk, amount=2,
            reason="Reconocer el aporte al prototipo compartido.", idempotency_key="JURY-VALERIA-MATEO-001",
        )
        self.assertTrue(created)
        request = review_transfer(actor=coordinator, request_id=request.pk, decision="approve", reason="Aporte confirmado por coordinación.")
        self.assertEqual(request.status, TransferRequest.Status.APPROVED)
        self.assertEqual(TransferMovement.objects.filter(request=request).count(), 2)
        self.assertEqual(points_total(enrollment), 100)
        self.assertTrue(AuditEvent.objects.filter(action="transfer.submitted", object_id=str(request.pk)).exists())
        self.assertTrue(AuditEvent.objects.filter(action="transfer.approved", object_id=str(request.pk)).exists())

        campaign = EvaluationCampaign.objects.get(
            offering__course__code="SIS101", period__code="2026-2", title="Experiencia académica en Ingeniería de Sistemas",
        )
        self.assertEqual(campaign.status, EvaluationCampaign.Status.PUBLISHED)
        self.assertTrue(campaign.aggregates.filter(response_count__gte=5, state=EvaluationAggregate.State.PUBLISHED).exists())
        self.assertFalse(any(field.name in {"user", "enrollment", "eligibility"} for field in EvaluationSubmission._meta.fields))


def points_total(enrollment):
    return sum(PointsMovement.objects.filter(enrollment=enrollment).values_list("points", flat=True))
