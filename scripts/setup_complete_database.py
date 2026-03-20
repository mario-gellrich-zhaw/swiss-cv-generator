"""
Complete database setup script.

This script runs all setup scripts in the correct order:
1. Initialize collections
2. Analyze CV_DATA
3. Setup demographic sampling
4. Organize portrait images
5. Generate cantons
6. Generate first names
7. Generate last names
8. Extract skills
9. Extract and enhance companies

Run: python scripts/setup_complete_database.py
"""
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from src.config import get_settings
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from pymongo.errors import OperationFailure

console = Console()
settings = get_settings()


def run_script(script_path: str, description: str) -> bool:
    """
    Run a Python script and return success status.
    
    Args:
        script_path: Path to script.
        description: Description of what the script does.
    
    Returns:
        True if successful, False otherwise.
    """
    console.print(f"[cyan]Running: {description}...[/cyan]")
    
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            console.print(f"[green]✅ {description} completed[/green]")
            return True
        else:
            console.print(f"[red]❌ {description} failed[/red]")
            if result.stderr:
                console.print(f"[dim]{result.stderr[:500]}[/dim]")
            return False
    except subprocess.TimeoutExpired:
        console.print(f"[red]❌ {description} timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]❌ {description} error: {e}[/red]")
        return False


def get_database_statistics() -> Dict[str, Any]:
    """Get statistics from both databases."""
    stats = {
        "source_db": {},
        "target_db": {},
        "portraits": {},
        "demographic": {}
    }
    
    try:
        db_manager = get_db_manager()
        db_manager.connect()
        
        # SOURCE DB statistics
        source_col = db_manager.get_source_collection(settings.mongodb_collection_occupations)
        total_occupations = source_col.count_documents({})
        
        # Calculate average completeness
        pipeline = [
            {"$group": {
                "_id": None,
                "avg_completeness": {"$avg": "$data_completeness.completeness_score"}
            }}
        ]
        completeness_result = list(source_col.aggregate(pipeline))
        avg_completeness = completeness_result[0].get("avg_completeness", 0) if completeness_result else 0
        
        stats["source_db"] = {
            "occupations": total_occupations,
            "avg_completeness": avg_completeness
        }
        
        # TARGET DB statistics
        target_db = db_manager.target_db
        
        stats["target_db"] = {
            "cantons": target_db.cantons.count_documents({}),
            "first_names": target_db.first_names.count_documents({}),
            "last_names": target_db.last_names.count_documents({}),
            "companies": target_db.companies.count_documents({}),
            "occupation_skills": target_db.occupation_skills.count_documents({}),
            "demographic_config": target_db.demographic_config.count_documents({}) > 0
        }
        
        # Calculate workforce coverage
        companies = list(target_db.companies.find({}, {"estimated_workforce": 1}))
        total_workforce_represented = sum(
            c.get("estimated_workforce", 0) for c in companies if c.get("estimated_workforce")
        )
        
        # Estimate total Swiss workforce (from demographic data)
        total_swiss_workforce = 5_200_000  # Approximate
        workforce_coverage = (total_workforce_represented / total_swiss_workforce * 100) if total_swiss_workforce > 0 else 0
        
        stats["target_db"]["workforce_coverage"] = workforce_coverage
        
        # Portrait statistics
        portrait_index_file = project_root / "data" / "portraits" / "portrait_index.json"
        if portrait_index_file.exists():
            import json
            with open(portrait_index_file, "r", encoding="utf-8") as f:
                portrait_data = json.load(f)
            
            portrait_index = portrait_data.get("portrait_index", {})
            stats["portraits"] = {
                "total": portrait_data.get("total_images", 0),
                "male": {
                    "total": len(portrait_index.get("male", {}).get("18-25", [])) +
                             len(portrait_index.get("male", {}).get("26-40", [])) +
                             len(portrait_index.get("male", {}).get("41-65", [])),
                    "18-25": len(portrait_index.get("male", {}).get("18-25", [])),
                    "26-40": len(portrait_index.get("male", {}).get("26-40", [])),
                    "41-65": len(portrait_index.get("male", {}).get("41-65", []))
                },
                "female": {
                    "total": len(portrait_index.get("female", {}).get("18-25", [])) +
                              len(portrait_index.get("female", {}).get("26-40", [])) +
                              len(portrait_index.get("female", {}).get("41-65", [])),
                    "18-25": len(portrait_index.get("female", {}).get("18-25", [])),
                    "26-40": len(portrait_index.get("female", {}).get("26-40", [])),
                    "41-65": len(portrait_index.get("female", {}).get("41-65", []))
                }
            }
        
        # Demographic setup statistics
        sampling_file = project_root / "data" / "sampling_weights.json"
        if sampling_file.exists():
            import json
            with open(sampling_file, "r", encoding="utf-8") as f:
                sampling_data = json.load(f)
            
            gender_dist = sampling_data.get("gender_distribution", {})
            stats["demographic"] = {
                "age_distribution_configured": True,
                "gender_male_pct": gender_dist.get("male", {}).get("percentage", 0),
                "gender_female_pct": gender_dist.get("female", {}).get("percentage", 0),
                "career_level_mappings": True,
                "industry_weights": True
            }
        
        db_manager.close()
        
    except Exception as e:
        console.print(f"[yellow]⚠️  Error getting statistics: {e}[/yellow]")
    
    return stats


