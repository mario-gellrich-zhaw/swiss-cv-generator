#!/usr/bin/env python3
"""
Initialize MongoDB with essential data on startup.

This script:
1. Checks if MongoDB is running
2. Checks if collections exist and have data
3. If empty, loads essential data (cantons, first_names, last_names)
4. Provides summary of what was loaded

This is designed to run automatically on Codespaces startup.

Run: python scripts/init_mongodb_on_startup.py
"""
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

from pymongo.errors import ConnectionFailure

from src.config import get_settings
from src.database.mongodb_manager import get_db_manager

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


console_output = []


def log(msg: str, level: str = "info"):
    """Log messages to console and store them."""
    symbols = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
    symbol = symbols.get(level, "•")
    output = f"{symbol} {msg}"
    console_output.append(output)
    print(output)


def wait_for_mongodb(timeout: int = 30) -> bool:
    """Wait for MongoDB to be ready."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            manager = get_db_manager()
            manager.connect()
            return True
        except ConnectionFailure:
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:
                log(f"Waiting for MongoDB... ({elapsed}s)", "info")
            time.sleep(2)

    return False


def check_collections_exist(db_manager) -> Dict[str, bool]:
    """Check which essential collections exist and have data."""
    target_db = db_manager.target_db

    collections = {
        "cantons": False,
        "first_names": False,
        "last_names": False,
        "companies": False,
    }

    try:
        existing_collections = target_db.list_collection_names()
        for coll_name in collections.keys():
            if coll_name in existing_collections:
                coll = target_db[coll_name]
                collections[coll_name] = coll.count_documents({}) > 0
    except Exception as e:
        log(f"Error checking collections: {e}", "warning")

    return collections


def init_collections(db_manager) -> bool:
    """Initialize collection structure."""
    try:
        log("Initializing MongoDB collections...", "info")
        subprocess.run(
            [sys.executable, str(project_root / "src" /
                                 "database" / "init_collections.py")],
            cwd=str(project_root),
            capture_output=True,
            timeout=30,
            check=False
        )
        log("Collections initialized", "success")
        return True
    except Exception as e:
        log(f"Error initializing collections: {e}", "warning")
        return False


def load_cantons(db_manager) -> int:
    """Load canton data from fallback script."""
    try:
        log("Loading canton data...", "info")
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" /
                                 "load_cantons_fallback.py")],
            cwd=str(project_root),
            capture_output=True,
            timeout=30,
            check=False
        )
        if result.returncode == 0:
            coll = db_manager.get_target_collection("cantons")
            count = coll.count_documents({})
            log(f"Loaded {count} cantons", "success")
            return count
        else:
            log(
                f"Failed to load cantons: {result.stderr.decode()[:100]}", "warning")
            return 0
    except Exception as e:
        log(f"Error loading cantons: {e}", "warning")
        return 0


def load_first_names(db_manager) -> int:
    """Load first names from generation script."""
    try:
        log("Loading first names...", "info")
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" /
                                 "ai_generate_first_names.py"), "--skip-existing"],
            cwd=str(project_root),
            capture_output=True,
            timeout=120,
            check=False
        )
        if result.returncode == 0:
            coll = db_manager.get_target_collection("first_names")
            count = coll.count_documents({})
            log(f"Loaded {count} first names", "success")
            return count
        else:
            error_msg = result.stderr.decode()[:200]
            if "OpenAI" in error_msg:
                log("Skipping first names (OpenAI not configured)", "warning")
            else:
                log(
                    f"Failed to load first names: {error_msg}", "warning")
            return 0
    except Exception as e:
        log(f"Error loading first names: {e}", "warning")
        return 0


def load_last_names(db_manager) -> int:
    """Load last names from generation script."""
    try:
        log("Loading last names...", "info")
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" /
                                 "ai_generate_last_names.py")],
            cwd=str(project_root),
            capture_output=True,
            timeout=120,
            check=False
        )
        if result.returncode == 0:
            coll = db_manager.get_target_collection("last_names")
            count = coll.count_documents({})
            log(f"Loaded {count} last names", "success")
            return count
        else:
            error_msg = result.stderr.decode()[:200]
            if "OpenAI" in error_msg:
                log("Skipping last names (OpenAI not configured)", "warning")
            else:
                log(
                    f"Failed to load last names: {error_msg}", "warning")
            return 0
    except Exception as e:
        log(f"Error loading last names: {e}", "warning")
        return 0


def load_occupation_skills(db_manager) -> int:
    """Load occupation skills from extraction script."""
    try:
        log("Extracting occupation skills...", "info")
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" /
                                 "extract_skills_from_cv_data.py")],
            cwd=str(project_root),
            capture_output=True,
            timeout=120,
            check=False
        )
        if result.returncode == 0:
            coll = db_manager.get_target_collection("occupation_skills")
            count = coll.count_documents({})
            log(f"Extracted {count} occupation skills", "success")
            return count
        else:
            log(
                f"Failed to extract skills: {result.stderr.decode()[:100]}", "warning")
            return 0
    except Exception as e:
        log(f"Error extracting skills: {e}", "warning")
        return 0


def main():
    """Main initialization logic."""
    print("\n" + "=" * 60)
    print("🚀 MongoDB Startup Initialization")
    print("=" * 60 + "\n")

    settings = get_settings()

    try:
        # Step 1: Wait for MongoDB
        log(f"Connecting to MongoDB at {settings.mongodb_uri}...", "info")
        if not wait_for_mongodb():
            log("MongoDB did not become ready. Skipping initialization.", "error")
            print("\n" + "=" * 60 + "\n")
            return False

        log("Connected to MongoDB", "success")

        # Step 2: Check what data we have
        db_manager = get_db_manager()
        db_manager.connect()

        collections = check_collections_exist(db_manager)

        # Step 3: If any essential collection is empty, restore from JSON snapshots first
        missing = [name for name, has_data in collections.items() if not has_data]
        if missing:
            snapshot_dir = project_root / "data" / "swiss_cv_generator"
            if snapshot_dir.exists():
                log(f"Missing collections: {missing}. Restoring from snapshots...", "info")
                result = subprocess.run(
                    [sys.executable, str(project_root / "scripts" / "import_database.py")],
                    cwd=str(project_root),
                    capture_output=True,
                    timeout=120,
                    check=False
                )
                if result.returncode == 0:
                    log("Restored from snapshots successfully", "success")
                    # Refresh collection status after import
                    collections = check_collections_exist(db_manager)
                    missing = [name for name, has_data in collections.items() if not has_data]
                else:
                    log(f"Snapshot import failed: {result.stderr.decode()[:200]}", "warning")
            else:
                log("No snapshots found in data/swiss_cv_generator/", "warning")

        # Step 4: Fall back to AI generation for anything still missing
        if not any(collections.values()):
            log("No collections found. Initializing...", "info")
            init_collections(db_manager)

        if collections.get("cantons", 0) == 0:
            load_cantons(db_manager)
        else:
            log(
                f"Cantons already loaded ({collections['cantons']} records)", "success")

        if collections.get("first_names", 0) == 0:
            load_first_names(db_manager)
        else:
            log(
                f"First names already loaded ({collections['first_names']} records)", "success")

        if collections.get("last_names", 0) == 0:
            load_last_names(db_manager)
        else:
            log(
                f"Last names already loaded ({collections['last_names']} records)", "success")

        if collections.get("occupation_skills", 0) == 0:
            load_occupation_skills(db_manager)

        # Step 5: Summary
        print("\n" + "-" * 60)
        log("MongoDB Status:", "info")
        print("-" * 60)

        # Refresh counts
        collections = check_collections_exist(db_manager)
        for coll_name, count in collections.items():
            if count > 0:
                log(f"{coll_name}: {count} documents", "success")
            else:
                log(f"{coll_name}: empty (not loaded)", "warning")

        print("\n" + "=" * 60)
        log("MongoDB startup initialization complete!", "success")
        print("=" * 60 + "\n")

        return True

    except Exception as e:
        log(f"Unexpected error: {e}", "error")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            db_manager.close()
        except:
            pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
