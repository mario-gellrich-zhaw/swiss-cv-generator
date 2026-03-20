"""
Generate Swiss first names using OpenAI and store in MongoDB.

This script:
1. Generates authentic Swiss first names for de/fr/it languages
2. Covers male and female genders
3. Stores in MongoDB first_names collection
4. Uses rate limiting and progress tracking

Run: python scripts/ai_generate_first_names.py [--skip-existing]
"""
import sys
import json
import time
import argparse
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
    Get region hint for language.
    
    Args:
        language: Language code (de, fr, it).
    
    Returns:
        Region hint string.
    """
    hints = {
        "de": "Zürich/Bern region",
        "fr": "Romandie",
        "it": "Ticino"
    }
    return hints.get(language, language)


def generate_first_names_for_language(
    language: str,
    gender: str,
    count: int
) -> List[Dict[str, Any]]:
    """
    Generate first names using OpenAI.
    
    Args:
        language: Language code (de, fr, it).
        gender: Gender (male, female).
        count: Number of names to generate.
    
    Returns:
        List of name dictionaries with metadata.
    
    Raises:
        ValueError: If OpenAI is not available or API key is missing.
    """
    if not OPENAI_AVAILABLE:
        raise ValueError("OpenAI package not available")
    
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    
    region = get_region_hint(language)
    
    prompt = f"""Generate {count} authentic Swiss {language} first names for {gender} in {region}. 
Mix traditional (40%), modern (40%), international (20%). 
Return JSON array: [{{"name": "Name", "frequency": 1-100, "origin": "traditional|modern|international"}}].
Only return valid JSON, no markdown, no explanation."""

    try:
        messages = [
            {"role": "system", "content": "You are a Swiss naming expert. Return only valid JSON arrays."},
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
        names_data = json.loads(content)
        
        # Add metadata
        result = []
        for item in names_data:
            if isinstance(item, dict) and "name" in item:
                result.append({
                    "name": item["name"],
                    "gender": gender,
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


def check_existing_data(collection, language: str, gender: str) -> bool:
    """
    Check if data already exists for language/gender combination.
    
    Args:
        collection: MongoDB collection.
        language: Language code.
        gender: Gender.
    
    Returns:
        True if data exists, False otherwise.
    """
    count = collection.count_documents({
        "language": language,
        "gender": gender
    })
    return count > 0


def insert_names(collection, names: List[Dict[str, Any]]) -> int:
    """
    Insert names into MongoDB with upsert.
    
    Args:
        collection: MongoDB collection.
        names: List of name dictionaries.
    
    Returns:
        Number of names inserted/updated.
    """
    inserted_count = 0
    
    for name_doc in names:
        try:
            result = collection.update_one(
                {
                    "name": name_doc["name"],
                    "language": name_doc["language"],
                    "gender": name_doc["gender"]
                },
                {"$set": name_doc},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                inserted_count += 1
                
        except Exception as e:
            console.print(f"[red]❌ Error inserting {name_doc.get('name')}: {e}[/red]")
            continue
    
    return inserted_count


def estimate_cost() -> float:
    """
    Estimate cost for generating all names.
    
    Returns:
        Estimated cost in USD.
    """
    # GPT-3.5-turbo pricing: ~$0.0015 per 1K input tokens, $0.002 per 1K output tokens
    # Average prompt: ~150 tokens, average response: ~500 tokens
    # Total per request: ~650 tokens
    # Cost per request: ~$0.001
    
    languages = ["de", "fr", "it"]
    genders = ["male", "female"]
    counts = {"male": 80, "female": 80}
    
    total_requests = sum(len(languages) * counts[g] // 20 for g in genders)  # Assuming ~20 names per request
    cost_per_request = 0.001
    total_cost = total_requests * cost_per_request
    
    return total_cost


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Generate Swiss first names using AI")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip language/gender combinations that already have data"
    )
    args = parser.parse_args()
    
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]AI First Names Generator[/bold blue]")
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
        
        collection = db_manager.get_target_collection("first_names")
        
        # Configuration
        languages = ["de", "fr", "it"]
        genders = {
            "male": 80,
            "female": 80
        }
        
        # Calculate total tasks
        total_tasks = 0
        tasks_list = []
        
        for language in languages:
            for gender, count in genders.items():
                if args.skip_existing:
                    if check_existing_data(collection, language, gender):
                        console.print(f"[dim]⏭️  Skipping {language}/{gender} (data exists)[/dim]")
                        continue
                
                # Calculate number of API calls needed (20 names per call)
                num_calls = (count + 19) // 20  # Ceiling division
                for _ in range(num_calls):
                    tasks_list.append((language, gender, min(20, count)))
                    count -= 20
                    if count <= 0:
                        break
        
        total_tasks = len(tasks_list)
        
        if total_tasks == 0:
            console.print("[yellow]⚠️  No tasks to execute (all skipped or no data needed)[/yellow]")
            return
        
        console.print(f"[cyan]Generating names: {total_tasks} API calls[/cyan]")
        console.print()
        
        # Generate names with progress bar
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
                "[cyan]Generating names...",
                total=total_tasks
            )
            
            for language, gender, count in tasks_list:
                try:
                    # Generate names
                    names = generate_first_names_for_language(language, gender, count)
                    
                    if names:
                        # Insert into MongoDB
                        inserted = insert_names(collection, names)
                        total_inserted += inserted
                        
                        progress.update(
                            task,
                            advance=1,
                            description=f"[cyan]Generated {len(names)} {language}/{gender} names[/cyan]"
                        )
                    else:
                        progress.update(task, advance=1)
                    
                    # Rate limiting
                    if settings.ai_rate_limit_delay > 0:
                        time.sleep(settings.ai_rate_limit_delay)
                        
                except Exception as e:
                    console.print(f"[red]❌ Error generating {language}/{gender}: {e}[/red]")
                    progress.update(task, advance=1)
                    continue
        
        console.print()
        console.print("[bold green]=" * 60)
        console.print(f"[bold green]✅ Generated and inserted {total_inserted} first names[/bold green]")
        console.print("[bold green]=" * 60)
        console.print()
        
        # Print summary
        summary_table = Table(title="Summary by Language/Gender")
        summary_table.add_column("Language", style="cyan")
        summary_table.add_column("Gender", style="magenta")
        summary_table.add_column("Count", style="green", justify="right")
        
        for language in languages:
            for gender in genders.keys():
                count = collection.count_documents({
                    "language": language,
                    "gender": gender
                })
                if count > 0:
                    summary_table.add_row(language, gender, str(count))
        
        console.print(summary_table)
        console.print()
        
        console.print("[dim]To verify in mongosh, run:[/dim]")
        console.print("[dim]  use swiss_cv_generator[/dim]")
        console.print("[dim]  db.first_names.countDocuments({language: \"de\"})[/dim]")
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

