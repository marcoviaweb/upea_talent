from datetime import date
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
            sample_accounts = self._seed_trajectory(actor, institution, career, period_objects, courses)
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo ficticio listo: {institution.short_name}, {career.code}, "
            f"{len(period_objects)} periodos, {len(courses)} asignaturas y {len(courses) * len(period_objects)} grupos; "
            f"{sample_accounts} cuentas sintéticas de trayectoria."
        ))
        if not actor:
            self.stdout.write(self.style.WARNING(
                "Para generar estudiantes/docente ficticios y sus asignaciones, crea un superusuario y vuelve a ejecutar seed_demo."
            ))
        else:
            self.stdout.write("Cuentas sintéticas sin contraseña: demo.estudiante01–03 y demo.docente01. Asigna claves locales con `manage.py changepassword <usuario>`.")

    def _seed_trajectory(self, actor, institution, career, periods, courses):
        previous_period = periods["2026-1"]
        current_period = periods["2026-2"]
        student_specs = [
            ("demo.estudiante01", "Andrea", "Ejemplo", "DEMO-SIS-001"),
            ("demo.estudiante02", "Mateo", "Ficticio", "DEMO-SIS-002"),
            ("demo.estudiante03", "Lucía", "Muestra", "DEMO-SIS-003"),
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

        previous_enrollments = [enrollment for _user, _profile, enrollment, period in students if period.pk == previous_period.pk]
        grade_values = ([Decimal("84"), Decimal("78"), Decimal("91"), Decimal("88")],
                        [Decimal("73"), Decimal("82"), Decimal("76"), Decimal("80")],
                        [Decimal("92"), Decimal("86"), Decimal("89"), Decimal("94")])
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

        primary_user, _profile, current_enrollment, _period = students[1]
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
        return len(student_specs) + 1
