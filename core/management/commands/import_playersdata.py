import csv
import os
from typing import Optional

from django.core.management.base import BaseCommand, CommandParser
from django.conf import settings

from core.models import Card

RENAMES = {
    "Name": "Name",
    "Rating": "Overall",
    "Position": "Position",
    "Club": "Club",
    "League": "League",
    "Country": "Nation",
    "Pace": "Pace",
    "Shooting": "Shooting",
    "Passing": "Passing",
    "Dribbling": "Dribbling",
    "Defending": "Defending",
    "Phyiscality": "Physical", 
    "SkillsMoves": "Skill Moves",
    "WeakFoot": "Weak Foot",
    "BaseStats": "Base Stats",
    "InGameStats": "In-Game Stats",
    "WorkRate": "Work Rate",
    "Height": "Height",
    "Revision": "Revision",
    "Popularity": "Popularity",
    "Price": "Price",
}


class Command(BaseCommand):
    help = "Import players CSV data into Card model"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--path",
            dest="path",
            default=settings.PLAYER_DATA_CSV_PATH,
            help="Path to the players CSV file",
        )
        parser.add_argument(
            "--id-column",
            dest="id_column",
            default=settings.PLAYER_DATA_ID_COLUMN,
            help="Column name that uniquely identifies a card (e.g., 'sofifa_id')",
        )
        parser.add_argument(
            "--name-column",
            dest="name_column",
            default=None,
            help="Optional column to use as display name (e.g., 'short_name' or 'name')",
        )
        parser.add_argument(
            "--id-composite",
            dest="id_composite",
            default=None,
            help="Comma-separated list of columns to combine as a unique external_id when a single ID column is absent",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete existing Card rows before import",
        )

    def handle(self, *args, **options):
        path: str = options["path"]
        id_col: str = options["id_column"]
        id_composite_opt = options["id_composite"]
        name_col: Optional[str] = options["name_column"]
        truncate: bool = options["truncate"]

        if not os.path.exists(path):
            self.stderr.write(self.style.ERROR(f"CSV not found: {path}"))
            return

        if not truncate and Card.objects.exists():
            self.stdout.write(self.style.WARNING("Database already seeded. Use --truncate to re-seed."))
            return

        if truncate:
            Card.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing Card rows deleted."))

        created = 0
        updated = 0

        with open(path, mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            # Prepare composite columns if provided
            composite_cols = None
            if id_composite_opt:
                composite_cols = [c.strip() for c in str(id_composite_opt).split(",") if c.strip()]
                # Validate presence (we'll warn but still proceed, skipping rows missing values)
                missing = [c for c in composite_cols if c not in fieldnames]
                if missing:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Composite ID columns missing in headers: {missing}; present headers: {fieldnames}"
                        )
                    )

            if id_col and id_col not in fieldnames:

                id_candidates = [id_col, "ID", "id", "sofifa_id", "player_id"]
                detected = next((c for c in id_candidates if c in fieldnames), None)
                if detected:
                    self.stdout.write(self.style.WARNING(f"ID column '{id_col}' not found; using '{detected}' from headers."))
                    id_col = detected
                else:
                    self.stderr.write(
                        self.style.WARNING(
                            f"ID column '{id_col}' not in CSV headers: {fieldnames}. Will use composite or row index."
                        )
                    )

            if not name_col:
                for candidate in ("Name",):
                    if candidate in fieldnames:
                        name_col = candidate
                        break

            row_idx = 0
            for row in reader:
                row_idx += 1
                ext_id = str(row.get(id_col) or "").strip()
                if not ext_id:

                    if composite_cols:
                        parts = []
                        for c in composite_cols:
                            v = row.get(c)
                            if v is None:
                                parts = []
                                break
                            parts.append(f"{c}:{str(v).strip()}")
                        if parts:
                            ext_id = "|".join(parts)
                            
                    if not ext_id:
                        ext_id = f"row:{row_idx}"
                name_val = None
                if name_col:
                    v = row.get(name_col)
                    if v is not None:
                        name_val = str(v)

                data_out = {}
                for k, v in row.items():
                    key = RENAMES.get(str(k), str(k))
                    data_out[key] = "" if v is None else str(v)

                obj, is_created = Card.objects.update_or_create(
                    external_id=ext_id,
                    defaults={
                        "name": name_val,
                        "data": data_out,
                    },
                )
                if is_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Created: {created}, Updated: {updated}."
            )
        )
