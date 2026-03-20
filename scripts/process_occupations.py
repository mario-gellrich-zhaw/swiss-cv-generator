#!/usr/bin/env python3
"""
Process berufsberatung occupations data and transform to standardized format.
"""
import json
from pathlib import Path
from typing import Dict, Any


def map_berufsfeld_to_industry(berufsfeld: str) -> str:
    """
    Map Berufsfeld to industry enum.
    
    Maps:
    - Informatik/IT → technology
    - Wirtschaft/Finanz → finance
    - Gesundheit → healthcare
    - Bau → construction
    - else → other
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
    
    # Default to other
    return "other"


def transform_occupation(occ: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a single occupation entry to the target structure.
    
    Input fields: ID, Name, Description, Berufsfelder, Branchen, Bildungstypen, Swissdoc
    Output: id, name_de, description_de, berufsfeld, branchen, bildungstyp, swissdoc, industry
    """
    berufsfeld = occ.get("Berufsfelder", "")
    industry = map_berufsfeld_to_industry(berufsfeld)
    
    return {
        "id": occ.get("ID", ""),
        "name_de": occ.get("Name", ""),
        "description_de": occ.get("Description", ""),
        "berufsfeld": berufsfeld,
        "branchen": occ.get("Branchen", ""),
        "bildungstyp": occ.get("Bildungstypen", ""),
        "swissdoc": occ.get("Swissdoc", ""),
        "industry": industry
    }


def main():
    """Main processing function."""
    # Paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    input_file = project_root / "data" / "source" / "berufsberatung_occupations_de.json"
    output_file = project_root / "data" / "processed" / "occupations.json"
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Read input file
    print(f"Reading {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        occupations = json.load(f)
    
    # Transform occupations
    print(f"Processing {len(occupations)} occupations...")
    processed = [transform_occupation(occ) for occ in occupations]
    
    # Save output
    print(f"Saving to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)
    
    # Print summary
    print(f"✅ Processed {len(processed)} occupations → {output_file}")


if __name__ == "__main__":
    main()

