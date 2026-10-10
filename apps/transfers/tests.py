from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import AcademicPeriod, Career, Enrollment, Institution, StudentProfile
from apps.activities.models import Activity, ActivityCategory, PointsMovement, Regulation
from apps.activities.services import revoke_activity
from apps.audit.models import AuditEvent
from .models import TransferAdjustment, TransferAllocation, TransferMovement, TransferRequest, TransferRiskAlert, TransferReview
from .services import create_transfer_request, review_transfer


class E08TransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_superuser(username="e08_admin", email="admin-e08@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Universidad E08", short_name="E08-U")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.period = AcademicPeriod.objects.create(career=cls.career, code="E08-P", name="Periodo E08", starts_on=today-timedelta(days=25), ends_on=today+timedelta(days=90))
        cls.other_career = Career.objects.create(institution=cls.institution, code="ELC", name="Ingeniería Electrónica")
        cls.other_period = AcademicPeriod.objects.create(career=cls.other_career, code="E08-X", name="Periodo alternativo", starts_on=today-timedelta(days=5), ends_on=today+timedelta(days=90))
        cls.sender, cls.sender_enrollment = cls.make_student("e08_sender", "E08-001", cls.career, cls.period)
        cls.recipient, cls.recipient_enrollment = cls.make_student("e08_recipient", "E08-002", cls.career, cls.period)
        cls.second_recipient, cls.second_recipient_enrollment = cls.make_student("e08_recipient2", "E08-003", cls.career, cls.period)
        cls.outsider, cls.outsider_enrollment = cls.make_student("e08_outsider", "E08-004", cls.other_career, cls.other_period)
        cls.coordinator = User.objects.create_user(username="e08_coord", email="coord-e08@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.coordinator, role=RoleAssignment.Role.COORDINATOR,
                   scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Coordinación E08")
        cls.other_coordinator = User.objects.create_user(username="e08_other_coord", email="other-coord-e08@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.other_coordinator, role=RoleAssignment.Role.COORDINATOR,
                   scope=RoleAssignment.Scope.CAREER, career=cls.other_career, reason="Coordinación E08 alterna")
        cls.regulation = Regulation.objects.create(career=cls.career, version=1, title="Reglamento E08",
            effective_from=today-timedelta(days=1), created_by=cls.admin)
        cls.transferable = ActivityCategory.objects.create(regulation=cls.regulation, code="collaboration",
            name="Colaboración validada", criterion="Aporte colaborativo documentado.", points=10, transferable=True,
            reviewer_roles=["coordinator", "career_admin"])
        cls.not_transferable = ActivityCategory.objects.create(regulation=cls.regulation, code="research",
            name="Investigación", criterion="Participación validada.", points=25, transferable=False,
            reviewer_roles=["coordinator", "career_admin"])
        cls.regulation.published = True
        cls.regulation.published_by = cls.admin
        cls.regulation.published_at = timezone.now()
        cls.regulation.save()

    @classmethod
    def make_student(cls, username, number, career, period):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=user, institution=career.institution, student_number=number)
        enrollment = Enrollment.objects.create(student=profile, career=career, period=period, valid_from=period.starts_on)
        grant_role(actor=cls.admin, user=user, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER,
                   career=career, reason="Fixture E08")
        return user, enrollment

    def source_activity(self, *, enrollment=None, category=None, title=None, points=10):
        enrollment = enrollment or self.sender_enrollment
        category = category or self.transferable
        activity = Activity.objects.create(
            enrollment=enrollment, category=category, title=title or f"Aporte colaborativo {uuid4().hex[:6]}",
            description="Aporte ficticio validado", occurred_on=timezone.localdate(), source="Constancia E08",
            created_by=enrollment.student.user, status=Activity.Status.APPROVED,
        )
        return PointsMovement.objects.create(
            enrollment=enrollment, activity=activity, regulation=self.regulation, category=category,
            actor=self.admin, points=points, reason="Mérito sintético transferible",
        )

    def post_transfer(self, *, recipient=None, source=None, amount=5, key=None, sender=None):
        source = source or self.source_activity(enrollment=sender or self.sender_enrollment)
        sender = sender or source.enrollment
        client = APIClient()
        client.force_authenticate(user=sender.student.user)
        response = client.post(reverse("transfers-list"), {
            "senderEnrollment": str(sender.pk), "recipientEnrollment": str(recipient or self.recipient_enrollment.pk),
            "activity": str(source.activity_id), "amount": amount,
            "reason": "Reconocimiento por aporte documentado en el proyecto del equipo.",
            "idempotencyKey": key or uuid4().hex,
        }, format="json")
        return response, source

    def test_idempotent_request_reserves_source_until_cancelled(self):
        source = self.source_activity()
        key = uuid4().hex
        first, _ = self.post_transfer(source=source, amount=5, key=key)
        repeated, _ = self.post_transfer(source=source, amount=5, key=key)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(first.data["id"], repeated.data["id"])
        self.assertEqual(TransferRequest.objects.count(), 1)
        self.assertEqual(TransferAllocation.objects.filter(request_id=first.data["id"]).count(), 1)
        student_client = APIClient()
        student_client.force_authenticate(user=self.sender)
        self.assertEqual(student_client.get(reverse("transfers-list")).data["sources"][0]["available"], 5)
        cancel = student_client.post(reverse("transfers-cancel", args=(first.data["id"],)), {}, format="json")
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(student_client.get(reverse("transfers-list")).data["sources"][0]["available"], 10)
        self.assertEqual(TransferRequest.objects.get(pk=first.data["id"]).status, TransferRequest.Status.CANCELLED)

    def test_independent_approval_creates_balanced_immutable_pair_and_recipient_cannot_retransfer(self):
        source = self.source_activity()
        created, _ = self.post_transfer(source=source, amount=10)
        self.assertEqual(created.status_code, 201, created.data)
        for party in (self.sender, self.recipient):
            with self.assertRaises(PermissionDenied):
                review_transfer(actor=party, request_id=created.data["id"], decision="approve", reason="No debe aprobarse a sí mismo.")
        reviewer = APIClient()
        reviewer.force_authenticate(user=self.coordinator)
        approved = reviewer.post(reverse("transfers-review", args=(created.data["id"],)),
            {"decision": "approve", "reason": "La constancia confirma el aporte descrito."}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], TransferRequest.Status.APPROVED)
        movements = list(TransferMovement.objects.filter(request_id=created.data["id"]).order_by("side"))
        self.assertEqual(len(movements), 2)
        self.assertEqual(sum(row.points for row in movements), 0)
        self.assertEqual({row.source_movement_id for row in movements}, {source.pk})
        self.assertEqual({row.points for row in movements}, {-10, 10})
        with self.assertRaises(ValidationError):
            movements[0].delete()
        recipient_client = APIClient()
        recipient_client.force_authenticate(user=self.recipient)
        data = recipient_client.get(reverse("transfers-list")).data
        self.assertEqual(data["balances"][0]["merit"], 0)
        self.assertEqual(data["balances"][0]["received"], 10)
        self.assertEqual(data["sources"], [])
        self.assertTrue(AuditEvent.objects.filter(action="transfer.approved", object_id=created.data["id"]).exists())

    def test_per_request_and_per_person_month_limits_are_rechecked(self):
        sources = [self.source_activity(title=f"Origen de cuota {i}") for i in range(3)]
        first, _ = self.post_transfer(source=sources[0], amount=10)
        second, _ = self.post_transfer(recipient=self.second_recipient_enrollment.pk, source=sources[1], amount=10)
        third, _ = self.post_transfer(source=sources[2], amount=1)
        too_large, _ = self.post_transfer(recipient=self.second_recipient_enrollment.pk, source=sources[2], amount=11)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(third.status_code, 400)
        self.assertIn("límite", third.data["detail"].lower())
        self.assertEqual(too_large.status_code, 400)
        self.assertIn("amount", too_large.data)
        self.assertEqual(TransferRequest.objects.count(), 2)

    def test_nontransferable_and_cross_career_origins_are_rejected_and_scope_isolated(self):
        locked = self.source_activity(category=self.not_transferable)
        bad_origin, _ = self.post_transfer(source=locked)
        valid = self.source_activity()
        cross_career, _ = self.post_transfer(recipient=self.outsider_enrollment.pk, source=valid)
        request, _ = self.post_transfer(source=valid)
        other = APIClient()
        other.force_authenticate(user=self.other_coordinator)
        forbidden = other.post(reverse("transfers-review", args=(request.data["id"],)),
            {"decision": "approve", "reason": "Intento de otra carrera"}, format="json")
        self.assertEqual(bad_origin.status_code, 400)
        self.assertEqual(cross_career.status_code, 400)
        self.assertEqual(forbidden.status_code, 403)

    def test_duplicate_recognition_is_rejected_and_request_requires_real_reason(self):
        source = self.source_activity()
        first, _ = self.post_transfer(source=source)
        duplicate, _ = self.post_transfer(source=source, key=uuid4().hex)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("solicitud activa", duplicate.data["detail"].lower())

    def test_risky_reciprocal_pattern_is_restricted_to_independent_review(self):
        first_source = self.source_activity()
        first, _ = self.post_transfer(source=first_source, amount=5)
        second_source = self.source_activity(enrollment=self.recipient_enrollment, title="Aporte propio del receptor")
        second, _ = self.post_transfer(sender=self.recipient_enrollment, recipient=self.sender_enrollment.pk, source=second_source, amount=5)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201, second.data)
        request = TransferRequest.objects.get(pk=second.data["id"])
        self.assertEqual(request.status, TransferRequest.Status.FLAGGED)
        self.assertIn("reciprocal_pattern", request.risk_flags)
        sender_view = APIClient()
        sender_view.force_authenticate(user=self.recipient)
        public_row = next(row for row in sender_view.get(reverse("transfers-list")).data["requests"] if row["id"] == str(request.pk))
        self.assertEqual(public_row["status"], TransferRequest.Status.IN_REVIEW)
        self.assertEqual(public_row["riskFlags"], [])
        manager = APIClient()
        manager.force_authenticate(user=self.coordinator)
        staff_row = next(row for row in manager.get(reverse("transfers-list")).data["reviewQueue"] if row["id"] == str(request.pk))
        self.assertIn("reciprocal_pattern", staff_row["riskFlags"])

    def test_origin_revocation_opens_restricted_alert_freezes_account_and_audits_resolution(self):
        source = self.source_activity()
        second_source = self.source_activity(title="Segundo mérito transferible")
        created, _ = self.post_transfer(source=source, amount=5)
        reviewer = APIClient()
        reviewer.force_authenticate(user=self.coordinator)
        approved = reviewer.post(reverse("transfers-review", args=(created.data["id"],)),
            {"decision": "approve", "reason": "Colaboración comprobada por fuente independiente."}, format="json")
        self.assertEqual(approved.status_code, 200)
        revoke_activity(actor=self.coordinator, activity=source.activity, reason="La constancia original fue invalidada en revisión.")
        alert = TransferRiskAlert.objects.get(request_id=created.data["id"], code="origin_revoked_after_transfer")
        blocked, _ = self.post_transfer(source=second_source, amount=1)
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("revisión pendiente", blocked.data["detail"].lower())
        manager_alerts = reviewer.get(reverse("transfers-list")).data["riskAlerts"]
        self.assertTrue(any(row["id"] == str(alert.pk) for row in manager_alerts))
        student_client = APIClient()
        student_client.force_authenticate(user=self.sender)
        student_row = next(row for row in student_client.get(reverse("transfers-list")).data["requests"] if row["id"] == created.data["id"])
        self.assertEqual(student_row["riskAlerts"], [])
        resolved = reviewer.post(reverse("transfers-alert-resolve", args=(alert.pk,)),
            {"reason": "Se verificó la colaboración y se registró el ajuste administrativo pertinente."}, format="json")
        self.assertEqual(resolved.status_code, 200, resolved.data)
        compensations = list(TransferAdjustment.objects.filter(alert=alert))
        self.assertEqual(len(compensations), 2)
        self.assertEqual(sum(row.points for row in compensations), 0)
        self.assertEqual({row.points for row in compensations}, {-5, 5})
        allowed, _ = self.post_transfer(source=second_source, amount=1)
        self.assertEqual(allowed.status_code, 201, allowed.data)
        alert.refresh_from_db()
        self.assertEqual(alert.status, TransferRiskAlert.Status.RESOLVED)
        self.assertTrue(AuditEvent.objects.filter(action="transfer.risk_resolved", object_id=str(alert.pk)).exists())

    def test_reviewer_cannot_be_a_sender_or_recipient(self):
        source = self.source_activity()
        transfer, _ = self.post_transfer(source=source)
        for party in (self.sender, self.recipient):
            with self.assertRaises(PermissionDenied):
                review_transfer(actor=party, request_id=transfer.data["id"], decision="approve", reason="No debe revisar.")


