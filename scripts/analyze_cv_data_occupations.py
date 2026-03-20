"""
Analyze CV_DATA.cv_berufsberatung collection and create mapping file.

This script:
1. Connects to CV_DATA.cv_berufsberatung (SOURCE DB)
2. Analyzes data structure and completeness
3. Creates data/cv_data_mapping.json with field mappings
4. Generates statistics and recommendations

Run: python scripts/analyze_cv_data_occupations.py
"""
import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter, defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.mongodb_manager import get_db_manager
from src.config import get_settings
from rich.console import Console
from rich.table import Table
from pymongo.errors import OperationFailure

console = Console()
settings = get_settings()


def analyze_data_structure(collection) -> Dict[str, Any]:
    """
    Analyze the data structure of the collection.
    
    Args:
        collection: MongoDB collection.
    
    Returns:
        Dictionary with analysis results.
    """
    analysis = {
        "total_documents": collection.count_documents({}),
        "completeness_scores": [],
        "bildungstypen": set(),
        "berufsfelder": set(),
        "occupations_per_berufsfeld": Counter(),
        "field_completeness": defaultdict(int),
        "all_fields": set()
    }
    
    # Sample documents to analyze structure
    sample_size = min(1000, analysis["total_documents"])
    sample_docs = list(collection.find().limit(sample_size))
    
    for doc in sample_docs:
        # Collect all field names
        analysis["all_fields"].update(doc.keys())
        
        # Completeness score
        if "completeness_score" in doc:
            analysis["completeness_scores"].append(doc["completeness_score"])
        
        # Bildungstypen
        if "categories" in doc and "bildungstypen" in doc["categories"]:
            bildungstyp = doc["categories"]["bildungstypen"]
            if isinstance(bildungstyp, list):
                analysis["bildungstypen"].update(bildungstyp)
            elif bildungstyp:
                analysis["bildungstypen"].add(bildungstyp)
        
        # Berufsfelder
        if "categories" in doc and "berufsfelder" in doc["categories"]:
            berufsfeld = doc["categories"]["berufsfelder"]
            if isinstance(berufsfeld, list):
                for bf in berufsfeld:
                    if bf:
                        analysis["berufsfelder"].add(bf)
                        analysis["occupations_per_berufsfeld"][bf] += 1
            elif berufsfeld:
                analysis["berufsfelder"].add(berufsfeld)
                analysis["occupations_per_berufsfeld"][berufsfeld] += 1
        
        # Field completeness
        for field in doc.keys():
            if doc[field] is not None and doc[field] != "":
                if isinstance(doc[field], (dict, list)):
                    if doc[field]:  # Non-empty dict/list
                        analysis["field_completeness"][field] += 1
                else:
                    analysis["field_completeness"][field] += 1
    
    # Convert sets to sorted lists
    analysis["bildungstypen"] = sorted(list(analysis["bildungstypen"]))
    analysis["berufsfelder"] = sorted(list(analysis["berufsfelder"]))
    analysis["all_fields"] = sorted(list(analysis["all_fields"]))
    
    return analysis


def map_berufsfeld_to_industry(berufsfeld: str) -> str:
    """
    Map Berufsfeld to Industry enum.
    
    Args:
        berufsfeld: Berufsfeld string.
    
    Returns:
        Industry enum value.
    """
    if not berufsfeld:
        return "other"
    
    berufsfeld_lower = berufsfeld.lower()
    
    # Check for IT/Informatik
    if "informatik" in berufsfeld_lower or "it" in berufsfeld_lower:
        return "technology"
    
    # Check for Wirtschaft/Finanz
    if "wirtschaft" in berufsfeld_lower or "finanz" in berufsfeld_lower:
        return "finance"
    
    # Check for Gesundheit
    if "gesundheit" in berufsfeld_lower:
        return "healthcare"
    
    # Check for Bau
    if "bau" in berufsfeld_lower:
        return "construction"
    
    # Check for manufacturing
    if "produktion" in berufsfeld_lower or "industrie" in berufsfeld_lower:
        return "manufacturing"
    
    # Check for education
    if "bildung" in berufsfeld_lower or "erziehung" in berufsfeld_lower:
        return "education"
    
    # Check for retail
    if "handel" in berufsfeld_lower or "verkauf" in berufsfeld_lower:
        return "retail"
    
    # Check for hospitality
    if "gastronomie" in berufsfeld_lower or "hotellerie" in berufsfeld_lower:
        return "hospitality"
    
    # Default to other
    return "other"


