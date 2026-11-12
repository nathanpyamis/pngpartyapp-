from rest_framework.permissions import BasePermission

from apps.accounts.models import User

from .models import Member


def members_visible_to(user):
    """Single source of truth for RBAC scoping of member records."""
    qs = Member.objects.select_related("electorate__province")
    if not user.is_authenticated:
        return qs.none()
    if user.is_exec:
        return qs
    if user.role == User.Role.COORDINATOR:
        return qs.filter(electorate__province_id=user.assigned_province_id)
    if user.role == User.Role.AGENT:
        return qs.filter(registered_by=user)
    return qs.none()


def can_register_in(user, electorate) -> bool:
    if user.is_exec:
        return True
    if user.role == User.Role.COORDINATOR:
        return electorate.province_id == user.assigned_province_id
    if user.role == User.Role.AGENT:
        return electorate.pk == user.assigned_electorate_id
    return False


class CanRegisterMembers(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in User.Role.values


class IsCoordinatorOrExec(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_exec or u.role == User.Role.COORDINATOR)
