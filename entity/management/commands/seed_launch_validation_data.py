from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from Authentication.models import User
from entity.launch_seed import LaunchSeedService
from entity.models import Entity


class Command(BaseCommand):
    help = "Seed idempotent launch-validation master data for stage/browser test runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity-id",
            action="append",
            type=int,
            default=[],
            help="Entity id to seed. Repeat for multiple entities.",
        )
        parser.add_argument(
            "--entity-name",
            action="append",
            default=[],
            help="Entity name to seed, case-insensitive. Repeat for multiple entities.",
        )
        parser.add_argument(
            "--all-entities",
            action="store_true",
            help="Seed launch fixtures for every active entity.",
        )
        parser.add_argument(
            "--geography-only",
            action="store_true",
            help="Only seed India state/district/city launch geography.",
        )
        parser.add_argument(
            "--skip-entity-bootstrap",
            action="store_true",
            help="Skip standard entity bootstrap repair and only add launch-specific entity fixtures.",
        )
        parser.add_argument(
            "--actor-email",
            default=None,
            help="Optional user email to stamp as createdby/actor for seeded rows.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes inside a transaction and roll them back.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output.",
        )

    def handle(self, *args, **options):
        actor = self._resolve_actor(options.get("actor_email"))
        entities = [] if options["geography_only"] else self._resolve_entities(options)
        summary = LaunchSeedService.seed(
            entities=entities,
            actor=actor,
            dry_run=options["dry_run"],
            include_entity_bootstrap=not options["skip_entity_bootstrap"],
        )

        if options["json"]:
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True, default=str))
            return

        self.stdout.write(self.style.SUCCESS("Launch validation seed complete."))
        self.stdout.write(f"dry_run: {summary['dry_run']}")
        self.stdout.write(f"geography: {summary['geography']}")
        if not summary["entities"]:
            self.stdout.write("entities: none")
        for row in summary["entities"]:
            self.stdout.write(
                f"entity {row['entity_id']} - {row['entity_name']}: "
                f"product={row['product']['productname']} customers={len(row['customers'])} "
                f"godown={row['godown']['code']}"
            )

    def _resolve_actor(self, actor_email):
        if not actor_email:
            return None
        actor = User.objects.filter(email__iexact=actor_email).first()
        if actor is None:
            raise CommandError(f"Actor user '{actor_email}' was not found.")
        return actor

    def _resolve_entities(self, options):
        if options["all_entities"]:
            return list(Entity.objects.filter(isactive=True).order_by("id"))

        resolved = []
        seen_ids = set()
        for entity_id in options["entity_id"]:
            entity = Entity.objects.filter(pk=entity_id).first()
            if entity is None:
                raise CommandError(f"Entity id '{entity_id}' was not found.")
            if entity.id not in seen_ids:
                resolved.append(entity)
                seen_ids.add(entity.id)

        for entity_name in options["entity_name"]:
            matches = list(Entity.objects.filter(entityname__iexact=entity_name).order_by("id"))
            if not matches:
                raise CommandError(f"Entity '{entity_name}' was not found.")
            if len(matches) > 1:
                ids = ", ".join(str(row.id) for row in matches)
                raise CommandError(f"Entity name '{entity_name}' matched multiple ids: {ids}. Use --entity-id.")
            entity = matches[0]
            if entity.id not in seen_ids:
                resolved.append(entity)
                seen_ids.add(entity.id)
        return resolved