def create_mapping_file(analysis: Dict[str, Any], collection_name: str, database_name: str) -> Dict[str, Any]:
    """
    Create mapping file structure.
    
    Args:
        analysis: Analysis results.
        collection_name: Name of the collection.
        database_name: Name of the database.
    
    Returns:
        Mapping dictionary.
    """
    # Create industry mapping
    industry_mapping = {}
    for berufsfeld in analysis["berufsfelder"]:
        industry_mapping[berufsfeld] = map_berufsfeld_to_industry(berufsfeld)
    
    mapping = {
        "source_database": {
            "database": database_name,
            "collection": collection_name,
            "total_documents": analysis["total_documents"],
            "sample_size": len(analysis["completeness_scores"]) if analysis["completeness_scores"] else 0
        },
        "field_mapping": {
            "job_id": "id",
            "title": "name_de",
            "categories.berufsfelder": "berufsfeld",
            "categories.branchen": "branchen",
            "taetigkeiten.kategorien": "activities",
            "voraussetzungen.kategorisierte_anforderungen": "requirements",
            "weiterbildung.career_progression": "career_path",
            "categories.bildungstypen": "bildungstyp",
            "swissdoc": "swissdoc",
            "description": "description_de"
        },
        "industry_mapping": industry_mapping,
        "data_structure": {
            "all_fields": analysis["all_fields"],
            "bildungstypen": analysis["bildungstypen"],
            "berufsfelder": analysis["berufsfelder"]
        },
        "field_completeness": {
            field: round(count / analysis["total_documents"] * 100, 2)
            for field, count in sorted(analysis["field_completeness"].items(), key=lambda x: x[1], reverse=True)
        }
    }
    
    return mapping


