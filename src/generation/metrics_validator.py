"""
CV Metrics Validator.

This module validates and ensures realistic metrics in CV responsibility bullets:
- Realistic metric ranges per career level
- Validation during generation
- Metric consistency per job
- AI prompt enhancement

Run: Used by CV generation pipeline AFTER bullet generation, BEFORE adding to CV
"""
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class MetricType(Enum):
    """Types of metrics found in CV bullets."""
    PERCENTAGE = "percentage"
    TEAM_SIZE = "team_size"
    PROJECTS = "projects"
    CUSTOMERS = "customers"
    FINANCIAL = "financial"
    UNKNOWN = "unknown"


@dataclass
class MetricRange:
    """Range for a metric type at a career level."""
    min_val: float
    max_val: float
    absolute_max: float


@dataclass
class ExtractedMetric:
    """Extracted metric from bullet text."""
    value: float
    metric_type: MetricType
    unit: str
    text: str
    position: int  # Position in text


# REALISTIC METRIC RANGES
METRIC_RANGES = {
    MetricType.PERCENTAGE: {
        "junior": MetricRange(5.0, 15.0, 50.0),
        "mid": MetricRange(10.0, 25.0, 50.0),
        "senior": MetricRange(15.0, 35.0, 50.0),
        "lead": MetricRange(20.0, 40.0, 50.0),
    },
    MetricType.TEAM_SIZE: {
        "junior": MetricRange(0.0, 0.0, 0.0),  # No team
        "mid": MetricRange(2.0, 8.0, 100.0),
        "senior": MetricRange(5.0, 15.0, 100.0),
        "lead": MetricRange(10.0, 50.0, 100.0),
    },
    MetricType.PROJECTS: {
        "junior": MetricRange(1.0, 5.0, 50.0),  # Per year
        "mid": MetricRange(3.0, 10.0, 50.0),
        "senior": MetricRange(5.0, 20.0, 50.0),
        "lead": MetricRange(10.0, 30.0, 50.0),
    },
    MetricType.CUSTOMERS: {
        "junior": MetricRange(5.0, 20.0, 500.0),  # Per day/month/year
        "mid": MetricRange(10.0, 50.0, 500.0),
        "senior": MetricRange(20.0, 100.0, 500.0),
        "lead": MetricRange(50.0, 200.0, 500.0),
    },
    MetricType.FINANCIAL: {
        "junior": MetricRange(0.0, 0.0, 0.0),  # None
        "mid": MetricRange(100000.0, 500000.0, 10000000.0),  # CHF
        "senior": MetricRange(500000.0, 2000000.0, 10000000.0),
        "lead": MetricRange(1000000.0, 10000000.0, 10000000.0),
    },
}

# REJECT PATTERNS
REJECT_PATTERNS = {
    "percentage_over_100": lambda val: val > 100.0,
    "team_size_over_100": lambda val: val > 100.0,
    "projects_over_50": lambda val: val > 50.0,
    "negative_numbers": lambda val: val < 0.0,
    "numbers_over_10000": lambda val: val > 10000.0 and val < 100000.0,  # Likely calculation error
}


