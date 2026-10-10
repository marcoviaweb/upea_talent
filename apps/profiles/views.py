from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.conf import settings

from apps.accounts.models import RoleAssignment
from apps.accounts.permissions import current_role_assignments, visible_course_enrollments
from apps.academics.models import CourseEnrollment, CourseOffering, GradeRecord

from .forms import DevelopmentReviewForm, StudentProjectForm, StudentSkillForm
from .models import DevelopmentRecord, StudentProject, StudentSkill
from .services import (
    enrollment_for_actor,
    review_development_record,
    save_development_record,
    student_enrollments,
)


RECORD_TYPES = {"project": StudentProject, "skill": StudentSkill}
RECORD_FORMS = {"project": StudentProjectForm, "skill": StudentSkillForm}


def frontend_app(request, *args, **kwargs):
    return render(request, "profiles/spa.html", {"frontend_dev_server": settings.FRONTEND_DEV_SERVER})


def assigned_teacher_offerings(user):
    group_ids = current_role_assignments(user).filter(
        scope=RoleAssignment.Scope.GROUP,
        role__in=(RoleAssignment.Role.TEACHER, RoleAssignment.Role.EVIDENCE_REVIEWER),
    ).values("group_id")
    today = timezone.localdate()
    return CourseOffering.objects.filter(
        pk__in=group_ids,
        teaching_assignments__user=user,
        teaching_assignments__active=True,
        teaching_assignments__starts_on__lte=today,
    ).filter(
        models_q_assignment_end()
    ).annotate(student_count=Count("roster", filter=Q(roster__active=True, roster__enrollment__status="active"))).select_related(
        "course__career", "period"
    ).distinct()


def models_q_assignment_end():
    from django.db.models import Q
    return Q(teaching_assignments__ends_on__isnull=True) | Q(teaching_assignments__ends_on__gte=timezone.localdate())


@login_required
def trajectory_home(request):
    enrollments = student_enrollments(request.user)
    offerings = assigned_teacher_offerings(request.user)
    if not enrollments.exists() and not offerings.exists():
        raise PermissionDenied("Tu cuenta no tiene una matrícula estudiantil ni grupos docentes vigentes.")
    return render(request, "profiles/trajectory_home.html", {
        "enrollments": enrollments,
        "offerings": offerings,
        "show_groups": offerings.exists(),
    })


@login_required
def group_roster(request, offering_id):
    offering = get_object_or_404(assigned_teacher_offerings(request.user), pk=offering_id)
    roster = visible_course_enrollments(request.user).filter(offering=offering).select_related(
        "enrollment__student__user", "enrollment__career", "enrollment__period"
    ).order_by("enrollment__student__user__last_name", "enrollment__student__user__first_name")
    return render(request, "profiles/group_roster.html", {"offering": offering, "roster": roster})


@login_required
def enrollment_profile(request, enrollment_id):
    enrollment = enrollment_for_actor(request.user, enrollment_id)
    projects = StudentProject.objects.filter(enrollment=enrollment).select_related("validated_by", "created_by")
    skills = StudentSkill.objects.filter(enrollment=enrollment).select_related("validated_by", "created_by")
    grades = GradeRecord.objects.filter(enrollment=enrollment, status=GradeRecord.Status.VERIFIED).select_related(
        "offering__course", "offering__period", "verified_by"
    )
    from .services import validated_development_counts
    development_counts = validated_development_counts(enrollment)
    average = None
    if grades.exists():
        values = list(grades.values_list("grade_value", flat=True))
        average = (sum(values) / Decimal(len(values))).quantize(Decimal("0.01"))
    is_owner = enrollment.student.user_id == request.user.pk and student_enrollments(request.user).filter(pk=enrollment.pk).exists()
    course_rows = CourseEnrollment.objects.filter(enrollment=enrollment, active=True).select_related("offering__course", "offering__period")
    return render(request, "profiles/enrollment_profile.html", {
        "enrollment": enrollment,
        "projects": projects,
        "skills": skills,
        "grades": grades,
        "average": average,
        "is_owner": is_owner,
        "course_rows": course_rows,
        "validated_project_count": development_counts["projects"],
        "validated_skill_count": development_counts["skills"],
    })


@login_required
def development_form(request, enrollment_id, record_type, record_id=None):
    form_class = RECORD_FORMS.get(record_type)
    if not form_class:
        raise PermissionDenied("Tipo de registro no admitido.")
    enrollment = enrollment_for_actor(request.user, enrollment_id)
    if enrollment.student.user_id != request.user.pk or not student_enrollments(request.user).filter(pk=enrollment.pk).exists():
        raise PermissionDenied("Solo puedes editar el desarrollo de tu propia trayectoria.")
    if enrollment.status != enrollment.Status.ACTIVE:
        raise PermissionDenied("La matrícula está cerrada y solo permite consulta histórica.")
    model = RECORD_TYPES[record_type]
    instance = None
    if record_id:
        instance = get_object_or_404(model, pk=record_id, enrollment=enrollment)
        if instance.status not in {DevelopmentRecord.Status.DECLARED, DevelopmentRecord.Status.NEEDS_CHANGES}:
            raise PermissionDenied("El registro ya está enviado o validado y no se puede editar.")
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        submit = request.POST.get("intent") == "submit"
        try:
            save_development_record(actor=request.user, enrollment=enrollment, record=record, submit=submit)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Enviado a revisión." if submit else "Borrador guardado.")
            return redirect("profiles:enrollment-profile", enrollment_id=enrollment.pk)
    if form.errors:
        form.first_error_field = None
        for field_name in form.errors:
            if field_name == "__all__":
                continue
            field = form[field_name]
            attrs = field.field.widget.attrs
            attrs["aria-invalid"] = "true"
            error_id = f"{field.id_for_label}-error"
            attrs["aria-describedby"] = " ".join(filter(None, (attrs.get("aria-describedby"), error_id)))
            if form.first_error_field is None:
                form.first_error_field = field_name
    return render(request, "profiles/development_form.html", {
        "form": form,
        "enrollment": enrollment,
        "record_type": record_type,
        "editing": bool(instance),
    })


@login_required
@require_POST
def review_development(request, record_type, record_id):
    model = RECORD_TYPES.get(record_type)
    if not model:
        raise PermissionDenied("Tipo de registro no admitido.")
    record = get_object_or_404(model.objects.select_related("enrollment__student__user"), pk=record_id)
    # Check scope before returning even form errors or a redirect containing the enrollment ID.
    enrollment_for_actor(request.user, record.enrollment_id)
    form = DevelopmentReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Selecciona una decisión y, si solicitas cambios, explica qué falta.")
        return redirect("profiles:enrollment-profile", enrollment_id=record.enrollment_id)
    try:
        review_development_record(
            actor=request.user,
            record=record,
            outcome=form.cleaned_data["outcome"],
            note=form.cleaned_data["note"],
        )
    except PermissionDenied as exc:
        raise Http404("Declaración no encontrada.") from exc
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("profiles:enrollment-profile", enrollment_id=record.enrollment_id)
    messages.success(request, "Declaración validada." if form.cleaned_data["outcome"] == "approve" else "Se solicitó una corrección al estudiante.")
    return redirect("profiles:enrollment-profile", enrollment_id=record.enrollment_id)