def get_top_occupations_by_completeness(collection, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get top occupations by completeness score.
    
    Args:
        collection: MongoDB collection.
        limit: Number of top occupations to return.
    
    Returns:
        List of occupation documents.
    """
    pipeline = [
        {"$match": {"completeness_score": {"$exists": True}}},
        {"$sort": {"completeness_score": -1}},
        {"$limit": limit},
        {"$project": {
            "job_id": 1,
            "title": 1,
            "completeness_score": 1,
            "categories.berufsfelder": 1
        }}
    ]
    
    return list(collection.aggregate(pipeline))


def get_top_occupations_by_schnupperanfragen(collection, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get top occupations by Schnupperanfragen count.
    
    Args:
        collection: MongoDB collection.
        limit: Number of top occupations to return.
    
    Returns:
        List of occupation documents.
    """
    pipeline = [
        {"$match": {"schnupperanfragen": {"$exists": True, "$type": "number"}}},
        {"$sort": {"schnupperanfragen": -1}},
        {"$limit": limit},
        {"$project": {
            "job_id": 1,
            "title": 1,
            "schnupperanfragen": 1,
            "categories.berufsfelder": 1
        }}
    ]
    
    return list(collection.aggregate(pipeline))


def get_bildungstypen_distribution(collection) -> Dict[str, int]:
    """
    Get distribution of bildungstypen.
    
    Args:
        collection: MongoDB collection.
    
    Returns:
        Dictionary mapping bildungstyp to count.
    """
    pipeline = [
        {"$unwind": {
            "path": "$categories.bildungstypen",
            "preserveNullAndEmptyArrays": True
        }},
        {"$group": {
            "_id": "$categories.bildungstypen",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    results = list(collection.aggregate(pipeline))
    return {result["_id"] or "unknown": result["count"] for result in results}


def identify_excluded_occupations(collection, min_completeness: float = 0.7) -> Dict[str, Any]:
    """
    Identify occupations that should be excluded.
    
    Args:
        collection: MongoDB collection.
        min_completeness: Minimum completeness score threshold.
    
    Returns:
        Dictionary with exclusion information.
    """
    # Occupations with low completeness score
    low_completeness = collection.count_documents({
        "completeness_score": {"$lt": min_completeness}
    })
    
    # Occupations missing critical fields
    missing_taetigkeiten = collection.count_documents({
        "$or": [
            {"taetigkeiten": {"$exists": False}},
            {"taetigkeiten": None},
            {"taetigkeiten": ""},
            {"taetigkeiten": []}
        ]
    })
    
    missing_ausbildung = collection.count_documents({
        "$or": [
            {"ausbildung": {"$exists": False}},
            {"ausbildung": None},
            {"ausbildung": ""},
            {"ausbildung": []}
        ]
    })
    
    # Combined exclusion criteria
    excluded = collection.count_documents({
        "$or": [
            {"completeness_score": {"$lt": min_completeness}},
            {
                "$and": [
                    {
                        "$or": [
                            {"taetigkeiten": {"$exists": False}},
                            {"taetigkeiten": None},
                            {"taetigkeiten": ""},
                            {"taetigkeiten": []}
                        ]
                    },
                    {
                        "$or": [
                            {"ausbildung": {"$exists": False}},
                            {"ausbildung": None},
                            {"ausbildung": ""},
                            {"ausbildung": []}
                        ]
                    }
                ]
            }
        ]
    })
    
    return {
        "low_completeness": low_completeness,
        "missing_taetigkeiten": missing_taetigkeiten,
        "missing_ausbildung": missing_ausbildung,
        "total_excluded": excluded,
        "min_completeness_threshold": min_completeness
    }


def main():
    """Main analysis function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]CV_DATA Occupations Analysis[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        # Get database manager
        db_manager = get_db_manager()
        
        # Connect to MongoDB
        console.print("[cyan]Connecting to MongoDB...[/cyan]")
        db_manager.connect()
        console.print(f"[green]✅ Connected[/green]")
        console.print(f"   Source DB: {db_manager.source_db.name}")
        console.print()
        
        # Get collection
        collection = db_manager.get_source_collection(settings.mongodb_collection_occupations)
        
        # 1. Total Documents
        total_docs = collection.count_documents({})
        console.print(f"[cyan]Total Documents: {total_docs:,}[/cyan]")
        console.print()
        
        # 2. Analyze data structure
        console.print("[bold cyan]Analyzing data structure...[/bold cyan]")
        analysis = analyze_data_structure(collection)
        console.print("[green]✅ Analysis complete[/green]")
        console.print()
        
        # 3. Create mapping file
        console.print("[bold cyan]Creating mapping file...[/bold cyan]")
        mapping = create_mapping_file(
            analysis,
            settings.mongodb_collection_occupations,
            settings.mongodb_database_source
        )
        
        # Save mapping file
        mapping_file = project_root / "data" / "cv_data_mapping.json"
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        
        console.print(f"[green]✅ Mapping file created: {mapping_file}[/green]")
        console.print()
        
        # 4. Statistics Tables
        console.print("[bold cyan]Statistics[/bold cyan]")
        console.print()
        
        # Berufsfelder with counts
        table = Table(title="Occupations per Berufsfeld")
        table.add_column("Berufsfeld", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Industry", style="magenta")
        
        for berufsfeld, count in analysis["occupations_per_berufsfeld"].most_common():
            industry = map_berufsfeld_to_industry(berufsfeld)
            table.add_row(berufsfeld, str(count), industry)
        
        console.print(table)
        console.print()
        
        # Bildungstypen distribution
        bildungstypen_dist = get_bildungstypen_distribution(collection)
        table = Table(title="Bildungstypen Distribution")
        table.add_column("Bildungstyp", style="cyan")
        table.add_column("Count", style="green", justify="right")
        
        for bildungstyp, count in sorted(bildungstypen_dist.items(), key=lambda x: x[1], reverse=True):
            table.add_row(bildungstyp or "unknown", str(count))
        
        console.print(table)
        console.print()
        
        # Top 10 by completeness
        top_completeness = get_top_occupations_by_completeness(collection, limit=10)
        if top_completeness:
            table = Table(title="Top 10 Most Complete Occupations")
            table.add_column("Job ID", style="cyan")
            table.add_column("Title", style="green")
            table.add_column("Completeness", style="magenta", justify="right")
            table.add_column("Berufsfeld", style="yellow")
            
            for occ in top_completeness:
                title = occ.get("title", "")[:50]
                if len(occ.get("title", "")) > 50:
                    title += "..."
                berufsfeld = ""
                if "categories" in occ and "berufsfelder" in occ["categories"]:
                    bf = occ["categories"]["berufsfelder"]
                    if isinstance(bf, list):
                        berufsfeld = ", ".join(bf[:2])
                    else:
                        berufsfeld = str(bf)
                
                table.add_row(
                    str(occ.get("job_id", "")),
                    title,
                    f"{occ.get('completeness_score', 0):.2f}",
                    berufsfeld
                )
            
            console.print(table)
            console.print()
        
        # Top 10 by Schnupperanfragen
        top_schnupper = get_top_occupations_by_schnupperanfragen(collection, limit=10)
        if top_schnupper:
            table = Table(title="Top 10 Occupations by Schnupperanfragen")
            table.add_column("Job ID", style="cyan")
            table.add_column("Title", style="green")
            table.add_column("Schnupperanfragen", style="magenta", justify="right")
            table.add_column("Berufsfeld", style="yellow")
            
            for occ in top_schnupper:
                title = occ.get("title", "")[:50]
                if len(occ.get("title", "")) > 50:
                    title += "..."
                berufsfeld = ""
                if "categories" in occ and "berufsfelder" in occ["categories"]:
                    bf = occ["categories"]["berufsfelder"]
                    if isinstance(bf, list):
                        berufsfeld = ", ".join(bf[:2])
                    else:
                        berufsfeld = str(bf)
                
                table.add_row(
                    str(occ.get("job_id", "")),
                    title,
                    str(occ.get("schnupperanfragen", 0)),
                    berufsfeld
                )
            
            console.print(table)
            console.print()
        
        # 5. Excluded occupations
        console.print("[bold cyan]Exclusion Analysis[/bold cyan]")
        console.print()
        
        exclusion_info = identify_excluded_occupations(collection, min_completeness=0.7)
        
        table = Table(title="Occupations to Exclude")
        table.add_column("Criteria", style="cyan")
        table.add_column("Count", style="red", justify="right")
        
        table.add_row("Completeness < 0.7", str(exclusion_info["low_completeness"]))
        table.add_row("Missing Tätigkeiten", str(exclusion_info["missing_taetigkeiten"]))
        table.add_row("Missing Ausbildung", str(exclusion_info["missing_ausbildung"]))
        table.add_row("Total Excluded", str(exclusion_info["total_excluded"]))
        
        console.print(table)
        console.print()
        
        # 6. Recommendations
        console.print("[bold cyan]Recommendations[/bold cyan]")
        console.print()
        
        recommendations = []
        
        total = analysis["total_documents"]
        excluded = exclusion_info["total_excluded"]
        usable = total - excluded
        
        recommendations.append(
            f"✅ Use {usable:,} occupations ({usable/total*100:.1f}%) "
            f"after excluding {excluded:,} incomplete records"
        )
        
        if analysis["completeness_scores"]:
            avg_completeness = sum(analysis["completeness_scores"]) / len(analysis["completeness_scores"])
            recommendations.append(
                f"📊 Average completeness score: {avg_completeness:.2f}"
            )
        
        recommendations.append(
            f"📋 Field mapping available in: data/cv_data_mapping.json"
        )
        
        recommendations.append(
            f"🏭 Industry mapping covers {len(mapping['industry_mapping'])} Berufsfelder"
        )
        
        recommendations.append(
            f"⚠️  Filter out occupations with completeness_score < 0.7"
        )
        
        recommendations.append(
            f"⚠️  Ensure taetigkeiten and ausbildung fields are present"
        )
        
        for rec in recommendations:
            console.print(f"   {rec}")
        
        console.print()
        console.print("[bold green]✅ Analysis complete![/bold green]")
        console.print(f"   Mapping file: {mapping_file}")
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

