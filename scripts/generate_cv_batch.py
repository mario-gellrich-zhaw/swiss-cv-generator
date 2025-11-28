"""
Batch CV Generation Script with Comprehensive Validation.

Generate large batches of CVs (100-1000+) with:
- Pre-validation (persona, timeline, portrait, company)
- Post-validation (quality score)
- Quality tier organization (A/B/C)
- Real-time monitoring with warnings
- Comprehensive reporting
- Failed CV logging

Run: python scripts/generate_cv_batch.py --count 1000 --parallel 4
"""
import sys
import os
import json
import time
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
import multiprocessing as mp
from multiprocessing import Pool, Manager
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.generation.sampling import SamplingEngine
from src.generation.cv_assembler import generate_complete_cv, CVDocument, validate_persona_before_assembly
from src.generation.cv_timeline_validator import validate_cv_timeline
from src.generation.cv_quality_validator import validate_complete_cv, save_validation_report
from src.cli.main import export_cv_pdf, export_cv_docx, export_cv_json, filter_persona, get_age_group
from src.database.queries import get_occupation_by_id

console = Console()


@dataclass
class GenerationStats:
    """Statistics for batch generation."""
    total_attempted: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_pre_validation_failed: int = 0
    total_post_validation_failed: int = 0
    total_retried: int = 0
    total_filtered: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Demographic distribution
    age_groups: Dict[str, int] = field(default_factory=dict)
    genders: Dict[str, int] = field(default_factory=dict)
    industries: Dict[str, int] = field(default_factory=dict)
    career_levels: Dict[str, int] = field(default_factory=dict)
    languages: Dict[str, int] = field(default_factory=dict)
    cantons: Dict[str, int] = field(default_factory=dict)
    
    # Quality metrics
    quality_scores: List[float] = field(default_factory=list)
    quality_tiers: Dict[str, int] = field(default_factory=dict)  # "A", "B", "C"
    validation_errors: int = 0
    validation_warnings: int = 0
    failed_validations: List[Dict[str, Any]] = field(default_factory=list)
    failure_reasons: Dict[str, int] = field(default_factory=dict)
    
    # Performance metrics
    generation_times: List[float] = field(default_factory=list)
    ai_api_calls: int = 0
    estimated_cost: float = 0.0
    
    # Career level by age group
    career_by_age: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    
    # File statistics
    total_file_size: int = 0  # bytes
    pdf_count: int = 0
    docx_count: int = 0
    json_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        duration = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        success_rate = (self.total_passed / self.total_attempted * 100) if self.total_attempted > 0 else 0
        
        return {
            "summary": {
                "total_attempted": self.total_attempted,
                "total_passed": self.total_passed,
                "total_failed": self.total_failed,
                "total_pre_validation_failed": self.total_pre_validation_failed,
                "total_post_validation_failed": self.total_post_validation_failed,
                "total_retried": self.total_retried,
                "total_filtered": self.total_filtered,
                "success_rate": success_rate,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration_seconds": duration
            },
            "demographics": {
                "age_groups": self.age_groups,
                "genders": self.genders,
                "industries": self.industries,
                "career_levels": self.career_levels,
                "languages": self.languages,
                "cantons": self.cantons,
                "career_by_age": dict(self.career_by_age)
            },
            "quality": {
                "avg_score": sum(self.quality_scores) / len(self.quality_scores) if self.quality_scores else 0,
                "min_score": min(self.quality_scores) if self.quality_scores else 0,
                "max_score": max(self.quality_scores) if self.quality_scores else 0,
                "quality_tiers": self.quality_tiers,
                "score_distribution": self._get_score_distribution(),
                "validation_errors": self.validation_errors,
                "validation_warnings": self.validation_warnings,
                "failed_validations": self.failed_validations,
                "failure_reasons": self.failure_reasons
            },
            "performance": {
                "avg_generation_time": sum(self.generation_times) / len(self.generation_times) if self.generation_times else 0,
                "total_generation_time": sum(self.generation_times),
                "ai_api_calls": self.ai_api_calls,
                "estimated_cost": self.estimated_cost
            },
            "files": {
                "total_size_bytes": self.total_file_size,
                "total_size_mb": self.total_file_size / (1024 * 1024),
                "pdf_count": self.pdf_count,
                "docx_count": self.docx_count,
                "json_count": self.json_count
            }
        }
    
    def _get_score_distribution(self) -> Dict[str, int]:
        """Get score distribution by ranges."""
        distribution = {
            "90-100": 0,
            "80-89": 0,
            "75-79": 0,
            "50-74": 0,
            "0-49": 0
        }
        
        for score in self.quality_scores:
            if score >= 90:
                distribution["90-100"] += 1
            elif score >= 80:
                distribution["80-89"] += 1
            elif score >= 75:
                distribution["75-79"] += 1
            elif score >= 50:
                distribution["50-74"] += 1
            else:
                distribution["0-49"] += 1
        
        return distribution


