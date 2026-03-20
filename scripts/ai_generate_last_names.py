"""
Generate Swiss last names (surnames) using OpenAI and store in MongoDB.

This script:
1. Generates authentic Swiss surnames for de/fr/it languages
2. Covers different origin types (occupational, geographical, patronymic, modern)
3. Stores in MongoDB last_names collection
4. Shows top 10 most frequent names per language

Run: python scripts/ai_generate_last_names.py
"""
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import get_settings
from src.database.mongodb_manager import get_db_manager
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.console import Console
from rich.table import Table
from pymongo.errors import OperationFailure

console = Console()
settings = get_settings()

# OpenAI client setup - support both modern and legacy APIs
OPENAI_AVAILABLE = False
_openai_client = None

try:
    # Try modern OpenAI client (>=1.0.0)
    try:
        from openai import OpenAI
        if settings.openai_api_key:
            _openai_client = OpenAI(api_key=settings.openai_api_key)
            OPENAI_AVAILABLE = True
    except ImportError:
        # Fallback to legacy client (0.28.x)
        try:
            import openai
            if settings.openai_api_key:
                openai.api_key = settings.openai_api_key
            OPENAI_AVAILABLE = True
        except ImportError:
            pass
except Exception:
    pass

if not OPENAI_AVAILABLE:
    console.print("[yellow]⚠️  OpenAI package not available. Install with: pip install openai[/yellow]")


def get_region_hint(language: str) -> str:
    """
    Get region hint with naming patterns for language.
    
    Args:
        language: Language code (de, fr, it).
    
    Returns:
        Region hint string with naming patterns.
    """
    hints = {
        "de": "German-speaking Switzerland (Zürich/Bern region). Common patterns: -er, -mann endings",
        "fr": "French-speaking Switzerland (Romandie). Common patterns: -et, -az endings",
        "it": "Italian-speaking Switzerland (Ticino). Common patterns: -i, -etti endings"
    }
    return hints.get(language, language)


def generate_surnames_for_language(
    language: str,
    count: int
) -> List[Dict[str, Any]]:
    """
    Generate surnames using OpenAI.
    
    Args:
        language: Language code (de, fr, it).
        count: Number of surnames to generate.
    
    Returns:
        List of surname dictionaries with metadata.
    
    Raises:
        ValueError: If OpenAI is not available or API key is missing.
    """
    if not OPENAI_AVAILABLE:
        raise ValueError("OpenAI package not available")
    
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    
    region = get_region_hint(language)
    
    prompt = f"""Generate {count} authentic Swiss surnames for {region}. 
Mix occupational (35%), geographical (30%), patronymic (20%), modern (15%). 
Return JSON array: [{{"name": "Surname", "frequency": 1-100, "origin": "occupational|geographical|patronymic|modern"}}].
Only return valid JSON, no markdown, no explanation."""

    try:
        messages = [
            {"role": "system", "content": "You are a Swiss naming expert specializing in surnames. Return only valid JSON arrays."},
            {"role": "user", "content": prompt}
        ]
        
        # Try modern client first
        if _openai_client and hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=2000
            )
            content = response.choices[0].message.content.strip()
        else:
            # Fallback to legacy client
            import openai
            response = openai.ChatCompletion.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=2000
            )
            # Handle both dict and object responses
            if isinstance(response, dict):
                content = response["choices"][0]["message"]["content"].strip()
            else:
                content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        # Parse JSON
        surnames_data = json.loads(content)
        
        # Add metadata
        result = []
        for item in surnames_data:
            if isinstance(item, dict) and "name" in item:
                result.append({
                    "name": item["name"],
                    "language": language,
                    "frequency": item.get("frequency", 50),
                    "origin": item.get("origin", "modern")
                })
        
        return result
        
    except json.JSONDecodeError as e:
        console.print(f"[red]❌ JSON parse error: {e}[/red]")
        console.print(f"[dim]Response: {content[:200]}...[/dim]")
        return []
    except Exception as e:
        console.print(f"[red]❌ OpenAI error: {e}[/red]")
        return []


