from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import RoleAssignment, User
from apps.accounts.services import grant_role
from apps.academics.models import (
    AcademicPeriod, Career, Course, CourseEnrollment, CourseOffering, Enrollment,
    GradeRecord, Institution, StudentProfile, TeachingAssignment,
)
from apps.audit.services import record_event
from apps.profiles.models import DevelopmentRecord, StudentProject, StudentSkill
from apps.activities.services import seed_regulation
from apps.activities.models import ActivityCategory, Activity
from apps.activities.services import record_verified_activity
from apps.opportunities.models import Opportunity, OpportunityVersion, OpportunityRequirement
from apps.transfers.models import TransferRequest
from apps.transfers.services import create_transfer_request, review_transfer
from apps.evaluations.models import EvaluationCampaign
from apps.evaluations.services import create_campaign as create_evaluation_campaign, publish_campaign as publish_evaluation_campaign


class Command(BaseCommand):
    help = "Crea/actualiza catálogos ficticios de UPEA e Ingeniería de Sistemas para desarrollo local."

    @transaction.atomic
    def handle(self, *args, **options):
        institution, _ = Institution.objects.update_or_create(
            short_name="UPEA-DEMO",
            defaults={"name": "Universidad Pública de El Alto (datos ficticios)", "timezone": "America/La_Paz", "active": True},
        )
        career, _ = Career.objects.update_or_create(
            institution=institution,
            code="SIS",
            defaults={"name": "Ingeniería de Sistemas (datos ficticios)", "active": True},
        )
        periods = [
            ("2026-1", "I/2026", date(2026, 2, 2), date(2026, 7, 31), AcademicPeriod.Status.CLOSED),
            ("2026-2", "II/2026", date(2026, 8, 3), date(2026, 12, 18), AcademicPeriod.Status.OPEN),
            ("2027-1", "I/2027", date(2027, 2, 1), date(2027, 7, 30), AcademicPeriod.Status.PLANNED),
        ]
        period_objects = {}
        for code, name, start, end, status in periods:
            period_objects[code], _ = AcademicPeriod.objects.update_or_create(
                career=career, code=code,
                defaults={"name": name, "starts_on": start, "ends_on": end, "grade_scale": 100, "pass_threshold": 51, "status": status},
            )
        courses = [
            ("INF101", "Programación I", 5),
            ("MAT101", "Cálculo I", 5),
            ("SIS101", "Introducción a la Ingeniería de Sistemas", 4),
            ("INF102", "Estructuras de Datos", 5),
            ("MET201", "Metodología de la Investigación", 4),
        ]
        for code, name, credits in courses:
            course, _ = Course.objects.update_or_create(
                career=career, code=code,
                defaults={"name": name, "credits": credits, "active": True},
            )
            for period_code in period_objects:
                CourseOffering.objects.update_or_create(
                    course=course, period=period_objects[period_code], group_code="A",
                    defaults={"status": {
                        AcademicPeriod.Status.OPEN: CourseOffering.Status.OPEN,
                        AcademicPeriod.Status.CLOSED: CourseOffering.Status.CLOSED,
                        AcademicPeriod.Status.PLANNED: CourseOffering.Status.PLANNED,
                    }[period_objects[period_code].status]},
                )
        actor = User.objects.filter(is_superuser=True, is_active=True).order_by("date_joined").first()
        sample_accounts = 0
        if actor:
            regulation = seed_regulation(career=career, actor=actor)
            sample_accounts = self._seed_trajectory(actor, institution, career, period_objects, courses)
            self._seed_opportunity(actor, career)
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo ficticio listo: {institution.short_name}, {career.code}, "
            f"{len(period_objects)} periodos, {len(courses)} asignaturas y {len(courses) * len(period_objects)} grupos; "
            f"{sample_accounts} cuentas sintéticas de trayectoria; reglamento SPD v{regulation.version if actor else 'sin publicar'}."
        ))
        if not actor:
            self.stdout.write(self.style.WARNING(
                "Para generar estudiantes/docente ficticios y sus asignaciones, crea un superusuario y vuelve a ejecutar seed_demo."
            ))
        else:
            self.stdout.write("Cuentas sintéticas sin contraseña: demo.estudiante01–05, demo.docente01 y demo.coordinador01. Asigna claves locales con `manage.py changepassword <usuario>`.")

    def _seed_trajectory(self, actor, institution, career, periods, courses):
        previous_period = periods["2026-1"]
        current_period = periods["2026-2"]
        student_specs = [
            ("demo.estudiante01", "Andrea", "Ejemplo", "DEMO-SIS-001"),
            ("demo.estudiante02", "Mateo", "Ficticio", "DEMO-SIS-002"),
            ("demo.estudiante03", "Lucía", "Muestra", "DEMO-SIS-003"),
            ("demo.estudiante04", "Carlos", "Demostración", "DEMO-SIS-004"),
            ("demo.estudiante05", "Valeria", "Ficticia", "DEMO-SIS-005"),
        ]
        students = []
        for username, first_name, last_name, student_number in student_specs:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name, "email": f"{username}@example.test"},
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=("password",))
            profile, _ = StudentProfile.objects.update_or_create(
                user=user,
                defaults={"institution": institution, "student_number": student_number},
            )
            for period in (previous_period, current_period):
                completed = period == previous_period
                enrollment, _ = Enrollment.objects.get_or_create(
                    student=profile, career=career, period=period,
                    defaults={
                        "semester_number": 1 if completed else 2,
                        "status": Enrollment.Status.COMPLETED if completed else Enrollment.Status.ACTIVE,
                        "valid_from": period.starts_on,
                        "valid_to": period.ends_on if completed else None,
                    },
                )
                if not user.role_assignments.filter(user=user, role=RoleAssignment.Role.STUDENT, scope=RoleAssignment.Scope.CAREER, career=career, active=True).exists():
                    grant_role(actor=actor, user=user, role=RoleAssignment.Role.STUDENT,
                               scope=RoleAssignment.Scope.CAREER, career=career, reason="Cuenta sintética para demostración local")
                students.append((user, profile, enrollment, period))

        students_by_username = {
            user.username: (user, profile, enrollment, period)
            for user, profile, enrollment, period in students
        }

        course_objects = {course.code: course for course in Course.objects.filter(career=career, code__in=[row[0] for row in courses])}
        offering_by_period_and_course = {}
        for (code, _name, _credits) in courses:
            for period in (previous_period, current_period):
                offering = CourseOffering.objects.get(course=course_objects[code], period=period, group_code="A")
                offering_by_period_and_course[(period.pk, code)] = offering
                for _user, _profile, enrollment, _enrollment_period in students:
                    if enrollment.period_id == period.pk:
                        CourseEnrollment.objects.get_or_create(enrollment=enrollment, offering=offering, defaults={"active": True})

        teacher, created = User.objects.get_or_create(
            username="demo.docente01",
            defaults={"first_name": "Docente", "last_name": "Ficticio", "email": "demo.docente01@example.test"},
        )
        if created:
            teacher.set_unusable_password()
            teacher.save(update_fields=("password",))
        current_offerings = [offering_by_period_and_course[(current_period.pk, code)] for code, _name, _credits in courses]
        for offering in current_offerings:
            if not teacher.role_assignments.filter(role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP, group=offering, active=True).exists():
                grant_role(actor=actor, user=teacher, role=RoleAssignment.Role.TEACHER,
                           scope=RoleAssignment.Scope.GROUP, group=offering, reason="Asignación docente sintética")
            TeachingAssignment.objects.get_or_create(
                user=teacher, offering=offering, role=TeachingAssignment.AssignmentRole.TEACHER,
                defaults={"starts_on": current_period.starts_on, "active": True},
            )

        evaluation_offering = offering_by_period_and_course[(current_period.pk, "INF101")]
        if not EvaluationCampaign.objects.filter(
            offering=evaluation_offering, title="Encuesta académica de demostración",
        ).exists():
            now = timezone.now()
            evaluation_campaign = create_evaluation_campaign(
                actor=actor, offering_id=evaluation_offering.pk,
                title="Encuesta académica de demostración",
                opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=14),
                minimum_responses=5,
            )
            publish_evaluation_campaign(actor=actor, campaign_id=evaluation_campaign.pk)

        previous_enrollments = [enrollment for _user, _profile, enrollment, period in students if period.pk == previous_period.pk]
        grade_values = ([Decimal("84"), Decimal("78"), Decimal("91"), Decimal("88"), Decimal("90")],
                        [Decimal("73"), Decimal("82"), Decimal("76"), Decimal("80"), Decimal("85")],
                        [Decimal("92"), Decimal("86"), Decimal("89"), Decimal("94"), Decimal("95")],
                        [Decimal("81"), Decimal("77"), Decimal("84"), Decimal("88"), Decimal("82")],
                        [Decimal("89"), Decimal("91"), Decimal("86"), Decimal("93"), Decimal("90")])
        for index, enrollment in enumerate(previous_enrollments):
            for course_index, (code, _name, _credits) in enumerate(courses):
                offering = offering_by_period_and_course[(previous_period.pk, code)]
                grade, created = GradeRecord.objects.get_or_create(
                    enrollment=enrollment, offering=offering,
                    defaults={
                        "grade_value": grade_values[index][course_index],
                        "scale_snapshot": previous_period.grade_scale,
                        "pass_threshold_snapshot": previous_period.pass_threshold,
                        "status": GradeRecord.Status.VERIFIED,
                        "source": "Datos sintéticos de demostración",
                        "source_reference": f"DEMO-E05-{enrollment.student.student_number}-{code}",
                        "recorded_by": actor,
                        "verified_by": actor,
                        "verified_at": timezone.now(),
                    },
                )
                if created:
                    record_event(actor=actor, action="demo.grade_seeded", obj=grade, scope_type="career", scope_id=career.pk,
                                 reason="Carga de nota ficticia para prueba local", safe_metadata={"offering": code})

        # Andrea is a deterministic, fully verified applicant for the E07 walkthrough.
        eligible_user, _profile, eligible_enrollment, _period = students_by_username["demo.estudiante01"]
        for code, value in zip((row[0] for row in courses), (84, 88, 91, 86, 89)):
            offering = offering_by_period_and_course[(current_period.pk, code)]
            grade, created = GradeRecord.objects.get_or_create(
                enrollment=eligible_enrollment, offering=offering,
                defaults={"grade_value": Decimal(value), "scale_snapshot": current_period.grade_scale,
                          "pass_threshold_snapshot": current_period.pass_threshold,
                          "status": GradeRecord.Status.VERIFIED, "source": "Datos sintéticos de demostración E07",
                          "source_reference": f"DEMO-E07-{eligible_enrollment.student.student_number}-{code}",
                          "recorded_by": actor, "verified_by": actor, "verified_at": timezone.now()},
            )
            if created:
                record_event(actor=actor, action="demo.grade_seeded", obj=grade, scope_type="career", scope_id=career.pk,
                             reason="Carga ficticia verificada para el recorrido E07", safe_metadata={"offering": code})
        StudentProject.objects.get_or_create(
            enrollment=eligible_enrollment, title="Investigación aplicada de datos urbanos",
            defaults={"description": "Proyecto demostrativo validado para comprobar requisitos de una beca ficticia.",
                      "role": "Análisis y prototipado", "started_on": current_period.starts_on,
                      "status": DevelopmentRecord.Status.VALIDATED, "created_by": eligible_user,
                      "validated_by": actor, "validated_at": timezone.now()},
        )
        regulation = seed_regulation(career=career, actor=actor)
        # Lucía has a separate, clearly synthetic mentoring award to exercise E08
        # without changing Andrea's 100-point E07 eligibility walkthrough.
        transfer_sender, _transfer_profile, transfer_enrollment, _transfer_period = students_by_username["demo.estudiante02"]
        transfer_title = "Mentoría entre pares para prueba E08"
        transfer_date = current_period.starts_on + timedelta(days=26)
        if not Activity.objects.filter(enrollment=transfer_enrollment, occurred_on=transfer_date, title=transfer_title).exists():
            mentoring = ActivityCategory.objects.get(regulation=regulation, code="mentoring")
            record_verified_activity(actor=actor, enrollment=transfer_enrollment, category=mentoring,
                                     title=transfer_title,
                                     description="Actividad ficticia aprobada para recorrer la solicitud de transferencia E08.",
                                     occurred_on=transfer_date, source="Constancia sintética de mentoría entre pares")
        # Give Mateo both a transferable source and a received item in his history.
        _recipient_user, _recipient_profile, recipient_enrollment, _recipient_period = students_by_username["demo.estudiante02"]
        sender_user, _sender_profile, sender_enrollment, _sender_period = students_by_username["demo.estudiante03"]
        sender_title = "Mentoría entre pares para transferencia de muestra"
        sender_date = current_period.starts_on + timedelta(days=27)
        sender_activity = Activity.objects.filter(
            enrollment=sender_enrollment, occurred_on=sender_date, title=sender_title,
        ).first()
        if not sender_activity:
            sender_activity = record_verified_activity(
                actor=actor, enrollment=sender_enrollment, category=mentoring,
                title=sender_title,
                description="Mentoría ficticia aprobada como origen de una transferencia de demostración.",
                occurred_on=sender_date, source="Constancia sintética de mentoría entre pares",
            )
        sample_key = "DEMO-E08-LUCIA-MATEO-001"
        if not TransferRequest.objects.filter(sender=sender_enrollment, idempotency_key=sample_key).exists():
            sample_request, _created = create_transfer_request(
                actor=sender_user, sender_id=sender_enrollment.pk,
                recipient_id=recipient_enrollment.pk, activity_id=sender_activity.pk,
                amount=2,
                reason="Aporte conjunto en la preparación y validación del prototipo de laboratorio.",
                idempotency_key=sample_key,
            )
            review_transfer(
                actor=actor, request_id=sample_request.pk, decision="approve",
                reason="Aporte corroborado en el registro ficticio de demostración.",
            )
        for index, (category_code, title) in enumerate((
            ("research", "Colaboración en investigación de muestra"),
            ("collaboration", "Colaboración validada para reconocimiento E08"),
            ("featured_project", "Proyecto destacado de muestra"),
            ("contest_winner", "Reconocimiento académico de muestra"),
            ("seminar", "Seminario académico de muestra"),
        )):
            occurred_on = current_period.starts_on + timedelta(days=20 + index)
            if not Activity.objects.filter(enrollment=eligible_enrollment, occurred_on=occurred_on, title=title).exists():
                category = ActivityCategory.objects.get(regulation=regulation, code=category_code)
                record_verified_activity(actor=actor, enrollment=eligible_enrollment, category=category,
                                         title=title, description="Hecho ficticio para demostrar el libro de méritos propios en E07.",
                                         occurred_on=occurred_on, source="Constancia sintética de seed_demo")

        primary_user, _profile, current_enrollment, _period = students_by_username["demo.estudiante01"]
        demo_project, created = StudentProject.objects.get_or_create(
            enrollment=current_enrollment,
            title="Sistema de inventario para laboratorio",
            defaults={
                "description": "Aplicación académica de muestra para controlar equipos y préstamos del laboratorio.",
                "role": "Desarrollo de base de datos y reportes",
                "started_on": date(2026, 8, 10),
                "status": DevelopmentRecord.Status.IN_REVIEW,
                "created_by": primary_user,
            },
        )
        if created:
            record_event(actor=actor, action="demo.project_seeded", obj=demo_project, scope_type="career", scope_id=career.pk,
                         reason="Carga de proyecto ficticio para prueba local", safe_metadata={"status": demo_project.status})
        StudentSkill.objects.get_or_create(
            enrollment=current_enrollment,
            name="Python",
            defaults={"proficiency_label": "Intermedio (declarado)", "description": "Uso en cursos y proyectos académicos.", "status": DevelopmentRecord.Status.DECLARED, "created_by": primary_user},
        )
        return len(student_specs) + 2

    def _seed_opportunity(self, actor, career):
        from apps.accounts.models import User
        from apps.accounts.services import grant_role

        coordinator, created = User.objects.get_or_create(
            username="demo.coordinador01",
            defaults={"first_name": "Coordinación", "last_name": "Ficticia", "email": "demo.coordinador01@example.test"},
        )
        if created:
            coordinator.set_unusable_password()
            coordinator.save(update_fields=("password",))
        if not coordinator.role_assignments.filter(role=RoleAssignment.Role.COORDINATOR, scope=RoleAssignment.Scope.CAREER, career=career, active=True).exists():
            grant_role(actor=actor, user=coordinator, role=RoleAssignment.Role.COORDINATOR,
                       scope=RoleAssignment.Scope.CAREER, career=career,
                       reason="Coordinación sintética para recorrido local de oportunidades")
        existing = OpportunityVersion.objects.filter(title="Beca de Investigación", careers=career).first()
        if existing:
            return
        opportunity = Opportunity.objects.create(owner=coordinator, created_by=coordinator,
                                                  status=Opportunity.Status.DRAFT)
        now = timezone.now()
        version = OpportunityVersion.objects.create(
            opportunity=opportunity, version_number=1, title="Beca de Investigación",
            kind=OpportunityVersion.Kind.SCHOLARSHIP,
            description="Apoyo ficticio para estudiantes que desarrollan proyectos de investigación aplicada en Ingeniería de Sistemas.",
            benefits="Apoyo económico de demostración, mentoría académica y acceso a laboratorio.",
            application_instructions="Postula desde UPEA Talent+ y revisa el estado de tu solicitud en esta página.",
            opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=45), capacity=2,
            published_by=coordinator,
        )
        version.careers.set([career])
        definitions = (
            ("average", "gte", Decimal("70"), "Promedio simple verificado mínimo", ""),
            ("own_points", "gte", Decimal("100"), "Puntos propios SPD mínimos", ""),
            ("validated_project", "exists", None, "Participación en al menos un proyecto validado", ""),
            ("approved_course", "exists", None, "Curso de investigación aprobado", "MET201"),
        )
        for order, (field, operator, target, label, course_code) in enumerate(definitions):
            OpportunityRequirement.objects.get_or_create(
                version=version, field_code=field, course_code=course_code,
                defaults={"operator": operator, "target_number": target, "display_label": label, "sort_order": order},
            )
        version.published_at = now
        version.save(update_fields=("published_at", "published_by"))
        opportunity.status = Opportunity.Status.PUBLISHED
        opportunity.active_version = version
        opportunity.save(update_fields=("status", "active_version", "updated_at"))
