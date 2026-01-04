"""
Load Swiss canton data (fallback without OpenAI).

This script loads all 26 Swiss cantons from hardcoded data if OpenAI is not available.
Run: python scripts/load_cantons_fallback.py
"""
from src.database.mongodb_manager import get_db_manager
from src.config import get_settings
from rich.table import Table
from rich.console import Console
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


console = Console()
settings = get_settings()

# All 26 Swiss cantons with accurate data (as of 2023)
CANTONS_DATA = [
    {"code": "ZH", "name_de": "Zürich", "name_fr": "Zurich", "name_it": "Zurigo", "population": 1553423, "workforce": 820000,
        "language_de": 0.83, "language_fr": 0.05, "language_it": 0.03, "language_en": 0.09, "major_city": "Zürich"},
    {"code": "BE", "name_de": "Bern", "name_fr": "Berne", "name_it": "Berna", "population": 1043132, "workforce": 550000,
        "language_de": 0.84, "language_fr": 0.08, "language_it": 0.02, "language_en": 0.06, "major_city": "Bern"},
    {"code": "LU", "name_de": "Luzern", "name_fr": "Lucerne", "name_it": "Lucerna", "population": 416347, "workforce": 230000,
        "language_de": 0.89, "language_fr": 0.03, "language_it": 0.02, "language_en": 0.06, "major_city": "Luzern"},
    {"code": "UR", "name_de": "Uri", "name_fr": "Uri", "name_it": "Uri", "population": 36819, "workforce": 20000,
        "language_de": 0.92, "language_fr": 0.02, "language_it": 0.02, "language_en": 0.04, "major_city": "Altdorf"},
    {"code": "SZ", "name_de": "Schwyz", "name_fr": "Schwytz", "name_it": "Svitto", "population": 162157, "workforce": 90000,
        "language_de": 0.89, "language_fr": 0.03, "language_it": 0.02, "language_en": 0.06, "major_city": "Schwyz"},
    {"code": "OW", "name_de": "Obwalden", "name_fr": "Obwald", "name_it": "Obvaldo", "population": 38108, "workforce": 21000,
        "language_de": 0.91, "language_fr": 0.02, "language_it": 0.02, "language_en": 0.05, "major_city": "Sarnen"},
    {"code": "NW", "name_de": "Nidwalden", "name_fr": "Nidwald", "name_it": "Nidvaldo", "population": 43520, "workforce": 24000,
        "language_de": 0.90, "language_fr": 0.02, "language_it": 0.02, "language_en": 0.06, "major_city": "Stans"},
    {"code": "GL", "name_de": "Glarus", "name_fr": "Glaris", "name_it": "Glarona", "population": 40851, "workforce": 22000,
        "language_de": 0.88, "language_fr": 0.03, "language_it": 0.02, "language_en": 0.07, "major_city": "Glarus"},
    {"code": "ZG", "name_de": "Zug", "name_fr": "Zoug", "name_it": "Zugo", "population": 130183, "workforce": 75000,
        "language_de": 0.82, "language_fr": 0.04, "language_it": 0.03, "language_en": 0.11, "major_city": "Zug"},
    {"code": "FR", "name_de": "Freiburg", "name_fr": "Fribourg", "name_it": "Friburgo", "population": 326302, "workforce": 170000,
        "language_de": 0.29, "language_fr": 0.67, "language_it": 0.01, "language_en": 0.03, "major_city": "Fribourg"},
    {"code": "SO", "name_de": "Solothurn", "name_fr": "Soleure", "name_it": "Soletta", "population": 278907, "workforce": 150000,
        "language_de": 0.88, "language_fr": 0.04, "language_it": 0.02, "language_en": 0.06, "major_city": "Solothurn"},
    {"code": "BS", "name_de": "Basel-Stadt", "name_fr": "Bâle-Ville", "name_it": "Basilea Città", "population": 195845,
        "workforce": 110000, "language_de": 0.75, "language_fr": 0.06, "language_it": 0.04, "language_en": 0.15, "major_city": "Basel"},
    {"code": "BL", "name_de": "Basel-Landschaft", "name_fr": "Bâle-Campagne", "name_it": "Basilea Campagna", "population": 291201,
        "workforce": 160000, "language_de": 0.86, "language_fr": 0.04, "language_it": 0.03, "language_en": 0.07, "major_city": "Liestal"},
    {"code": "SH", "name_de": "Schaffhausen", "name_fr": "Schaffhouse", "name_it": "Sciaffusa", "population": 83485, "workforce": 46000,
        "language_de": 0.87, "language_fr": 0.03, "language_it": 0.03, "language_en": 0.07, "major_city": "Schaffhausen"},
    {"code": "AR", "name_de": "Appenzell Ausserrhoden", "name_fr": "Appenzell Rhodes-Extérieures", "name_it": "Appenzello Esterno", "population": 55309,
        "workforce": 30000, "language_de": 0.90, "language_fr": 0.02, "language_it": 0.02, "language_en": 0.06, "major_city": "Herisau"},
    {"code": "AI", "name_de": "Appenzell Innerrhoden", "name_fr": "Appenzell Rhodes-Intérieures", "name_it": "Appenzello Interno", "population": 16293,
        "workforce": 9000, "language_de": 0.93, "language_fr": 0.01, "language_it": 0.01, "language_en": 0.05, "major_city": "Appenzell"},
    {"code": "SG", "name_de": "St. Gallen", "name_fr": "Saint-Gall", "name_it": "San Gallo", "population": 515682, "workforce": 280000,
        "language_de": 0.88, "language_fr": 0.03, "language_it": 0.02, "language_en": 0.07, "major_city": "St. Gallen"},
    {"code": "GR", "name_de": "Graubünden", "name_fr": "Grisons", "name_it": "Grigioni", "population": 200096, "workforce": 110000,
        "language_de": 0.76, "language_fr": 0.02, "language_it": 0.10, "language_en": 0.12, "major_city": "Chur"},
    {"code": "AG", "name_de": "Aargau", "name_fr": "Argovie", "name_it": "Argovia", "population": 694761, "workforce": 380000,
        "language_de": 0.84, "language_fr": 0.04, "language_it": 0.03, "language_en": 0.09, "major_city": "Aarau"},
    {"code": "TG", "name_de": "Thurgau", "name_fr": "Thurgovie", "name_it": "Turgovia", "population": 282909, "workforce": 155000,
        "language_de": 0.87, "language_fr": 0.03, "language_it": 0.03, "language_en": 0.07, "major_city": "Frauenfeld"},
    {"code": "TI", "name_de": "Tessin", "name_fr": "Tessin", "name_it": "Ticino", "population": 350986, "workforce": 190000,
        "language_de": 0.08, "language_fr": 0.03, "language_it": 0.83, "language_en": 0.06, "major_city": "Bellinzona"},
    {"code": "VD", "name_de": "Waadt", "name_fr": "Vaud", "name_it": "Vaud", "population": 814762, "workforce": 430000,
        "language_de": 0.07, "language_fr": 0.84, "language_it": 0.02, "language_en": 0.07, "major_city": "Lausanne"},
    {"code": "VS", "name_de": "Wallis", "name_fr": "Valais", "name_it": "Vallese", "population": 348503, "workforce": 185000,
        "language_de": 0.28, "language_fr": 0.68, "language_it": 0.01, "language_en": 0.03, "major_city": "Sion"},
    {"code": "NE", "name_de": "Neuenburg", "name_fr": "Neuchâtel", "name_it": "Neuchâtel", "population": 176850, "workforce": 95000,
        "language_de": 0.06, "language_fr": 0.88, "language_it": 0.01, "language_en": 0.05, "major_city": "Neuchâtel"},
    {"code": "GE", "name_de": "Genf", "name_fr": "Genève", "name_it": "Ginevra", "population": 506343, "workforce": 280000,
        "language_de": 0.04, "language_fr": 0.76, "language_it": 0.04, "language_en": 0.16, "major_city": "Genève"},
    {"code": "JU", "name_de": "Jura", "name_fr": "Jura", "name_it": "Giura", "population": 73709, "workforce": 39000,
        "language_de": 0.07, "language_fr": 0.90, "language_it": 0.01, "language_en": 0.02, "major_city": "Delémont"},
]


