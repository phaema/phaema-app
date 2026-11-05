# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who can see and change a project.

See:        everyone with a role, except confidential projects, which only administrators, the lead and the team see.
Create:     administrators and surveyors.
Manage:     administrators, the lead, and team members whose role lets them change records (Surveyors).
Contribute: anyone who can manage, plus any team member (for example a legal contributor): notes and documents.
"""
from django.db.models import Q

from apps.core.roles import ADMINISTRATORS, SURVEYORS, has_role, is_administrator, role_of


def visible(user, qs=None):
    from .models import Project

    qs = qs if qs is not None else Project.objects.all()
    if not has_role(user):
        return qs.none()
    if is_administrator(user):
        return qs
    return qs.filter(Q(confidential=False) | Q(lead=user) | Q(members__user=user)).distinct()


def can_see(user, project):
    if not has_role(user):
        return False
    return (not project.confidential or is_administrator(user) or project.lead_id == user.pk
            or project.members.filter(user=user).exists())


def can_create(user):
    return role_of(user) in (ADMINISTRATORS, SURVEYORS)


def is_member(user, project):
    return project.lead_id == user.pk or project.members.filter(user=user).exists()


def can_manage(user, project):
    if is_administrator(user):
        return True
    return role_of(user) == SURVEYORS and is_member(user, project)


def can_contribute(user, project):
    return can_manage(user, project) or (has_role(user) and is_member(user, project))
