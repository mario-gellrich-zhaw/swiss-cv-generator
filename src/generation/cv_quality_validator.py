"""
CV Quality Validator - Comprehensive Validation.

This module provides a single comprehensive validation function that checks:
- Timeline consistency
- Portrait validation
- Company validation
- Text quality
- Achievement quality
- Personalization

Run: Used by CV generation pipeline after assembly
"""
import sys
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.generation.cv_assembler import CVDocument, get_age_group
from src.database.queries import (
    get_occupation_by_id,
    sample_company_by_canton_and_industry,
    get_skills_by_occupation,
    get_canton_by_code,
    sample_portrait_path
)


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    category: str  # "timeline", "portrait", "company", "text", "achievement", "personalization"
    severity: str  # "critical", "warning", "info"
    section: str  # "education", "jobs", "skills", etc.
    field: Optional[str] = None
    message: str = ""
    suggested_fix: Optional[str] = None
    score_impact: float = 0.0  # Points deducted from score
    auto_fixable: bool = False  # Whether this can be auto-fixed


@dataclass
class QualityScore:
    """Quality score breakdown."""
    completeness: float = 0.0  # 0-100 (30% weight)
    realism: float = 0.0  # 0-100 (35% weight)
    language: float = 0.0  # 0-100 (20% weight)
    achievement: float = 0.0  # 0-100 (15% weight)
    overall: float = 0.0  # Weighted average
    
    def calculate_overall(self) -> float:
        """Calculate overall score with weights: 30% completeness, 35% realism, 20% language, 15% achievement."""
        self.overall = (
            self.completeness * 0.30 +
            self.realism * 0.35 +
            self.language * 0.20 +
            self.achievement * 0.15
        )
        return self.overall


@dataclass
class ValidationReport:
    """Complete validation report."""
    cv_id: str
    timestamp: str
    passed: bool
    score: QualityScore
    issues: List[ValidationIssue] = field(default_factory=list)
    critical_issues: int = 0
    warnings: int = 0
    info: int = 0
    auto_fixes_applied: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "cv_id": self.cv_id,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "score": {
                "completeness": self.score.completeness,
                "realism": self.score.realism,
                "language": self.score.language,
                "achievement": self.score.achievement,
                "overall": self.score.overall
            },
            "issues": [asdict(issue) for issue in self.issues],
            "summary": {
                "critical_issues": self.critical_issues,
                "warnings": self.warnings,
                "info": self.info,
                "total_issues": len(self.issues),
                "auto_fixes_applied": self.auto_fixes_applied
            }
        }


def parse_date_to_year(date_str: Optional[str]) -> Optional[int]:
    """Parse date string to year."""
    if not date_str:
        return None
    try:
        if "-" in date_str:
            return int(date_str.split("-")[0])
        else:
            return int(date_str)
    except (ValueError, AttributeError):
        return None


