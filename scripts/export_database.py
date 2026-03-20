"""
Export all swiss_cv_generator collections to JSON snapshots.

Snapshots are stored in data/swiss_cv_generator/ and committed to git so that
a new Codespace can import them instantly — without running AI generation scripts.

Usage:
    python scripts/export_database.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from bson import ObjectId

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from rich.console import Console
from rich.table import Table

console = Console()

SNAPSHOT_DIR = project_root / "data" / "swiss_cv_generator"

# Collections to export from the target DB
TARGET_COLLECTIONS = [
    "cantons",
    "demographic_config",
    "first_names",
    "last_names",
    "companies",
    "occupation_skills",
]


def bson_to_json(obj):
    """Convert BSON types to JSON-serializable format."""
    if isinstance(obj, ObjectId):
        return {"$oid": str(obj)}
    if isinstance(obj, datetime):
        return {"$date": obj.isoformat()}
    if isinstance(obj, dict):
        return {k: bson_to_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [bson_to_json(item) for item in obj]
    return obj


def export_collection(db, collection_name: str, output_path: Path) -> int:
    """Export a single collection to a JSON file. Returns document count."""
    docs = list(db[collection_name].find({}))
    serializable = bson_to_json(docs)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    return len(docs)


def main():
    console.print("[bold blue]Swiss CV Generator — Database Export[/bold blue]")
    console.print(f"Snapshot directory: [cyan]{SNAPSHOT_DIR}[/cyan]\n")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    db = get_db_manager()

    table = Table(title="Export results")
    table.add_column("Collection", style="cyan")
    table.add_column("Documents", justify="right")
    table.add_column("File size", justify="right")
    table.add_column("Status")

    total_docs = 0
    for coll in TARGET_COLLECTIONS:
        output_path = SNAPSHOT_DIR / f"{coll}.json"
        try:
            count = export_collection(db.target_db, coll, output_path)
            size_kb = output_path.stat().st_size / 1024
            table.add_row(coll, str(count), f"{size_kb:.0f} KB", "[green]✅ OK[/green]")
            total_docs += count
        except Exception as e:
            table.add_row(coll, "—", "—", f"[red]❌ {e}[/red]")

    console.print(table)
    console.print(f"\n[green]✅ Exported {total_docs} documents total[/green]")
    console.print(
        "\nCommit the [cyan]data/swiss_cv_generator/[/cyan] directory to git so new "
        "Codespaces can import instantly without AI generation."
    )


if __name__ == "__main__":
    main()
