"""
Migrate occupations from data/processed/occupations.json to MongoDB.

This script:
1. Loads occupations from data/processed/occupations.json
2. Transforms them to MongoDB documents
3. Upserts each occupation into the occupations collection
4. Adds created_at timestamp
5. Shows progress with rich progress bar

Run: python scripts/migrate_occupations_to_mongodb.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.console import Console
from rich.table import Table
from pymongo.errors import OperationFailure

console = Console()


def load_occupations(file_path: Path) -> list[Dict[str, Any]]:
    """
    Load occupations from JSON file.
    
    Args:
        file_path: Path to occupations.json file.
    
    Returns:
        List of occupation dictionaries.
    
    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file contains invalid JSON.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Occupations file not found: {file_path}")
    
    console.print(f"[cyan]Loading occupations from {file_path}...[/cyan]")
    
    with open(file_path, "r", encoding="utf-8") as f:
        occupations = json.load(f)
    
    console.print(f"[green]✅ Loaded {len(occupations)} occupations[/green]")
    return occupations


def transform_occupation(occ: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform occupation to MongoDB document format.
    
    Args:
        occ: Occupation dictionary from JSON.
    
    Returns:
        MongoDB document dictionary.
    """
    # Ensure all required fields are present
    document = {
        "id": occ.get("id", ""),
        "name_de": occ.get("name_de", ""),
        "name_fr": occ.get("name_fr") or None,
        "name_it": occ.get("name_it") or None,
        "description_de": occ.get("description_de", ""),
        "berufsfeld": occ.get("berufsfeld", ""),
        "branchen": occ.get("branchen", ""),
        "industry": occ.get("industry", "other"),
        "bildungstyp": occ.get("bildungstyp", ""),
        "swissdoc": occ.get("swissdoc", ""),
        "created_at": datetime.utcnow()
    }
    
    # Handle branchen as array if it's a string
    if isinstance(document["branchen"], str):
        # Split by comma if it contains multiple values
        if "," in document["branchen"]:
            document["branchen"] = [b.strip() for b in document["branchen"].split(",")]
        else:
            document["branchen"] = [document["branchen"]] if document["branchen"] else []
    elif not isinstance(document["branchen"], list):
        document["branchen"] = []
    
    return document


def migrate_occupations(occupations: list[Dict[str, Any]], db_manager) -> int:
    """
    Migrate occupations to MongoDB.
    
    Args:
        occupations: List of occupation dictionaries.
        db_manager: MongoDBManager instance.
    
    Returns:
        Number of occupations migrated.
    """
    collection = db_manager.get_collection("occupations")
    
    migrated_count = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task(
            "[cyan]Migrating occupations...",
            total=len(occupations)
        )
        
        for occ in occupations:
            try:
                # Transform occupation
                document = transform_occupation(occ)
                
                # Upsert using id as unique identifier
                result = collection.update_one(
                    {"id": document["id"]},
                    {"$set": document},
                    upsert=True
                )
                
                if result.upserted_id or result.modified_count > 0:
                    migrated_count += 1
                
                progress.update(task, advance=1)
                
            except Exception as e:
                console.print(f"[red]❌ Error migrating occupation {occ.get('id', 'unknown')}: {e}[/red]")
                progress.update(task, advance=1)
                continue
    
    return migrated_count


def print_sample_occupation(db_manager) -> None:
    """
    Print a sample occupation from MongoDB for verification.
    
    Args:
        db_manager: MongoDBManager instance.
    """
    collection = db_manager.get_collection("occupations")
    
    sample = collection.find_one()
    
    if sample:
        console.print("\n[cyan]📋 Sample Occupation (for verification):[/cyan]")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        
        # Display key fields
        fields_to_show = [
            ("id", sample.get("id")),
            ("name_de", sample.get("name_de")),
            ("industry", sample.get("industry")),
            ("berufsfeld", sample.get("berufsfeld")),
            ("bildungstyp", sample.get("bildungstyp")),
            ("swissdoc", sample.get("swissdoc")),
            ("created_at", str(sample.get("created_at"))),
        ]
        
        for field, value in fields_to_show:
            if value:
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 60:
                    value_str = value_str[:57] + "..."
                table.add_row(field, value_str)
        
        console.print(table)
        
        # Show branchen if it's an array
        if sample.get("branchen"):
            branchen_str = ", ".join(sample["branchen"][:3])
            if len(sample["branchen"]) > 3:
                branchen_str += f" ... (+{len(sample['branchen']) - 3} more)"
            console.print(f"[dim]Branchen: {branchen_str}[/dim]")
    else:
        console.print("[yellow]⚠️  No occupations found in database[/yellow]")


def main():
    """Main migration function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Occupations Migration to MongoDB[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        # Get database manager
        db_manager = get_db_manager()
        
        # Connect to MongoDB
        console.print("[cyan]Connecting to MongoDB...[/cyan]")
        db_manager.connect()
        console.print(f"[green]✅ Connected to database: {db_manager.database.name}[/green]")
        console.print()
        
        # Load occupations
        occupations_file = project_root / "data" / "processed" / "occupations.json"
        occupations = load_occupations(occupations_file)
        console.print()
        
        # Migrate occupations
        migrated_count = migrate_occupations(occupations, db_manager)
        console.print()
        
        # Print summary
        console.print("[bold green]=" * 60)
        console.print(f"[bold green]✅ Migrated {migrated_count} occupations[/bold green]")
        console.print("[bold green]=" * 60)
        console.print()
        
        # Print sample occupation
        print_sample_occupation(db_manager)
        console.print()
        
        console.print("[dim]To verify in mongosh, run:[/dim]")
        console.print("[dim]  use swiss_cv_generator[/dim]")
        console.print("[dim]  db.occupations.findOne()[/dim]")
        console.print()
        
    except FileNotFoundError as e:
        console.print(f"[red]❌ File not found: {e}[/red]")
        console.print("[yellow]💡 Make sure to run scripts/process_occupations.py first[/yellow]")
        sys.exit(1)
    except OperationFailure as e:
        console.print(f"[red]❌ MongoDB operation failed: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        console.print_exception()
        sys.exit(1)
    finally:
        # Close connection
        try:
            db_manager.close()
        except:
            pass


if __name__ == "__main__":
    main()