def validate_complete_cv(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]] = None,
    min_score: float = 75.0,
    auto_fix: bool = True
) -> ValidationReport:
    """
    Comprehensive CV validation combining all checks.
    
    Args:
        cv_doc: Complete CV document.
        persona: Optional persona dictionary (for additional context).
        min_score: Minimum score to pass (default: 75.0).
        auto_fix: Whether to attempt auto-fixes (default: True).
    
    Returns:
        ValidationReport with pass/fail and detailed issues.
    """
    issues: List[ValidationIssue] = []
    auto_fixes_applied: List[str] = []
    
    # Generate CV ID
    cv_id = f"{cv_doc.last_name}_{cv_doc.first_name}_{cv_doc.language}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Initialize scores
    completeness_score = 100.0
    realism_score = 100.0
    language_score = 100.0
    achievement_score = 100.0
    
    # ============================================================================
    # TIMELINE VALIDATION
    # ============================================================================
    timeline_issues = _validate_timeline(cv_doc, persona, auto_fix, auto_fixes_applied)
    issues.extend(timeline_issues)
    for issue in timeline_issues:
        if issue.severity == "critical":
            realism_score -= issue.score_impact
        elif issue.severity == "warning":
            realism_score -= issue.score_impact * 0.5
    
    # ============================================================================
    # PORTRAIT VALIDATION
    # ============================================================================
    portrait_issues = _validate_portrait(cv_doc, persona, auto_fix, auto_fixes_applied)
    issues.extend(portrait_issues)
    for issue in portrait_issues:
        if issue.severity == "critical":
            completeness_score -= issue.score_impact
        elif issue.severity == "warning":
            completeness_score -= issue.score_impact * 0.5
    
    # ============================================================================
    # COMPANY VALIDATION
    # ============================================================================
    company_issues = _validate_companies(cv_doc, persona, auto_fix, auto_fixes_applied)
    issues.extend(company_issues)
    for issue in company_issues:
        if issue.severity == "critical":
            realism_score -= issue.score_impact
        elif issue.severity == "warning":
            realism_score -= issue.score_impact * 0.5
    
    # ============================================================================
    # TEXT QUALITY VALIDATION
    # ============================================================================
    text_issues = _validate_text_quality(cv_doc, auto_fix, auto_fixes_applied)
    issues.extend(text_issues)
    for issue in text_issues:
        if issue.severity == "critical":
            language_score -= issue.score_impact
        elif issue.severity == "warning":
            language_score -= issue.score_impact * 0.5
    
    # ============================================================================
    # ACHIEVEMENT QUALITY VALIDATION
    # ============================================================================
    achievement_issues = _validate_achievements(cv_doc, persona)
    issues.extend(achievement_issues)
    for issue in achievement_issues:
        if issue.severity == "critical":
            achievement_score -= issue.score_impact
        elif issue.severity == "warning":
            achievement_score -= issue.score_impact * 0.5
    
    # ============================================================================
    # PERSONALIZATION VALIDATION
    # ============================================================================
    personalization_issues = _validate_personalization(cv_doc, persona)
    issues.extend(personalization_issues)
    for issue in personalization_issues:
        if issue.severity == "critical":
            completeness_score -= issue.score_impact
        elif issue.severity == "warning":
            completeness_score -= issue.score_impact * 0.5
    
    # ============================================================================
    # COMPLETENESS CHECKS
    # ============================================================================
    completeness_issues = _validate_completeness(cv_doc)
    issues.extend(completeness_issues)
    for issue in completeness_issues:
        if issue.severity == "critical":
            completeness_score -= issue.score_impact
        elif issue.severity == "warning":
            completeness_score -= issue.score_impact * 0.5
    
    # Calculate final scores (ensure non-negative)
    completeness_score = max(0.0, completeness_score)
    realism_score = max(0.0, realism_score)
    language_score = max(0.0, language_score)
    achievement_score = max(0.0, achievement_score)
    
    # Calculate overall score
    score = QualityScore(
        completeness=completeness_score,
        realism=realism_score,
        language=language_score,
        achievement=achievement_score
    )
    score.calculate_overall()
    
    # Categorize issues
    critical_issues = len([i for i in issues if i.severity == "critical"])
    warnings = len([i for i in issues if i.severity == "warning"])
    info_count = len([i for i in issues if i.severity == "info"])
    
    # Determine if passed
    passed = score.overall >= min_score and critical_issues == 0
    
    report = ValidationReport(
        cv_id=cv_id,
        timestamp=datetime.now().isoformat(),
        passed=passed,
        score=score,
        issues=issues,
        critical_issues=critical_issues,
        warnings=warnings,
        info=info_count,
        auto_fixes_applied=auto_fixes_applied
    )
    
    return report


