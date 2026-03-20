#!/usr/bin/env python3
"""
Test edge cases for skills generation.
"""
from src.generation.cv_assembler import categorize_skills, generate_complete_cv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_empty_skills():
    """Test case where persona has no skills."""
    print("📝 Test Case 1: Empty skills list")

    persona = {
        "first_name": "Test",
        "last_name": "Person",
        "age": 30,
        "gender": "male",
        "canton": "ZH",
        "language": "de",
        "occupation": "Test Occupation",
        "industry": "Test",
        "career_level": "mid",
        "years_experience": 5,
        "job_id": None,  # No job_id - can't fetch from DB
        "skills": [],  # Empty skills
        "education_level": "vocational",
        "start_year": 2015,
    }

    cv_doc, _ = generate_complete_cv(persona)

    if cv_doc:
        skills = cv_doc.skills
        technical = skills.get("technical", [])
        soft = skills.get("soft", [])
        total = len(technical) + len(soft)

        print(f"   Technical: {len(technical)}")
        print(f"   Soft: {len(soft)}")
        print(f"   Total: {total}")

        if total > 0:
            print(f"   ✅ Fallback worked! Got {total} skills")
            print(f"      Soft skills: {soft}")
            return True
        else:
            print(f"   ❌ FAILED: No skills generated")
            return False
    else:
        print(f"   ❌ CV generation failed")
        return False


def test_dict_skills_empty():
    """Test case where persona has dict skills but they're empty."""
    print("\n📝 Test Case 2: Empty dict skills")

    persona = {
        "first_name": "Test",
        "last_name": "Person2",
        "age": 30,
        "gender": "female",
        "canton": "ZH",
        "language": "de",
        "occupation": "Test Occupation",
        "industry": "Test",
        "career_level": "mid",
        "years_experience": 5,
        "job_id": None,
        # Empty skill name
        "skills": [{"skill_name_de": "", "skill_category": "technical"}],
        "education_level": "vocational",
        "start_year": 2015,
    }

    cv_doc, _ = generate_complete_cv(persona)

    if cv_doc:
        skills = cv_doc.skills
        technical = skills.get("technical", [])
        soft = skills.get("soft", [])
        total = len(technical) + len(soft)

        print(f"   Technical: {len(technical)}")
        print(f"   Soft: {len(soft)}")
        print(f"   Total: {total}")

        if total > 0:
            print(f"   ✅ Fallback worked! Got {total} skills")
            return True
        else:
            print(f"   ❌ FAILED: No skills generated")
            return False
    else:
        print(f"   ❌ CV generation failed")
        return False


def test_categorize_skills_empty():
    """Test categorize_skills with empty list."""
    print("\n📝 Test Case 3: categorize_skills with empty list")

    result = categorize_skills([])
    technical = result.get("technical", [])
    soft = result.get("soft", [])

    print(f"   Result: {result}")

    if len(technical) == 0 and len(soft) == 0:
        print(f"   ✅ Returns empty dict as expected")
        return True
    else:
        print(f"   ❌ Unexpected result")
        return False


if __name__ == "__main__":
    print("🔍 Testing Skills Edge Cases\n")
    print("=" * 60)

    test1 = test_empty_skills()
    test2 = test_dict_skills_empty()
    test3 = test_categorize_skills_empty()

    print("\n" + "=" * 60)

    if test1 and test2 and test3:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)
