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
from apps.activities.models import Activity, ActivityCategory, PointsMovement, Regulation
from apps.profiles.models import DevelopmentRecord, StudentProject
from .models import Application, ApplicationDecision, Opportunity, OpportunityRequirement, OpportunityVersion
from .services import evaluate_eligibility


class E07OpportunityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = User.objects.create_superuser(username="e07_admin", email="admin-e07@example.test", password="test-pass-123")
        cls.institution = Institution.objects.create(name="Universidad E07", short_name="E07-U")
        cls.career = Career.objects.create(institution=cls.institution, code="SIS", name="Ingeniería de Sistemas")
        cls.other_career = Career.objects.create(institution=cls.institution, code="ELC", name="Ingeniería Electrónica")
        cls.period = AcademicPeriod.objects.create(career=cls.career, code="E07-P", name="Periodo E07", starts_on=today - timedelta(days=20), ends_on=today + timedelta(days=70), status=AcademicPeriod.Status.OPEN)
        cls.course = Course.objects.create(career=cls.career, code="MET201", name="Metodología de la Investigación")
        cls.offering = CourseOffering.objects.create(course=cls.course, period=cls.period, group_code="A", status=CourseOffering.Status.OPEN)
        cls.student, cls.enrollment = cls.make_student("e07_student", "E07-001", cls.career, cls.period)
        cls.stranger, cls.stranger_enrollment = cls.make_student("e07_stranger", "E07-002", cls.other_career,
            AcademicPeriod.objects.create(career=cls.other_career, code="E07-X", name="Otro periodo", starts_on=today - timedelta(days=1), ends_on=today + timedelta(days=50)))
        cls.coordinator = User.objects.create_user(username="e07_coord", email="coord-e07@example.test", password="test-pass-123")
        grant_role(actor=cls.admin, user=cls.coordinator, role=RoleAssignment.Role.COORDINATOR, scope=RoleAssignment.Scope.CAREER, career=cls.career, reason="Coordinación E07")
        cls.regulation = Regulation.objects.create(career=cls.career, version=1, title="Reglamento de prueba", effective_from=today - timedelta(days=1), created_by=cls.admin)
        cls.category = ActivityCategory.objects.create(regulation=cls.regulation, code="research", name="Investigación", criterion="Acreditación ficticia.", points=100)
        cls.opportunity, cls.version = cls.make_opportunity()

    @classmethod
    def make_student(cls, username, number, career, period):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="test-pass-123")
        profile = StudentProfile.objects.create(user=user, institution=career.institution, student_number=number)
        enrollment = Enrollment.objects.create(student=profile, career=career, period=period, valid_from=period.starts_on)
        grant_role(actor=cls.admin, user=user, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER, career=career, reason="Fixture E07")
        return user, enrollment

    @classmethod
    def make_opportunity(cls):
        now = timezone.now()
        opportunity = Opportunity.objects.create(owner=cls.coordinator, created_by=cls.coordinator)
        version = OpportunityVersion.objects.create(
            opportunity=opportunity, version_number=1, title="Beca de Investigación", kind=OpportunityVersion.Kind.SCHOLARSHIP,
            description="Convocatoria de prueba", benefits="Mentoría académica", opens_at=now - timedelta(days=1),
            closes_at=now + timedelta(days=20), capacity=1,
        )
        version.careers.set([cls.career])
        rows = [
            ("average", "gte", Decimal("70"), "Promedio mínimo", ""),
            ("own_points", "gte", Decimal("100"), "Puntos propios", ""),
            ("validated_project", "exists", None, "Proyecto validado", ""),
            ("approved_course", "exists", None, "Investigación aprobada", "MET201"),
        ]
        for index, (field, operator, target, label, course) in enumerate(rows):
            OpportunityRequirement.objects.create(version=version, field_code=field, operator=operator,
                target_number=target, course_code=course, display_label=label, sort_order=index)
        version.published_at = now
        version.published_by = cls.coordinator
        version.save(update_fields=("published_at", "published_by"))
        opportunity.status = Opportunity.Status.PUBLISHED
        opportunity.active_version = version
        opportunity.save(update_fields=("status", "active_version", "updated_at"))
        return opportunity, version

    def make_eligible(self, enrollment=None, student=None):
        enrollment = enrollment or self.enrollment
        student = student or enrollment.student.user
        GradeRecord.objects.create(enrollment=enrollment, offering=self.offering, grade_value=Decimal("84"), scale_snapshot=100,
            pass_threshold_snapshot=51, status=GradeRecord.Status.VERIFIED, source="Fixture verificado", recorded_by=self.admin,
            verified_by=self.admin, verified_at=timezone.now())
        StudentProject.objects.create(enrollment=enrollment, created_by=student, title=f"Proyecto {enrollment.student.student_number}",
            description="Proyecto validado ficticio", role="Investigación", status=DevelopmentRecord.Status.VALIDATED,
            validated_by=self.admin, validated_at=timezone.now())
        activity = Activity.objects.create(enrollment=enrollment, category=self.category, title=f"Mérito {enrollment.student.student_number}",
            description="Muestra de mérito", occurred_on=timezone.localdate(), created_by=self.admin, status=Activity.Status.APPROVED)
        PointsMovement.objects.create(enrollment=enrollment, activity=activity, regulation=self.regulation, category=self.category,
            actor=self.admin, points=100, reason="Fixture sintético")

    def test_eligibility_uses_verified_grades_project_and_own_ledger(self):
        self.make_eligible()
        result = evaluate_eligibility(self.version, self.enrollment)
        self.assertEqual(result.overall_status, "eligible")
        self.assertEqual(len(result.results), 4)
        self.assertEqual({row["status"] for row in result.results}, {"meets"})
        self.assertIn("sin transferencias", result.results[1]["source"])

    def test_unverified_grade_is_insufficient_instead_of_failing_course(self):
        GradeRecord.objects.create(enrollment=self.enrollment, offering=self.offering, grade_value=90, scale_snapshot=100,
            pass_threshold_snapshot=51, status=GradeRecord.Status.UNVERIFIED, source="Pendiente", recorded_by=self.admin)
        result = evaluate_eligibility(self.version, self.enrollment)
        self.assertEqual(result.results[0]["status"], "insufficient")
        self.assertEqual(result.results[3]["status"], "insufficient")
        self.assertEqual(result.overall_status, "ineligible")

    def test_semester_and_verified_activity_are_available_typed_criteria(self):
        now = timezone.now()
        opportunity = Opportunity.objects.create(owner=self.coordinator, created_by=self.coordinator)
        version = OpportunityVersion.objects.create(opportunity=opportunity, version_number=1, title="Criterios tipados",
            kind=OpportunityVersion.Kind.PROJECT, description="Prueba", opens_at=now, closes_at=now + timedelta(days=2), capacity=1)
        version.careers.set([self.career])
        OpportunityRequirement.objects.create(version=version, field_code="semester", operator="gte", target_number=2,
            display_label="Segundo semestre mínimo", sort_order=0)
        OpportunityRequirement.objects.create(version=version, field_code="validated_activity", operator="exists",
            display_label="Actividad verificada", sort_order=1)
        first = evaluate_eligibility(version, self.enrollment)
        self.assertEqual([row["status"] for row in first.results], ["does_not_meet", "does_not_meet"])
        self.enrollment.semester_number = 2
        self.enrollment.save(update_fields=("semester_number", "updated_at"))
        Activity.objects.create(enrollment=self.enrollment, category=self.category, title="Actividad verificada",
            description="Actividad de prueba", occurred_on=timezone.localdate(), created_by=self.admin,
            status=Activity.Status.APPROVED)
        second = evaluate_eligibility(version, self.enrollment)
        self.assertEqual([row["status"] for row in second.results], ["meets", "meets"])

    def test_student_can_apply_and_snapshot_is_preserved_when_data_changes(self):
        self.make_eligible()
        client = APIClient()
        client.force_login(self.student)
        response = client.post(reverse("opportunities:apply", args=(self.version.pk,)), {"enrollmentId": str(self.enrollment.pk)}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        application = Application.objects.get(pk=response.json()["id"])
        original = application.eligibility.results
        project = StudentProject.objects.get(enrollment=self.enrollment)
        project.status = DevelopmentRecord.Status.NEEDS_CHANGES
        project.validated_by = None
        project.validated_at = None
        project.save(update_fields=("status", "validated_by", "validated_at", "updated_at"))
        resolution = APIClient()
        resolution.force_login(self.coordinator)
        denied_selection = resolution.post(reverse("opportunities:decision", args=(application.pk,)), {"decision": "selected", "reason": "Los datos cambiaron."}, format="json")
        self.assertEqual(denied_selection.status_code, 400)
        application.refresh_from_db()
        self.assertEqual(application.eligibility.results, original)
        self.assertEqual(application.status, Application.Status.SUBMITTED)

    def test_student_cannot_read_other_career_opportunity_or_apply_as_another_student(self):
        client = APIClient()
        client.force_login(self.stranger)
        listing = client.get(reverse("opportunities:list"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["opportunities"], [])
        apply = client.post(reverse("opportunities:apply", args=(self.version.pk,)), {"enrollmentId": str(self.enrollment.pk)}, format="json")
        self.assertEqual(apply.status_code, 404)

    def test_coordinator_scope_and_capacity_are_enforced(self):
        self.make_eligible()
        other_user, other_enrollment = self.make_student("e07_second", "E07-003", self.career, self.period)
        self.make_eligible(other_enrollment, other_user)
        client = APIClient()
        client.force_login(self.student)
        first = client.post(reverse("opportunities:apply", args=(self.version.pk,)), {"enrollmentId": str(self.enrollment.pk)}, format="json")
        client.force_login(other_user)
        second = client.post(reverse("opportunities:apply", args=(self.version.pk,)), {"enrollmentId": str(other_enrollment.pk)}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        client.force_login(self.coordinator)
        select_first = client.post(reverse("opportunities:decision", args=(first.json()["id"],)), {"decision": "selected", "reason": "Perfil alineado con la convocatoria."}, format="json")
        select_second = client.post(reverse("opportunities:decision", args=(second.json()["id"],)), {"decision": "selected", "reason": "Cupo agotado."}, format="json")
        self.assertEqual(select_first.status_code, 200)
        self.assertEqual(select_second.status_code, 400)
        self.assertEqual(ApplicationDecision.objects.filter(application__version=self.version).count(), 1)
        self.assertEqual(Application.objects.filter(version=self.version, status=Application.Status.SELECTED).count(), 1)

    def test_published_version_and_requirements_are_immutable(self):
        requirement = self.version.requirements.first()
        requirement.display_label = "Mutado"
        with self.assertRaises(ValidationError):
            requirement.save()
        self.version.title = "Mutado"
        with self.assertRaises(ValidationError):
            self.version.save()

    def test_close_requires_scoped_reason_and_resolves_after_pending_decisions(self):
        self.make_eligible()
        student_client = APIClient()
        student_client.force_login(self.student)
        submitted = student_client.post(reverse("opportunities:apply", args=(self.version.pk,)),
            {"enrollmentId": str(self.enrollment.pk)}, format="json")
        stranger_client = APIClient()
        stranger_client.force_login(self.stranger)
        forbidden = stranger_client.post(reverse("opportunities:close", args=(self.opportunity.pk,)),
            {"action": "close", "reason": "Intento desde otra carrera."}, format="json")
        self.assertEqual(forbidden.status_code, 403)
        manager = APIClient()
        manager.force_login(self.coordinator)
        close = manager.post(reverse("opportunities:close", args=(self.opportunity.pk,)),
            {"action": "close", "reason": "Se completó el plazo de recepción."}, format="json")
        self.assertEqual(close.status_code, 200)
        self.assertEqual(close.json()["status"], Opportunity.Status.CLOSED)
        rejected_retry = student_client.post(reverse("opportunities:apply", args=(self.version.pk,)),
            {"enrollmentId": str(self.enrollment.pk)}, format="json")
        self.assertEqual(rejected_retry.status_code, 400)
        manager.post(reverse("opportunities:decision", args=(submitted.json()["id"],)),
            {"decision": "selected", "reason": "Adjudicación según requisitos y revisión humana."}, format="json")
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.status, Opportunity.Status.RESOLVED)

    def test_new_publication_becomes_current_and_notifies_existing_applicant(self):
        self.make_eligible()
        student_client = APIClient()
        student_client.force_login(self.student)
        submitted = student_client.post(reverse("opportunities:apply", args=(self.version.pk,)),
            {"enrollmentId": str(self.enrollment.pk)}, format="json")
        self.assertEqual(submitted.status_code, 201)
        now = timezone.now()
        coordinator_client = APIClient()
        coordinator_client.force_login(self.coordinator)
        payload = {
            "title": "Beca de Investigación", "kind": "scholarship", "description": "Condiciones revisadas",
            "benefits": "Mentoría", "instructions": "Postulación desde el portal",
            "opensAt": (now - timedelta(hours=1)).isoformat(), "closesAt": (now + timedelta(days=10)).isoformat(),
            "capacity": 1, "careerIds": [str(self.career.pk)],
            "requirements": [
                {"field": "average", "label": "Promedio mínimo", "target": "70"},
                {"field": "own_points", "label": "Puntos propios", "target": "100"},
                {"field": "validated_project", "label": "Proyecto validado"},
                {"field": "approved_course", "label": "Curso aprobado", "courseCode": "MET201"},
                {"field": "semester", "label": "Segundo semestre", "target": "2"},
                {"field": "period", "label": "Periodo vigente", "periodCode": "E07-P"},
                {"field": "validated_activity", "label": "Actividad verificada"},
            ],
        }
        response = coordinator_client.post(reverse("opportunities:new-version", args=(self.opportunity.pk,)), payload, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        student_state = student_client.get(reverse("opportunities:list")).json()
        old_application = next(app for app in student_state["applications"] if app["id"] == submitted.json()["id"])
        self.assertEqual(old_application["newVersionId"], response.json()["versionId"])
        self.assertEqual(old_application["versionId"], str(self.version.pk))
        old_version_retry = student_client.post(reverse("opportunities:apply", args=(self.version.pk,)),
            {"enrollmentId": str(self.enrollment.pk)}, format="json")
        self.assertEqual(old_version_retry.status_code, 400)


    def test_changed_verified_data_marks_decision_stale_and_can_reopen_review(self):
        self.make_eligible()
        student_client = APIClient()
        student_client.force_login(self.student)
        submitted = student_client.post(reverse("opportunities:apply", args=(self.version.pk,)),
            {"enrollmentId": str(self.enrollment.pk)}, format="json")
        self.assertEqual(submitted.status_code, 201, submitted.json())
        manager = APIClient()
        manager.force_login(self.coordinator)
        selected = manager.post(reverse("opportunities:decision", args=(submitted.json()["id"],)),
            {"decision": "selected", "reason": "Adjudicación inicial conforme a los criterios."}, format="json")
        self.assertEqual(selected.status_code, 200, selected.json())
        project = StudentProject.objects.get(enrollment=self.enrollment)
        project.status = DevelopmentRecord.Status.NEEDS_CHANGES
        project.validated_by = None
        project.validated_at = None
        project.save(update_fields=("status", "validated_by", "validated_at", "updated_at"))
        managed = manager.get(reverse("opportunities:list")).json()["managed"]
        app_data = managed[0]["applications"][0]
        self.assertTrue(app_data["eligibilityChanged"])
        self.assertEqual(app_data["status"], Application.Status.SELECTED)
        reopened = manager.post(reverse("opportunities:decision", args=(submitted.json()["id"],)),
            {"decision": "in_review", "reason": "Proyecto dejó de estar validado; revisar adjudicación."}, format="json")
        self.assertEqual(reopened.status_code, 200, reopened.json())
        self.assertEqual(reopened.json()["status"], Application.Status.IN_REVIEW)
        self.assertEqual(ApplicationDecision.objects.filter(application_id=submitted.json()["id"]).count(), 2)
        self.assertEqual(ApplicationDecision.objects.filter(application_id=submitted.json()["id"]).order_by("decided_at").last().previous_status,
            Application.Status.SELECTED)

    def test_coordinator_creates_and_publishes_first_version(self):
        now = timezone.now()
        client = APIClient()
        client.force_login(self.coordinator)
        payload = {
            "title": "Pasantía de Sistemas", "kind": "internship", "description": "Experiencia ficticia de prueba",
            "opensAt": (now - timedelta(minutes=1)).isoformat(), "closesAt": (now + timedelta(days=5)).isoformat(),
            "capacity": 2, "careerIds": [str(self.career.pk)], "publish": True,
            "requirements": [{"field": "validated_project", "label": "Proyecto validado"}],
        }
        response = client.post(reverse("opportunities:create"), payload, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        opportunity = Opportunity.objects.get(pk=response.json()["id"])
        self.assertEqual(opportunity.status, Opportunity.Status.PUBLISHED)
        self.assertEqual(str(opportunity.active_version_id), response.json()["versionId"])
        self.assertIsNotNone(opportunity.active_version.published_at)
