from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
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
from apps.activities.services import record_verified_activity, submit_activity
from apps.opportunities.models import Application, Opportunity, OpportunityVersion, OpportunityRequirement
from apps.opportunities.services import evaluate_eligibility
from apps.transfers.models import TransferRequest
from apps.transfers.services import create_transfer_request, review_transfer
from apps.evaluations.models import EvaluationCampaign, EvaluationEligibility
from apps.evaluations.services import (
    QUESTIONS, close_campaign, create_campaign as create_evaluation_campaign,
    publish_campaign as publish_evaluation_campaign,
    publish_results as publish_evaluation_results, submit_ballot,
)
from apps.support.models import SupportAction, SupportAlert, SupportCase, SupportRuleVersion
from apps.support.services import evaluate_active_rules


class Command(BaseCommand):
    help = "Prepara el catálogo local de feria para UPEA e Ingeniería de Sistemas."

    @transaction.atomic
    def handle(self, *args, **options):
        institution, _ = Institution.objects.update_or_create(
            short_name="UPEA-DEMO",
            defaults={"name": "Universidad Pública de El Alto", "timezone": "America/La_Paz", "active": True},
        )
        career, _ = Career.objects.update_or_create(
            institution=institution,
            code="SIS",
            defaults={"name": "Ingeniería de Sistemas", "active": True},
        )
        periods = [
            ("2025-2", "II/2025", date(2025, 8, 4), date(2025, 12, 19), AcademicPeriod.Status.CLOSED),
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
            self._seed_mateo_complete_profile(actor, career, period_objects, courses)
            self._seed_support(actor, career, period_objects, courses)
            self._seed_jury_walkthrough(actor, career, period_objects, courses)
        self.stdout.write(self.style.SUCCESS(
            f"Entorno local preparado: {institution.short_name}, {career.code}, "
            f"{len(period_objects)} periodos, {len(courses)} asignaturas y {len(courses) * len(period_objects)} grupos; "
            f"{sample_accounts} cuentas de trayectoria; reglamento SPD v{regulation.version if actor else 'sin publicar'}."
        ))
        if not actor:
            self.stdout.write(self.style.WARNING(
                "Para generar las cuentas y asignaciones de feria, crea una cuenta técnica y vuelve a ejecutar seed_demo."
            ))
        else:
            self.stdout.write("Cuentas de acceso sin contraseña: demo.estudiante01–05, demo.docente01 y demo.coordinador01. Asigna claves locales con `manage.py changepassword <usuario>`.")

    def _seed_trajectory(self, actor, institution, career, periods, courses):
        previous_period = periods["2026-1"]
        current_period = periods["2026-2"]
        student_specs = [
            ("demo.estudiante01", "Andrea", "Flores", "SIS-2026-001"),
            ("demo.estudiante02", "Mateo", "Rojas", "SIS-2026-002"),
            ("demo.estudiante03", "Lucía", "Condori", "SIS-2026-003"),
            ("demo.estudiante04", "Carlos", "Mamani", "SIS-2026-004"),
            ("demo.estudiante05", "Valeria", "Quispe", "SIS-2026-005"),
        ]
        students = []
        for username, first_name, last_name, student_number in student_specs:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name, "email": f"{username}@example.test"},
            )
            if (user.first_name, user.last_name) != (first_name, last_name):
                user.first_name, user.last_name = first_name, last_name
                user.save(update_fields=("first_name", "last_name"))
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
                               scope=RoleAssignment.Scope.CAREER, career=career, reason="Asignación estudiantil de Ingeniería de Sistemas")
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
            defaults={"first_name": "Patricia", "last_name": "Choque", "email": "demo.docente01@example.test"},
        )
        if created:
            teacher.set_unusable_password()
            teacher.save(update_fields=("password",))
        elif (teacher.first_name, teacher.last_name) != ("Patricia", "Choque"):
            teacher.first_name, teacher.last_name = "Patricia", "Choque"
            teacher.save(update_fields=("first_name", "last_name"))
        current_offerings = [offering_by_period_and_course[(current_period.pk, code)] for code, _name, _credits in courses]
        for offering in current_offerings:
            if not teacher.role_assignments.filter(role=RoleAssignment.Role.TEACHER, scope=RoleAssignment.Scope.GROUP, group=offering, active=True).exists():
                grant_role(actor=actor, user=teacher, role=RoleAssignment.Role.TEACHER,
                           scope=RoleAssignment.Scope.GROUP, group=offering, reason="Asignación docente de Ingeniería de Sistemas")
            TeachingAssignment.objects.get_or_create(
                user=teacher, offering=offering, role=TeachingAssignment.AssignmentRole.TEACHER,
                defaults={"starts_on": current_period.starts_on, "active": True},
            )

        evaluation_offering = offering_by_period_and_course[(current_period.pk, "INF101")]
        legacy_title = "Encuesta académica de demostración"
        campaign_title = "Experiencia académica en Programación I"
        evaluation_campaign = EvaluationCampaign.objects.filter(
            offering=evaluation_offering, title__in=(legacy_title, campaign_title),
        ).first()
        if not evaluation_campaign:
            now = timezone.now()
            evaluation_campaign = create_evaluation_campaign(
                actor=actor, offering_id=evaluation_offering.pk,
                title=campaign_title,
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
                        "source": "Registro académico del periodo",
                        "source_reference": f"SIS-2026-1-{enrollment.student.student_number}-{code}",
                        "recorded_by": actor,
                        "verified_by": actor,
                        "verified_at": timezone.now(),
                    },
                )
                if created:
                    record_event(actor=actor, action="grade.recorded", obj=grade, scope_type="career", scope_id=career.pk,
                                 reason="Registro académico de periodo cerrado", safe_metadata={"offering": code})

        # E10 comparison baseline: Mateo has a second fully verified, concluded period.
        # It creates a safe, reproducible example without treating the active term as evidence.
        mateo_user, mateo_profile, _mateo_current, _ = students_by_username["demo.estudiante02"]
        baseline_period = periods["2025-2"]
        baseline_enrollment, _ = Enrollment.objects.get_or_create(student=mateo_profile, career=career, period=baseline_period,
            defaults={"semester_number": 1, "status": Enrollment.Status.COMPLETED,
                      "valid_from": baseline_period.starts_on, "valid_to": baseline_period.ends_on})
        for index, (code, _name, _credits) in enumerate(courses):
            offering = CourseOffering.objects.get(course=Course.objects.get(career=career, code=code), period=baseline_period, group_code="A")
            CourseEnrollment.objects.get_or_create(enrollment=baseline_enrollment, offering=offering, defaults={"active": True})
            GradeRecord.objects.get_or_create(enrollment=baseline_enrollment, offering=offering, defaults={
                "grade_value": Decimal((95, 94, 96, 93, 95)[index]), "scale_snapshot": baseline_period.grade_scale,
                "pass_threshold_snapshot": baseline_period.pass_threshold, "status": GradeRecord.Status.VERIFIED,
                "source": "Registro académico del periodo", "source_reference": f"SIS-2025-2-{mateo_profile.student_number}-{code}",
                "recorded_by": actor, "verified_by": actor, "verified_at": timezone.now(),
            })

        # Andrea is a deterministic, fully verified applicant for the E07 walkthrough.
        eligible_user, _profile, eligible_enrollment, _period = students_by_username["demo.estudiante01"]
        for code, value in zip((row[0] for row in courses), (84, 88, 91, 86, 89)):
            offering = offering_by_period_and_course[(current_period.pk, code)]
            grade, created = GradeRecord.objects.get_or_create(
                enrollment=eligible_enrollment, offering=offering,
                defaults={"grade_value": Decimal(value), "scale_snapshot": current_period.grade_scale,
                          "pass_threshold_snapshot": current_period.pass_threshold,
                          "status": GradeRecord.Status.VERIFIED, "source": "Registro académico del periodo",
                          "source_reference": f"SIS-2026-2-{eligible_enrollment.student.student_number}-{code}",
                          "recorded_by": actor, "verified_by": actor, "verified_at": timezone.now()},
            )
            if created:
                record_event(actor=actor, action="grade.recorded", obj=grade, scope_type="career", scope_id=career.pk,
                             reason="Registro académico del periodo", safe_metadata={"offering": code})
        StudentProject.objects.get_or_create(
            enrollment=eligible_enrollment, title="Investigación aplicada de datos urbanos",
            defaults={"description": "Proyecto de investigación aplicada con análisis y prototipado de datos urbanos.",
                      "role": "Análisis y prototipado", "started_on": current_period.starts_on,
                      "status": DevelopmentRecord.Status.VALIDATED, "created_by": eligible_user,
                      "validated_by": actor, "validated_at": timezone.now()},
        )
        regulation = seed_regulation(career=career, actor=actor)
        mentoring = ActivityCategory.objects.get(regulation=regulation, code="mentoring")
        # Mateo has a separate mentoring award to exercise E08 without changing
        # Andrea's eligibility walkthrough.
        transfer_sender, _transfer_profile, transfer_enrollment, _transfer_period = students_by_username["demo.estudiante02"]
        transfer_title = "Mentoría entre pares para prueba E08"
        transfer_date = current_period.starts_on + timedelta(days=26)
        if not Activity.objects.filter(enrollment=transfer_enrollment, occurred_on=transfer_date, title=transfer_title).exists():
            record_verified_activity(actor=actor, enrollment=transfer_enrollment, category=mentoring,
                                     title=transfer_title,
                                     description="Acompañamiento entre pares en la preparación de un prototipo de laboratorio.",
                                     occurred_on=transfer_date, source="Registro de mentoría académica")
        # Give Mateo both a transferable source and a received item in his history.
        _recipient_user, _recipient_profile, recipient_enrollment, _recipient_period = students_by_username["demo.estudiante02"]
        sender_user, _sender_profile, sender_enrollment, _sender_period = students_by_username["demo.estudiante03"]
        sender_title = "Mentoría entre pares en laboratorio de innovación"
        sender_date = current_period.starts_on + timedelta(days=27)
        sender_activity = Activity.objects.filter(
            enrollment=sender_enrollment, occurred_on=sender_date, title=sender_title,
        ).first()
        if not sender_activity:
            sender_activity = record_verified_activity(
                actor=actor, enrollment=sender_enrollment, category=mentoring,
                title=sender_title,
                description="Acompañamiento a un equipo estudiantil en el diseño de un prototipo.",
                occurred_on=sender_date, source="Registro de mentoría académica",
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
                reason="Aporte confirmado por la coordinación del proyecto.",
            )
        for index, (category_code, title) in enumerate((
            ("research", "Colaboración en investigación de datos urbanos"),
            ("collaboration", "Colaboración en el proyecto de laboratorio"),
            ("featured_project", "Proyecto destacado de automatización"),
            ("contest_winner", "Primer lugar en concurso de programación"),
            ("seminar", "Seminario de arquitectura de software"),
        )):
            occurred_on = current_period.starts_on + timedelta(days=20 + index)
            if not Activity.objects.filter(enrollment=eligible_enrollment, occurred_on=occurred_on, title=title).exists():
                category = ActivityCategory.objects.get(regulation=regulation, code=category_code)
                record_verified_activity(actor=actor, enrollment=eligible_enrollment, category=category,
                                         title=title, description="Participación académica registrada en Ingeniería de Sistemas.",
                                         occurred_on=occurred_on, source="Constancia de participación académica")

        primary_user, _profile, current_enrollment, _period = students_by_username["demo.estudiante01"]
        demo_project, created = StudentProject.objects.get_or_create(
            enrollment=current_enrollment,
            title="Sistema de inventario para laboratorio",
            defaults={
                "description": "Aplicación académica para controlar equipos y préstamos del laboratorio.",
                "role": "Desarrollo de base de datos y reportes",
                "started_on": date(2026, 8, 10),
                "status": DevelopmentRecord.Status.IN_REVIEW,
                "created_by": primary_user,
            },
        )
        if created:
            record_event(actor=actor, action="development.project_submitted", obj=demo_project, scope_type="career", scope_id=career.pk,
                         reason="Presentación del proyecto para revisión", safe_metadata={"status": demo_project.status})
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
            defaults={"first_name": "Sandra", "last_name": "López", "email": "demo.coordinador01@example.test"},
        )
        if created:
            coordinator.set_unusable_password()
            coordinator.save(update_fields=("password",))
        elif (coordinator.first_name, coordinator.last_name) != ("Sandra", "López"):
            coordinator.first_name, coordinator.last_name = "Sandra", "López"
            coordinator.save(update_fields=("first_name", "last_name"))
        if not coordinator.role_assignments.filter(role=RoleAssignment.Role.COORDINATOR, scope=RoleAssignment.Scope.CAREER, career=career, active=True).exists():
            grant_role(actor=actor, user=coordinator, role=RoleAssignment.Role.COORDINATOR,
                       scope=RoleAssignment.Scope.CAREER, career=career,
                       reason="Coordinación de Ingeniería de Sistemas")
        existing = OpportunityVersion.objects.filter(title="Beca de Investigación", careers=career).first()
        if existing:
            return
        opportunity = Opportunity.objects.create(owner=coordinator, created_by=coordinator,
                                                  status=Opportunity.Status.DRAFT)
        now = timezone.now()
        version = OpportunityVersion.objects.create(
            opportunity=opportunity, version_number=1, title="Beca de Investigación",
            kind=OpportunityVersion.Kind.SCHOLARSHIP,
            description="Apoyo a estudiantes que desarrollan proyectos de investigación aplicada en Ingeniería de Sistemas.",
            benefits="Apoyo económico, mentoría académica y acceso a laboratorio.",
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

    def _seed_mateo_complete_profile(self, actor, career, periods, courses):
        """Give the primary student account useful, connected data in every student area."""
        from pathlib import Path
        from django.conf import settings

        from apps.activities.models import Activity, ActivityCategory, Regulation
        from apps.activities.services import record_verified_activity, submit_activity
        from apps.academics.models import CourseEnrollment
        from apps.opportunities.models import EligibilitySnapshot

        student = User.objects.get(username="demo.estudiante02")
        profile = StudentProfile.objects.get(user=student)
        enrollment = Enrollment.objects.get(student=profile, career=career, period=periods["2026-2"])
        coordinator = User.objects.get(username="demo.coordinador01")
        regulation = Regulation.objects.get(career=career, version=1)
        course_objects = {code: Course.objects.get(career=career, code=code) for code, _name, _credits in courses}

        # Current-period grades complete the active transcript and support verified reporting.
        grades = {"INF101": 86, "MAT101": 78, "SIS101": 90, "INF102": 82, "MET201": 91}
        for code, value in grades.items():
            offering = CourseOffering.objects.get(course=course_objects[code], period=periods["2026-2"], group_code="A")
            GradeRecord.objects.get_or_create(enrollment=enrollment, offering=offering, defaults={
                "grade_value": Decimal(value), "scale_snapshot": periods["2026-2"].grade_scale,
                "pass_threshold_snapshot": periods["2026-2"].pass_threshold,
                "status": GradeRecord.Status.VERIFIED, "source": "Registro académico del periodo",
                "source_reference": f"SIS-2026-2-{profile.student_number}-{code}",
                "recorded_by": actor, "verified_by": actor, "verified_at": timezone.now(),
            })

        # Approved activities bring Mateo's own SPD balance above the published scholarship threshold.
        merits = (
            ("contest_winner", "Reconocimiento en encuentro de programación", 32),
            ("research", "Colaboración en análisis de datos urbanos", 33),
            ("featured_project", "Proyecto destacado de automatización", 34),
            ("seminar", "Seminario de arquitectura de software", 35),
        )
        for code, title, day in merits:
            occurred_on = periods["2026-2"].starts_on + timedelta(days=day)
            if not Activity.objects.filter(enrollment=enrollment, occurred_on=occurred_on, title=title).exists():
                category = ActivityCategory.objects.get(regulation=regulation, code=code)
                record_verified_activity(
                    actor=coordinator, enrollment=enrollment, category=category, title=title,
                    description="Participación académica en actividades de investigación y desarrollo de software.",
                    occurred_on=occurred_on, source="Registro de actividad académica",
                )

        StudentProject.objects.get_or_create(enrollment=enrollment, title="Plataforma de seguimiento de consumo energético", defaults={
            "description": "Prototipo web para registrar mediciones, visualizar tendencias y comparar el consumo energético de ambientes universitarios.",
            "role": "Diseño del modelo de datos y desarrollo de visualizaciones", "started_on": periods["2026-2"].starts_on,
            "completed_on": periods["2026-2"].starts_on + timedelta(days=38),
            "status": DevelopmentRecord.Status.VALIDATED, "created_by": student,
            "validated_by": coordinator, "validated_at": timezone.now(),
        })
        StudentProject.objects.get_or_create(enrollment=enrollment, title="Asistente de consulta de material académico", defaults={
            "description": "Aplicación que organiza recursos de asignaturas y permite localizarlos por tema, curso y tipo de material.",
            "role": "Prototipado de interfaz y pruebas funcionales", "started_on": periods["2026-2"].starts_on + timedelta(days=20),
            "status": DevelopmentRecord.Status.IN_REVIEW, "created_by": student,
        })
        skills = (
            ("Python", "Avanzado", "Desarrollo de scripts, servicios web y procesamiento de datos.", DevelopmentRecord.Status.VALIDATED),
            ("Diseño de bases de datos", "Intermedio", "Modelado relacional y consultas SQL para aplicaciones académicas.", DevelopmentRecord.Status.VALIDATED),
            ("Desarrollo frontend", "Intermedio", "Construcción de interfaces web accesibles y adaptables.", DevelopmentRecord.Status.VALIDATED),
            ("Comunicación técnica", "Intermedio", "Documentación de decisiones y presentación de avances de proyectos.", DevelopmentRecord.Status.DECLARED),
        )
        for name, level, description, status_value in skills:
            defaults = {"proficiency_label": level, "description": description, "status": status_value, "created_by": student}
            if status_value == DevelopmentRecord.Status.VALIDATED:
                defaults.update({"validated_by": coordinator, "validated_at": timezone.now()})
            StudentSkill.objects.get_or_create(enrollment=enrollment, name=name, defaults=defaults)

        # A pending course record with an attached file gives the evidence workflow a student-side example.
        evidence_title = "Taller de investigación y análisis de datos"
        if not Activity.objects.filter(enrollment=enrollment, title=evidence_title).exists():
            from django.core.files.uploadedfile import SimpleUploadedFile
            evidence_path = Path(settings.BASE_DIR) / "output" / "pdf" / "constancia_curso_investigacion.pdf"
            if not evidence_path.is_file():
                raise CommandError(f"No se encontró el archivo de apoyo requerido: {evidence_path}")
            course_enrollment = CourseEnrollment.objects.get(
                enrollment=enrollment, offering__course=course_objects["MET201"], active=True,
            )
            submit_activity(
                user=student, enrollment=enrollment,
                category=ActivityCategory.objects.get(regulation=regulation, code="certified_course"),
                title=evidence_title,
                description="Taller de actualización en investigación aplicada y organización de datos académicos.",
                occurred_on=periods["2026-2"].starts_on + timedelta(days=50),
                source="Declaración de participación académica",
                uploaded_file=SimpleUploadedFile(evidence_path.name, evidence_path.read_bytes(), content_type="application/pdf"),
                course_enrollment=course_enrollment,
            )

        # Keep one current, explainable application tied to a persisted eligibility snapshot.
        version = OpportunityVersion.objects.filter(title="Beca de Investigación", careers=career, published_at__isnull=False).first()
        if version and not Application.objects.filter(version=version, enrollment=enrollment).exclude(status=Application.Status.WITHDRAWN).exists():
            result = evaluate_eligibility(version, enrollment)
            if result.overall_status == EligibilitySnapshot.Overall.ELIGIBLE:
                application = Application.objects.create(version=version, enrollment=enrollment, eligibility=result)
                record_event(actor=student, action="opportunity.application_submitted", obj=application,
                             scope_type="career", scope_id=career.pk,
                             reason="Postulación a convocatoria abierta", safe_metadata={"version": version.version_number,
                                                                                         "eligibility": result.overall_status})

    def _seed_jury_walkthrough(self, actor, career, periods, courses):
        """Prepare a single coherent presentation path without altering module permissions."""
        from pathlib import Path
        from django.conf import settings
        from django.core.files import File
        from apps.activities.models import EvidenceFile, Regulation
        from apps.activities.models import Activity as SPDActivity
        from apps.academics.models import CourseEnrollment

        coordinator = User.objects.get(username="demo.coordinador01")
        valeria = User.objects.get(username="demo.estudiante05")
        profile = StudentProfile.objects.get(user=valeria)
        enrollment = Enrollment.objects.get(student=profile, career=career, period=periods["2026-2"])
        regulation = Regulation.objects.get(career=career, version=1, published=True)
        current_courses = {row[0]: Course.objects.get(career=career, code=row[0]) for row in courses}

        # Four already approved merits make the next 10-point validation cross 100 exactly.
        starting_merits = (
            ("contest_winner", "Primer lugar en concurso de programación", 20),
            ("featured_project", "Proyecto destacado de automatización", 21),
            ("improved_performance", "Mejora del rendimiento académico", 22),
            ("collaboration", "Colaboración en el proyecto de laboratorio", 23),
        )
        for code, title, day in starting_merits:
            if Activity.objects.filter(enrollment=enrollment, title=title).exists():
                continue
            category = ActivityCategory.objects.get(regulation=regulation, code=code)
            record_verified_activity(
                actor=coordinator, enrollment=enrollment, category=category,
                title=title, description="Participación académica registrada en Ingeniería de Sistemas.",
                occurred_on=periods["2026-2"].starts_on + timedelta(days=day),
                source="Constancia de participación académica",
            )
        # Prepare a pending certified-course activity with a local supporting file.
        # The assigned offering allows Patricia to review it through normal permissions.
        pending_title = "Curso certificado de investigación aplicada"
        pending_activity = SPDActivity.objects.filter(enrollment=enrollment, title=pending_title).first()
        if not pending_activity:
            course_enrollment = CourseEnrollment.objects.get(
                enrollment=enrollment, offering__course=current_courses["MET201"], active=True,
            )
            category = ActivityCategory.objects.get(regulation=regulation, code="certified_course")
            evidence_path = Path(settings.BASE_DIR) / "output" / "pdf" / "constancia_curso_investigacion.pdf"
            if not evidence_path.is_file():
                raise CommandError(f"No se encontró el archivo de apoyo requerido: {evidence_path}")
            pending_activity = submit_activity(
                user=valeria, enrollment=enrollment, category=category, title=pending_title,
                description="Curso de actualización en investigación aplicada y gestión de datos, con una duración de 12 horas.",
                occurred_on=periods["2026-2"].starts_on + timedelta(days=30),
                source="Declaración de participación académica",
                uploaded_file=SimpleUploadedFile(
                    evidence_path.name, evidence_path.read_bytes(), content_type="application/pdf",
                ), course_enrollment=course_enrollment,
            )
        if not pending_activity.files.exists():
            evidence_path = Path(settings.BASE_DIR) / "output" / "pdf" / "constancia_curso_investigacion.pdf"
            if not evidence_path.is_file():
                raise CommandError(f"No se encontró el archivo de apoyo requerido: {evidence_path}")
            with evidence_path.open("rb") as source:
                evidence = EvidenceFile(
                    activity=pending_activity, original_name="constancia_curso_investigacion.pdf",
                    content_type="application/pdf", size=evidence_path.stat().st_size, uploaded_by=valeria,
                )
                evidence.file.save("constancia_curso_investigacion.pdf", File(source), save=True)

        grade_values = {"INF101": "84", "MAT101": "88", "SIS101": "91", "INF102": "86", "MET201": "89"}
        for code, value in grade_values.items():
            offering = CourseOffering.objects.get(course=current_courses[code], period=periods["2026-2"], group_code="A")
            GradeRecord.objects.get_or_create(
                enrollment=enrollment, offering=offering,
                defaults={
                    "grade_value": Decimal(value), "scale_snapshot": periods["2026-2"].grade_scale,
                    "pass_threshold_snapshot": periods["2026-2"].pass_threshold,
                    "status": GradeRecord.Status.VERIFIED, "source": "Registro académico del periodo",
                    "source_reference": f"SIS-2026-2-{profile.student_number}-{code}",
                    "recorded_by": actor, "verified_by": actor, "verified_at": timezone.now(),
                },
            )

        StudentProject.objects.get_or_create(
            enrollment=enrollment, title="Sistema de análisis de datos urbanos",
            defaults={
                "description": "Herramienta para organizar y analizar indicadores urbanos para un proyecto de investigación.",
                "role": "Análisis de datos y desarrollo del prototipo", "started_on": periods["2026-2"].starts_on,
                "status": DevelopmentRecord.Status.VALIDATED, "created_by": valeria,
                "validated_by": coordinator, "validated_at": timezone.now(),
            },
        )
        # Create this version as a draft so the jury sees a real publication action.
        opportunity_title = "Beca de Investigación Aplicada"
        version = OpportunityVersion.objects.filter(title=opportunity_title, careers=career).first()
        if not version:
            opportunity = Opportunity.objects.create(owner=coordinator, created_by=coordinator, status=Opportunity.Status.DRAFT)
            now = timezone.now()
            version = OpportunityVersion.objects.create(
                opportunity=opportunity, version_number=1, title=opportunity_title,
                kind=OpportunityVersion.Kind.SCHOLARSHIP,
                description="Apoyo a proyectos estudiantiles de investigación aplicada y análisis de datos.",
                benefits="Acompañamiento metodológico y acceso al laboratorio de innovación.",
                application_instructions="Presenta tu postulación desde UPEA Talent+ y consulta su estado en esta sección.",
                opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=45), capacity=2,
            )
            version.careers.set([career])
        requirements = (
            ("average", "gte", Decimal("70"), "Promedio simple verificado mínimo", ""),
            ("own_points", "gte", Decimal("100"), "Puntos propios SPD mínimos", ""),
            ("validated_project", "exists", None, "Proyecto validado", ""),
            ("approved_course", "exists", None, "Metodología de la Investigación aprobada", "MET201"),
        )
        for order, (field, operator, target, label, course_code) in enumerate(requirements):
            OpportunityRequirement.objects.get_or_create(
                version=version, field_code=field, course_code=course_code,
                defaults={"operator": operator, "target_number": target, "display_label": label, "sort_order": order},
            )

        # A separate course campaign carries only anonymous answers; the active INF101 campaign remains usable.
        evaluation_offering = CourseOffering.objects.get(
            course=current_courses["SIS101"], period=periods["2026-2"], group_code="A",
        )
        campaign_title = "Experiencia académica en Ingeniería de Sistemas"
        campaign = EvaluationCampaign.objects.filter(offering=evaluation_offering, title=campaign_title).first()
        if not campaign:
            campaign = create_evaluation_campaign(
                actor=coordinator, offering_id=evaluation_offering.pk, title=campaign_title,
                opens_at=timezone.now() - timedelta(days=1), closes_at=timezone.now() + timedelta(days=365),
                minimum_responses=5,
            )
            campaign = publish_evaluation_campaign(actor=coordinator, campaign_id=campaign.pk)
        elif campaign.status == EvaluationCampaign.Status.DRAFT:
            campaign = publish_evaluation_campaign(actor=coordinator, campaign_id=campaign.pk)
        if campaign.status == EvaluationCampaign.Status.OPEN:
            score_rows = (
                (4, 4, 4, 3, 4, 5, 4), (4, 3, 4, 4, 4, 4, 5),
                (5, 4, 4, 3, 4, 4, 4), (3, 4, 4, 5, 3, 5, 4),
                (4, 5, 3, 4, 5, 3, 5),
            )
            students = list(User.objects.filter(username__in=[f"demo.estudiante0{i}" for i in range(1, 6)]).order_by("username"))
            for target in campaign.targets.all():
                for index, student in enumerate(students):
                    eligibility = EvaluationEligibility.objects.filter(target=target, enrollment__student__user=student).first()
                    if eligibility and not eligibility.answered:
                        submit_ballot(
                            actor=student, target_id=target.pk,
                            response={code: score_rows[index][position] for position, (code, _label) in enumerate(QUESTIONS)},
                        )
            close_campaign(actor=coordinator, campaign_id=campaign.pk, reason="Cierre para publicar resultados agregados.")
            publish_evaluation_results(actor=coordinator, campaign_id=campaign.pk)
        elif campaign.status == EvaluationCampaign.Status.CLOSED:
            publish_evaluation_results(actor=coordinator, campaign_id=campaign.pk)

        opportunity_count = OpportunityVersion.objects.filter(title=opportunity_title, careers=career).count()
        if opportunity_count != 1:
            raise CommandError("La beca de investigación aplicada debe tener una sola versión para la carrera.")
        if not campaign.aggregates.filter(response_count__gte=5).exists():
            counts = list(campaign.aggregates.values_list("response_count", flat=True))
            raise CommandError(f"La evaluación {campaign.status} no alcanzó el mínimo de privacidad; respuestas agregadas: {counts}.")

    def _seed_support(self, actor, career, periods, courses):
        coordinator = User.objects.get(username="demo.coordinador01")
        rule, _ = SupportRuleVersion.objects.get_or_create(career=career,
            indicator=SupportRuleVersion.Indicator.VERIFIED_AVERAGE_DECLINE, version=1,
            defaults={"valid_from": periods["2026-1"], "threshold_points": Decimal("10"),
                      "minimum_verified_courses": 3, "active": True, "created_by": coordinator,
                      "published_at": timezone.now()})
        if not rule.active:
            SupportRuleVersion.objects.filter(career=career, indicator=rule.indicator, active=True).update(active=False)
            rule.active = True
            rule.save(update_fields=("active",))
        evaluate_active_rules(actor=coordinator, career=career)
        alert = SupportAlert.objects.filter(rule=rule, enrollment__student__student_number="SIS-2026-002").first()
        if alert:
            case, created_case = SupportCase.objects.get_or_create(alert=alert,
                defaults={"assigned_to": coordinator, "created_by": coordinator})
            if created_case:
                alert.status = SupportAlert.Status.CASE_OPEN
                alert.save(update_fields=("status",))
                SupportAction.objects.create(case=case, kind=SupportAction.Kind.ADVISING,
                    description="Reunión inicial para conversar sobre estrategias de estudio y acordar un plan de refuerzo en Programación.",
                    due_date=timezone.localdate() + timedelta(days=7), status="planned", recorded_by=coordinator)