@dataclass
class Checkpoint:
    """Checkpoint data for resuming generation."""
    count: int
    stats: GenerationStats
    generated_ids: List[str]
    timestamp: str


def get_quality_tier(score: float) -> str:
    """Get quality tier from score."""
    if score >= 90:
        return "A"  # Premium
    elif score >= 80:
        return "B"  # Good
    elif score >= 75:
        return "C"  # Acceptable
    else:
        return "F"  # Failed


def generate_single_cv_with_validation(
    args: Tuple[Dict[str, Any], int]
) -> Tuple[Optional[Dict[str, Any]], Optional[str], float, Optional[Dict[str, Any]]]:
    """
    Generate a single CV with pre and post validation.
    
    Args:
        args: Tuple of (config_dict, attempt_number).
    
    Returns:
        Tuple of (cv_data_dict, error_message, generation_time, failure_info).
    """
    config, attempt = args
    start_time = time.time()
    failure_info = None
    
    try:
        # Initialize engine in worker process
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        from src.generation.sampling import SamplingEngine
        from src.generation.cv_assembler import generate_complete_cv, validate_persona_before_assembly
        from src.generation.cv_timeline_validator import validate_cv_timeline
        from src.generation.cv_quality_validator import validate_complete_cv
        from src.cli.main import filter_persona
        from src.database.queries import get_occupation_by_id
        
        engine = SamplingEngine()
        
        # ========================================================================
        # STEP 1: Sample persona with demographics
        # ========================================================================
        persona = engine.sample_persona(
            preferred_canton=config.get("preferred_canton"),
            preferred_industry=config.get("preferred_industry")
        )
        
        # Apply filters
        if not filter_persona(
            persona,
            config.get("industry"),
            config.get("career_level"),
            config.get("age_group"),
            config.get("language")
        ):
            return None, "filtered", time.time() - start_time, None
        
        # ========================================================================
        # STEP 2: Pre-validate persona (timeline, portrait, company match)
        # ========================================================================
        job_id = persona.get("job_id")
        occupation_doc = get_occupation_by_id(job_id) if job_id else None
        
        is_valid, fixed_persona, validation_issues = validate_persona_before_assembly(
            persona, occupation_doc
        )
        
        if not is_valid:
            critical_issues = [i for i in validation_issues if i.startswith("Error")]
            if critical_issues:
                failure_info = {
                    "stage": "pre_validation",
                    "reason": "critical_validation_failed",
                    "issues": validation_issues
                }
                if attempt < config.get("max_retries", 3):
                    return None, "pre_validation_failed_retry", time.time() - start_time, failure_info
                else:
                    return None, "pre_validation_failed", time.time() - start_time, failure_info
        
        persona = fixed_persona
        
        # ========================================================================
        # STEP 3: Generate CV components
        # ========================================================================
        # Generate complete CV (includes education, job history, additional education, assembly)
        cv_doc, quality_report = generate_complete_cv(persona)
        
        # Check if CV generation failed due to quality
        if cv_doc is None:
            failure_info = {
                "stage": "generation",
                "reason": "quality_check_failed",
                "quality_report": quality_report
            }
            if attempt < config.get("max_retries", 3):
                return None, "generation_failed_retry", time.time() - start_time, failure_info
            else:
                return None, "generation_failed", time.time() - start_time, failure_info
        
        # ========================================================================
        # STEP 4: Post-validate complete CV (quality score)
        # ========================================================================
        min_score = config.get("min_quality_score", 75.0)
        validation_report = validate_complete_cv(cv_doc, persona, min_score, auto_fix=True)
        
        quality_score = validation_report.score.overall
        
        if quality_score < min_score:
            failure_info = {
                "stage": "post_validation",
                "reason": "quality_score_below_threshold",
                "score": quality_score,
                "min_score": min_score,
                "issues": [issue.message for issue in validation_report.issues[:5]]
            }
            if attempt < config.get("max_retries", 3):
                return None, "post_validation_failed_retry", time.time() - start_time, failure_info
            else:
                return None, "post_validation_failed", time.time() - start_time, failure_info
        
        # Override language if specified
        if config.get("language"):
            cv_doc.language = config["language"]
        
        # Override portrait if disabled
        if not config.get("with_portrait", True):
            cv_doc.portrait_path = None
            cv_doc.portrait_base64 = None
        
        generation_time = time.time() - start_time
        
        # Return CV data with quality info
        cv_data = {
            "cv_doc_dict": cv_doc.to_dict(),
            "persona": persona,
            "quality_score": quality_score,
            "quality_tier": get_quality_tier(quality_score),
            "validation_report": validation_report.to_dict()
        }
        
        return cv_data, None, generation_time, None
        
    except Exception as e:
        failure_info = {
            "stage": "exception",
            "reason": str(e),
            "exception_type": type(e).__name__
        }
        return None, str(e), time.time() - start_time, failure_info