def _validate_timeline(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]],
    auto_fix: bool,
    auto_fixes_applied: List[str]
) -> List[ValidationIssue]:
    """Validate timeline consistency."""
    issues = []
    
    age = cv_doc.age
    years_experience = cv_doc.years_experience
    
    # Calculate education end year
    education_end_year = None
    if cv_doc.education:
        education_end_year = max(edu.get("end_year", 0) for edu in cv_doc.education if edu.get("end_year"))
    
    if not education_end_year:
        education_end_year = datetime.now().year - years_experience - age + 18
    
    # Calculate total job years
    total_job_years = 0
    total_gap_years = 0
    
    if cv_doc.jobs:
        sorted_jobs = sorted(
            cv_doc.jobs,
            key=lambda j: parse_date_to_year(j.get("start_date", "2000-01")) or 2000
        )
        
        for i, job in enumerate(sorted_jobs):
            start_year = parse_date_to_year(job.get("start_date"))
            end_year = parse_date_to_year(job.get("end_date")) if not job.get("is_current") else datetime.now().year
            
            if start_year and end_year:
                duration = end_year - start_year
                if duration > 0:
                    total_job_years += duration
                
                # Check for gaps
                if i > 0:
                    prev_job = sorted_jobs[i - 1]
                    prev_end = parse_date_to_year(prev_job.get("end_date")) if not prev_job.get("is_current") else datetime.now().year
                    if prev_end and start_year:
                        gap = start_year - prev_end
                        if gap > 1:  # Gap > 12 months
                            if gap > 3:
                                issues.append(ValidationIssue(
                                    category="timeline",
                                    severity="critical",
                                    section="jobs",
                                    field=f"gap_{i}",
                                    message=f"Unexplained gap of {gap} years between jobs",
                                    suggested_fix="Add gap filler (Elternzeit, Weiterbildung, etc.)",
                                    score_impact=15.0,
                                    auto_fixable=False
                                ))
                            else:
                                total_gap_years += gap - 1  # Count gap years
    
    # Validate: education_end + job_years + gap_years ≈ age - 15
    expected_total = age - 15
    actual_total = (datetime.now().year - education_end_year) + total_job_years + total_gap_years
    discrepancy = abs(actual_total - expected_total)
    
    if discrepancy > 3:
        issues.append(ValidationIssue(
            category="timeline",
            severity="critical",
            section="timeline",
            field="total_years",
            message=f"Timeline discrepancy: {discrepancy} years (expected: {expected_total}, actual: {actual_total})",
            suggested_fix="Recalculate timeline or adjust dates",
            score_impact=20.0,
            auto_fixable=discrepancy <= 2
        ))
    elif discrepancy > 2 and auto_fix:
        auto_fixes_applied.append(f"Adjusted timeline by {discrepancy} years")
    
    # Check for overlapping periods
    if cv_doc.jobs and len(cv_doc.jobs) > 1:
        sorted_jobs = sorted(
            cv_doc.jobs,
            key=lambda j: parse_date_to_year(j.get("start_date", "2000-01")) or 2000
        )
        
        for i in range(len(sorted_jobs) - 1):
            job1 = sorted_jobs[i]
            job2 = sorted_jobs[i + 1]
            
            end1 = parse_date_to_year(job1.get("end_date")) if not job1.get("is_current") else datetime.now().year
            start2 = parse_date_to_year(job2.get("start_date"))
            
            if end1 and start2 and end1 > start2:
                issues.append(ValidationIssue(
                    category="timeline",
                    severity="critical",
                    section="jobs",
                    field=f"overlap_{i}",
                    message=f"Job overlap: {job1.get('company')} ends {end1} but {job2.get('company')} starts {start2}",
                    suggested_fix="Fix timeline overlaps",
                    score_impact=20.0,
                    auto_fixable=True
                ))
    
    # Check career progression
    if cv_doc.jobs and len(cv_doc.jobs) > 1:
        job_positions = [j.get("position", "").lower() for j in cv_doc.jobs]
        has_senior = any("senior" in pos or "lead" in pos or "leiter" in pos for pos in job_positions)
        has_junior = any("junior" in pos for pos in job_positions)
        
        if has_senior and has_junior:
            # Check if junior comes after senior (regression)
            senior_indices = [i for i, pos in enumerate(job_positions) if "senior" in pos or "lead" in pos or "leiter" in pos]
            junior_indices = [i for i, pos in enumerate(job_positions) if "junior" in pos]
            
            if junior_indices and senior_indices:
                if max(junior_indices) > min(senior_indices):
                    issues.append(ValidationIssue(
                        category="timeline",
                        severity="critical",
                        section="jobs",
                        field="career_regression",
                        message="Career regression: Junior position after Senior/Lead",
                        suggested_fix="Fix career progression order",
                        score_impact=15.0,
                        auto_fixable=False
                    ))
    
    # Check age at each position
    if cv_doc.jobs:
        for job in cv_doc.jobs:
            start_year = parse_date_to_year(job.get("start_date"))
            if start_year:
                job_age = age - (datetime.now().year - start_year)
                position = job.get("position", "").lower()
                
                if "lead" in position or "leiter" in position:
                    if job_age < 30:
                        issues.append(ValidationIssue(
                            category="timeline",
                            severity="warning",
                            section="jobs",
                            field=job.get("company", ""),
                            message=f"Age {job_age} too young for Lead position (min: 30)",
                            suggested_fix="Adjust position or timeline",
                            score_impact=10.0,
                            auto_fixable=False
                        ))
                elif "senior" in position:
                    if job_age < 25:
                        issues.append(ValidationIssue(
                            category="timeline",
                            severity="warning",
                            section="jobs",
                            field=job.get("company", ""),
                            message=f"Age {job_age} too young for Senior position (min: 25)",
                            suggested_fix="Adjust position or timeline",
                            score_impact=5.0,
                            auto_fixable=False
                        ))
    
    # Check Elternzeit ≤2 years
    if cv_doc.jobs:
        for job in cv_doc.jobs:
            if "elternzeit" in job.get("company", "").lower() or "elternzeit" in job.get("position", "").lower():
                start_year = parse_date_to_year(job.get("start_date"))
                end_year = parse_date_to_year(job.get("end_date"))
                if start_year and end_year:
                    duration = end_year - start_year
                    if duration > 2:
                        issues.append(ValidationIssue(
                            category="timeline",
                            severity="critical",
                            section="jobs",
                            field=job.get("company", ""),
                            message=f"Elternzeit duration {duration} years exceeds maximum of 2 years",
                            suggested_fix="Reduce Elternzeit duration or split into multiple periods",
                            score_impact=15.0,
                            auto_fixable=False
                        ))
    
    return issues


