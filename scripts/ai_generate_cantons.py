"""
Generate Swiss canton data using OpenAI and store in MongoDB.

This script:
1. Generates accurate data for all 26 Swiss cantons
2. Validates data (exactly 26 cantons, language percentages sum correctly)
3. Stores in MongoDB cantons collection
4. Uses GPT-4 for better factual accuracy

Run: python scripts/ai_generate_cantons.py
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from pymongo.errors import OperationFailure
from rich.console import Console
from rich.table import Table

from src.config import get_settings
from src.database.mongodb_manager import get_db_manager

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


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
    console.print(
        "[yellow]⚠️  OpenAI package not available. Install with: pip install openai[/yellow]")


def validate_canton_data(cantons: List[Dict[str, Any]]) -> tuple[bool, List[str]]:
    """
    Validate canton data.

    Args:
        cantons: List of canton dictionaries.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    errors = []

    # Check exactly 26 cantons
    if len(cantons) != 26:
        errors.append(f"Expected exactly 26 cantons, got {len(cantons)}")

    # Validate each canton
    required_fields = ["code", "name_de", "population"]
    seen_codes = set()

    for i, canton in enumerate(cantons):
        # Check required fields
        for field in required_fields:
            if field not in canton:
                errors.append(
                    f"Canton {i+1}: Missing required field '{field}'")

        # Check unique codes
        code = canton.get("code", "").upper()
        if code in seen_codes:
            errors.append(f"Canton {i+1}: Duplicate code '{code}'")
        seen_codes.add(code)

        # Validate language percentages
        lang_de = canton.get("language_de", 0)
        lang_fr = canton.get("language_fr", 0)
        lang_it = canton.get("language_it", 0)

        lang_sum = lang_de + lang_fr + lang_it

        if not (0.50 <= lang_sum <= 1.00):
            errors.append(
                f"Canton {code}: Language percentages sum to {lang_sum:.2f}, "
                f"expected 0.50-1.00 (de: {lang_de:.2f}, fr: {lang_fr:.2f}, it: {lang_it:.2f})"
            )

    return len(errors) == 0, errors


def generate_canton_data() -> List[Dict[str, Any]]:
    """
    Generate canton data using OpenAI.

    Returns:
        List of canton dictionaries.

    Raises:
        ValueError: If OpenAI is not available or API key is missing.
        RuntimeError: If validation fails after max retries.
    """
    if not OPENAI_AVAILABLE:
        raise ValueError("OpenAI package not available")

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")

    prompt = """Generate accurate data for all 26 Swiss cantons. 
Return JSON array with exactly 26 objects, each containing:
- code: 2-letter canton code (e.g., "ZH", "BE", "VD")
- name_de: German name
- name_fr: French name  
- name_it: Italian name
- population: integer population (2023 estimate)
- workforce: integer workforce size (optional, can be null)
- language_de: decimal percentage (0.0-1.0) for German speakers
- language_fr: decimal percentage (0.0-1.0) for French speakers
- language_it: decimal percentage (0.0-1.0) for Italian speakers
- major_city: name of the largest city

Important:
- language_de + language_fr + language_it should sum to approximately 1.0 (0.95-1.05 range)
- Include all 26 cantons: AG, AI, AR, BE, BL, BS, FR, GE, GL, GR, JU, LU, NE, NW, OW, SG, SH, SO, SZ, TG, TI, UR, VD, VS, ZG, ZH
- Use accurate, current data
- Return only valid JSON, no markdown, no explanation"""

    max_retries = settings.ai_max_retries

    for attempt in range(max_retries):
        try:
            messages = [
                {"role": "system", "content": "You are a Swiss geography expert. Return only valid JSON arrays with accurate data."},
                {"role": "user", "content": prompt}
            ]

            # Try modern client first
            if _openai_client and hasattr(_openai_client, 'chat'):
                response = _openai_client.chat.completions.create(
                    model=settings.openai_model_full,
                    messages=messages,
                    temperature=settings.ai_temperature_factual,
                    max_tokens=4000
                )
                content = response.choices[0].message.content.strip()
            else:
                # Fallback to legacy client
                import openai
                response = openai.ChatCompletion.create(
                    model=settings.openai_model_full,
                    messages=messages,
                    temperature=settings.ai_temperature_factual,
                    max_tokens=4000
                )
                # Handle both dict and object responses
                if isinstance(response, dict):
                    content = response["choices"][0]["message"]["content"].strip(
                    )
                else:
                    content = response.choices[0].message.content.strip()

            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            # Parse JSON
            cantons_data = json.loads(content)

            # Validate
            is_valid, errors = validate_canton_data(cantons_data)

            if is_valid:
                return cantons_data
            else:
                console.print(
                    f"[yellow]⚠️  Validation failed (attempt {attempt + 1}/{max_retries}):[/yellow]")
                for error in errors[:5]:  # Show first 5 errors
                    console.print(f"   [dim]{error}[/dim]")

                if attempt < max_retries - 1:
                    console.print("[dim]Retrying...[/dim]")
                    time.sleep(1)
                    continue
                else:
                    raise RuntimeError(
                        f"Validation failed after {max_retries} attempts. Errors: {errors}")

        except json.JSONDecodeError as e:
            console.print(
                f"[red]❌ JSON parse error (attempt {attempt + 1}/{max_retries}): {e}[/red]")
            if attempt < max_retries - 1:
                console.print("[dim]Retrying...[/dim]")
                time.sleep(1)
                continue
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                console.print(
                    f"[yellow]⚠️  Error (attempt {attempt + 1}/{max_retries}): {e}[/yellow]")
                console.print("[dim]Retrying...[/dim]")
                time.sleep(1)
                continue
            else:
                raise

    raise RuntimeError(
        f"Failed to generate valid canton data after {max_retries} attempts")