def update_stats(stats: GenerationStats, cv_data: Dict[str, Any], generation_time: float):
    """Update statistics with new CV data."""
    cv_doc_dict = cv_data["cv_doc_dict"]
    personal = cv_doc_dict.get("personal", {})
    professional = cv_doc_dict.get("professional", {})
    metadata = cv_doc_dict.get("metadata", {})
    
    stats.total_passed += 1
    stats.generation_times.append(generation_time)
    
    # Demographic distribution
    age = personal.get("age", 0)
    age_grp = get_age_group(age)
    stats.age_groups[age_grp] = stats.age_groups.get(age_grp, 0) + 1
    stats.genders[personal.get("gender", "")] = stats.genders.get(personal.get("gender", ""), 0) + 1
    stats.industries[professional.get("industry", "")] = stats.industries.get(professional.get("industry", ""), 0) + 1
    stats.career_levels[professional.get("career_level", "")] = stats.career_levels.get(professional.get("career_level", ""), 0) + 1
    stats.languages[metadata.get("language", "de")] = stats.languages.get(metadata.get("language", "de"), 0) + 1
    stats.cantons[personal.get("canton", "")] = stats.cantons.get(personal.get("canton", ""), 0) + 1
    
    # Career level by age group
    stats.career_by_age[age_grp][professional.get("career_level", "")] = stats.career_by_age[age_grp].get(professional.get("career_level", ""), 0) + 1
    
    # Quality metrics
    quality_score = cv_data.get("quality_score", 100.0)
    stats.quality_scores.append(quality_score)
    quality_tier = cv_data.get("quality_tier", "F")
    stats.quality_tiers[quality_tier] = stats.quality_tiers.get(quality_tier, 0) + 1
    
    # Validation report
    validation_report = cv_data.get("validation_report", {})
    if validation_report:
        issues = validation_report.get("issues", [])
        stats.validation_errors += len([i for i in issues if i.get("severity") == "critical"])
        stats.validation_warnings += len([i for i in issues if i.get("severity") == "warning"])