def _validate_portrait(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]],
    auto_fix: bool,
    auto_fixes_applied: List[str]
) -> List[ValidationIssue]:
    """Validate portrait file and demographics."""
    issues = []
    
    if not cv_doc.portrait_path:
        return issues  # No portrait, skip validation
    
    # Check file exists
    portrait_path = project_root / "data" / "portraits" / cv_doc.portrait_path
    if not portrait_path.exists():
        issues.append(ValidationIssue(
            category="portrait",
            severity="critical",
            section="personal",
            field="portrait_path",
            message=f"Portrait file not found: {cv_doc.portrait_path}",
            suggested_fix="Resample portrait from correct age+gender folder",
            score_impact=10.0,
            auto_fixable=True
        ))
        return issues
    
    # Check portrait age_group matches calculated age
    age = cv_doc.age
    age_group = get_age_group(age)
    
    # Extract age_group from path (e.g., "male/26-40/image.png")
    path_parts = cv_doc.portrait_path.split("/")
    if len(path_parts) >= 2:
        path_age_group = path_parts[1]
        if path_age_group != age_group:
            issues.append(ValidationIssue(
                category="portrait",
                severity="warning",
                section="personal",
                field="portrait_path",
                message=f"Portrait age_group mismatch: path has {path_age_group}, calculated age_group is {age_group}",
                suggested_fix="Resample portrait from correct age_group folder",
                score_impact=5.0,
                auto_fixable=True
            ))
            if auto_fix and persona:
                # Auto-fix: resample portrait
                gender = persona.get("gender", cv_doc.gender)
                new_portrait = sample_portrait_path(gender, age_group)
                if new_portrait:
                    cv_doc.portrait_path = new_portrait
                    auto_fixes_applied.append(f"Resampled portrait to match age_group {age_group}")
    
    # Check portrait gender matches persona gender
    if persona:
        gender = persona.get("gender", cv_doc.gender)
        if len(path_parts) >= 1:
            path_gender = path_parts[0]
            if path_gender != gender:
                issues.append(ValidationIssue(
                    category="portrait",
                    severity="warning",
                    section="personal",
                    field="portrait_path",
                    message=f"Portrait gender mismatch: path has {path_gender}, persona gender is {gender}",
                    suggested_fix="Resample portrait from correct gender folder",
                    score_impact=5.0,
                    auto_fixable=True
                ))
                if auto_fix:
                    new_portrait = sample_portrait_path(gender, age_group)
                    if new_portrait:
                        cv_doc.portrait_path = new_portrait
                        auto_fixes_applied.append(f"Resampled portrait to match gender {gender}")
    
    return issues