def extract_metric_from_text(text: str) -> Optional[ExtractedMetric]:
    """
    Extract metric from bullet text.
    
    Args:
        text: Bullet text (e.g., "Reduzierte Kosten um 18%", "Leitete Team von 12 Entwicklern").
    
    Returns:
        ExtractedMetric or None if no metric found.
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Pattern 1: Percentage (18%, 25 Prozent, um 30% reduziert)
    percentage_patterns = [
        r'(\d+(?:[.,]\d+)?)\s*%',
        r'(\d+(?:[.,]\d+)?)\s*prozent',
        r'um\s+(\d+(?:[.,]\d+)?)\s*%',
        r'um\s+(\d+(?:[.,]\d+)?)\s*prozent',
    ]
    for pattern in percentage_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return ExtractedMetric(
                    value=value,
                    metric_type=MetricType.PERCENTAGE,
                    unit="%",
                    text=text,
                    position=match.start()
                )
            except ValueError:
                continue
    
    # Pattern 2: Team size (12 Entwickler, Team von 8 Personen, 15-köpfiges Team)
    team_patterns = [
        r'team\s+von\s+(\d+)\s*(?:entwicklern?|personen?|mitarbeitern?|kollegen?)',
        r'(\d+)\s*(?:entwicklern?|personen?|mitarbeitern?|kollegen?)',
        r'(\d+)[-–]\s*köpfiges?\s+team',
        r'führte\s+(\d+)\s*(?:personen?|mitarbeiter)',
    ]
    for pattern in team_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1))
                return ExtractedMetric(
                    value=value,
                    metric_type=MetricType.TEAM_SIZE,
                    unit="Personen",
                    text=text,
                    position=match.start()
                )
            except ValueError:
                continue
    
    # Pattern 3: Projects (25 Projekte, 10 Kundenprojekte, 8 parallele Projekte)
    project_patterns = [
        r'(\d+)\s*(?:projekte?|kundenprojekte?)',
        r'(\d+)\s*parallele\s+projekte',
        r'(\d+)\s*projekte\s+erfolgreich',
    ]
    for pattern in project_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1))
                return ExtractedMetric(
                    value=value,
                    metric_type=MetricType.PROJECTS,
                    unit="Projekte",
                    text=text,
                    position=match.start()
                )
            except ValueError:
                continue
    
    # Pattern 4: Customers (50 Kunden, 100 Kunden pro Jahr, 20 Kunden betreut)
    customer_patterns = [
        r'(\d+)\s*(?:kunden?|clients?|kundinnen?)',
        r'(\d+)\s*kunden\s+(?:pro\s+(?:jahr|monat|tag)|betreut)',
    ]
    for pattern in customer_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1))
                return ExtractedMetric(
                    value=value,
                    metric_type=MetricType.CUSTOMERS,
                    unit="Kunden",
                    text=text,
                    position=match.start()
                )
            except ValueError:
                continue
    
    # Pattern 5: Financial (CHF 500K, Budget von 2M, 1.5 Millionen CHF)
    financial_patterns = [
        r'chf\s+(\d+(?:[.,]\d+)?)\s*(?:k|m|millionen?)',
        r'budget\s+von\s+(\d+(?:[.,]\d+)?)\s*(?:k|m|millionen?)',
        r'(\d+(?:[.,]\d+)?)\s*(?:millionen?|mio)\s+chf',
        r'(\d+(?:[.,]\d+)?)\s*(?:k|m)\s+chf',
    ]
    for pattern in financial_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value_str = match.group(1).replace(',', '.')
                value = float(value_str)
                
                # Convert K/M to actual numbers
                if 'k' in text_lower[match.end():match.end()+5]:
                    value *= 1000
                elif 'm' in text_lower[match.end():match.end()+5] or 'millionen' in text_lower[match.end():match.end()+10]:
                    value *= 1000000
                
                return ExtractedMetric(
                    value=value,
                    metric_type=MetricType.FINANCIAL,
                    unit="CHF",
                    text=text,
                    position=match.start()
                )
            except ValueError:
                continue
    
    return None


def validate_metric(
    metric: ExtractedMetric,
    career_level: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate metric against realistic ranges for career level.
    
    Args:
        metric: Extracted metric from bullet text.
        career_level: Career level (junior, mid, senior, lead).
    
    Returns:
        Tuple of (is_valid, error_message).
    """
    if not metric:
        return False, "No metric found"
    
    # Check reject patterns first
    for pattern_name, reject_func in REJECT_PATTERNS.items():
        if reject_func(metric.value):
            return False, f"Metric rejected by pattern: {pattern_name} (value: {metric.value})"
    
    # Get range for this metric type and career level
    ranges = METRIC_RANGES.get(metric.metric_type)
    if not ranges:
        return True, None  # Unknown metric type, allow it
    
    level_range = ranges.get(career_level)
    if not level_range:
        return True, None  # Unknown career level, allow it
    
    # Special case: percentages > 100% are always invalid
    if metric.metric_type == MetricType.PERCENTAGE and metric.value > 100.0:
        return False, f"Percentage {metric.value}% exceeds 100%"
    
    # Check if value is within absolute max
    if metric.value > level_range.absolute_max:
        return False, f"Metric {metric.value} exceeds absolute max {level_range.absolute_max} for {metric.metric_type.value}"
    
    # Check if value is within realistic range (warning, not error)
    if metric.value < level_range.min_val or metric.value > level_range.max_val:
        # Allow if within absolute max, but return warning
        return True, f"Metric {metric.value} outside typical range [{level_range.min_val}-{level_range.max_val}] for {career_level}"
    
    return True, None


