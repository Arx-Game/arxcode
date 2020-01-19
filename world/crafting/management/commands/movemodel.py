# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import io
import os
import sys

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import migrations
from django.db.migrations import Migration
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState
from django.db.migrations.writer import MigrationWriter


# noinspection PyAttributeOutsideInit
# noinspection PyProtectedMember
class Command(BaseCommand):
    help = 'Moves a model from one app to another'

    def add_arguments(self, parser):
        parser.add_argument('model_name', nargs='?')
        parser.add_argument('source_app', nargs='?')
        parser.add_argument('dest_app', nargs='?')

    def handle(self, *args, **options):
        self.model_name = options[str('model_name')]
        self.source_app = options[str('source_app')]
        self.dest_app = options[str('dest_app')]

        # make sure the apps exist
        app_labels = {self.source_app, self.dest_app}
        bad_app_labels = set()
        for app_label in app_labels:
            try:
                apps.get_app_config(app_label)
            except LookupError:
                bad_app_labels.add(app_label)
        if bad_app_labels:
            for app_label in bad_app_labels:
                self.stderr.write(self.style.ERROR(
                    "App '{}' could not be found. Is it in INSTALLED_APPS?".format(app_label)
                ))
            sys.exit(2)

        if len(app_labels) == 1:
            self.stderr.write(self.style.ERROR(
                "Cannot move '{}' within the same app '{}'.".format(self.model_name, self.dest_app)
            ))
            sys.exit(2)

        # load the current graph
        loader = MigrationLoader(None, ignore_no_migrations=True)

        questioner = NonInteractiveMigrationQuestioner()

        self.from_state = loader.project_state()
        self.to_state = ProjectState.from_apps(apps)

        autodetector = MigrationAutodetector(
            self.from_state,
            self.to_state,
            questioner,
        )

        _migrations = []
        rename_table = self._get_rename_table_migration()
        _migrations.append(rename_table)
        create_model = self._get_create_model_migration([
            (rename_table.app_label, rename_table.name),
        ])
        _migrations.append(create_model)
        model_fk = self._get_model_fk_migrations([
            (create_model.app_label, create_model.name),
        ])
        delete_model_deps = [
            (rename_table.app_label, rename_table.name),
            (create_model.app_label, create_model.name),
        ]
        for fk_migration in model_fk:
            _migrations.append(fk_migration)
            delete_model_deps.append(
                (fk_migration.app_label, fk_migration.name),
            )
        delete_model = self._get_delete_model_migration(delete_model_deps)
        _migrations.append(delete_model)

        changes = {}
        for migration in _migrations:
            changes.setdefault(migration.app_label, []).append(migration)
        changes = autodetector.arrange_for_graph(
            changes=changes,
            graph=loader.graph,
        )
        self.write_migration_files(changes)

        self.stdout.write(self.style.SUCCESS("Done!"))

    def _get_rename_table_migration(self, dependencies=None):
        dependencies = dependencies or []
        database_operations = []
        state_operations = []

        database_operations.append(
            migrations.AlterModelTable(
                self.model_name.lower(),
                '{}_{}'.format(self.dest_app, self.model_name.lower())
            )
        )

        migration = Migration('rename_table', self.source_app)
        migration.dependencies = dependencies
        migration.operations = [
            migrations.SeparateDatabaseAndState(
                database_operations=database_operations,
                state_operations=state_operations
            )
        ]
        return migration

    def _get_create_model_migration(self, dependencies=None):
        dependencies = dependencies or []
        database_operations = []
        state_operations = []

        model_state = self.to_state.models[self.dest_app, self.model_name.lower()]
        model_opts = self.to_state.apps.get_model(self.dest_app, self.model_name)._meta
        related_fields = {}
        for field in model_opts.local_fields:
            if field.remote_field:
                if field.remote_field.model:
                    if not field.remote_field.parent_link:
                        related_fields[field.name] = field
                if (getattr(field.remote_field, 'through', None) and
                        not field.remote_field.through._meta.auto_created):
                    related_fields[field.name] = field
        for field in model_opts.local_many_to_many:
            if field.remote_field.model:
                related_fields[field.name] = field
            if getattr(field.remote_field, 'through', None) and not field.remote_field.through._meta.auto_created:
                related_fields[field.name] = field

        state_operations.append(
            migrations.CreateModel(
                name=model_state.name,
                fields=[d for d in model_state.fields if d[0] not in related_fields],
                options=model_state.options,
                bases=model_state.bases,
                managers=model_state.managers,
            )
        )

        migration = Migration('create_model', self.dest_app)
        migration.dependencies = dependencies
        migration.operations = [
            migrations.SeparateDatabaseAndState(
                database_operations=database_operations,
                state_operations=state_operations,
            )
        ]
        return migration

    def _get_model_fk_migrations(self, dependencies=None):
        dependencies = dependencies or []
        _migrations = []

        model_opts = self.to_state.apps.get_model(self.dest_app, self.model_name)._meta

        for field in model_opts.get_fields(include_hidden=True):
            if field.is_relation:
                operations = [migrations.AlterField(
                        model_name=field.related_model._meta.model_name,
                        name=field.remote_field.name,
                        field=field.remote_field,
                    )]
                migration = Migration('alter_model_fk', field.related_model._meta.app_label)
                migration.dependencies = dependencies
                migration.operations = operations

                _migrations.append(migration)

        return _migrations

    def _get_delete_model_migration(self, dependencies=None):
        dependencies = dependencies or []
        database_operations = []
        state_operations = [migrations.DeleteModel(name=self.model_name)]

        migration = Migration('delete_model', self.source_app)
        migration.dependencies = dependencies
        migration.operations = [
            migrations.SeparateDatabaseAndState(
                database_operations=database_operations,
                state_operations=state_operations,
            )
        ]
        return migration

    @staticmethod
    def write_migration_files(changes):
        directory_created = {}
        for app_label, app_migrations in changes.items():
            for migration in app_migrations:
                writer = MigrationWriter(migration)
                migrations_directory = os.path.dirname(writer.path)
                if not directory_created.get(app_label):
                    if not os.path.isdir(migrations_directory):
                        os.mkdir(migrations_directory)
                    init_path = os.path.join(migrations_directory, '__init__.py')
                    if not os.path.isfile(init_path):
                        io.open(init_path, 'w').close()
                    directory_created[app_label] = True
                migration_string = writer.as_string()
                with io.open(writer.path, 'w', encoding='utf-8') as fh:
                    fh.write(migration_string)