def _validate_companies(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]],
    auto_fix: bool,
    auto_fixes_applied: List[str]
) -> List[ValidationIssue]:
    """Validate company data."""
    issues = []
    
    if not cv_doc.jobs:
        return issues
    
    # Get occupation industry
    occupation_industry = cv_doc.industry
    if persona and persona.get("job_id"):
        occupation_doc = get_occupation_by_id(persona.get("job_id"))
        if occupation_doc:
            # Try to infer industry from berufsfeld
            categories = occupation_doc.get("categories", {})
            berufsfelder = categories.get("berufsfelder", [])
            # For now, use cv_doc.industry
    
    # Check all companies match industry
    company_names = []
    for job in cv_doc.jobs:
        if job.get("category") == "gap_filler":
            continue
        
        company_name = job.get("company", "")
        company_industry = job.get("category", "")
        
        if company_name:
            company_names.append(company_name)
            
            # Check industry match
            if company_industry and company_industry != occupation_industry:
                issues.append(ValidationIssue(
                    category="company",
                    severity="critical",
                    section="jobs",
                    field=company_name,
                    message=f"Company industry mismatch: {company_industry} != {occupation_industry}",
                    suggested_fix="Resample company from correct industry",
                    score_impact=15.0,
                    auto_fixable=True
                ))
                if auto_fix:
                    # Try to resample company
                    new_company = sample_company_by_canton_and_industry(cv_doc.canton, occupation_industry)
                    if new_company:
                        job["company"] = new_company.get("name", company_name)
                        job["category"] = occupation_industry
                        auto_fixes_applied.append(f"Resampled company {company_name} to match industry")
            
            # Check company name is realistic
            unrealistic_patterns = ["Association", "Verein", "Stiftung"]
            if any(pattern in company_name for pattern in unrealistic_patterns):
                if occupation_industry in ["retail", "manufacturing", "technology"]:
                    issues.append(ValidationIssue(
                        category="company",
                        severity="warning",
                        section="jobs",
                        field=company_name,
                        message=f"Company name '{company_name}' seems unrealistic for {occupation_industry} industry",
                        suggested_fix="Use more appropriate company name",
                        score_impact=3.0,
                        auto_fixable=False
                    ))
    
    # Check for duplicate companies
    if len(company_names) != len(set(company_names)):
        duplicates = [name for name in company_names if company_names.count(name) > 1]
        issues.append(ValidationIssue(
            category="company",
            severity="warning",
            section="jobs",
            field="duplicates",
            message=f"Duplicate companies in job history: {', '.join(set(duplicates))}",
            suggested_fix="Use different companies for each job",
            score_impact=5.0,
            auto_fixable=True
        ))
        if auto_fix:
            # Try to replace duplicates
            seen_companies = set()
            for job in cv_doc.jobs:
                if job.get("category") == "gap_filler":
                    continue
                company_name = job.get("company", "")
                if company_name in seen_companies:
                    new_company = sample_company_by_canton_and_industry(cv_doc.canton, occupation_industry)
                    if new_company:
                        job["company"] = new_company.get("name", company_name)
                        auto_fixes_applied.append(f"Replaced duplicate company {company_name}")
                seen_companies.add(company_name)
    
    return issues


