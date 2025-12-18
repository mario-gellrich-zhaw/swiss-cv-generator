"""
Import CV_DATA collection from JSON file to MongoDB.

This script imports the cv_berufsberatung collection from a JSON file
into the CV_DATA database. This allows the scraper to be skipped during setup.

Usage:
    python scripts/import_cv_data.py [--input data/CV_DATA.cv_berufsberatung.json]
"""
import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from bson import ObjectId

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from src.config import get_settings
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from pymongo.errors import BulkWriteError

console = Console()
settings = get_settings()


def convert_objectid(obj: Any) -> Any:
    """
    Convert MongoDB ObjectId format from JSON to actual ObjectId.
    
    Args:
        obj: Object that may contain ObjectId format.
    
    Returns:
        Object with ObjectIds converted.
    """
    if isinstance(obj, dict):
        if "$oid" in obj:
            return ObjectId(obj["$oid"])
        return {k: convert_objectid(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    return obj


def import_collection(input_path: Path, skip_existing: bool = True) -> bool:
    """
    Import cv_berufsberatung collection from JSON file.
    
    Args:
        input_path: Path to input JSON file.
        skip_existing: If True, skip documents that already exist (by _id).
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        if not input_path.exists():
            console.print(f"[red]❌ File not found: {input_path}[/red]")
            return False
        
        console.print(f"[cyan]Reading JSON file: {input_path}...[/cyan]")
        
        # Read JSON file
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle both array format and object format
        if isinstance(data, list):
            documents = data
        elif isinstance(data, dict) and "documents" in data:
            documents = data["documents"]
        else:
            console.print("[red]❌ Invalid JSON format. Expected array or object with 'documents' key.[/red]")
            return False
        
        total_docs = len(documents)
        console.print(f"[green]Found {total_docs} documents in JSON file[/green]")
        
        if total_docs == 0:
            console.print("[yellow]⚠️  No documents to import.[/yellow]")
            return False
        
        # Connect to MongoDB
        console.print(f"[cyan]Connecting to MongoDB...[/cyan]")
        db_manager = get_db_manager()
        db_manager.connect()
        
        # Get collection
        collection = db_manager.get_source_collection(settings.mongodb_collection_occupations)
        
        # Check if collection already has data
        existing_count = collection.count_documents({})
        if existing_count > 0:
            if skip_existing:
                console.print(f"[yellow]⚠️  Collection already contains {existing_count} documents.[/yellow]")
                console.print("[yellow]Skipping import (use --force to overwrite).[/yellow]")
                return True
            else:
                console.print(f"[yellow]⚠️  Collection already contains {existing_count} documents.[/yellow]")
                console.print("[yellow]Dropping existing collection...[/yellow]")
                collection.drop()
        
        # Convert ObjectIds and prepare documents
        console.print(f"[cyan]Preparing documents for import...[/cyan]")
        prepared_docs: List[Dict[str, Any]] = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("Preparing...", total=total_docs)
            
            for doc in documents:
                # Convert ObjectId format
                prepared_doc = convert_objectid(doc)
                prepared_docs.append(prepared_doc)
                progress.update(task, advance=1)
        
        # Import documents in batches
        console.print(f"[cyan]Importing {total_docs} documents to MongoDB...[/cyan]")
        batch_size = 100
        imported = 0
        errors = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("Importing...", total=total_docs)
            
            for i in range(0, len(prepared_docs), batch_size):
                batch = prepared_docs[i:i + batch_size]
                try:
                    result = collection.insert_many(batch, ordered=False)
                    imported += len(result.inserted_ids)
                except BulkWriteError as e:
                    # Count successfully inserted
                    inserted = len(e.details.get("insertedIds", []))
                    imported += inserted
                    errors += len(e.details.get("writeErrors", []))
                except Exception as e:
                    console.print(f"[red]Error importing batch: {e}[/red]")
                    errors += len(batch)
                
                progress.update(task, advance=len(batch))
        
        # Verify import
        final_count = collection.count_documents({})
        
        console.print()
        console.print(f"[green]✅ Import completed![/green]")
        console.print(f"   Imported: {imported} documents")
        if errors > 0:
            console.print(f"   Errors: {errors} documents")
        console.print(f"   Total in collection: {final_count} documents")
        
        # Create indexes
        console.print()
        console.print("[cyan]Creating indexes...[/cyan]")
        try:
            collection.create_index("job_id", unique=True)
            collection.create_index("url", unique=True)
            collection.create_index("title")
            collection.create_index("categories.berufsfelder")
            collection.create_index("categories.branchen")
            console.print("[green]✅ Indexes created[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Index creation warning: {e}[/yellow]")
        
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Import failed: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return False
    finally:
        try:
            db_manager.close()
        except:
            pass


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Import CV_DATA collection from JSON")
    parser.add_argument(
        "--input",
        type=str,
        default="data/CV_DATA.cv_berufsberatung.json",
        help="Input JSON file path (default: data/CV_DATA.cv_berufsberatung.json)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force import even if collection already has data (drops existing collection)"
    )
    
    args = parser.parse_args()
    input_path = Path(project_root / args.input)
    
    console.print("[bold blue]CV_DATA Import Tool[/bold blue]")
    console.print()
    
    success = import_collection(input_path, skip_existing=not args.force)
    
    if success:
        console.print()
        console.print("[green]✨ Import completed![/green]")
        console.print("The CV_DATA database is now ready to use.")
    else:
        console.print()
        console.print("[red]❌ Import failed![/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()

