from django.db.models import Q
from django.utils import timezone

from apps.academics.models import CourseEnrollment, TeachingAssignment
from .models import RoleAssignment


def current_role_assignments(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return RoleAssignment.objects.none()
    today = timezone.localdate()
    return RoleAssignment.objects.filter(
        user=user, active=True, starts_at__lte=today,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=today))


def visible_course_enrollments(user):
    """Return roster rows the actor may access. IDs supplied by clients never expand this set."""
    roles = current_role_assignments(user)
    career_ids = roles.filter(
        scope="career", role__in=(RoleAssignment.Role.COORDINATOR, RoleAssignment.Role.CAREER_ADMIN)
    ).values("career_id")
    assigned_teacher_groups = TeachingAssignment.objects.filter(
        user=user, role=TeachingAssignment.AssignmentRole.TEACHER, active=True,
        starts_on__lte=timezone.localdate(),
    ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=timezone.localdate())).values("offering_id")
    assigned_reviewer_groups = TeachingAssignment.objects.filter(
        user=user, active=True, starts_on__lte=timezone.localdate(),
    ).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=timezone.localdate())).values("offering_id")
    teacher_group_ids = roles.filter(
        scope="group", role=RoleAssignment.Role.TEACHER, group_id__in=assigned_teacher_groups
    ).values("group_id")
    reviewer_group_ids = roles.filter(
        scope="group", role=RoleAssignment.Role.EVIDENCE_REVIEWER, group_id__in=assigned_reviewer_groups
    ).values("group_id")
    student_career_ids = roles.filter(scope="career", role=RoleAssignment.Role.STUDENT).values("career_id")

    visible = Q(enrollment__career_id__in=career_ids)
    visible |= Q(offering_id__in=teacher_group_ids, offering__teaching_assignments__user=user,
                 offering__teaching_assignments__role=TeachingAssignment.AssignmentRole.TEACHER,
                 offering__teaching_assignments__active=True,
                 offering__teaching_assignments__starts_on__lte=timezone.localdate()) & (
                     Q(offering__teaching_assignments__ends_on__isnull=True)
                     | Q(offering__teaching_assignments__ends_on__gte=timezone.localdate())
                 )
    visible |= Q(offering_id__in=reviewer_group_ids, offering__teaching_assignments__user=user,
                 offering__teaching_assignments__active=True,
                 offering__teaching_assignments__starts_on__lte=timezone.localdate()) & (
                     Q(offering__teaching_assignments__ends_on__isnull=True)
                     | Q(offering__teaching_assignments__ends_on__gte=timezone.localdate())
                 )
    visible |= Q(enrollment__student__user=user, enrollment__career_id__in=student_career_ids)
    return CourseEnrollment.objects.filter(active=True, enrollment__status="active").filter(visible).distinct()


def can_access_course_enrollment(user, course_enrollment_id):
    return visible_course_enrollments(user).filter(pk=course_enrollment_id).exists()
