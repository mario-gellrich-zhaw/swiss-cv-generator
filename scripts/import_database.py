"""
Import swiss_cv_generator collections from JSON snapshots.

Reads from data/swiss_cv_generator/ and populates the target MongoDB database.
This replaces the need to run AI generation scripts on new Codespace creation.

Usage:
    python scripts/import_database.py              # skip collections that already have data
    python scripts/import_database.py --force      # drop and reimport all collections
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo.errors import BulkWriteError

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from rich.console import Console
from rich.table import Table

console = Console()

SNAPSHOT_DIR = project_root / "data" / "swiss_cv_generator"

TARGET_COLLECTIONS = [
    "cantons",
    "demographic_config",
    "first_names",
    "last_names",
    "companies",
    "occupation_skills",
]


def json_to_bson(obj: Any) -> Any:
    """Convert JSON-serialized BSON types back to Python/BSON objects."""
    if isinstance(obj, dict):
        if "$oid" in obj and len(obj) == 1:
            return ObjectId(obj["$oid"])
        return {k: json_to_bson(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_to_bson(item) for item in obj]
    return obj


def import_collection(db, collection_name: str, snapshot_path: Path, force: bool) -> tuple[int, str]:
    """
    Import one collection from its snapshot.

    Returns (document_count, status_message).
    """
    if not snapshot_path.exists():
        return 0, "⚠ no snapshot file"

    existing = db[collection_name].count_documents({})
    if existing > 0 and not force:
        return existing, f"skipped ({existing} docs already present)"

    with open(snapshot_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    docs = json_to_bson(raw)
    if not docs:
        return 0, "⚠ snapshot is empty"

    if force and existing > 0:
        db[collection_name].drop()

    try:
        result = db[collection_name].insert_many(docs, ordered=False)
        count = len(result.inserted_ids)
    except BulkWriteError as e:
        count = len(e.details.get("insertedIds", []))

    return count, "✅ imported"


def main():
    parser = argparse.ArgumentParser(description="Import swiss_cv_generator DB from snapshots")
    parser.add_argument("--force", action="store_true",
                        help="Drop and reimport even if collections already have data")
    args = parser.parse_args()

    if not SNAPSHOT_DIR.exists():
        console.print(f"[red]❌ Snapshot directory not found: {SNAPSHOT_DIR}[/red]")
        console.print("Run [cyan]python scripts/export_database.py[/cyan] first.")
        sys.exit(1)

    console.print("[bold blue]Swiss CV Generator — Database Import[/bold blue]")
    console.print(f"Snapshot directory: [cyan]{SNAPSHOT_DIR}[/cyan]")
    if args.force:
        console.print("[yellow]--force: existing collections will be dropped and reimported[/yellow]")
    console.print()

    db = get_db_manager()

    table = Table(title="Import results")
    table.add_column("Collection", style="cyan")
    table.add_column("Documents", justify="right")
    table.add_column("Status")

    total = 0
    all_ok = True
    for coll in TARGET_COLLECTIONS:
        snapshot = SNAPSHOT_DIR / f"{coll}.json"
        try:
            count, status = import_collection(db.target_db, coll, snapshot, args.force)
            table.add_row(coll, str(count) if count else "—", status)
            total += count
        except Exception as e:
            table.add_row(coll, "—", f"[red]❌ {e}[/red]")
            all_ok = False

    console.print(table)
    console.print(f"\n[green]✅ {total} documents available in swiss_cv_generator[/green]")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
