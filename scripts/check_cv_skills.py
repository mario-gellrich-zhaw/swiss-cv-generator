#!/usr/bin/env python3
"""
Check if CVs have proper skills.
This script analyzes CV generation to verify skills are present.
"""
from src.generation.sampling import SamplingEngine
from src.generation.cv_assembler import generate_complete_cv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_cv_generation():
    """Generate a few test CVs and check if they have skills."""
    engine = SamplingEngine()

    print("🔍 Testing CV Skills Generation\n")
    print("=" * 60)

    issues_found = 0

    for i in range(5):
        print(f"\n📝 Test CV #{i+1}")

        # Sample persona
        persona = engine.sample_persona()
        name = f"{persona.get('first_name', '')} {persona.get('last_name', '')}"
        print(f"   Name: {name}")
        print(f"   Occupation: {persona.get('occupation', 'N/A')}")

        # Generate CV
        cv_doc, quality_report = generate_complete_cv(persona)

        if cv_doc is None:
            print(f"   ❌ CV generation failed (quality too low)")
            issues_found += 1
            continue

        # Check skills
        skills = cv_doc.skills
        technical = skills.get("technical", [])
        soft = skills.get("soft", [])
        languages = skills.get("languages", [])

        print(f"   Technical skills: {len(technical)}")
        print(f"   Soft skills: {len(soft)}")
        print(f"   Languages: {len(languages)}")

        # Verify at least some skills exist
        total_skills = len(technical) + len(soft)

        if total_skills == 0:
            print(f"   ❌ NO SKILLS FOUND!")
            print(f"      Skills dict: {skills}")
            issues_found += 1
        elif total_skills < 5:
            print(f"   ⚠️  Warning: Only {total_skills} skills found")
            print(f"      Technical: {technical}")
            print(f"      Soft: {soft}")
        else:
            print(f"   ✅ Skills OK ({total_skills} total)")
            if technical:
                print(f"      Sample technical: {technical[:3]}")
            if soft:
                print(f"      Sample soft: {soft[:3]}")

    print("\n" + "=" * 60)
    print(f"\n🎯 Result: {issues_found} issues found out of 5 CVs")

    return issues_found


if __name__ == "__main__":
    issues = check_cv_generation()
    sys.exit(0 if issues == 0 else 1)
