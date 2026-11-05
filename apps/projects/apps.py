# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ProjectsConfig(AppConfig):
    name = "apps.projects"
    label = "projects"
    verbose_name = "Projects"

    def ready(self):
        from apps.core import audit

        from . import models

        for model in (models.Project, models.ProjectType, models.ProjectProperty, models.ProjectMember,
                      models.ProjectParty, models.GatewayDecision, models.Milestone, models.ProjectTask,
                      models.ProjectNote, models.ProjectDocument):
            audit.register(model)

        def seed(sender, **kwargs):
            from django.db import connection

            if sender.label == "projects" and "projects_projecttype" in connection.introspection.table_names():
                from .workflow import ensure_types

                ensure_types()

        post_migrate.connect(seed, dispatch_uid="phaema_project_types", weak=False)