def main():
    """Load canton data into MongoDB."""
    console.print(
        "\n[bold cyan]Swiss Canton Data Loader (Fallback)[/bold cyan]\n")

    try:
        # Connect to database
        console.print("Connecting to MongoDB...")
        db_manager = get_db_manager()
        db_manager.connect()

        # Get cantons collection
        cantons_collection = db_manager.target_db.cantons

        # Check if data already exists
        existing_count = cantons_collection.count_documents({})
        if existing_count > 0:
            console.print(
                f"[yellow]⚠️  Found {existing_count} existing cantons in database[/yellow]")
            console.print("[yellow]Clearing existing data...[/yellow]")
            cantons_collection.delete_many({})

        # Insert canton data
        console.print(f"Inserting {len(CANTONS_DATA)} cantons...")

        # Convert to MongoDB format and add primary language
        for canton in CANTONS_DATA:
            # Determine primary language
            if canton["language_de"] > canton["language_fr"] and canton["language_de"] > canton["language_it"]:
                canton["primary_language"] = "de"
            elif canton["language_fr"] > canton["language_de"] and canton["language_fr"] > canton["language_it"]:
                canton["primary_language"] = "fr"
            else:
                canton["primary_language"] = "it"

        result = cantons_collection.insert_many(CANTONS_DATA)

        console.print(
            f"[green]✅ Inserted {len(result.inserted_ids)} cantons successfully![/green]")

        # Display summary table
        table = Table(title="Loaded Cantons", show_header=True,
                      header_style="bold cyan")
        table.add_column("Code", style="cyan", width=5)
        table.add_column("Name (DE)", style="white", width=20)
        table.add_column("Population", justify="right",
                         style="yellow", width=12)
        table.add_column("Primary Lang", style="green", width=12)

        for canton in sorted(CANTONS_DATA, key=lambda x: x["code"]):
            table.add_row(
                canton["code"],
                canton["name_de"],
                f"{canton['population']:,}",
                canton["primary_language"].upper()
            )

        console.print("\n", table, "\n")

        console.print("[green]✨ Canton data loaded successfully![/green]\n")

    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
