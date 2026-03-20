"""
Extract skills from CV_DATA.cv_berufsberatung and store in TARGET DB.

This script:
1. Loads occupations with completeness_score >= 0.8
2. Extracts skills from voraussetzungen.kategorisierte_anforderungen
3. Uses static translations for common skills
4. Batch AI translation for missing translations
5. Assigns importance automatically
6. Inserts into target_db.occupation_skills

Run: python scripts/extract_skills_from_cv_data.py
"""
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from pymongo.errors import OperationFailure
from rich.console import Console
from rich.progress import (BarColumn, Progress, SpinnerColumn, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table

from src.config import get_settings
from src.database.mongodb_manager import get_db_manager

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


console = Console()
settings = get_settings()

# Static translations for common skills (30-50 most frequent)
STATIC_SKILL_TRANSLATIONS = {
    "Teamfähigkeit": {"fr": "Esprit d'équipe", "it": "Spirito di squadra"},
    "Kommunikationsfähigkeit": {"fr": "Capacité de communication", "it": "Capacità di comunicazione"},
    "Selbstständigkeit": {"fr": "Autonomie", "it": "Autonomia"},
    "Zuverlässigkeit": {"fr": "Fiabilité", "it": "Affidabilità"},
    "Belastbarkeit": {"fr": "Résistance au stress", "it": "Resistenza allo stress"},
    "Kreativität": {"fr": "Créativité", "it": "Creatività"},
    "Analytisches Denken": {"fr": "Pensée analytique", "it": "Pensiero analitico"},
    "Problemlösungsfähigkeit": {"fr": "Capacité de résolution de problèmes", "it": "Capacità di risoluzione dei problemi"},
    "Organisationsfähigkeit": {"fr": "Capacité d'organisation", "it": "Capacità organizzative"},
    "Zeitmanagement": {"fr": "Gestion du temps", "it": "Gestione del tempo"},
    "Flexibilität": {"fr": "Flexibilité", "it": "Flessibilità"},
    "Lernbereitschaft": {"fr": "Disposition à apprendre", "it": "Disponibilità ad apprendere"},
    "Durchsetzungsvermögen": {"fr": "Force de persuasion", "it": "Forza di persuasione"},
    "Empathie": {"fr": "Empathie", "it": "Empatia"},
    "Geduld": {"fr": "Patience", "it": "Pazienza"},
    "Präzision": {"fr": "Précision", "it": "Precisione"},
    "Sorgfalt": {"fr": "Soin", "it": "Cura"},
    "Verantwortungsbewusstsein": {"fr": "Sens des responsabilités", "it": "Senso di responsabilità"},
    "Kundenorientierung": {"fr": "Orientation client", "it": "Orientamento al cliente"},
    "Konfliktfähigkeit": {"fr": "Capacité de gestion des conflits", "it": "Capacità di gestione dei conflitti"},
    "Handwerkliches Geschick": {"fr": "Habileté manuelle", "it": "Abilità manuale"},
    "Technisches Verständnis": {"fr": "Compréhension technique", "it": "Comprensione tecnica"},
    "Räumliches Vorstellungsvermögen": {"fr": "Représentation spatiale", "it": "Rappresentazione spaziale"},
    "Mathematisches Verständnis": {"fr": "Compréhension mathématique", "it": "Comprensione matematica"},
    "Sprachliche Fähigkeiten": {"fr": "Compétences linguistiques", "it": "Competenze linguistiche"},
    "IT-Kenntnisse": {"fr": "Connaissances informatiques", "it": "Conoscenze informatiche"},
    "Schwindelfreiheit": {"fr": "Absence de vertige", "it": "Assenza di vertigini"},
    "Körperliche Belastbarkeit": {"fr": "Résistance physique", "it": "Resistenza fisica"},
    "Gute körperliche Verfassung": {"fr": "Bonne condition physique", "it": "Buona condizione fisica"},
    "Beweglichkeit": {"fr": "Mobilité", "it": "Mobilità"},
    "Ausdauer": {"fr": "Endurance", "it": "Resistenza"},
    "Kraft": {"fr": "Force", "it": "Forza"},
    "Geschicklichkeit": {"fr": "Dextérité", "it": "Destrezza"},
    "Koordinationsfähigkeit": {"fr": "Capacité de coordination", "it": "Capacità di coordinamento"},
    "Reaktionsfähigkeit": {"fr": "Capacité de réaction", "it": "Capacità di reazione"},
    "Konzentrationsfähigkeit": {"fr": "Capacité de concentration", "it": "Capacità di concentrazione"},
    "Multitasking": {"fr": "Multitâche", "it": "Multitasking"},
    "Projektmanagement": {"fr": "Gestion de projet", "it": "Gestione del progetto"},
    "Führungsfähigkeit": {"fr": "Capacité de leadership", "it": "Capacità di leadership"},
    "Verkaufsfähigkeit": {"fr": "Capacité de vente", "it": "Capacità di vendita"},
    "Beratungskompetenz": {"fr": "Compétence en conseil", "it": "Competenza di consulenza"},
    "Serviceorientierung": {"fr": "Orientation service", "it": "Orientamento al servizio"},
    "Qualitätsbewusstsein": {"fr": "Sens de la qualité", "it": "Senso della qualità"},
    "Innovationsfähigkeit": {"fr": "Capacité d'innovation", "it": "Capacità di innovazione"},
    "Strategisches Denken": {"fr": "Pensée stratégique", "it": "Pensiero strategico"},
    "Networking": {"fr": "Réseautage", "it": "Networking"},
    "Interkulturelle Kompetenz": {"fr": "Compétence interculturelle", "it": "Competenza interculturale"},
    "Digitale Kompetenz": {"fr": "Compétence numérique", "it": "Competenza digitale"},
    "Kritisches Denken": {"fr": "Pensée critique", "it": "Pensiero critico"},
    "Anpassungsfähigkeit": {"fr": "Capacité d'adaptation", "it": "Capacità di adattamento"}
}

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


def extract_skills_from_occupation(occ: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract skills from an occupation document.

    Args:
        occ: Occupation document from CV_DATA.

    Returns:
        List of skill dictionaries.
    """
    skills = []
    job_id = str(occ.get("job_id", ""))

    if not job_id:
        return skills

    # Extract from voraussetzungen.kategorisierte_anforderungen
    voraussetzungen = occ.get("voraussetzungen", {})
    if not isinstance(voraussetzungen, dict):
        return skills

    kategorisierte = voraussetzungen.get("kategorisierte_anforderungen", {})
    if not isinstance(kategorisierte, dict):
        return skills

    # Extract physische_anforderungen
    physische = kategorisierte.get("physische_anforderungen", [])
    if isinstance(physische, list) and len(physische) > 0:
        for skill_name in physische:
            if skill_name and isinstance(skill_name, str):
                skill_clean = skill_name.strip()
                if skill_clean and len(skill_clean) > 2:  # Minimum length check
                    skills.append({
                        "job_id": job_id,
                        "skill_name_de": skill_clean,
                        "skill_category": "physical",
                        "importance": 3  # Default for physical
                    })

    # Extract fachliche_faehigkeiten
    fachliche = kategorisierte.get("fachliche_faehigkeiten", [])
    if isinstance(fachliche, list) and len(fachliche) > 0:
        for skill_name in fachliche:
            if skill_name and isinstance(skill_name, str):
                skill_clean = skill_name.strip()
                if skill_clean and len(skill_clean) > 2:  # Minimum length check
                    skills.append({
                        "job_id": job_id,
                        "skill_name_de": skill_clean,
                        "skill_category": "technical",
                        "importance": 4  # Default for technical
                    })

    # Extract persoenliche_eigenschaften
    persoenliche = kategorisierte.get("persoenliche_eigenschaften", [])
    if isinstance(persoenliche, list) and len(persoenliche) > 0:
        for skill_name in persoenliche:
            if skill_name and isinstance(skill_name, str):
                skill_clean = skill_name.strip()
                if skill_clean and len(skill_clean) > 2:  # Minimum length check
                    skills.append({
                        "job_id": job_id,
                        "skill_name_de": skill_clean,
                        "skill_category": "soft",
                        "importance": 3  # Default for soft
                    })

    return skills


def assign_importance(skill: Dict[str, Any]) -> int:
    """
    Assign importance score to a skill.

    Args:
        skill: Skill dictionary.

    Returns:
        Importance score (1-5).
    """
    category = skill.get("skill_category", "")

    if category == "technical":
        return 4  # Fachliche Fähigkeiten are most important
    elif category == "soft":
        return 3  # Persönliche Eigenschaften
    elif category == "physical":
        return 3  # Physische Anforderungen

    return 3  # Default


def translate_skills_batch(skills_de: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Translate skills using OpenAI in a single batch call.

    Args:
        skills_de: List of German skill names.

    Returns:
        Dictionary mapping DE skill to {fr: ..., it: ...}
    """
    if not OPENAI_AVAILABLE or not settings.openai_api_key:
        return {}

    if not skills_de:
        return {}

    # Create prompt
    skills_json = json.dumps(skills_de, ensure_ascii=False)
    prompt = f"""Translate these {len(skills_de)} German skills to French and Italian.
Return JSON object: {{"skill_de": {{"fr": "French translation", "it": "Italian translation"}}, ...}}

Skills to translate:
{skills_json}

Return only valid JSON, no markdown, no explanation."""

    try:
        messages = [
            {"role": "system", "content": "You are a professional translator. Return only valid JSON objects."},
            {"role": "user", "content": prompt}
        ]

        # Try modern client first
        if _openai_client and hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_factual,
                max_tokens=2000
            )
            content = response.choices[0].message.content.strip()
        else:
            # Fallback to legacy client
            import openai
            response = openai.ChatCompletion.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_factual,
                max_tokens=2000
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
        translations = json.loads(content)
        return translations

    except Exception as e:
        console.print(f"[red]❌ Translation error: {e}[/red]")
        return {}


def main():
    """Main extraction function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Extract Skills from CV_DATA[/bold blue]")
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
        console.print(f"   Target DB: {db_manager.target_db.name}")
        console.print()

        # Get collections
        source_col = db_manager.get_source_collection(
            settings.mongodb_collection_occupations)
        target_col = db_manager.get_target_collection("occupation_skills")

        # 1. Load occupations with completeness_score >= 0.8
        # Note: completeness_score is nested in data_completeness.completeness_score
        console.print(
            "[cyan]Loading occupations (completeness_score >= 0.8)...[/cyan]")
        console.print(
            "[dim]   Using data_completeness.completeness_score[/dim]")

        # First, check if we have the nested field
        sample = source_col.find_one({})
        if sample and "data_completeness" in sample and "completeness_score" in sample.get("data_completeness", {}):
            # Use nested field
            query = {
                "data_completeness.completeness_score": {"$gte": 0.8},
                "voraussetzungen.kategorisierte_anforderungen": {"$exists": True}
            }
        else:
            # Fallback: try direct field or no filter
            query = {
                "$or": [
                    {"completeness_score": {"$gte": 0.8}},
                    {"data_completeness.completeness_score": {"$gte": 0.8}}
                ],
                "voraussetzungen.kategorisierte_anforderungen": {"$exists": True}
            }

        occupations = list(source_col.find(query))

        console.print(
            f"[green]✅ Loaded {len(occupations)} occupations[/green]")
        console.print()

        # 2. Extract skills
        console.print("[cyan]Extracting skills...[/cyan]")
        all_skills = []
        skills_by_job = defaultdict(list)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Processing occupations...", total=len(occupations))

            for occ in occupations:
                skills = extract_skills_from_occupation(occ)
                for skill in skills:
                    skill["importance"] = assign_importance(skill)
                    all_skills.append(skill)
                    skills_by_job[skill["job_id"]].append(skill)

                progress.update(task, advance=1)

        console.print(
            f"[green]✅ Extracted {len(all_skills)} skills from {len(skills_by_job)} occupations[/green]")
        console.print()

        # 3. Collect unique skills for translation
        unique_skills_de = set()
        for skill in all_skills:
            skill_de = skill["skill_name_de"]
            if skill_de not in STATIC_SKILL_TRANSLATIONS:
                unique_skills_de.add(skill_de)

        console.print(f"[cyan]Translation Analysis:[/cyan]")
        console.print(
            f"   Skills in static dictionary: {len(STATIC_SKILL_TRANSLATIONS)}")
        console.print(
            f"   Unique skills found: {len(set(s['skill_name_de'] for s in all_skills))}")
        console.print(
            f"   Skills needing AI translation: {len(unique_skills_de)}")
        console.print()

        # 4. Batch AI translation
        translations = {}
        if unique_skills_de and OPENAI_AVAILABLE and settings.openai_api_key:
            console.print("[cyan]Translating skills with AI (batch)...[/cyan]")
            skills_list = list(unique_skills_de)

            # Process in batches of 50
            batch_size = 50
            for i in range(0, len(skills_list), batch_size):
                batch = skills_list[i:i + batch_size]
                batch_translations = translate_skills_batch(batch)
                translations.update(batch_translations)

                if i + batch_size < len(skills_list):
                    time.sleep(settings.ai_rate_limit_delay)

            console.print(
                f"[green]✅ Translated {len(translations)} skills[/green]")
            console.print()

        # 5. Add translations to skills
        console.print("[cyan]Adding translations to skills...[/cyan]")
        for skill in all_skills:
            skill_de = skill["skill_name_de"]

            # Check static translations first
            if skill_de in STATIC_SKILL_TRANSLATIONS:
                static = STATIC_SKILL_TRANSLATIONS[skill_de]
                skill["skill_name_fr"] = static.get("fr")
                skill["skill_name_it"] = static.get("it")
            # Check AI translations
            elif skill_de in translations:
                ai_trans = translations[skill_de]
                if isinstance(ai_trans, dict):
                    skill["skill_name_fr"] = ai_trans.get("fr")
                    skill["skill_name_it"] = ai_trans.get("it")
            # No translation available
            else:
                skill["skill_name_fr"] = None
                skill["skill_name_it"] = None

        console.print("[green]✅ Translations added[/green]")
        console.print()

        # 6. Insert into target DB
        console.print("[cyan]Inserting skills into TARGET DB...[/cyan]")
        inserted_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Inserting skills...", total=len(all_skills))

            for skill in all_skills:
                try:
                    result = target_col.update_one(
                        {
                            "job_id": skill["job_id"],
                            "skill_name_de": skill["skill_name_de"]
                        },
                        {"$set": skill},
                        upsert=True
                    )

                    if result.upserted_id or result.modified_count > 0:
                        inserted_count += 1

                    progress.update(task, advance=1)
                except Exception as e:
                    console.print(f"[red]❌ Error inserting skill: {e}[/red]")
                    progress.update(task, advance=1)

        console.print(
            f"[green]✅ Inserted/updated {inserted_count} skills[/green]")
        console.print()

        # 7. Print Summary
        console.print("[bold cyan]Summary[/bold cyan]")
        console.print()

        # Statistics table
        table = Table(title="Extraction Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Total Occupations Processed", str(len(occupations)))
        table.add_row("Total Skills Extracted", str(len(all_skills)))
        table.add_row("Unique Skills", str(
            len(set(s["skill_name_de"] for s in all_skills))))
        table.add_row("Skills with Static Translation", str(
            sum(1 for s in all_skills if s["skill_name_de"] in STATIC_SKILL_TRANSLATIONS)))
        table.add_row("Skills with AI Translation", str(len(translations)))
        table.add_row("Skills Inserted/Updated", str(inserted_count))

        # Category breakdown
        category_counts = Counter(s["skill_category"] for s in all_skills)
        table.add_row("", "")
        table.add_row("Technical Skills", str(
            category_counts.get("technical", 0)))
        table.add_row("Soft Skills", str(category_counts.get("soft", 0)))
        table.add_row("Physical Skills", str(
            category_counts.get("physical", 0)))

        console.print(table)
        console.print()

        # Cost estimate
        ai_calls = (len(unique_skills_de) + 49) // 50  # Ceiling division
        estimated_cost = ai_calls * 0.01  # ~$0.01 per batch of 50

        console.print(
            f"[yellow]💰 Estimated AI Translation Cost: ~${estimated_cost:.2f}[/yellow]")
        console.print(f"[dim]   ({ai_calls} batch call(s) × ~$0.01)[/dim]")
        console.print()

        console.print("[bold green]✅ Extraction complete![/bold green]")
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