def main():
    """Main setup function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Complete Database Setup[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    start_time = datetime.now()
    
    # Define setup steps
    setup_steps = [
        {
            "script": "src/database/init_collections.py",
            "description": "Initialize Collections",
            "required": True
        },
        {
            "script": "scripts/analyze_cv_data_occupations.py",
            "description": "Analyze CV_DATA",
            "required": False
        },
        {
            "script": "scripts/setup_demographic_sampling.py",
            "description": "Setup Demographic Sampling",
            "required": True
        },
        {
            "script": "scripts/organize_portrait_images.py",
            "description": "Organize Portrait Images",
            "required": False
        },
        {
            "script": "scripts/ai_generate_cantons.py",
            "description": "Generate Cantons",
            "required": True
        },
        {
            "script": "scripts/ai_generate_first_names.py",
            "description": "Generate First Names",
            "required": True
        },
        {
            "script": "scripts/ai_generate_last_names.py",
            "description": "Generate Last Names",
            "required": True
        },
        {
            "script": "scripts/extract_skills_from_cv_data.py",
            "description": "Extract Skills",
            "required": True
        },
        {
            "script": "scripts/extract_and_enhance_companies.py",
            "description": "Extract and Enhance Companies",
            "required": True
        },
    ]
    
    # Track results
    results = []
    total_cost = 0.0
    
    # Cost estimates per script
    cost_estimates = {
        "scripts/ai_generate_cantons.py": 0.02,
        "scripts/ai_generate_first_names.py": 0.05,
        "scripts/ai_generate_last_names.py": 0.04,
        "scripts/extract_skills_from_cv_data.py": 0.01,
        "scripts/extract_and_enhance_companies.py": 0.12,
    }
    
    # Run setup steps
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Running setup steps...", total=len(setup_steps))
        
        for step in setup_steps:
            script_path = project_root / step["script"]
            
            if not script_path.exists():
                console.print(f"[yellow]⚠️  Script not found: {step['script']}[/yellow]")
                if step["required"]:
                    console.print(f"[red]❌ Required script missing, aborting[/red]")
                    sys.exit(1)
                progress.update(task, advance=1)
                continue
            
            success = run_script(str(script_path), step["description"])
            results.append({
                "step": step["description"],
                "success": success,
                "required": step["required"]
            })
            
            # Add cost if applicable
            if step["script"] in cost_estimates:
                total_cost += cost_estimates[step["script"]]
            
            progress.update(task, advance=1)
            console.print()
    
    # Check for failures
    failed_required = [r for r in results if not r["success"] and r["required"]]
    if failed_required:
        console.print("[red]❌ Some required steps failed:[/red]")
        for result in failed_required:
            console.print(f"  - {result['step']}")
        console.print()
    
    # Get final statistics
    console.print("[cyan]Collecting final statistics...[/cyan]")
    stats = get_database_statistics()
    console.print()
    
    # Display results
    console.print("[bold cyan]Setup Results[/bold cyan]")
    console.print()
    
    # Summary table
    table = Table(title="Setup Steps")
    table.add_column("Step", style="cyan")
    table.add_column("Status", style="green")
    
    for result in results:
        status = "✅ Success" if result["success"] else "❌ Failed"
        if not result["success"] and result["required"]:
            status = "❌ Failed (Required)"
        table.add_row(result["step"], status)
    
    console.print(table)
    console.print()
    
    # Database statistics
    console.print("[bold cyan]Database Statistics[/bold cyan]")
    console.print()
    
    # SOURCE DB
    console.print("[bold]SOURCE DB (CV_DATA):[/bold]")
    source_stats = stats.get("source_db", {})
    console.print(f"  Occupations: {source_stats.get('occupations', 0):,}")
    console.print(f"  Avg completeness: {source_stats.get('avg_completeness', 0):.2f}")
    console.print()
    
    # TARGET DB
    console.print("[bold]TARGET DB (swiss_cv_generator):[/bold]")
    target_stats = stats.get("target_db", {})
    console.print(f"  Cantons: {target_stats.get('cantons', 0)}")
    console.print(f"  First Names: {target_stats.get('first_names', 0):,}")
    console.print(f"  Last Names: {target_stats.get('last_names', 0):,}")
    console.print(f"  Companies: {target_stats.get('companies', 0):,} (representing {target_stats.get('workforce_coverage', 0):.1f}% of workforce)")
    console.print(f"  Occupation Skills: {target_stats.get('occupation_skills', 0):,}")
    console.print(f"  Demographic Config: {'✓' if target_stats.get('demographic_config', False) else '✗'}")
    console.print()
    
    # Portrait data
    console.print("[bold]PORTRAIT DATA:[/bold]")
    portrait_stats = stats.get("portraits", {})
    if portrait_stats:
        console.print(f"  Total portraits: {portrait_stats.get('total', 0)}")
        male_stats = portrait_stats.get("male", {})
        console.print(f"  Male portraits: {male_stats.get('total', 0)} (18-25: {male_stats.get('18-25', 0)}, 26-40: {male_stats.get('26-40', 0)}, 41-65: {male_stats.get('41-65', 0)})")
        female_stats = portrait_stats.get("female", {})
        console.print(f"  Female portraits: {female_stats.get('total', 0)} (18-25: {female_stats.get('18-25', 0)}, 26-40: {female_stats.get('26-40', 0)}, 41-65: {female_stats.get('41-65', 0)})")
        
        # Check coverage
        all_age_groups_covered = (
            male_stats.get('18-25', 0) > 0 and
            male_stats.get('26-40', 0) > 0 and
            male_stats.get('41-65', 0) > 0 and
            female_stats.get('18-25', 0) > 0 and
            female_stats.get('26-40', 0) > 0 and
            female_stats.get('41-65', 0) > 0
        )
        console.print(f"  Coverage: {'All age groups ✓' if all_age_groups_covered else 'Some age groups missing ✗'}")
    else:
        console.print("  No portrait data found")
    console.print()
    
    # Demographic setup
    console.print("[bold]DEMOGRAPHIC SETUP:[/bold]")
    demo_stats = stats.get("demographic", {})
    if demo_stats:
        console.print(f"  Age distribution configured: {'✓' if demo_stats.get('age_distribution_configured', False) else '✗'}")
        male_pct = demo_stats.get('gender_male_pct', 0)
        female_pct = demo_stats.get('gender_female_pct', 0)
        console.print(f"  Gender distribution: {male_pct:.1f}% M / {female_pct:.1f}% F")
        console.print(f"  Career level mappings: {'✓' if demo_stats.get('career_level_mappings', False) else '✗'}")
        console.print(f"  Industry weights (NOGA): {'✓' if demo_stats.get('industry_weights', False) else '✗'}")
    else:
        console.print("  Demographic setup not found")
    console.print()
    
    # Cost summary
    console.print("[bold cyan]Cost Summary[/bold cyan]")
    console.print()
    console.print(f"💰 Estimated total cost: ~${total_cost:.2f}")
    console.print()
    
    # Time summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    console.print(f"⏱️  Total setup time: {minutes}m {seconds}s")
    console.print()
    
    # Final status
    if not failed_required:
        console.print("[bold green]✅ Database setup complete![/bold green]")
        console.print()
        console.print("All required steps completed successfully.")
        console.print("The database is ready for CV generation.")
    else:
        console.print("[bold yellow]⚠️  Setup completed with some failures[/bold yellow]")
        console.print("Please review the failed steps above.")
    
    console.print()


if __name__ == "__main__":
    main()