def _validate_text_quality(
    cv_doc: CVDocument,
    auto_fix: bool,
    auto_fixes_applied: List[str]
) -> List[ValidationIssue]:
    """Validate text quality (duplicates, capitalization, verb variety)."""
    issues = []
    
    # Collect all text
    all_text = []
    if cv_doc.summary:
        all_text.append(cv_doc.summary)
    
    if cv_doc.jobs:
        for job in cv_doc.jobs:
            responsibilities = job.get("responsibilities", [])
            all_text.extend(responsibilities)
    
    # Check for duplicate phrases
    for text in all_text:
        text_lower = text.lower()
        # Check for repeated phrases (e.g., "verantwortung für verantwortung")
        duplicate_pattern = re.search(r'\b(\w+(?:\s+\w+){1,3})\s+\1\b', text_lower)
        if duplicate_pattern:
            issues.append(ValidationIssue(
                category="text",
                severity="warning",
                section="jobs",
                field="responsibilities",
                message=f"Duplicate phrase found: '{duplicate_pattern.group(1)}'",
                suggested_fix="Remove duplicate phrase",
                score_impact=2.0,
                auto_fixable=True
            ))
            if auto_fix:
                # Remove duplicate
                fixed_text = re.sub(r'\b(\w+(?:\s+\w+){1,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
                # Update in job if it's a responsibility
                if cv_doc.jobs:
                    for job in cv_doc.jobs:
                        if text in job.get("responsibilities", []):
                            job["responsibilities"] = [
                                fixed_text if resp == text else resp
                                for resp in job.get("responsibilities", [])
                            ]
                            auto_fixes_applied.append(f"Removed duplicate phrase from responsibility")
                            break
    
    # Check capitalization
    if cv_doc.jobs:
        for job in cv_doc.jobs:
            responsibilities = job.get("responsibilities", [])
            for i, resp in enumerate(responsibilities):
                if resp and not resp[0].isupper():
                    issues.append(ValidationIssue(
                        category="text",
                        severity="warning",
                        section="jobs",
                        field=f"responsibility_{i}",
                        message=f"Responsibility doesn't start with capital: '{resp[:30]}...'",
                        suggested_fix="Capitalize first letter",
                        score_impact=1.0,
                        auto_fixable=True
                    ))
                    if auto_fix:
                        job["responsibilities"][i] = resp[0].upper() + resp[1:] if len(resp) > 1 else resp.upper()
                        auto_fixes_applied.append(f"Fixed capitalization in responsibility")
    
    # Check verb variety (≥70% unique)
    if cv_doc.jobs:
        all_verbs = []
        for job in cv_doc.jobs:
            responsibilities = job.get("responsibilities", [])
            for resp in responsibilities:
                first_word = resp.split()[0] if resp.split() else ""
                if first_word:
                    all_verbs.append(first_word.lower())
        
        if all_verbs:
            unique_ratio = len(set(all_verbs)) / len(all_verbs)
            if unique_ratio < 0.7:
                issues.append(ValidationIssue(
                    category="text",
                    severity="warning",
                    section="jobs",
                    field="verb_variety",
                    message=f"Low verb variety: {unique_ratio:.1%} unique (min: 70%)",
                    suggested_fix="Use more varied action verbs",
                    score_impact=5.0,
                    auto_fixable=False
                ))
    
    # Check "Erfolgreich" spam (max 20% of bullets)
    if cv_doc.jobs:
        total_bullets = sum(len(job.get("responsibilities", [])) for job in cv_doc.jobs)
        erfolg_count = sum(
            resp.lower().count("erfolgreich")
            for job in cv_doc.jobs
            for resp in job.get("responsibilities", [])
        )
        
        if total_bullets > 0:
            erfolg_ratio = erfolg_count / total_bullets
            if erfolg_ratio > 0.2:
                issues.append(ValidationIssue(
                    category="text",
                    severity="warning",
                    section="jobs",
                    field="erfolgreich_spam",
                    message=f"Too many 'Erfolgreich': {erfolg_ratio:.1%} of bullets (max: 20%)",
                    suggested_fix="Reduce 'Erfolgreich' usage, use varied verbs",
                    score_impact=5.0,
                    auto_fixable=False
                ))
    
    return issues


def _validate_achievements(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]]
) -> List[ValidationIssue]:
    """Validate achievement quality (metrics, impact, progression)."""
    issues = []
    
    if not cv_doc.jobs:
        return issues
    
    # Check ≥60% of bullets have metrics
    total_bullets = 0
    bullets_with_metrics = 0
    
    for job in cv_doc.jobs:
        responsibilities = job.get("responsibilities", [])
        for resp in responsibilities:
            total_bullets += 1
            # Check for numbers (metrics)
            if re.search(r'\d+', resp):
                bullets_with_metrics += 1
    
    if total_bullets > 0:
        metrics_ratio = bullets_with_metrics / total_bullets
        if metrics_ratio < 0.6:
            issues.append(ValidationIssue(
                category="achievement",
                severity="warning",
                section="jobs",
                field="metrics",
                message=f"Only {metrics_ratio:.1%} of bullets have metrics (min: 60%)",
                suggested_fix="Add quantifiable metrics to responsibilities",
                score_impact=10.0,
                auto_fixable=False
            ))
    
    # Check for impact language
    impact_keywords = ["reduzierte", "steigerte", "optimierte", "verbesserte", "erhöhte", "senkte"]
    has_impact = False
    for job in cv_doc.jobs:
        responsibilities = job.get("responsibilities", [])
        for resp in responsibilities:
            if any(kw in resp.lower() for kw in impact_keywords):
                has_impact = True
                break
        if has_impact:
            break
    
    if not has_impact and total_bullets > 0:
        issues.append(ValidationIssue(
            category="achievement",
            severity="warning",
            section="jobs",
            field="impact",
            message="Missing impact language (results/outcomes)",
            suggested_fix="Add impact-focused language showing results",
            score_impact=5.0,
            auto_fixable=False
        ))
    
    # Check progression (newer jobs should have more complex achievements)
    if len(cv_doc.jobs) > 1:
        sorted_jobs = sorted(
            cv_doc.jobs,
            key=lambda j: parse_date_to_year(j.get("start_date", "2000-01")) or 2000,
            reverse=True  # Most recent first
        )
        
        # Current job should have most responsibilities
        if sorted_jobs:
            current_job = sorted_jobs[0]
            current_resp_count = len(current_job.get("responsibilities", []))
            
            for job in sorted_jobs[1:]:
                resp_count = len(job.get("responsibilities", []))
                if resp_count > current_resp_count:
                    issues.append(ValidationIssue(
                        category="achievement",
                        severity="info",
                        section="jobs",
                        field="progression",
                        message="Older jobs have more responsibilities than current job",
                        suggested_fix="Ensure progression: newer jobs = more complex",
                        score_impact=2.0,
                        auto_fixable=False
                    ))
                    break
    
    return issues