def insert_surnames(collection, surnames: List[Dict[str, Any]]) -> int:
    """
    Insert surnames into MongoDB with upsert.
    
    Args:
        collection: MongoDB collection.
        surnames: List of surname dictionaries.
    
    Returns:
        Number of surnames inserted/updated.
    """
    inserted_count = 0
    
    for surname_doc in surnames:
        try:
            result = collection.update_one(
                {
                    "name": surname_doc["name"],
                    "language": surname_doc["language"]
                },
                {"$set": surname_doc},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                inserted_count += 1
                
        except Exception as e:
            console.print(f"[red]❌ Error inserting {surname_doc.get('name')}: {e}[/red]")
            continue
    
    return inserted_count


def print_top_surnames(collection, language: str, limit: int = 10) -> None:
    """
    Print top N most frequent surnames for a language.
    
    Args:
        collection: MongoDB collection.
        language: Language code.
        limit: Number of top surnames to show.
    """
    top_surnames = collection.find(
        {"language": language}
    ).sort("frequency", -1).limit(limit)
    
    if top_surnames:
        table = Table(title=f"Top {limit} Most Frequent Surnames - {language.upper()}")
        table.add_column("Rank", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Frequency", style="magenta", justify="right")
        table.add_column("Origin", style="yellow")
        
        for rank, surname in enumerate(top_surnames, 1):
            table.add_row(
                str(rank),
                surname.get("name", ""),
                str(surname.get("frequency", 0)),
                surname.get("origin", "unknown")
            )
        
        console.print(table)
    else:
        console.print(f"[yellow]No surnames found for language: {language}[/yellow]")


def estimate_cost() -> float:
    """
    Estimate cost for generating all surnames.
    
    Returns:
        Estimated cost in USD.
    """
    # GPT-3.5-turbo pricing: ~$0.0015 per 1K input tokens, $0.002 per 1K output tokens
    # Average prompt: ~150 tokens, average response: ~500 tokens
    # Total per request: ~650 tokens
    # Cost per request: ~$0.001
    
    counts = {"de": 120, "fr": 80, "it": 60}
    
    # Assuming ~20 surnames per request
    total_requests = sum((count + 19) // 20 for count in counts.values())
    cost_per_request = 0.001
    total_cost = total_requests * cost_per_request
    
    return total_cost


def main():
    """Main function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]AI Last Names (Surnames) Generator[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    if not OPENAI_AVAILABLE:
        console.print("[red]❌ OpenAI package not available[/red]")
        sys.exit(1)
    
    if not settings.openai_api_key:
        console.print("[red]❌ OPENAI_API_KEY not set in environment[/red]")
        sys.exit(1)
    
    # Cost estimate
    estimated_cost = estimate_cost()
    console.print(f"[yellow]💰 Estimated cost: ~${estimated_cost:.2f}[/yellow]")
    console.print()
    
    try:
        # Get database manager
        db_manager = get_db_manager()
        
        # Connect to MongoDB
        console.print("[cyan]Connecting to MongoDB...[/cyan]")
        db_manager.connect()
        console.print(f"[green]✅ Connected to database: {db_manager.target_db.name}[/green]")
        console.print()
        
        collection = db_manager.get_target_collection("last_names")
        
        # Configuration: de(120), fr(80), it(60) = 260 surnames
        language_counts = {
            "de": 120,
            "fr": 80,
            "it": 60
        }
        
        # Calculate total tasks
        tasks_list = []
        
        for language, count in language_counts.items():
            # Calculate number of API calls needed (20 surnames per call)
            num_calls = (count + 19) // 20  # Ceiling division
            remaining = count
            for _ in range(num_calls):
                call_count = min(20, remaining)
                tasks_list.append((language, call_count))
                remaining -= call_count
                if remaining <= 0:
                    break
        
        total_tasks = len(tasks_list)
        
        console.print(f"[cyan]Generating surnames: {total_tasks} API calls[/cyan]")
        console.print(f"[dim]Total surnames: {sum(language_counts.values())} (de: {language_counts['de']}, fr: {language_counts['fr']}, it: {language_counts['it']})[/dim]")
        console.print()
        
        # Generate surnames with progress bar
        total_inserted = 0
        
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
                "[cyan]Generating surnames...",
                total=total_tasks
            )
            
            for language, count in tasks_list:
                try:
                    # Generate surnames
                    surnames = generate_surnames_for_language(language, count)
                    
                    if surnames:
                        # Insert into MongoDB
                        inserted = insert_surnames(collection, surnames)
                        total_inserted += inserted
                        
                        progress.update(
                            task,
                            advance=1,
                            description=f"[cyan]Generated {len(surnames)} {language} surnames[/cyan]"
                        )
                    else:
                        progress.update(task, advance=1)
                    
                    # Rate limiting
                    if settings.ai_rate_limit_delay > 0:
                        time.sleep(settings.ai_rate_limit_delay)
                        
                except Exception as e:
                    console.print(f"[red]❌ Error generating {language} surnames: {e}[/red]")
                    progress.update(task, advance=1)
                    continue
        
        console.print()
        console.print("[bold green]=" * 60)
        console.print(f"[bold green]✅ Generated and inserted {total_inserted} surnames[/bold green]")
        console.print("[bold green]=" * 60)
        console.print()
        
        # Print top 10 most frequent per language
        console.print("[bold cyan]Top 10 Most Frequent Surnames by Language:[/bold cyan]")
        console.print()
        
        for language in language_counts.keys():
            print_top_surnames(collection, language, limit=10)
            console.print()
        
        # Print summary
        summary_table = Table(title="Summary by Language")
        summary_table.add_column("Language", style="cyan")
        summary_table.add_column("Count", style="green", justify="right")
        
        for language, count in language_counts.items():
            db_count = collection.count_documents({"language": language})
            summary_table.add_row(language, str(db_count))
        
        console.print(summary_table)
        console.print()
        
        console.print("[dim]To verify in mongosh, run:[/dim]")
        console.print("[dim]  use swiss_cv_generator[/dim]")
        console.print("[dim]  db.last_names.countDocuments({language: \"de\"})[/dim]")
        console.print("[dim]  db.last_names.find({language: \"de\"}).sort({frequency: -1}).limit(10)[/dim]")
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
        # Close connection
        try:
            db_manager.close()
        except:
            pass


if __name__ == "__main__":
    main()