class E08TransferConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        today = timezone.localdate()
        self.admin = User.objects.create_superuser(username="e08_race_admin", email="race-admin@example.test", password="test-pass-123")
        institution = Institution.objects.create(name="Institución carrera concurrente", short_name="E08-RACE")
        career = Career.objects.create(institution=institution, code="RACE", name="Carrera concurrente")
        period = AcademicPeriod.objects.create(career=career, code="RACE-P", name="Periodo concurrente",
            starts_on=today-timedelta(days=1), ends_on=today+timedelta(days=30))
        self.sender, self.sender_enrollment = self.make_student("e08_race_sender", "RACE-001", career, period)
        self.recipient1, self.enrollment1 = self.make_student("e08_race_recipient1", "RACE-002", career, period)
        self.recipient2, self.enrollment2 = self.make_student("e08_race_recipient2", "RACE-003", career, period)
        regulation = Regulation.objects.create(career=career, version=1, title="Reglamento de concurrencia",
            effective_from=today-timedelta(days=1), created_by=self.admin)
        category = ActivityCategory.objects.create(regulation=regulation, code="collaboration", name="Colaboración",
            criterion="Aporte validado", points=10, transferable=True)
        regulation.published = True
        regulation.published_by = self.admin
        regulation.published_at = timezone.now()
        regulation.save()
        activity = Activity.objects.create(enrollment=self.sender_enrollment, category=category, title="Origen compartido",
            description="Aporte comprobado", occurred_on=today, source="Fixture", created_by=self.sender,
            status=Activity.Status.APPROVED)
        self.origin = PointsMovement.objects.create(enrollment=self.sender_enrollment, activity=activity,
            regulation=regulation, category=category, actor=self.admin, points=10, reason="Puntos para prueba concurrente")

    def make_student(self, username, number, career, period):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=user, institution=career.institution, student_number=number)
        enrollment = Enrollment.objects.create(student=profile, career=career, period=period, valid_from=period.starts_on)
        grant_role(actor=self.admin, user=user, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER,
                   career=career, reason="Fixture concurrente E08")
        return user, enrollment

    def test_concurrent_requests_cannot_reserve_the_same_points_twice(self):
        barrier = Barrier(2)

        def attempt(recipient_id, key):
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.sender.pk)
                barrier.wait(timeout=10)
                request, created = create_transfer_request(
                    actor=actor, sender_id=self.sender_enrollment.pk, recipient_id=recipient_id,
                    activity_id=self.origin.activity_id, amount=6,
                    reason="Reconocimiento por aporte compartido comprobable.", idempotency_key=key,
                )
                return "created" if created else "replayed", str(request.pk)
            except ValidationError:
                return "rejected", None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda args: attempt(*args), (
                (self.enrollment1.pk, "race-key-1"), (self.enrollment2.pk, "race-key-2"),
            )))
        self.assertCountEqual([result[0] for result in results], ["created", "rejected"])
        self.assertEqual(TransferRequest.objects.filter(sender=self.sender_enrollment).count(), 1)
        self.assertEqual(sum(TransferAllocation.objects.filter(source_movement=self.origin).values_list("amount", flat=True)), 6)