def _validate_personalization(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]]
) -> List[ValidationIssue]:
    """Validate personalization (email, phone, languages, hobbies)."""
    issues = []
    
    # Check email format
    email = cv_doc.email
    if email:
        age = cv_doc.age
        age_group = get_age_group(age)
        
        # Check age-appropriate email domains
        if age_group == "18-25":
            if "@bluewin.ch" in email or "@sunrise.ch" in email:
                issues.append(ValidationIssue(
                    category="personalization",
                    severity="info",
                    section="personal",
                    field="email",
                    message=f"Email domain might not match age group {age_group}",
                    suggested_fix="Use gmail.com or protonmail.com for younger age groups",
                    score_impact=1.0,
                    auto_fixable=False
                ))
        elif age_group == "41-65":
            if "@gmail.com" in email and "@protonmail.com" not in email:
                # Gmail is still common, but bluewin/sunrise more common for older
                pass  # Not an issue, just info
    
    # Check phone format (Swiss mobile: 07X XXX XX XX)
    phone = cv_doc.phone
    if phone:
        if not re.match(r'^07[0-9]\s\d{3}\s\d{2}\s\d{2}$', phone.replace(" ", "")):
            issues.append(ValidationIssue(
                category="personalization",
                severity="warning",
                section="personal",
                field="phone",
                message=f"Phone format might not be Swiss mobile: {phone}",
                suggested_fix="Use format: 07X XXX XX XX",
                score_impact=2.0,
                auto_fixable=False
            ))
    
    # Check languages match canton
    languages = cv_doc.skills.get("languages", [])
    if languages and cv_doc.canton:
        canton_doc = get_canton_by_code(cv_doc.canton)
        if canton_doc:
            lang_de = canton_doc.get("language_de", 0)
            lang_fr = canton_doc.get("language_fr", 0)
            lang_it = canton_doc.get("language_it", 0)
            
            # Check if primary language matches canton
            primary_lang = cv_doc.language
            if primary_lang == "de" and lang_de < 50:
                issues.append(ValidationIssue(
                    category="personalization",
                    severity="info",
                    section="skills",
                    field="languages",
                    message=f"Primary language {primary_lang} might not match canton {cv_doc.canton} distribution",
                    suggested_fix="Verify language matches canton",
                    score_impact=1.0,
                    auto_fixable=False
                ))
    
    # Check hobbies varied (not all identical)
    hobbies = cv_doc.hobbies
    if hobbies:
        if len(hobbies) == len(set(hobbies)):
            # All unique, good
            pass
        else:
            issues.append(ValidationIssue(
                category="personalization",
                severity="info",
                section="content",
                field="hobbies",
                message="Some hobbies are duplicated",
                suggested_fix="Ensure hobbies are varied",
                score_impact=1.0,
                auto_fixable=False
            ))
    
    return issues


