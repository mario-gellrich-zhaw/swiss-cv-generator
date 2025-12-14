"""
Setup demographic sampling configuration for CV generation.

This script:
1. Loads demographic data from JSON files
2. Calculates sampling weights for age groups and gender
3. Creates career level mappings
4. Stores configuration in MongoDB and JSON file

Run: python scripts/setup_demographic_sampling.py
"""
import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from src.config import get_settings
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pymongo.errors import OperationFailure

console = Console()
settings = get_settings()


def load_demographic_data() -> Dict[str, Any]:
    """
    Load demographic data from JSON file.
    
    Returns:
        Dictionary with demographic data.
    """
    demo_file = project_root / "data" / "source" / "Bevölkerungsdaten.json"
    
    if not demo_file.exists():
        console.print(f"[red]❌ Demographic data file not found: {demo_file}[/red]")
        sys.exit(1)
    
    with open(demo_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data


def calculate_sampling_weights(demo_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate sampling weights from demographic data.
    
    Args:
        demo_data: Demographic data dictionary.
    
    Returns:
        Dictionary with sampling weights and distributions.
    """
    # Extract age group data
    altersstruktur = demo_data.get("altersstruktur_detailliert", [])
    
    age_groups = {}
    total_18_65 = 0
    
    for group in altersstruktur:
        altersgruppe = group.get("altersgruppe", "")
        total_personen = group.get("total_personen_ca", 0)
        anteil_prozent = group.get("total_anteil_prozent_ca", 0)
        
        if "18-25" in altersgruppe:
            age_groups["18-25"] = {
                "total_personen": total_personen,
                "anteil_prozent": anteil_prozent,
                "career_level": "junior"
            }
            total_18_65 += total_personen
        elif "26-40" in altersgruppe:
            age_groups["26-40"] = {
                "total_personen": total_personen,
                "anteil_prozent": anteil_prozent,
                "career_level": "mid"
            }
            total_18_65 += total_personen
        elif "41-65" in altersgruppe:
            age_groups["41-65"] = {
                "total_personen": total_personen,
                "anteil_prozent": anteil_prozent,
                "career_level": "senior"
            }
            total_18_65 += total_personen
    
    # Calculate gender distribution from data
    total_male = 0
    total_female = 0
    
    for group in altersstruktur:
        daten = group.get("daten", [])
        for item in daten:
            geschlecht = item.get("geschlecht", "")
            anzahl = item.get("anzahl_personen_ca", 0)
            
            if "Männer" in geschlecht or "Mann" in geschlecht:
                total_male += anzahl
            elif "Frauen" in geschlecht or "Frau" in geschlecht:
                total_female += anzahl
    
    total_population = total_male + total_female
    male_percentage = (total_male / total_population * 100) if total_population > 0 else 50.0
    female_percentage = (total_female / total_population * 100) if total_population > 0 else 50.0
    
    # Create sampling weights
    sampling_config = {
        "age_groups": {
            "18-25": {
                "weight": age_groups.get("18-25", {}).get("anteil_prozent", 7.6),
                "total_personen": age_groups.get("18-25", {}).get("total_personen_ca", 693000),
                "career_level_distribution": {
                    "junior": 0.90,
                    "mid": 0.10,
                    "senior": 0.0,
                    "lead": 0.0
                }
            },
            "26-40": {
                "weight": age_groups.get("26-40", {}).get("anteil_prozent", 18.5),
                "total_personen": age_groups.get("26-40", {}).get("total_personen_ca", 1685000),
                "career_level_distribution": {
                    "junior": 0.20,
                    "mid": 0.60,
                    "senior": 0.20,
                    "lead": 0.0
                }
            },
            "41-65": {
                "weight": age_groups.get("41-65", {}).get("anteil_prozent", 31.0),
                "total_personen": age_groups.get("41-65", {}).get("total_personen_ca", 2820000),
                "career_level_distribution": {
                    "junior": 0.0,
                    "mid": 0.05,
                    "senior": 0.60,
                    "lead": 0.35
                }
            }
        },
        "gender_distribution": {
            "male": {
                "percentage": male_percentage,
                "total_personen": total_male
            },
            "female": {
                "percentage": female_percentage,
                "total_personen": total_female
            }
        },
        "total_population_18_65": total_18_65,
        "source": "mario_daten/Bevölkerungsdaten.json",
        "created_at": datetime.now().isoformat()
    }
    
    return sampling_config


def calculate_expected_distribution(config: Dict[str, Any], sample_size: int = 1000) -> Dict[str, Any]:
    """
    Calculate expected distribution for a given sample size.
    
    Args:
        config: Sampling configuration.
        sample_size: Number of CVs to generate.
    
    Returns:
        Dictionary with expected distributions.
    """
    age_groups = config["age_groups"]
    gender_dist = config["gender_distribution"]
    
    expected = {
        "sample_size": sample_size,
        "by_age_group": {},
        "by_gender": {},
        "by_career_level": {
            "junior": 0,
            "mid": 0,
            "senior": 0,
            "lead": 0
        }
    }
    
    # Calculate by age group
    for age_group, data in age_groups.items():
        weight = data["weight"] / 100.0
        count = int(sample_size * weight)
        expected["by_age_group"][age_group] = count
        
        # Calculate career level distribution within age group
        career_dist = data["career_level_distribution"]
        for level, level_weight in career_dist.items():
            expected["by_career_level"][level] += int(count * level_weight)
    
    # Calculate by gender
    male_pct = gender_dist["male"]["percentage"] / 100.0
    female_pct = gender_dist["female"]["percentage"] / 100.0
    
    expected["by_gender"]["male"] = int(sample_size * male_pct)
    expected["by_gender"]["female"] = int(sample_size * female_pct)
    
    return expected


def main():
    """Main function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Setup Demographic Sampling Configuration[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        # 1. Load demographic data
        console.print("[cyan]Loading demographic data...[/cyan]")
        demo_data = load_demographic_data()
        console.print("[green]✅ Demographic data loaded[/green]")
        console.print()
        
        # 2. Calculate sampling weights
        console.print("[cyan]Calculating sampling weights...[/cyan]")
        sampling_config = calculate_sampling_weights(demo_data)
        console.print("[green]✅ Sampling weights calculated[/green]")
        console.print()
        
        # 3. Save to JSON file
        output_file = project_root / "data" / "sampling_weights.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sampling_config, f, ensure_ascii=False, indent=2)
        
        console.print(f"[green]✅ Configuration saved to {output_file}[/green]")
        console.print()
        
        # 4. Store in MongoDB
        console.print("[cyan]Storing configuration in MongoDB...[/cyan]")
        db_manager = get_db_manager()
        db_manager.connect()
        
        config_col = db_manager.get_target_collection("demographic_config")
        
        # Store with versioning
        config_doc = {
            "version": "1.0",
            "config": sampling_config,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        result = config_col.update_one(
            {"version": "1.0"},
            {"$set": config_doc},
            upsert=True
        )
        
        if result.upserted_id or result.modified_count > 0:
            console.print("[green]✅ Configuration stored in MongoDB[/green]")
        console.print()
        
        # 5. Display configuration
        console.print("[bold cyan]Sampling Configuration[/bold cyan]")
        console.print()
        
        # Age groups table
        table = Table(title="Age Group Weights")
        table.add_column("Age Group", style="cyan")
        table.add_column("Weight %", style="green", justify="right")
        table.add_column("Total Personen", style="yellow", justify="right")
        table.add_column("Career Level Distribution", style="magenta")
        
        for age_group, data in sampling_config["age_groups"].items():
            career_dist = data["career_level_distribution"]
            career_str = ", ".join([f"{k}:{v:.0%}" for k, v in career_dist.items() if v > 0])
            
            table.add_row(
                age_group,
                f"{data['weight']:.1f}%",
                f"{data['total_personen']:,}",
                career_str
            )
        
        console.print(table)
        console.print()
        
        # Gender distribution table
        table = Table(title="Gender Distribution")
        table.add_column("Gender", style="cyan")
        table.add_column("Percentage", style="green", justify="right")
        table.add_column("Total Personen", style="yellow", justify="right")
        
        gender_dist = sampling_config["gender_distribution"]
        table.add_row(
            "Male",
            f"{gender_dist['male']['percentage']:.1f}%",
            f"{gender_dist['male']['total_personen']:,}"
        )
        table.add_row(
            "Female",
            f"{gender_dist['female']['percentage']:.1f}%",
            f"{gender_dist['female']['total_personen']:,}"
        )
        
        console.print(table)
        console.print()
        
        # 6. Validation: Expected distribution for 1000 CVs
        console.print("[bold cyan]Validation: Expected Distribution for 1000 CVs[/bold cyan]")
        console.print()
        
        expected = calculate_expected_distribution(sampling_config, sample_size=1000)
        
        # Age group distribution
        table = Table(title="Expected Distribution by Age Group")
        table.add_column("Age Group", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Percentage", style="yellow", justify="right")
        
        total_age = sum(expected["by_age_group"].values())
        for age_group, count in expected["by_age_group"].items():
            pct = (count / total_age * 100) if total_age > 0 else 0
            table.add_row(age_group, str(count), f"{pct:.1f}%")
        
        console.print(table)
        console.print()
        
        # Career level distribution
        table = Table(title="Expected Distribution by Career Level")
        table.add_column("Career Level", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Percentage", style="yellow", justify="right")
        
        total_career = sum(expected["by_career_level"].values())
        for level, count in expected["by_career_level"].items():
            pct = (count / total_career * 100) if total_career > 0 else 0
            table.add_row(level, str(count), f"{pct:.1f}%")
        
        console.print(table)
        console.print()
        
        # Gender distribution
        table = Table(title="Expected Distribution by Gender")
        table.add_column("Gender", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Percentage", style="yellow", justify="right")
        
        for gender, count in expected["by_gender"].items():
            pct = (count / 1000 * 100)
            table.add_row(gender, str(count), f"{pct:.1f}%")
        
        console.print(table)
        console.print()
        
        # 7. Verify realistic career progression
        console.print("[bold cyan]Career Progression Validation[/bold cyan]")
        console.print()
        
        validation_checks = []
        
        # Check: 18-25 should be mostly junior
        junior_18_25 = sampling_config["age_groups"]["18-25"]["career_level_distribution"]["junior"]
        if junior_18_25 >= 0.85:
            validation_checks.append(("✅ 18-25 age group: Mostly junior (≥85%)", True))
        else:
            validation_checks.append(("⚠️  18-25 age group: Junior < 85%", False))
        
        # Check: 26-40 should be mostly mid
        mid_26_40 = sampling_config["age_groups"]["26-40"]["career_level_distribution"]["mid"]
        if mid_26_40 >= 0.50:
            validation_checks.append(("✅ 26-40 age group: Mostly mid (≥50%)", True))
        else:
            validation_checks.append(("⚠️  26-40 age group: Mid < 50%", False))
        
        # Check: 41-65 should be mostly senior/lead
        senior_41_65 = sampling_config["age_groups"]["41-65"]["career_level_distribution"]["senior"]
        lead_41_65 = sampling_config["age_groups"]["41-65"]["career_level_distribution"]["lead"]
        if (senior_41_65 + lead_41_65) >= 0.85:
            validation_checks.append(("✅ 41-65 age group: Mostly senior/lead (≥85%)", True))
        else:
            validation_checks.append(("⚠️  41-65 age group: Senior/Lead < 85%", False))
        
        # Check: Gender should be balanced
        male_pct = sampling_config["gender_distribution"]["male"]["percentage"]
        if 45 <= male_pct <= 55:
            validation_checks.append(("✅ Gender distribution: Balanced (45-55%)", True))
        else:
            validation_checks.append(("⚠️  Gender distribution: Not balanced", False))
        
        for check, passed in validation_checks:
            if passed:
                console.print(f"  {check}")
            else:
                console.print(f"  {check}")
        
        console.print()
        console.print("[bold green]✅ Demographic sampling configuration complete![/bold green]")
        console.print()
        console.print(f"Configuration files:")
        console.print(f"  - JSON: {output_file}")
        console.print(f"  - MongoDB: demographic_config collection")
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