def validate_bullet_metrics(
    bullet: str,
    career_level: str
) -> Tuple[bool, Optional[str], Optional[ExtractedMetric]]:
    """
    Validate all metrics in a single bullet.
    
    Args:
        bullet: Bullet text.
        career_level: Career level.
    
    Returns:
        Tuple of (is_valid, error_message, extracted_metric).
    """
    metric = extract_metric_from_text(bullet)
    
    if not metric:
        return False, "No metric found in bullet", None
    
    is_valid, error_msg = validate_metric(metric, career_level)
    
    return is_valid, error_msg, metric


def validate_job_metric_consistency(
    bullets: List[str],
    career_level: str
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate metric consistency across bullets in a job.
    
    Rules:
    - Use ONE metric type per bullet (not mixing)
    - Vary metric types across bullets in same job
    - Reject bullets with multiple metric types
    
    Args:
        bullets: List of bullet texts for a job.
        career_level: Career level.
    
    Returns:
        Tuple of (is_valid, issues, metric_distribution).
    """
    issues = []
    metric_distribution = {
        MetricType.PERCENTAGE: 0,
        MetricType.TEAM_SIZE: 0,
        MetricType.PROJECTS: 0,
        MetricType.CUSTOMERS: 0,
        MetricType.FINANCIAL: 0,
        MetricType.UNKNOWN: 0,
    }
    
    bullets_with_metrics = []
    
    for i, bullet in enumerate(bullets):
        # Extract all numbers from bullet
        numbers = re.findall(r'\d+(?:[.,]\d+)?', bullet.lower())
        
        if len(numbers) > 3:
            # Too many numbers - likely mixing metrics
            issues.append(f"Bullet {i+1}: Too many numbers ({len(numbers)}), likely mixing metric types")
        
        metric = extract_metric_from_text(bullet)
        if metric:
            bullets_with_metrics.append((i, metric))
            metric_distribution[metric.metric_type] += 1
            
            # Validate this metric
            is_valid, error_msg = validate_metric(metric, career_level)
            if not is_valid:
                issues.append(f"Bullet {i+1}: {error_msg}")
    
    # Check for variety (at least 2 different metric types if 3+ bullets)
    if len(bullets_with_metrics) >= 3:
        used_types = [m.metric_type for _, m in bullets_with_metrics]
        unique_types = set(used_types)
        if len(unique_types) < 2:
            issues.append(f"Job has {len(bullets_with_metrics)} bullets but only {len(unique_types)} metric type(s) - needs more variety")
    
    # Check for excessive use of one type
    max_count = max(metric_distribution.values())
    if max_count > len(bullets) * 0.6:  # More than 60% of bullets use same type
        dominant_type = [k for k, v in metric_distribution.items() if v == max_count][0]
        issues.append(f"Too many bullets use {dominant_type.value} ({max_count}/{len(bullets)}) - needs more variety")
    
    is_valid = len(issues) == 0
    
    return is_valid, issues, metric_distribution


def get_metric_range_prompt(career_level: str) -> str:
    """
    Get metric range description for AI prompt enhancement.
    
    Args:
        career_level: Career level.
    
    Returns:
        Prompt text with realistic metric ranges.
    """
    ranges_text = []
    
    for metric_type, levels in METRIC_RANGES.items():
        level_range = levels.get(career_level)
        if not level_range or level_range.min_val == level_range.max_val == 0.0:
            continue
        
        if metric_type == MetricType.PERCENTAGE:
            ranges_text.append(f"percentages: {level_range.min_val:.0f}-{level_range.max_val:.0f}% (max 50%)")
        elif metric_type == MetricType.TEAM_SIZE:
            if level_range.min_val == 0:
                ranges_text.append(f"team size: none (no team leadership)")
            else:
                ranges_text.append(f"team size: {level_range.min_val:.0f}-{level_range.max_val:.0f} people (max 100)")
        elif metric_type == MetricType.PROJECTS:
            ranges_text.append(f"projects: {level_range.min_val:.0f}-{level_range.max_val:.0f} per year (max 50)")
        elif metric_type == MetricType.CUSTOMERS:
            ranges_text.append(f"customers: {level_range.min_val:.0f}-{level_range.max_val:.0f} (max 500)")
        elif metric_type == MetricType.FINANCIAL:
            ranges_text.append(f"budget: CHF {level_range.min_val/1000:.0f}K-{level_range.max_val/1000:.0f}K (max CHF {level_range.absolute_max/1000:.0f}K)")
    
    if ranges_text:
        return f"Use realistic metrics for {career_level} level: {', '.join(ranges_text)}. Never exceed absolute maximums."
    else:
        return f"Use realistic metrics for {career_level} level. Avoid unrealistic numbers (>100%, teams >100, projects >50)."


def enhance_achievement_prompt(
    base_prompt: str,
    career_level: str
) -> str:
    """
    Enhance achievement prompt with metric range guidance.
    
    Args:
        base_prompt: Base AI prompt for achievement generation.
        career_level: Career level.
    
    Returns:
        Enhanced prompt with metric guidance.
    """
    metric_guidance = get_metric_range_prompt(career_level)
    
    # Add metric guidance to prompt
    enhanced_prompt = f"""{base_prompt}

METRIC REQUIREMENTS:
- {metric_guidance}
- Use ONE metric type per bullet (not mixing percentages, team size, and projects)
- Vary metric types across bullets in the same job
- Example good bullets:
  * "Leitete Team von 12 Entwicklern" (team size)
  * "Optimierte Prozesse, reduzierte Kosten um 18%" (percentage)
  * "Betreute 25 Kundenprojekte erfolgreich" (projects)
- NEVER use: "Leitete 12 Personen, 301%, 70 Projekte" in one bullet (mixing types)
- NEVER exceed: 100% (percentages), 100 people (teams), 50 projects (per position)
"""
    
    return enhanced_prompt


def validate_job_bullets(
    bullets: List[str],
    career_level: str,
    auto_fix: bool = False
) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """
    Validate all bullets for a job and optionally fix issues.
    
    Args:
        bullets: List of bullet texts.
        career_level: Career level.
        auto_fix: Whether to attempt automatic fixes (currently not implemented).
    
    Returns:
        Tuple of (validated_bullets, issues, statistics).
    """
    validated_bullets = []
    all_issues = []
    statistics = {
        "total_bullets": len(bullets),
        "bullets_with_metrics": 0,
        "invalid_metrics": 0,
        "metric_types": {},
    }
    
    # Validate each bullet
    for i, bullet in enumerate(bullets):
        is_valid, error_msg, metric = validate_bullet_metrics(bullet, career_level)
        
        if metric:
            statistics["bullets_with_metrics"] += 1
            metric_type_name = metric.metric_type.value
            statistics["metric_types"][metric_type_name] = statistics["metric_types"].get(metric_type_name, 0) + 1
        
        if not is_valid:
            statistics["invalid_metrics"] += 1
            all_issues.append(f"Bullet {i+1}: {error_msg}")
            if auto_fix:
                # TODO: Implement auto-fix (regenerate with corrected prompt)
                pass
            else:
                # Reject invalid bullet
                continue
        
        validated_bullets.append(bullet)
    
    # Validate consistency across bullets
    is_consistent, consistency_issues, metric_dist = validate_job_metric_consistency(
        validated_bullets, career_level
    )
    
    if not is_consistent:
        all_issues.extend(consistency_issues)
    
    statistics["metric_distribution"] = {k.value: v for k, v in metric_dist.items()}
    statistics["consistency_valid"] = is_consistent
    
    return validated_bullets, all_issues, statistics