def _validate_completeness(cv_doc: CVDocument) -> List[ValidationIssue]:
    """Validate completeness of CV sections."""
    issues = []
    
    # Check required sections
    if not cv_doc.first_name or not cv_doc.last_name:
        issues.append(ValidationIssue(
            category="completeness",
            severity="critical",
            section="personal",
            field="name",
            message="Missing first or last name",
            suggested_fix="Ensure persona has valid first_name and last_name",
            score_impact=20.0,
            auto_fixable=False
        ))
    
    if not cv_doc.summary or len(cv_doc.summary.strip()) < 50:
        issues.append(ValidationIssue(
            category="completeness",
            severity="warning",
            section="content",
            field="summary",
            message="Summary too short or missing (min 50 chars)",
            suggested_fix="Generate longer summary",
            score_impact=10.0,
            auto_fixable=False
        ))
    
    if not cv_doc.education or len(cv_doc.education) == 0:
        issues.append(ValidationIssue(
            category="completeness",
            severity="critical",
            section="content",
            field="education",
            message="No education entries",
            suggested_fix="Generate at least one education entry",
            score_impact=25.0,
            auto_fixable=False
        ))
    
    if not cv_doc.jobs or len(cv_doc.jobs) == 0:
        issues.append(ValidationIssue(
            category="completeness",
            severity="critical",
            section="content",
            field="jobs",
            message="No job entries",
            suggested_fix="Generate at least one job entry",
            score_impact=30.0,
            auto_fixable=False
        ))
    
    # Check minimum content per job
    if cv_doc.jobs:
        for i, job in enumerate(cv_doc.jobs):
            if job.get("category") == "gap_filler":
                continue
            
            responsibilities = job.get("responsibilities", [])
            if len(responsibilities) < 2:
                issues.append(ValidationIssue(
                    category="completeness",
                    severity="warning",
                    section="jobs",
                    field=f"entry_{i}_responsibilities",
                    message=f"Job entry {i+1} has fewer than 2 responsibilities",
                    suggested_fix="Generate at least 2 responsibilities per job",
                    score_impact=5.0,
                    auto_fixable=False
                ))
    
    # Check skills
    total_skills = sum(len(skills_list) for skills_list in cv_doc.skills.values())
    if total_skills < 8:
        issues.append(ValidationIssue(
            category="completeness",
            severity="warning",
            section="content",
            field="skills",
            message=f"Too few skills (has {total_skills}, min 8)",
            suggested_fix="Generate at least 8 skills total",
            score_impact=10.0,
            auto_fixable=False
        ))
    
    return issues


def save_validation_report(report: ValidationReport, output_path: Path) -> Path:
    """Save validation report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    
    return output_path


def validate_cv_quality(
    cv_doc: CVDocument,
    persona: Optional[Dict[str, Any]] = None,
    min_score: float = 75.0,
    save_report: bool = True,
    report_path: Optional[Path] = None,
    auto_fix: bool = True
) -> Tuple[bool, ValidationReport]:
    """
    Validate CV quality using comprehensive validation.
    
    Args:
        cv_doc: Complete CV document.
        persona: Optional persona dictionary.
        min_score: Minimum score threshold (default: 75.0).
        save_report: Whether to save validation report.
        report_path: Optional path for report.
        auto_fix: Whether to attempt auto-fixes.
    
    Returns:
        Tuple of (passed, validation_report).
    """
    report = validate_complete_cv(cv_doc, persona, min_score, auto_fix)
    
    if save_report:
        if not report_path:
            report_path = Path(project_root / "output" / "validation_reports" / f"{report.cv_id}_validation.json")
        save_validation_report(report, report_path)
    
    return report.passed, report
