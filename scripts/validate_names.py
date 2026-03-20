"""
Validate name data in MongoDB collections.

This script:
1. Checks counts per language for first_names and last_names
2. Verifies minimum requirements (≥150 first names, ≥50 last names per language)
3. Analyzes frequency distribution
4. Shows random sample full names
5. Checks for duplicates
6. Provides final validation verdict

Run: python scripts/validate_names.py
"""
import sys
import random
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pymongo.errors import OperationFailure

console = Console()

# Validation thresholds
MIN_FIRST_NAMES_PER_LANGUAGE = 150
MIN_LAST_NAMES_PER_LANGUAGE = 50

LANGUAGES = ["de", "fr", "it"]


def get_counts_per_language(collection, language_field: str = "language") -> Dict[str, int]:
    """
    Get document counts per language.
    
    Args:
        collection: MongoDB collection.
        language_field: Field name for language.
    
    Returns:
        Dictionary mapping language to count.
    """
    pipeline = [
        {"$group": {
            "_id": f"${language_field}",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = list(collection.aggregate(pipeline))
    return {result["_id"]: result["count"] for result in results}


def get_frequency_stats(collection, language: str) -> Dict[str, float]:
    """
    Get frequency statistics for a language.
    
    Args:
        collection: MongoDB collection.
        language: Language code.
    
    Returns:
        Dictionary with avg, min, max frequency.
    """
    pipeline = [
        {"$match": {"language": language}},
        {"$group": {
            "_id": None,
            "avg": {"$avg": "$frequency"},
            "min": {"$min": "$frequency"},
            "max": {"$max": "$frequency"}
        }}
    ]
    
    results = list(collection.aggregate(pipeline))
    if results:
        return {
            "avg": results[0].get("avg", 0),
            "min": results[0].get("min", 0),
            "max": results[0].get("max", 0)
        }
    return {"avg": 0, "min": 0, "max": 0}


def get_random_sample_names(first_names_col, last_names_col, language: str, count: int = 5) -> List[Dict[str, str]]:
    """
    Get random sample full names for a language.
    
    Args:
        first_names_col: First names collection.
        last_names_col: Last names collection.
        language: Language code.
        count: Number of samples to generate.
    
    Returns:
        List of full name dictionaries.
    """
    # Get random first names
    first_names = list(first_names_col.aggregate([
        {"$match": {"language": language}},
        {"$sample": {"size": count * 2}}  # Get more to have variety
    ]))
    
    # Get random last names
    last_names = list(last_names_col.aggregate([
        {"$match": {"language": language}},
        {"$sample": {"size": count * 2}}
    ]))
    
    # Combine into full names
    samples = []
    for i in range(count):
        if i < len(first_names) and i < len(last_names):
            samples.append({
                "first": first_names[i].get("name", ""),
                "last": last_names[i].get("name", ""),
                "full": f"{first_names[i].get('name', '')} {last_names[i].get('name', '')}"
            })
    
    return samples


def check_duplicates(collection, unique_fields: List[str]) -> List[Dict[str, Any]]:
    """
    Check for duplicate documents based on unique fields.
    
    Args:
        collection: MongoDB collection.
        unique_fields: List of field names that should be unique together.
    
    Returns:
        List of duplicate groups.
    """
    # Build group key
    group_key = {field: f"${field}" for field in unique_fields}
    
    pipeline = [
        {"$group": {
            "_id": group_key,
            "count": {"$sum": 1},
            "ids": {"$push": "$_id"}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    duplicates = list(collection.aggregate(pipeline))
    return duplicates


def print_counts_table(first_names_col, last_names_col) -> Dict[str, Dict[str, int]]:
    """
    Print counts table and return counts.
    
    Args:
        first_names_col: First names collection.
        last_names_col: Last names collection.
    
    Returns:
        Dictionary with counts per language.
    """
    first_counts = get_counts_per_language(first_names_col)
    last_counts = get_counts_per_language(last_names_col)
    
    table = Table(title="Name Counts per Language")
    table.add_column("Language", style="cyan")
    table.add_column("First Names", style="green", justify="right")
    table.add_column("Last Names", style="magenta", justify="right")
    table.add_column("Status", style="yellow")
    
    counts = {}
    for lang in LANGUAGES:
        first_count = first_counts.get(lang, 0)
        last_count = last_counts.get(lang, 0)
        counts[lang] = {
            "first": first_count,
            "last": last_count
        }
        
        # Status
        first_ok = first_count >= MIN_FIRST_NAMES_PER_LANGUAGE
        last_ok = last_count >= MIN_LAST_NAMES_PER_LANGUAGE
        
        if first_ok and last_ok:
            status = "✅"
        elif first_ok:
            status = f"⚠️  Last names: {last_count}/{MIN_LAST_NAMES_PER_LANGUAGE}"
        elif last_ok:
            status = f"⚠️  First names: {first_count}/{MIN_FIRST_NAMES_PER_LANGUAGE}"
        else:
            status = "❌"
        
        table.add_row(
            lang.upper(),
            str(first_count),
            str(last_count),
            status
        )
    
    console.print(table)
    return counts


def print_frequency_stats(first_names_col, last_names_col) -> None:
    """
    Print frequency distribution statistics.
    
    Args:
        first_names_col: First names collection.
        last_names_col: Last names collection.
    """
    table = Table(title="Frequency Distribution Statistics")
    table.add_column("Collection", style="cyan")
    table.add_column("Language", style="green")
    table.add_column("Avg", style="magenta", justify="right")
    table.add_column("Min", style="yellow", justify="right")
    table.add_column("Max", style="red", justify="right")
    
    for lang in LANGUAGES:
        first_stats = get_frequency_stats(first_names_col, lang)
        last_stats = get_frequency_stats(last_names_col, lang)
        
        table.add_row(
            "First Names",
            lang.upper(),
            f"{first_stats['avg']:.1f}",
            str(int(first_stats['min'])),
            str(int(first_stats['max']))
        )
        
        table.add_row(
            "Last Names",
            lang.upper(),
            f"{last_stats['avg']:.1f}",
            str(int(last_stats['min'])),
            str(int(last_stats['max']))
        )
    
    console.print(table)


def print_sample_names(first_names_col, last_names_col) -> None:
    """
    Print random sample full names.
    
    Args:
        first_names_col: First names collection.
        last_names_col: Last names collection.
    """
    for lang in LANGUAGES:
        samples = get_random_sample_names(first_names_col, last_names_col, lang, count=5)
        
        if samples:
            table = Table(title=f"Sample Full Names - {lang.upper()}")
            table.add_column("#", style="cyan", justify="right")
            table.add_column("Full Name", style="green")
            
            for i, sample in enumerate(samples, 1):
                table.add_row(str(i), sample["full"])
            
            console.print(table)
            console.print()


def check_all_duplicates(first_names_col, last_names_col) -> Dict[str, List]:
    """
    Check for duplicates in both collections.
    
    Args:
        first_names_col: First names collection.
        last_names_col: Last names collection.
    
    Returns:
        Dictionary with duplicate information.
    """
    # Check first_names: unique on name+language+gender
    first_duplicates = check_duplicates(first_names_col, ["name", "language", "gender"])
    
    # Check last_names: unique on name+language
    last_duplicates = check_duplicates(last_names_col, ["name", "language"])
    
    return {
        "first_names": first_duplicates,
        "last_names": last_duplicates
    }


def main():
    """Main validation function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Name Data Validation[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        # Get database manager
        db_manager = get_db_manager()
        
        # Connect to MongoDB
        console.print("[cyan]Connecting to MongoDB...[/cyan]")
        db_manager.connect()
        console.print(f"[green]✅ Connected to database: {db_manager.target_db.name}[/green]")
        console.print()
        
        first_names_col = db_manager.get_target_collection("first_names")
        last_names_col = db_manager.get_target_collection("last_names")
        
        # 1. Query counts per language
        console.print("[bold cyan]1. Name Counts per Language[/bold cyan]")
        console.print()
        counts = print_counts_table(first_names_col, last_names_col)
        console.print()
        
        # 2. Verify minimum requirements
        console.print("[bold cyan]2. Minimum Requirements Check[/bold cyan]")
        console.print()
        
        validation_passed = True
        issues = []
        
        for lang in LANGUAGES:
            first_count = counts[lang]["first"]
            last_count = counts[lang]["last"]
            
            if first_count < MIN_FIRST_NAMES_PER_LANGUAGE:
                validation_passed = False
                issues.append(f"{lang.upper()}: First names {first_count} < {MIN_FIRST_NAMES_PER_LANGUAGE}")
            
            if last_count < MIN_LAST_NAMES_PER_LANGUAGE:
                validation_passed = False
                issues.append(f"{lang.upper()}: Last names {last_count} < {MIN_LAST_NAMES_PER_LANGUAGE}")
        
        if validation_passed:
            console.print(f"[green]✅ All languages meet minimum requirements[/green]")
            console.print(f"   First names: ≥{MIN_FIRST_NAMES_PER_LANGUAGE} per language")
            console.print(f"   Last names: ≥{MIN_LAST_NAMES_PER_LANGUAGE} per language")
        else:
            console.print("[red]❌ Some languages do not meet minimum requirements:[/red]")
            for issue in issues:
                console.print(f"   [red]  • {issue}[/red]")
        console.print()
        
        # 3. Frequency distribution
        console.print("[bold cyan]3. Frequency Distribution Statistics[/bold cyan]")
        console.print()
        print_frequency_stats(first_names_col, last_names_col)
        console.print()
        
        # 4. Random sample full names
        console.print("[bold cyan]4. Random Sample Full Names[/bold cyan]")
        console.print()
        print_sample_names(first_names_col, last_names_col)
        
        # 5. Duplicate check
        console.print("[bold cyan]5. Duplicate Check[/bold cyan]")
        console.print()
        
        duplicates = check_all_duplicates(first_names_col, last_names_col)
        
        first_dup_count = len(duplicates["first_names"])
        last_dup_count = len(duplicates["last_names"])
        
        if first_dup_count == 0 and last_dup_count == 0:
            console.print("[green]✅ No duplicates found[/green]")
        else:
            validation_passed = False
            if first_dup_count > 0:
                console.print(f"[red]❌ Found {first_dup_count} duplicate groups in first_names[/red]")
                # Show first few duplicates
                for dup in duplicates["first_names"][:3]:
                    console.print(f"   [dim]  {dup['_id']} (count: {dup['count']})[/dim]")
            
            if last_dup_count > 0:
                console.print(f"[red]❌ Found {last_dup_count} duplicate groups in last_names[/red]")
                # Show first few duplicates
                for dup in duplicates["last_names"][:3]:
                    console.print(f"   [dim]  {dup['_id']} (count: {dup['count']})[/dim]")
        console.print()
        
        # 6. Final verdict
        console.print("[bold blue]=" * 60)
        if validation_passed:
            console.print(Panel(
                "[bold green]✅ Validation PASSED[/bold green]",
                title="Final Verdict",
                border_style="green"
            ))
        else:
            console.print(Panel(
                "[bold red]❌ Validation FAILED[/bold red]",
                title="Final Verdict",
                border_style="red"
            ))
        console.print("[bold blue]=" * 60)
        console.print()
        
        # Exit with appropriate code
        sys.exit(0 if validation_passed else 1)
        
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

