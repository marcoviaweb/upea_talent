from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment, Institution, StudentProfile, TeachingAssignment
from apps.audit.models import AuditEvent
from .models import EvaluationAggregate, EvaluationCampaign, EvaluationEligibility, EvaluationSubmission
from .services import QUESTIONS, close_campaign, create_campaign, publish_campaign, publish_results, submit_ballot


class E09EvaluationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_superuser(username="e09_admin", email="admin-e09@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Institución E09", short_name="E09-U")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.other_career = Career.objects.create(institution=cls.institution, code="ELC", name="Ingeniería Electrónica")
        cls.period = AcademicPeriod.objects.create(career=cls.career, code="E09-P", name="Periodo E09", starts_on=today-timedelta(days=30), ends_on=today+timedelta(days=90))
        cls.other_period = AcademicPeriod.objects.create(career=cls.other_career, code="E09-X", name="Periodo E09 alternativo", starts_on=today-timedelta(days=30), ends_on=today+timedelta(days=90))
        cls.course = Course.objects.create(career=cls.career, code="E09-101", name="Curso de evaluación E09")
        cls.offering = CourseOffering.objects.create(course=cls.course, period=cls.period, group_code="A")
        cls.other_course = Course.objects.create(career=cls.other_career, code="E09-201", name="Curso de otra carrera")
        cls.other_offering = CourseOffering.objects.create(course=cls.other_course, period=cls.other_period, group_code="A")
        cls.coordinator = User.objects.create_user(username="e09_coordinator", email="coord-e09@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.coordinator, role=RoleAssignment.Role.COORDINATOR,
                   scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Coordinación de pruebas E09")
        cls.other_coordinator = User.objects.create_user(username="e09_other_coord", email="other-coord-e09@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.other_coordinator, role=RoleAssignment.Role.COORDINATOR,
                   scope=RoleAssignment.Scope.CAREER, career=cls.other_career, reason="Coordinación fuera de ámbito E09")
        cls.teacher = User.objects.create_user(username="e09_teacher", first_name="Docente", last_name="Evaluado", email="teacher-e09@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.teacher, role=RoleAssignment.Role.TEACHER,
                   scope=RoleAssignment.Scope.GROUP, group=cls.offering, reason="Docencia E09")
        TeachingAssignment.objects.create(user=cls.teacher, offering=cls.offering,
            role=TeachingAssignment.AssignmentRole.TEACHER, starts_on=today-timedelta(days=1))
        cls.students = []
        for index in range(6):
            user = User.objects.create_user(username=f"e09_student{index+1}", first_name=f"Estudiante{index+1}", email=f"student{index+1}-e09@example.test", password="test-pass-123")
            profile = StudentProfile.objects.create(user=user, institution=cls.institution, student_number=f"E09-{index+1:03d}")
            enrollment = Enrollment.objects.create(student=profile, career=cls.career, period=cls.period, valid_from=cls.period.starts_on)
            grant_role(actor=cls.admin, user=user, role=RoleAssignment.Role.STUDENT,
                       scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Estudiante E09")
            CourseEnrollment.objects.create(enrollment=enrollment, offering=cls.offering)
            cls.students.append((user, enrollment))
        cls.other_student = User.objects.create_user(username="e09_outsider", email="outsider-e09@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=cls.other_student, institution=cls.institution, student_number="E09-OUT")
        enrollment = Enrollment.objects.create(student=profile, career=cls.other_career, period=cls.other_period, valid_from=cls.other_period.starts_on)
        grant_role(actor=cls.admin, user=cls.other_student, role=RoleAssignment.Role.STUDENT,
                   scope=RoleAssignment.Scope.CAREER, career=cls.other_career, reason="Matrícula de otra carrera")
        CourseEnrollment.objects.create(enrollment=enrollment, offering=cls.other_offering)

    def setUp(self):
        self.opens = timezone.now() - timedelta(minutes=5)
        self.closes = timezone.now() + timedelta(days=1)
        self.campaign = create_campaign(actor=self.coordinator, offering_id=self.offering.pk,
            title="Encuesta de experiencia académica E09", opens_at=self.opens, closes_at=self.closes)
        publish_campaign(actor=self.coordinator, campaign_id=self.campaign.pk)
        self.target = self.campaign.targets.get()
        self.answers = {code: 4 for code, _label in QUESTIONS}

    def ballot(self, user, answers=None, target=None):
        return submit_ballot(actor=user, target_id=target or self.target.pk, response=answers or self.answers)

    def test_only_roster_students_can_answer_once_and_raw_response_is_unlinked(self):
        user, _enrollment = self.students[0]
        eligibility = self.ballot(user)
        self.assertTrue(eligibility.answered)
        self.assertEqual(EvaluationSubmission.objects.filter(target=self.target).count(), 1)
        submission = EvaluationSubmission.objects.get(target=self.target)
        self.assertNotIn("enrollment", {field.name for field in submission._meta.fields})
        self.assertNotIn("user", {field.name for field in submission._meta.fields})
        self.assertNotIn("eligibility", {field.name for field in submission._meta.fields})
        eligibility_fields = {field.name for field in eligibility._meta.fields}
        self.assertNotIn("answered_at", eligibility_fields)
        self.assertNotIn("submitted_at", eligibility_fields)
        with self.assertRaises(ValidationError):
            self.ballot(user)
        with self.assertRaises(PermissionDenied):
            self.ballot(self.other_student)

    def test_response_rejects_missing_extra_free_text_and_invalid_scale_values(self):
        user, _enrollment = self.students[0]
        with self.assertRaises(ValidationError):
            self.ballot(user, {"clarity": 5})
        with self.assertRaises(ValidationError):
            self.ballot(user, {**self.answers, "comment": "texto libre"})
        invalid = {**self.answers, "equity": 6}
        with self.assertRaises(ValidationError):
            self.ballot(user, invalid)
        self.assertEqual(EvaluationSubmission.objects.count(), 0)

    def test_manager_cannot_create_campaign_outside_career_scope(self):
        with self.assertRaises(PermissionDenied):
            create_campaign(actor=self.other_coordinator, offering_id=self.offering.pk,
                title="No autorizada", opens_at=self.opens, closes_at=self.closes)

    def test_minimum_of_five_suppresses_small_results_without_exact_count(self):
        for user, _enrollment in self.students[:4]:
            self.ballot(user)
        close_campaign(actor=self.coordinator, campaign_id=self.campaign.pk)
        campaign, aggregates = publish_results(actor=self.coordinator, campaign_id=self.campaign.pk)
        aggregate = aggregates[0]
        self.assertEqual(aggregate.state, EvaluationAggregate.State.SUPPRESSED)
        self.assertEqual(aggregate.metrics, {})
        client = APIClient(); client.force_authenticate(self.coordinator)
        data = client.get(reverse("evaluations:api-evaluations")).data
        row = next(item for item in data["campaigns"] if item["id"] == str(campaign.pk))
        self.assertEqual(row["targets"][0]["result"], {"state": "suppressed"})

    def test_aggregate_publishes_counts_mean_distribution_and_never_ballot_rows(self):
        for index, (user, _enrollment) in enumerate(self.students[:5]):
            self.ballot(user, {code: (index % 5) + 1 for code, _label in QUESTIONS})
        close_campaign(actor=self.coordinator, campaign_id=self.campaign.pk)
        _campaign, aggregates = publish_results(actor=self.coordinator, campaign_id=self.campaign.pk)
        aggregate = aggregates[0]
        self.assertEqual(aggregate.response_count, 5)
        self.assertEqual(aggregate.state, EvaluationAggregate.State.PUBLISHED)
        self.assertEqual(aggregate.metrics["clarity"]["mean"], 3)
        self.assertEqual(aggregate.metrics["clarity"]["distribution"], {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1})
        client = APIClient(); client.force_authenticate(self.teacher)
        data = client.get(reverse("evaluations:api-evaluations")).data
        self.assertEqual(data["subjectResults"][0]["responseCount"], 5)
        self.assertNotIn("submissions", data)
        self.assertNotIn("eligibilities", data)

    def test_open_campaign_and_response_are_audited_without_ballot_identity(self):
        self.assertTrue(AuditEvent.objects.filter(action="evaluation.campaign_created").exists())
        self.assertTrue(AuditEvent.objects.filter(action="evaluation.campaign_opened").exists())
        before = AuditEvent.objects.count()
        self.ballot(self.students[0][0])
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_version_replacement_before_responses_cancels_old_campaign(self):
        version_course = Course.objects.create(career=self.career, code="E09-102", name="Curso de versión E09")
        version_offering = CourseOffering.objects.create(course=version_course, period=self.period, group_code="A")
        grant_role(actor=self.admin, user=self.teacher, role=RoleAssignment.Role.TEACHER,
                   scope=RoleAssignment.Scope.GROUP, group=version_offering,
                   reason="Asignación de grupo para prueba de versiones E09")
        TeachingAssignment.objects.create(user=self.teacher, offering=version_offering,
            role=TeachingAssignment.AssignmentRole.TEACHER, starts_on=timezone.localdate()-timedelta(days=1))
        first = create_campaign(actor=self.coordinator, offering_id=version_offering.pk,
            title="Borrador inicial", opens_at=self.opens, closes_at=self.closes)
        replacement = create_campaign(actor=self.coordinator, offering_id=version_offering.pk,
            title="Versión corregida", opens_at=self.opens, closes_at=self.closes)
        first.refresh_from_db()
        self.assertEqual(first.status, EvaluationCampaign.Status.CANCELLED)
        self.assertEqual(replacement.version, 2)
        self.assertEqual(replacement.supersedes_id, first.pk)

    def test_campaign_with_ballots_cannot_be_reopened_as_an_intersection(self):
        self.ballot(self.students[0][0])
        with self.assertRaises(ValidationError):
            create_campaign(actor=self.coordinator, offering_id=self.offering.pk,
                title="Nueva encuesta", opens_at=self.opens, closes_at=self.closes)

    def test_open_campaign_cannot_be_cancelled_or_replaced_even_before_first_vote(self):
        from .services import cancel_campaign
        with self.assertRaises(ValidationError):
            cancel_campaign(actor=self.coordinator, campaign_id=self.campaign.pk,
                            reason="La coordinación decide probar una versión nueva.")
        with self.assertRaises(ValidationError):
            create_campaign(actor=self.coordinator, offering_id=self.offering.pk,
                title="Campaña solapada", opens_at=self.opens, closes_at=self.closes)

    def test_student_api_returns_only_own_ballot_status_and_accepts_structured_submission(self):
        user, _enrollment = self.students[0]
        client = APIClient(); client.force_authenticate(user)
        path = reverse("evaluations:api-evaluations")
        data = client.get(path).data
        self.assertEqual(len(data["mySurveys"]), 1)
        self.assertTrue(data["mySurveys"][0]["canRespond"])
        response = client.post(reverse("evaluations:api-evaluation-respond"),
            {"targetId": str(self.target.pk), "answers": self.answers}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("student", response.data)
        self.assertNotIn("answers", response.data)
        response = client.post(reverse("evaluations:api-evaluation-respond"),
            {"targetId": str(self.target.pk), "answers": self.answers}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_teacher_cannot_read_results_before_publication_or_individual_responses(self):
        for user, _enrollment in self.students[:5]:
            self.ballot(user)
        client = APIClient(); client.force_authenticate(self.teacher)
        data = client.get(reverse("evaluations:api-evaluations")).data
        self.assertEqual(data["subjectResults"], [])
        self.assertNotIn("submissions", data)
        self.assertNotIn("eligibilities", data)

    def test_non_manager_cannot_open_campaign(self):
        client = APIClient(); client.force_authenticate(self.students[0][0])
        response = client.post(reverse("evaluations:api-evaluation-open", args=(self.campaign.pk,)), {}, format="json")
        self.assertEqual(response.status_code, 403)

