"""
Test MongoDB connection to CV_DATA.cv_berufsberatung.

Run: python scripts/test_db_connection.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from rich.console import Console
from pymongo.errors import OperationFailure

console = Console()


def main():
    """Test connection to source database."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]MongoDB Connection Test[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        console.print("[cyan]Connecting to MongoDB...[/cyan]")
        db_manager = get_db_manager()
        db_manager.connect()
        
        console.print(f"[green]✅ Connected to MongoDB[/green]")
        console.print(f"   Source DB: {db_manager.source_db.name}")
        console.print(f"   Target DB: {db_manager.target_db.name}")
        console.print()
        
        # Test source collection
        console.print("[cyan]Testing source collection: cv_berufsberatung[/cyan]")
        occupations_col = db_manager.get_source_collection("cv_berufsberatung")
        count = occupations_col.count_documents({})
        
        console.print(f"[green]✅ Collection: cv_berufsberatung[/green]")
        console.print(f"   Document Count: {count:,}")
        console.print()
        
        # Show sample document
        sample = occupations_col.find_one()
        if sample:
            console.print("[cyan]Sample Document (first 10 keys):[/cyan]")
            keys = list(sample.keys())[:10]
            for key in keys:
                value = sample[key]
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                console.print(f"   [dim]{key}:[/dim] {value}")
        
        console.print()
        console.print("[bold green]✅ Connection test successful![/bold green]")
        console.print()
        
    except OperationFailure as e:
        console.print(f"[red]❌ MongoDB operation failed: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        console.print_exception()
        sys.exit(1)
    finally:
        try:
            db_manager.close()
        except:
            pass


if __name__ == "__main__":
    main()