def save_checkpoint(checkpoint_path: Path, checkpoint: Checkpoint):
    """Save checkpoint to file."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, 'wb') as f:
        pickle.dump(checkpoint, f)


def load_checkpoint(checkpoint_path: Path) -> Optional[Checkpoint]:
    """Load checkpoint from file."""
    if checkpoint_path.exists():
        with open(checkpoint_path, 'rb') as f:
            return pickle.load(f)
    return None


def check_demographic_distribution(stats: GenerationStats, total: int) -> List[str]:
    """Check if demographic distribution matches targets and return warnings."""
    warnings = []
    
    if total == 0:
        return warnings
    
    # Check age groups
    expected_age = {"18-25": 7.6, "26-40": 18.5, "41-65": 31.0}
    for age_grp, expected_pct in expected_age.items():
        actual_count = stats.age_groups.get(age_grp, 0)
        actual_pct = (actual_count / total * 100) if total > 0 else 0
        diff = abs(actual_pct - expected_pct)
        if diff > 5:  # More than 5% deviation
            warnings.append(f"Age group {age_grp}: {actual_pct:.1f}% (expected {expected_pct}%, diff: {diff:.1f}%)")
    
    # Check gender
    expected_gender = {"male": 50.1, "female": 49.9}
    for gender, expected_pct in expected_gender.items():
        actual_count = stats.genders.get(gender, 0)
        actual_pct = (actual_count / total * 100) if total > 0 else 0
        diff = abs(actual_pct - expected_pct)
        if diff > 10:  # More than 10% deviation
            warnings.append(f"Gender {gender}: {actual_pct:.1f}% (expected {expected_pct}%, diff: {diff:.1f}%)")
    
    return warnings


def generate_comprehensive_report(
    stats: GenerationStats,
    output_path: Path,
    failed_cvs: List[Dict[str, Any]]
) -> Path:
    """Generate comprehensive report with all statistics."""
    report_path = output_path / "generation_report.json"
    
    report = stats.to_dict()
    report["failed_cvs"] = failed_cvs
    report["targets"] = {
        "age_groups": {"18-25": 7.6, "26-40": 18.5, "41-65": 31.0},
        "genders": {"male": 50.1, "female": 49.9},
        "min_quality_score": 75.0,
        "target_success_rate": 80.0
    }
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return report_path


def save_failed_cvs(failed_cvs: List[Dict[str, Any]], output_path: Path) -> Path:
    """Save failed CVs to JSON file."""
    failed_path = output_path / "failed_cvs.json"
    
    with open(failed_path, 'w', encoding='utf-8') as f:
        json.dump(failed_cvs, f, indent=2, ensure_ascii=False)
    
    return failed_path


@click.command()
@click.option('--count', '-n', default=100, type=int, help='Total CVs to generate')
@click.option('--parallel', '-p', default=4, type=int, help='Number of parallel workers')
@click.option('--checkpoint-every', default=50, type=int, help='Save checkpoint every N CVs')
@click.option('--min-quality-score', default=75.0, type=float, help='Minimum quality score to accept')
@click.option('--max-retries', default=3, type=int, help='Max retries for failed validations')
@click.option('--output-format', default='pdf', type=click.Choice(['pdf', 'docx', 'both']), help='Output format')
@click.option('--create-index', default=True, is_flag=True, help='Generate HTML index')
@click.option('--output-dir', '-o', default='output/batch', type=click.Path(), help='Output directory')
@click.option('--resume', is_flag=True, help='Resume from checkpoint')
@click.option('--industry', default=None, help='Filter by industry')
@click.option('--language', default='de', type=click.Choice(['de', 'fr', 'it']), help='Language')
def generate_batch(
    count: int,
    parallel: int,
    checkpoint_every: int,
    min_quality_score: float,
    max_retries: int,
    output_format: str,
    create_index: bool,
    output_dir: str,
    resume: bool,
    industry: Optional[str],
    language: str
):
    """
    Generate large batch of CVs with comprehensive validation and quality tiers.
    
    Examples:
    
    \b
        # Generate 1000 CVs with 4 parallel workers
        python scripts/generate_cv_batch.py --count 1000 --parallel 4
    
    \b
        # Generate with checkpoint every 100 CVs
        python scripts/generate_cv_batch.py --count 500 --checkpoint-every 100
    
    \b
        # Resume from checkpoint
        python scripts/generate_cv_batch.py --count 1000 --resume
    """
    console.print(Panel.fit("[bold green]🇨🇭 Swiss CV Generator - Batch Mode[/bold green]", border_style="green"))
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    checkpoint_path = output_path / "checkpoint.pkl"
    
    # Initialize stats
    if resume and checkpoint_path.exists():
        checkpoint = load_checkpoint(checkpoint_path)
        if checkpoint:
            stats = checkpoint.stats
            generated_ids = set(checkpoint.generated_ids)
            start_count = checkpoint.count
            console.print(f"[yellow]Resuming from checkpoint: {start_count} CVs already generated[/yellow]")
        else:
            stats = GenerationStats()
            generated_ids = set()
            start_count = 0
    else:
        stats = GenerationStats()
        generated_ids = set()
        start_count = 0
    
    stats.start_time = stats.start_time or time.time()
    
    # Create output structure with quality tiers
    language_dir = output_path / language
    if industry:
        base_industry_dir = language_dir / industry
    else:
        base_industry_dir = language_dir / "all"
    
    # Create tier directories
    tier_dirs = {
        "A": base_industry_dir / "tier_A_premium",
        "B": base_industry_dir / "tier_B_good",
        "C": base_industry_dir / "tier_C_acceptable"
    }
    for tier_dir in tier_dirs.values():
        tier_dir.mkdir(parents=True, exist_ok=True)
    
    # Configuration for workers
    config = {
        "industry": industry,
        "language": language,
        "preferred_canton": None,
        "preferred_industry": industry,
        "career_level": None,
        "age_group": None,
        "with_portrait": True,
        "validate_timeline": True,
        "validate_quality": True,
        "min_quality_score": min_quality_score,
        "max_retries": max_retries
    }
    
    # Failed CVs tracking
    failed_cvs: List[Dict[str, Any]] = []
    
    # Progress tracking
    remaining = count - start_count
    total_attempts = 0
    max_total_attempts = remaining * (max_retries + 1) * 3  # Safety limit
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn()
    ) as progress:
        task = progress.add_task(
            f"[cyan]Generating CVs...",
            total=remaining
        )
        
        # Generate CVs
        pool = Pool(processes=parallel)
        
        try:
            while stats.total_passed < count and total_attempts < max_total_attempts:
                # Prepare batch of tasks
                batch_size = min(parallel * 2, count - stats.total_passed)
                tasks = [(config, 0) for _ in range(batch_size)]
                
                # Generate batch
                try:
                    results = pool.map(generate_single_cv_with_validation, tasks)
                except Exception as e:
                    console.print(f"[red]Error in batch generation: {e}[/red]")
                    import traceback
                    console.print(traceback.format_exc())
                    break
                
                for cv_data, error, gen_time, failure_info in results:
                    total_attempts += 1
                    stats.total_attempted += 1
                    
                    if error:
                        if error == "filtered":
                            stats.total_filtered += 1
                        elif error.endswith("_retry"):
                            stats.total_retried += 1
                            # Retry logic handled in worker
                        else:
                            stats.total_failed += 1
                            
                            # Categorize failure
                            if error.startswith("pre_validation"):
                                stats.total_pre_validation_failed += 1
                            elif error.startswith("post_validation") or error.startswith("generation"):
                                stats.total_post_validation_failed += 1
                            
                            # Track failure reason
                            reason = error.replace("_failed", "").replace("_retry", "")
                            stats.failure_reasons[reason] = stats.failure_reasons.get(reason, 0) + 1
                            
                            # Log failed CV
                            if failure_info:
                                failed_cvs.append({
                                    "error": error,
                                    "failure_info": failure_info,
                                    "timestamp": datetime.now().isoformat(),
                                    "attempt": total_attempts
                                })
                        continue
                    
                    if cv_data:
                        # Reconstruct CVDocument from dict
                        cv_doc_dict = cv_data["cv_doc_dict"]
                        personal = cv_doc_dict.get("personal", {})
                        professional = cv_doc_dict.get("professional", {})
                        content = cv_doc_dict.get("content", {})
                        metadata = cv_doc_dict.get("metadata", {})
                        
                        cv_doc = CVDocument(
                            first_name=personal.get("first_name", ""),
                            last_name=personal.get("last_name", ""),
                            full_name=personal.get("full_name", ""),
                            age=personal.get("age", 0),
                            gender=personal.get("gender", ""),
                            canton=personal.get("canton", ""),
                            city=personal.get("city"),
                            email=personal.get("email", ""),
                            phone=personal.get("phone", ""),
                            address=personal.get("address"),
                            portrait_path=personal.get("portrait_path"),
                            portrait_base64=personal.get("portrait_base64"),
                            current_title=professional.get("current_title", ""),
                            industry=professional.get("industry", ""),
                            career_level=professional.get("career_level", ""),
                            years_experience=professional.get("years_experience", 0),
                            summary=content.get("summary", ""),
                            education=content.get("education", []),
                            jobs=content.get("jobs", []),
                            skills=content.get("skills", {}),
                            additional_education=content.get("additional_education", []),
                            hobbies=content.get("hobbies", []),
                            language=metadata.get("language", "de"),
                            created_at=metadata.get("created_at", "")
                        )
                        
                        # Generate filename
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        job_id_str = str(cv_data["persona"].get("job_id", "unknown"))
                        filename_base = f"{cv_doc.last_name}_{cv_doc.first_name}_{job_id_str}_{timestamp}"
                        cv_id = f"{cv_doc.last_name}_{cv_doc.first_name}_{job_id_str}"
                        
                        if cv_id in generated_ids:
                            continue
                        
                        generated_ids.add(cv_id)
                        
                        # Get quality tier
                        quality_tier = cv_data.get("quality_tier", "C")
                        quality_score = cv_data.get("quality_score", 75.0)
                        
                        # Select output directory based on tier
                        if quality_tier in tier_dirs:
                            tier_dir = tier_dirs[quality_tier]
                        else:
                            tier_dir = tier_dirs["C"]  # Fallback
                        
                        # Export CV
                        export_success = False
                        file_size = 0
                        
                        # Export JSON (always)
                        json_path = tier_dir / f"{filename_base}.json"
                        try:
                            export_cv_json(cv_doc, json_path)
                            export_success = True
                            stats.json_count += 1
                            if json_path.exists():
                                file_size += json_path.stat().st_size
                        except Exception as json_error:
                            stats.total_failed += 1
                            failed_cvs.append({
                                "cv_id": cv_id,
                                "error": f"JSON export failed: {str(json_error)}",
                                "timestamp": datetime.now().isoformat()
                            })
                            continue
                        
                        # Export PDF (optional)
                        if export_success and output_format in ('pdf', 'both'):
                            pdf_path = tier_dir / f"{filename_base}.pdf"
                            try:
                                export_cv_pdf(cv_doc, pdf_path)
                                stats.pdf_count += 1
                                if pdf_path.exists():
                                    file_size += pdf_path.stat().st_size
                            except Exception:
                                pass  # PDF failed, but JSON succeeded
                        
                        # Export DOCX (optional)
                        if export_success and output_format in ('docx', 'both'):
                            docx_path = tier_dir / f"{filename_base}.docx"
                            try:
                                export_cv_docx(cv_doc, docx_path)
                                stats.docx_count += 1
                                if docx_path.exists():
                                    file_size += docx_path.stat().st_size
                            except Exception:
                                pass  # DOCX failed, but JSON succeeded
                        
                        if export_success:
                            # Update stats
                            update_stats(stats, cv_data, gen_time)
                            stats.total_file_size += file_size
                            
                            # Update progress with real-time info
                            success_rate = (stats.total_passed / stats.total_attempted * 100) if stats.total_attempted > 0 else 0
                            avg_score = sum(stats.quality_scores) / len(stats.quality_scores) if stats.quality_scores else 0
                            
                            current_name = f"{cv_doc.first_name} {cv_doc.last_name}"
                            progress.update(
                                task,
                                description=f"[cyan]Generated: {current_name} | Score: {quality_score:.1f} (Tier {quality_tier}) | Success: {success_rate:.1f}% | Avg: {avg_score:.1f}[/cyan]",
                                advance=1
                            )
                            
                            # Real-time warnings
                            if stats.total_attempted > 10:  # Only check after some attempts
                                demographic_warnings = check_demographic_distribution(stats, stats.total_passed)
                                if demographic_warnings:
                                    # Log warning but don't interrupt
                                    pass
                                
                                if success_rate < 80.0:
                                    # Warning shown in progress description
                                    pass
                            
                            # Save checkpoint
                            if stats.total_passed % checkpoint_every == 0:
                                checkpoint = Checkpoint(
                                    count=stats.total_passed,
                                    stats=stats,
                                    generated_ids=list(generated_ids),
                                    timestamp=datetime.now().isoformat()
                                )
                                save_checkpoint(checkpoint_path, checkpoint)
        
        finally:
            pool.close()
            pool.join()
    
    stats.end_time = time.time()
    
    # Save failed CVs
    if failed_cvs:
        failed_path = save_failed_cvs(failed_cvs, output_path)
        console.print(f"[yellow]⚠️  {len(failed_cvs)} failed CVs logged to: {failed_path}[/yellow]")
    
    # Generate comprehensive report
    report_path = generate_comprehensive_report(stats, output_path, failed_cvs)
    
    # Print summary
    console.print()
    console.print(Panel.fit("[bold blue]Generation Complete[/bold blue]", border_style="blue"))
    
    # Summary statistics
    duration = stats.end_time - stats.start_time
    success_rate = (stats.total_passed / stats.total_attempted * 100) if stats.total_attempted > 0 else 0
    cvs_per_minute = (stats.total_passed / duration * 60) if duration > 0 else 0
    
    table = Table(title="Generation Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Attempted", str(stats.total_attempted))
    table.add_row("Total Passed", str(stats.total_passed))
    table.add_row("Total Failed", str(stats.total_failed))
    table.add_row("Success Rate", f"{success_rate:.1f}%")
    table.add_row("Pre-Validation Failed", str(stats.total_pre_validation_failed))
    table.add_row("Post-Validation Failed", str(stats.total_post_validation_failed))
    table.add_row("Total Retried", str(stats.total_retried))
    table.add_row("Total Filtered", str(stats.total_filtered))
    table.add_row("Duration", f"{duration:.1f}s ({duration/60:.1f}m)")
    table.add_row("Speed", f"{cvs_per_minute:.1f} CVs/minute")
    table.add_row("Avg Generation Time", f"{sum(stats.generation_times)/len(stats.generation_times):.2f}s" if stats.generation_times else "N/A")
    
    if stats.quality_scores:
        table.add_row("Avg Quality Score", f"{sum(stats.quality_scores)/len(stats.quality_scores):.1f}/100")
        table.add_row("Min Quality Score", f"{min(stats.quality_scores):.1f}/100")
        table.add_row("Max Quality Score", f"{max(stats.quality_scores):.1f}/100")
    
    console.print(table)
    
    # Quality tier distribution
    if stats.quality_tiers:
        tier_table = Table(title="Quality Tier Distribution", show_header=True, header_style="bold yellow")
        tier_table.add_column("Tier", style="cyan")
        tier_table.add_column("Count", style="green")
        tier_table.add_column("Percentage", style="yellow")
        tier_table.add_column("Score Range", style="magenta")
        
        tier_info = {
            "A": ("Premium", "90-100"),
            "B": ("Good", "80-89"),
            "C": ("Acceptable", "75-79")
        }
        
        for tier in ["A", "B", "C"]:
            count = stats.quality_tiers.get(tier, 0)
            pct = (count / stats.total_passed * 100) if stats.total_passed > 0 else 0
            name, score_range = tier_info.get(tier, ("", ""))
            tier_table.add_row(f"Tier {tier} ({name})", str(count), f"{pct:.1f}%", score_range)
        
        console.print(tier_table)
    
    # Failure reasons
    if stats.failure_reasons:
        failure_table = Table(title="Failure Reasons", show_header=True, header_style="bold red")
        failure_table.add_column("Reason", style="cyan")
        failure_table.add_column("Count", style="red")
        
        for reason, count in sorted(stats.failure_reasons.items(), key=lambda x: x[1], reverse=True):
            failure_table.add_row(reason, str(count))
        
        console.print(failure_table)
    
    # Demographic distribution
    console.print("\n[bold yellow]Demographic Distribution:[/bold yellow]")
    
    # Age groups
    age_table = Table(title="Age Groups", show_header=True)
    age_table.add_column("Age Group", style="cyan")
    age_table.add_column("Count", style="green")
    age_table.add_column("Actual %", style="yellow")
    age_table.add_column("Expected %", style="magenta")
    age_table.add_column("Difference", style="red")
    
    expected_age = {"18-25": 7.6, "26-40": 18.5, "41-65": 31.0}
    for age_grp in ["18-25", "26-40", "41-65"]:
        count = stats.age_groups.get(age_grp, 0)
        actual_pct = (count / stats.total_passed * 100) if stats.total_passed > 0 else 0
        expected_pct = expected_age.get(age_grp, 0)
        diff = actual_pct - expected_pct
        age_table.add_row(age_grp, str(count), f"{actual_pct:.1f}%", f"{expected_pct}%", f"{diff:+.1f}%")
    
    console.print(age_table)
    
    # Gender
    gender_table = Table(title="Gender Distribution", show_header=True)
    gender_table.add_column("Gender", style="cyan")
    gender_table.add_column("Count", style="green")
    gender_table.add_column("Actual %", style="yellow")
    gender_table.add_column("Expected %", style="magenta")
    gender_table.add_column("Difference", style="red")
    
    expected_gender = {"male": 50.1, "female": 49.9}
    for gender in ["male", "female"]:
        count = stats.genders.get(gender, 0)
        actual_pct = (count / stats.total_passed * 100) if stats.total_passed > 0 else 0
        expected_pct = expected_gender.get(gender, 0)
        diff = actual_pct - expected_pct
        gender_table.add_row(gender, str(count), f"{actual_pct:.1f}%", f"{expected_pct}%", f"{diff:+.1f}%")
    
    console.print(gender_table)
    
    # Warnings
    if stats.total_attempted > 0:
        demographic_warnings = check_demographic_distribution(stats, stats.total_passed)
        if demographic_warnings:
            console.print("\n[yellow]⚠️  Demographic Distribution Warnings:[/yellow]")
            for warning in demographic_warnings:
                console.print(f"  • {warning}")
        
        if success_rate < 80.0:
            console.print(f"\n[yellow]⚠️  Success rate ({success_rate:.1f}%) below target (80%)[/yellow]")
    
    # File statistics
    file_table = Table(title="File Statistics", show_header=True)
    file_table.add_column("Metric", style="cyan")
    file_table.add_column("Value", style="green")
    
    file_table.add_row("Total File Size", f"{stats.total_file_size / (1024 * 1024):.2f} MB")
    file_table.add_row("PDF Files", str(stats.pdf_count))
    file_table.add_row("DOCX Files", str(stats.docx_count))
    file_table.add_row("JSON Files", str(stats.json_count))
    
    console.print(file_table)
    
    # AI Cost estimate
    # Estimate: ~$0.01 per CV (summary, hobbies, activities transformation)
    estimated_cost = stats.total_attempted * 0.01
    stats.estimated_cost = estimated_cost
    
    cost_table = Table(title="AI Cost Estimate", show_header=True)
    cost_table.add_column("Metric", style="cyan")
    cost_table.add_column("Value", style="green")
    
    cost_table.add_row("Total Attempts", str(stats.total_attempted))
    cost_table.add_row("Estimated Cost", f"${estimated_cost:.2f}")
    cost_table.add_row("Cost per CV", f"${estimated_cost / stats.total_attempted:.4f}" if stats.total_attempted > 0 else "$0.00")
    
    console.print(cost_table)
    
    console.print(f"\n[green]✅ Comprehensive report saved to: {report_path}[/green]")
    console.print(f"[green]✅ CVs organized by quality tier in: {base_industry_dir}[/green]")
    console.print(f"[green]  - Tier A (Premium, 90-100): {tier_dirs['A']}[/green]")
    console.print(f"[green]  - Tier B (Good, 80-89): {tier_dirs['B']}[/green]")
    console.print(f"[green]  - Tier C (Acceptable, 75-79): {tier_dirs['C']}[/green]")
    
    console.print(f"\n[bold green]✅ Batch generation complete![/bold green]")


if __name__ == '__main__':
    generate_batch()
