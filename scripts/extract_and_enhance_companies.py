"""
Extract and enhance companies from CV_DATA with demographic and branch data.

This script:
1. Loads demographic & branch data from JSON files
2. Maps berufsfelder to NOGA branches to Industry enum
3. Generates companies based on demographic context
4. Extracts seed companies from CV_DATA
5. Uses AI to generate additional companies
6. Inserts into target_db.companies

Run: python scripts/extract_and_enhance_companies.py
"""
import sys
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Set, Optional
from collections import defaultdict, Counter

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from src.config import get_settings
from src.data.models import Industry
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from pymongo.errors import OperationFailure

console = Console()
settings = get_settings()

# OpenAI client setup
OPENAI_AVAILABLE = False
_openai_client = None

try:
    try:
        from openai import OpenAI
        if settings.openai_api_key:
            _openai_client = OpenAI(api_key=settings.openai_api_key)
            OPENAI_AVAILABLE = True
    except ImportError:
        try:
            import openai
            if settings.openai_api_key:
                openai.api_key = settings.openai_api_key
            OPENAI_AVAILABLE = True
        except ImportError:
            pass
except Exception:
    pass

# Average company size for calculation
AVG_COMPANY_SIZE = 15  # Average employees per SME


def load_demographic_data() -> Dict[str, Any]:
    """
    Load demographic data from JSON file.
    
    Returns:
        Dictionary with demographic data.
    """
    demo_file = project_root / "data" / "source" / "Bevölkerungsdaten.json"
    
    if not demo_file.exists():
        console.print(f"[yellow]⚠️  Demographic data file not found: {demo_file}[/yellow]")
        return {}
    
    with open(demo_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data


def load_branch_data() -> Dict[str, float]:
    """
    Load branch distribution data from JSON file.
    
    Returns:
        Dictionary mapping branch name to percentage.
    """
    branch_file = project_root / "data" / "source" / "Branchenverteilung.json"
    
    if not branch_file.exists():
        console.print(f"[yellow]⚠️  Branch data file not found: {branch_file}[/yellow]")
        return {}
    
    with open(branch_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Extract branch percentages from the structure
    branch_percentages = {}
    
    if isinstance(data, dict):
        arbeitsgesellschaft = data.get("arbeitsgesellschaft_branchenverteilung", {})
        daten_list = arbeitsgesellschaft.get("daten_in_prozent", [])
        
        for item in daten_list:
            if isinstance(item, dict):
                branche = item.get("branche", "")
                anteil = item.get("anteil_prozent", 0)
                if branche and anteil:
                    branch_percentages[branche] = float(anteil)
    
    return branch_percentages


def save_demographics_json(demo_data: Dict, branch_data: Dict) -> None:
    """
    Save combined demographics data to data/demographics.json.
    
    Args:
        demo_data: Demographic data.
        branch_data: Branch distribution data.
    """
    output_file = project_root / "data" / "demographics.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    combined = {
        "demographic_data": demo_data,
        "branch_distribution": branch_data,
        "source": "mario_daten/Bevölkerungsdaten.json, mario_daten/Branchenverteilung.json"
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✅ Saved demographics data to {output_file}[/green]")


def map_berufsfeld_to_noga_branch(berufsfeld: str, branch_data: Dict) -> Optional[str]:
    """
    Map Berufsfeld to NOGA branch.
    
    Args:
        berufsfeld: Berufsfeld string.
        branch_data: Branch distribution data.
    
    Returns:
        NOGA branch name or None.
    """
    if not branch_data:
        return None
    
    berufsfeld_lower = berufsfeld.lower()
    
    # Mapping patterns
    mappings = {
        "informatik": "Informatik",
        "it": "Informatik",
        "gesundheit": "Gesundheit",
        "wirtschaft": "Wirtschaft",
        "verwaltung": "Wirtschaft",
        "bau": "Bau",
        "construction": "Bau",
        "produktion": "Produktion",
        "industrie": "Produktion",
        "handel": "Handel",
        "verkauf": "Handel",
        "gastronomie": "Gastronomie",
        "hotellerie": "Gastronomie",
        "bildung": "Bildung",
        "erziehung": "Bildung",
    }
    
    for key, branch in mappings.items():
        if key in berufsfeld_lower:
            # Check if branch exists in branch_data
            if isinstance(branch_data, dict):
                for branch_key in branch_data.keys():
                    if branch.lower() in branch_key.lower():
                        return branch_key
            return branch
    
    return None


def map_noga_branch_to_industry(branch: str) -> str:
    """
    Map NOGA branch to Industry enum.
    
    Args:
        branch: NOGA branch name.
    
    Returns:
        Industry enum value.
    """
    if not branch:
        return "other"
    
    branch_lower = branch.lower()
    
    # Mapping
    if "informatik" in branch_lower or "it" in branch_lower:
        return "technology"
    elif "wirtschaft" in branch_lower or "finanz" in branch_lower or "verwaltung" in branch_lower:
        return "finance"
    elif "gesundheit" in branch_lower:
        return "healthcare"
    elif "bau" in branch_lower:
        return "construction"
    elif "produktion" in branch_lower or "industrie" in branch_lower:
        return "manufacturing"
    elif "bildung" in branch_lower or "erziehung" in branch_lower:
        return "education"
    elif "handel" in branch_lower or "verkauf" in branch_lower:
        return "retail"
    elif "gastronomie" in branch_lower or "hotellerie" in branch_lower:
        return "hospitality"
    else:
        return "other"


def calculate_companies_needed(
    canton_workforce: int,
    branch_percentage: float,
    avg_company_size: int = AVG_COMPANY_SIZE
) -> int:
    """
    Calculate number of companies needed based on workforce and branch percentage.
    
    Args:
        canton_workforce: Total workforce in canton.
        branch_percentage: Percentage of workforce in this branch.
        avg_company_size: Average company size.
    
    Returns:
        Estimated number of companies needed.
    """
    workers_in_branch = int(canton_workforce * (branch_percentage / 100))
    companies_needed = max(1, workers_in_branch // avg_company_size)
    return companies_needed


def extract_organization_name(text: str) -> Optional[str]:
    """
    Extract organization name from text.
    
    Args:
        text: Text containing organization name.
    
    Returns:
        Extracted organization name or None.
    """
    if not text or not isinstance(text, str):
        return None
    
    # Common patterns
    patterns = [
        r"Bildungszentrum\s+([A-Z][A-Za-z\s&]+)",
        r"Berufsverband\s+([A-Z][A-Za-z\s&]+)",
        r"([A-Z][A-Za-z\s&]+)\s+(AG|GmbH|SA|SARL|Sàrl)",
        r"([A-Z][A-Za-z\s&]+)\s+Schule",
        r"([A-Z][A-Za-z\s&]+)\s+Institut",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'\s+', ' ', name)
            if len(name) > 3 and len(name) < 100:
                return name
    
    return None


def extract_seed_companies_from_cv_data(collection) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract seed companies from CV_DATA grouped by inferred canton and industry.
    
    Args:
        collection: Source collection.
    
    Returns:
        Dictionary mapping (canton, industry) to list of companies.
    """
    companies_by_location = defaultdict(list)
    seen_names = set()
    
    sample_size = min(500, collection.count_documents({}))
    sample_docs = list(collection.find().limit(sample_size))
    
    for doc in sample_docs:
        # Extract from weitere_informationen.adressen
        weitere_info = doc.get("weitere_informationen", {})
        if isinstance(weitere_info, dict):
            adressen = weitere_info.get("adressen", [])
            if isinstance(adressen, list):
                for addr in adressen:
                    if isinstance(addr, dict):
                        org_name = addr.get("name") or addr.get("organisation")
                        if org_name and org_name not in seen_names:
                            seen_names.add(org_name)
                            
                            # Try to infer canton from address
                            canton = "ZH"  # Default
                            if "ort" in addr or "city" in addr:
                                # Simple heuristic - could be improved
                                pass
                            
                            # Infer industry from berufsfeld
                            industry = "other"
                            if "categories" in doc and "berufsfelder" in doc["categories"]:
                                berufsfeld = doc["categories"]["berufsfelder"]
                                if isinstance(berufsfeld, list) and berufsfeld:
                                    industry = map_noga_branch_to_industry(berufsfeld[0])
                            
                            companies_by_location[(canton, industry)].append({
                                "name": org_name,
                                "is_real": True,
                                "source": "cv_data_adressen"
                            })
    
    return companies_by_location


def generate_companies_ai(
    canton: str,
    industry: str,
    branch_percentage: float,
    absolute_workers: int,
    seed_companies: List[str],
    count: int = 5
) -> List[Dict[str, Any]]:
    """
    Generate companies using AI with demographic and branch context.
    
    Args:
        canton: Canton code.
        industry: Industry name.
        branch_percentage: Percentage of workforce in this branch.
        absolute_workers: Absolute number of workers in this branch.
        seed_companies: List of real company names for context.
        count: Number of companies to generate.
    
    Returns:
        List of generated company dictionaries.
    """
    if not OPENAI_AVAILABLE or not settings.openai_api_key:
        return []
    
    seed_examples = ", ".join(seed_companies[:3]) if seed_companies else "None"
    
    prompt = f"""Generate Swiss {industry} companies for canton {canton}.

This sector employs {branch_percentage:.1f}% of Swiss workforce (~{absolute_workers:,} people).

Real companies in this sector: {seed_examples}.

Generate {count} additional realistic SME names with authentic Swiss legal forms (AG, GmbH, SA, SARL, Sàrl).
Company names should be:
- Authentic Swiss business names
- Include appropriate legal form suffix
- Realistic for {industry} industry in {canton}
- Mix of traditional and modern names
- Reflect the sector's employment size

Return JSON array: [{{"name": "Company Name AG", "size_band": "11-50", "is_real": false, "founded": 2010}}].
Only return valid JSON, no markdown, no explanation."""
    
    try:
        messages = [
            {"role": "system", "content": "You are a Swiss business naming expert. Return only valid JSON arrays."},
            {"role": "user", "content": prompt}
        ]
        
        # Try modern client first
        if _openai_client and hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=1000
            )
            content = response.choices[0].message.content.strip()
        else:
            # Fallback to legacy client
            import openai
            response = openai.ChatCompletion.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=1000
            )
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
        companies_data = json.loads(content)
        
        # Add metadata
        result = []
        for company in companies_data:
            if isinstance(company, dict) and "name" in company:
                result.append({
                    "name": company["name"],
                    "canton_code": canton,
                    "industry": industry,
                    "size_band": company.get("size_band", "11-50"),
                    "is_real": company.get("is_real", False),
                    "founded": company.get("founded"),
                    "noga_branch": None,  # Could be enhanced
                    "estimated_workforce": absolute_workers,
                    "source": "ai_generated"
                })
        
        return result
        
    except Exception as e:
        console.print(f"[red]❌ AI generation error for {canton}/{industry}: {e}[/red]")
        return []


def estimate_cost() -> float:
    """
    Estimate cost for generating companies.
    
    Returns:
        Estimated cost in USD.
    """
    return 0.12


def main():
    """Main function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Extract and Enhance Companies (with Demographics)[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        # 1. Load demographic & branch data
        console.print("[cyan]Loading demographic and branch data...[/cyan]")
        demo_data = load_demographic_data()
        branch_data = load_branch_data()
        
        if not demo_data or not branch_data:
            console.print("[yellow]⚠️  Some data files missing, continuing with available data[/yellow]")
        
        # Save combined data
        save_demographics_json(demo_data, branch_data)
        console.print()
        
        # Get database manager
        db_manager = get_db_manager()
        
        # Connect to MongoDB
        console.print("[cyan]Connecting to MongoDB...[/cyan]")
        db_manager.connect()
        console.print(f"[green]✅ Connected[/green]")
        console.print(f"   Source DB: {db_manager.source_db.name}")
        console.print(f"   Target DB: {db_manager.target_db.name}")
        console.print()
        
        # Get collections
        source_col = db_manager.get_source_collection(settings.mongodb_collection_occupations)
        target_col = db_manager.get_target_collection("companies")
        cantons_col = db_manager.get_target_collection("cantons")
        
        # Load canton data for workforce
        canton_workforce = {}
        for canton_doc in cantons_col.find({}, {"code": 1, "workforce": 1, "population": 1}):
            code = canton_doc.get("code", "")
            workforce = canton_doc.get("workforce")
            if not workforce:
                # Estimate workforce as ~50% of population
                workforce = int(canton_doc.get("population", 0) * 0.5)
            canton_workforce[code] = workforce
        
        console.print(f"[cyan]Loaded workforce data for {len(canton_workforce)} cantons[/cyan]")
        console.print()
        
        # 2. Extract seed companies from CV_DATA
        console.print("[cyan]Extracting seed companies from CV_DATA...[/cyan]")
        seed_companies_by_location = extract_seed_companies_from_cv_data(source_col)
        total_seed = sum(len(companies) for companies in seed_companies_by_location.values())
        console.print(f"[green]✅ Extracted {total_seed} seed companies[/green]")
        console.print()
        
        # 3. Get existing company names for deduplication
        existing_names = set()
        for company in target_col.find({}, {"name": 1}):
            if company.get("name"):
                existing_names.add(company["name"].lower())
        
        console.print(f"[cyan]Found {len(existing_names)} existing companies in target DB[/cyan]")
        console.print()
        
        # 4. Generate companies based on demographic data
        console.print("[cyan]Generating companies with demographic context...[/cyan]")
        console.print(f"[dim]Estimated cost: ~${estimate_cost():.2f}[/dim]")
        console.print()
        
        all_companies = []
        
        # Get branch percentages (already extracted in load_branch_data)
        branch_percentages = branch_data
        
        # Create canton+industry combinations with priorities
        combinations = []
        
        # Major cantons
        major_cantons = ["ZH", "BE", "VD", "AG", "SG", "BS", "GE", "LU", "TI", "VS"]
        
        # Process each branch
        for branch, percentage in sorted(branch_percentages.items(), key=lambda x: x[1], reverse=True):
            industry = map_noga_branch_to_industry(branch)
            
            # Skip "Übrige/Nicht separat erfasst" as it's too generic
            if "Übrige" in branch or "Nicht separat" in branch:
                continue
            
            # Prioritize branches with higher employment
            if percentage > 0.5:  # Only branches with >0.5% employment
                for canton in major_cantons:
                    workforce = canton_workforce.get(canton, 100000)
                    companies_needed = calculate_companies_needed(workforce, percentage)
                    
                    if companies_needed > 0:
                        combinations.append({
                            "canton": canton,
                            "industry": industry,
                            "branch": branch,
                            "percentage": percentage,
                            "companies_needed": companies_needed,
                            "absolute_workers": int(workforce * (percentage / 100))
                        })
        
        # Sort by priority (higher percentage first)
        combinations.sort(key=lambda x: x["percentage"], reverse=True)
        
        # Limit to top combinations for cost control
        combinations = combinations[:150]  # Limit to ~150 combinations
        
        total_combinations = len(combinations)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Generating companies...",
                total=total_combinations
            )
            
            for combo in combinations:
                try:
                    canton = combo["canton"]
                    industry = combo["industry"]
                    branch = combo["branch"]
                    percentage = combo["percentage"]
                    absolute_workers = combo["absolute_workers"]
                    companies_needed = min(combo["companies_needed"], 8)  # Cap at 8
                    
                    # Get seed companies for this location
                    seed_list = seed_companies_by_location.get((canton, industry), [])
                    seed_names = [c["name"] for c in seed_list]
                    
                    # Generate companies
                    generated = generate_companies_ai(
                        canton,
                        industry,
                        percentage,
                        absolute_workers,
                        seed_names,
                        count=companies_needed
                    )
                    
                    # Add branch metadata
                    for company in generated:
                        company["noga_branch"] = branch
                    
                    # Deduplicate
                    for company in generated:
                        if company["name"].lower() not in existing_names:
                            all_companies.append(company)
                            existing_names.add(company["name"].lower())
                    
                    progress.update(task, advance=1)
                    
                    # Rate limiting
                    if settings.ai_rate_limit_delay > 0:
                        time.sleep(settings.ai_rate_limit_delay)
                        
                except Exception as e:
                    console.print(f"[red]❌ Error generating {combo['canton']}/{combo['industry']}: {e}[/red]")
                    progress.update(task, advance=1)
                    continue
        
        console.print()
        console.print(f"[green]✅ Generated {len(all_companies)} new companies[/green]")
        console.print()
        
        # 5. Insert seed companies
        console.print("[cyan]Inserting seed companies...[/cyan]")
        real_inserted = 0
        
        for (canton, industry), companies in seed_companies_by_location.items():
            for seed_company in companies:
                company_doc = {
                    "name": seed_company["name"],
                    "canton_code": canton,
                    "industry": industry,
                    "size_band": None,
                    "is_real": True,
                    "founded": None,
                    "noga_branch": None,
                    "estimated_workforce": None,
                    "source": seed_company.get("source", "cv_data")
                }
                
                try:
                    result = target_col.update_one(
                        {"name": company_doc["name"]},
                        {"$set": company_doc},
                        upsert=True
                    )
                    
                    if result.upserted_id or result.modified_count > 0:
                        real_inserted += 1
                except Exception as e:
                    console.print(f"[red]❌ Error inserting {seed_company['name']}: {e}[/red]")
        
        console.print(f"[green]✅ Inserted {real_inserted} seed companies[/green]")
        console.print()
        
        # 6. Insert AI-generated companies
        console.print("[cyan]Inserting AI-generated companies...[/cyan]")
        ai_inserted = 0
        
        for company in all_companies:
            try:
                result = target_col.update_one(
                    {"name": company["name"]},
                    {"$set": company},
                    upsert=True
                )
                
                if result.upserted_id or result.modified_count > 0:
                    ai_inserted += 1
            except Exception as e:
                console.print(f"[red]❌ Error inserting {company['name']}: {e}[/red]")
        
        console.print(f"[green]✅ Inserted {ai_inserted} AI-generated companies[/green]")
        console.print()
        
        # 7. Print Statistics
        console.print("[bold cyan]Statistics[/bold cyan]")
        console.print()
        
        total_companies = target_col.count_documents({})
        real_companies = target_col.count_documents({"is_real": True})
        ai_companies = target_col.count_documents({"is_real": False})
        
        # Summary table
        table = Table(title="Company Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Real companies from CV_DATA", str(real_inserted))
        table.add_row("AI-generated companies", str(ai_inserted))
        table.add_row("Total unique companies", str(total_companies))
        table.add_row("Real companies (total)", str(real_companies))
        table.add_row("AI companies (total)", str(ai_companies))
        
        console.print(table)
        console.print()
        
        # Companies by canton
        canton_counts = {}
        for company in target_col.find({}, {"canton_code": 1}):
            canton = company.get("canton_code", "unknown")
            canton_counts[canton] = canton_counts.get(canton, 0) + 1
        
        if canton_counts:
            table = Table(title="Companies by Canton (Top 10)")
            table.add_column("Canton", style="cyan")
            table.add_column("Count", style="green", justify="right")
            
            for canton, count in sorted(canton_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                table.add_row(canton, str(count))
            
            console.print(table)
            console.print()
        
        # Companies by industry (sorted by NOGA %)
        industry_counts = {}
        industry_branches = {}
        for company in target_col.find({}, {"industry": 1, "noga_branch": 1}):
            industry = company.get("industry", "unknown")
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
            if company.get("noga_branch"):
                industry_branches[industry] = company.get("noga_branch")
        
        if industry_counts:
            table = Table(title="Companies by Industry (sorted by NOGA %)")
            table.add_column("Industry", style="cyan")
            table.add_column("Count", style="green", justify="right")
            table.add_column("NOGA Branch", style="yellow")
            table.add_column("Workforce %", style="magenta", justify="right")
            
            # Sort by branch percentage if available
            sorted_industries = sorted(
                industry_counts.items(),
                key=lambda x: branch_percentages.get(industry_branches.get(x[0], ""), 0),
                reverse=True
            )
            
            for industry, count in sorted_industries:
                branch = industry_branches.get(industry, "")
                percentage = branch_percentages.get(branch, 0)
                table.add_row(
                    industry,
                    str(count),
                    branch or "N/A",
                    f"{percentage:.1f}%" if percentage > 0 else "N/A"
                )
            
            console.print(table)
            console.print()
        
        # Coverage calculation
        total_workforce_represented = 0
        for company in target_col.find({}, {"estimated_workforce": 1}):
            workforce = company.get("estimated_workforce")
            if workforce:
                total_workforce_represented += workforce
        
        console.print(f"[cyan]Coverage:[/cyan]")
        console.print(f"   Total workforce represented: {total_workforce_represented:,}")
        console.print()
        
        console.print(f"[yellow]💰 Estimated cost: ~${estimate_cost():.2f}[/yellow]")
        console.print()
        console.print("[bold green]✅ Extraction and generation complete![/bold green]")
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