def insert_cantons(collection, cantons: List[Dict[str, Any]]) -> int:
    """
    Insert cantons into MongoDB with upsert.

    Args:
        collection: MongoDB collection.
        cantons: List of canton dictionaries.

    Returns:
        Number of cantons inserted/updated.
    """
    inserted_count = 0

    for canton_doc in cantons:
        # Add created_at timestamp
        canton_doc["created_at"] = datetime.utcnow()

        try:
            result = collection.update_one(
                {"code": canton_doc["code"].upper()},
                {"$set": canton_doc},
                upsert=True
            )

            if result.upserted_id or result.modified_count > 0:
                inserted_count += 1

        except Exception as e:
            console.print(
                f"[red]❌ Error inserting {canton_doc.get('code')}: {e}[/red]")
            continue

    return inserted_count


def print_sample_cantons(collection, limit: int = 5) -> None:
    """
    Print sample cantons.

    Args:
        collection: MongoDB collection.
        limit: Number of sample cantons to show.
    """
    samples = list(collection.find().limit(limit))

    if samples:
        table = Table(title=f"Sample Cantons (showing {len(samples)})")
        table.add_column("Code", style="cyan")
        table.add_column("Name (DE/FR/IT)", style="green")
        table.add_column("Population", style="magenta", justify="right")
        table.add_column("Languages", style="yellow")
        table.add_column("Major City", style="blue")

        for canton in samples:
            name_str = f"{canton.get('name_de', '')} / {canton.get('name_fr', '')} / {canton.get('name_it', '')}"
            lang_de = canton.get("language_de", 0)
            lang_fr = canton.get("language_fr", 0)
            lang_it = canton.get("language_it", 0)
            lang_str = f"DE:{lang_de:.0%} FR:{lang_fr:.0%} IT:{lang_it:.0%}"

            table.add_row(
                canton.get("code", ""),
                name_str,
                str(canton.get("population", 0)),
                lang_str,
                canton.get("major_city", "")
            )

        console.print(table)
    else:
        console.print("[yellow]No cantons found[/yellow]")


def estimate_cost() -> float:
    """
    Estimate cost for generating canton data.

    Returns:
        Estimated cost in USD.
    """
    # GPT-4 pricing: ~$0.03 per 1K input tokens, $0.06 per 1K output tokens
    # Average prompt: ~300 tokens, average response: ~2000 tokens
    # Total per request: ~2300 tokens
    # Cost per request: ~$0.15, but with retries and smaller response, estimate ~$0.02

    return 0.02


def main():
    """Main function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]AI Canton Data Generator[/bold blue]")
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
        console.print(
            f"[green]✅ Connected to database: {db_manager.target_db.name}[/green]")
        console.print()

        collection = db_manager.get_target_collection("cantons")

        # Generate canton data
        console.print("[cyan]Generating canton data with OpenAI...[/cyan]")
        console.print(f"[dim]Using model: {settings.openai_model_full}[/dim]")
        console.print(
            f"[dim]Temperature: {settings.ai_temperature_factual}[/dim]")
        console.print(f"[dim]Max retries: {settings.ai_max_retries}[/dim]")
        console.print()

        cantons = generate_canton_data()

        console.print(f"[green]✅ Generated {len(cantons)} cantons[/green]")
        console.print()

        # Insert into MongoDB
        console.print("[cyan]Inserting cantons into MongoDB...[/cyan]")
        inserted_count = insert_cantons(collection, cantons)
        console.print(
            f"[green]✅ Inserted/updated {inserted_count} cantons[/green]")
        console.print()

        # Print sample cantons
        console.print("[bold cyan]Sample Cantons:[/bold cyan]")
        console.print()
        print_sample_cantons(collection, limit=5)
        console.print()

        # Print summary
        total_count = collection.count_documents({})
        console.print(
            f"[green]✅ Total cantons in database: {total_count}[/green]")
        console.print()

        console.print("[dim]To verify in mongosh, run:[/dim]")
        console.print("[dim]  use swiss_cv_generator[/dim]")
        console.print(
            "[dim]  db.cantons.countDocuments() // should be 26[/dim]")
        console.print("[dim]  db.cantons.findOne()[/dim]")
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
