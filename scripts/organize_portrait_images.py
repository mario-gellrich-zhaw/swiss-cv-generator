"""
Organize portrait images into structured folders by gender and age group.

This script:
1. Scans uploaded portrait folders (Female_1-3, Male_1-3)
2. Maps folders to age groups
3. Creates organized structure and index
4. Validates images
5. Generates statistics

Run: python scripts/organize_portrait_images.py
"""
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
from PIL import Image

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

console = Console()

# Age group mapping
AGE_GROUP_MAPPING = {
    "Female_1": "18-25",
    "Male_1": "18-25",
    "Female_2": "26-40",
    "Male_2": "26-40",
    "Female_3": "41-65",
    "Male_3": "41-65"
}

# Supported image formats
SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}

# Minimum recommended dimensions
MIN_DIMENSIONS = (400, 400)


def find_portrait_folders(base_path: Path) -> Dict[str, Path]:
    """
    Find portrait folders in the project.
    
    Args:
        base_path: Base path to search.
    
    Returns:
        Dictionary mapping folder names to paths.
    """
    folders = {}
    
    # Look in common locations
    search_paths = [
        base_path,
        base_path / "data" / "portraits",
        base_path / "portraits",
        base_path / "images",
        base_path / "data" / "images",
    ]
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
        
        for folder_name in ["Female_1", "Female_2", "Female_3", "Male_1", "Male_2", "Male_3"]:
            folder_path = search_path / folder_name
            if folder_path.exists() and folder_path.is_dir():
                folders[folder_name] = folder_path
    
    # Also search recursively
    for search_path in search_paths:
        if search_path.exists():
            for folder_path in search_path.rglob("*"):
                if folder_path.is_dir() and folder_path.name in ["Female_1", "Female_2", "Female_3", "Male_1", "Male_2", "Male_3"]:
                    if folder_path.name not in folders:
                        folders[folder_path.name] = folder_path
    
    return folders


def count_images_in_folder(folder_path: Path) -> Tuple[int, List[Path]]:
    """
    Count images in a folder.
    
    Args:
        folder_path: Path to folder.
    
    Returns:
        Tuple of (count, list of image paths).
    """
    images = []
    if not folder_path.exists():
        return 0, images
    
    for file_path in folder_path.iterdir():
        if file_path.is_file() and file_path.suffix in SUPPORTED_FORMATS:
            images.append(file_path)
    
    return len(images), images


def validate_image(image_path: Path) -> Dict[str, Any]:
    """
    Validate an image file.
    
    Args:
        image_path: Path to image file.
    
    Returns:
        Dictionary with validation results.
    """
    result = {
        "valid": False,
        "format": image_path.suffix.lower(),
        "width": None,
        "height": None,
        "error": None
    }
    
    try:
        with Image.open(image_path) as img:
            result["width"] = img.width
            result["height"] = img.height
            result["valid"] = True
            
            # Check dimensions
            if img.width < MIN_DIMENSIONS[0] or img.height < MIN_DIMENSIONS[1]:
                result["warning"] = f"Dimensions below recommended {MIN_DIMENSIONS[0]}x{MIN_DIMENSIONS[1]}"
    except Exception as e:
        result["error"] = str(e)
        result["valid"] = False
    
    return result


def organize_portraits(folders: Dict[str, Path], output_base: Path) -> Dict[str, Any]:
    """
    Organize portrait images into structured folders.
    
    Args:
        folders: Dictionary of folder names to paths.
        output_base: Base output directory.
    
    Returns:
        Dictionary with organization results.
    """
    portrait_index = {
        "male": {
            "18-25": [],
            "26-40": [],
            "41-65": []
        },
        "female": {
            "18-25": [],
            "26-40": [],
            "41-65": []
        }
    }
    
    stats = {
        "total_images": 0,
        "by_gender": {"male": 0, "female": 0},
        "by_age_group": {"18-25": 0, "26-40": 0, "41-65": 0},
        "valid_images": 0,
        "invalid_images": 0,
        "warnings": []
    }
    
    # Create output structure
    for gender in ["male", "female"]:
        for age_group in ["18-25", "26-40", "41-65"]:
            output_dir = output_base / gender / age_group
            output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each folder
    for folder_name, folder_path in folders.items():
        gender = "male" if folder_name.startswith("Male") else "female"
        age_group = AGE_GROUP_MAPPING.get(folder_name, "26-40")
        
        console.print(f"[cyan]Processing {folder_name} → {gender}/{age_group}...[/cyan]")
        
        count, images = count_images_in_folder(folder_path)
        console.print(f"  Found {count} images")
        
        if count == 0:
            console.print(f"  [yellow]⚠️  No images found in {folder_name}[/yellow]")
            continue
        
        output_dir = output_base / gender / age_group
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Processing images...", total=len(images))
            
            for image_path in images:
                # Validate image
                validation = validate_image(image_path)
                
                if not validation["valid"]:
                    stats["invalid_images"] += 1
                    stats["warnings"].append({
                        "file": str(image_path),
                        "error": validation.get("error", "Unknown error")
                    })
                    progress.update(task, advance=1)
                    continue
                
                # Check dimensions
                if validation.get("warning"):
                    stats["warnings"].append({
                        "file": str(image_path),
                        "warning": validation["warning"],
                        "dimensions": f"{validation['width']}x{validation['height']}"
                    })
                
                # Copy image to organized structure
                new_filename = f"{folder_name}_{image_path.name}"
                dest_path = output_dir / new_filename
                
                try:
                    shutil.copy2(image_path, dest_path)
                    
                    # Add to index (relative path)
                    relative_path = f"{gender}/{age_group}/{new_filename}"
                    portrait_index[gender][age_group].append(relative_path)
                    
                    stats["total_images"] += 1
                    stats["by_gender"][gender] += 1
                    stats["by_age_group"][age_group] += 1
                    stats["valid_images"] += 1
                    
                except Exception as e:
                    stats["warnings"].append({
                        "file": str(image_path),
                        "error": f"Failed to copy: {e}"
                    })
                    stats["invalid_images"] += 1
                
                progress.update(task, advance=1)
    
    return {
        "index": portrait_index,
        "stats": stats
    }


def main():
    """Main function."""
    console.print("[bold blue]=" * 60)
    console.print("[bold blue]Organize Portrait Images[/bold blue]")
    console.print("[bold blue]=" * 60)
    console.print()
    
    try:
        # 1. Scan for portrait folders
        console.print("[cyan]Scanning for portrait folders...[/cyan]")
        folders = find_portrait_folders(project_root)
        
        if not folders:
            console.print("[yellow]⚠️  No portrait folders found (Female_1-3, Male_1-3)[/yellow]")
            console.print("[dim]Searched in: project root, data/portraits, portraits, images[/dim]")
            console.print()
            console.print("[yellow]Please ensure portrait folders exist in one of these locations.[/yellow]")
            return
        
        console.print(f"[green]✅ Found {len(folders)} portrait folders:[/green]")
        for folder_name, folder_path in folders.items():
            count, _ = count_images_in_folder(folder_path)
            age_group = AGE_GROUP_MAPPING.get(folder_name, "unknown")
            gender = "male" if folder_name.startswith("Male") else "female"
            console.print(f"  {folder_name}: {count} images → {gender}/{age_group}")
        console.print()
        
        # 2. Confirm mapping
        console.print("[bold cyan]Age Group Mapping:[/bold cyan]")
        table = Table()
        table.add_column("Folder", style="cyan")
        table.add_column("Gender", style="magenta")
        table.add_column("Age Group", style="green")
        
        for folder_name in sorted(folders.keys()):
            gender = "male" if folder_name.startswith("Male") else "female"
            age_group = AGE_GROUP_MAPPING.get(folder_name, "unknown")
            table.add_row(folder_name, gender, age_group)
        
        console.print(table)
        console.print()
        
        # 3. Create output structure
        output_base = project_root / "data" / "portraits"
        output_base.mkdir(parents=True, exist_ok=True)
        
        console.print(f"[cyan]Output directory: {output_base}[/cyan]")
        console.print()
        
        # 4. Organize portraits
        console.print("[cyan]Organizing portraits...[/cyan]")
        result = organize_portraits(folders, output_base)
        
        portrait_index = result["index"]
        stats = result["stats"]
        
        console.print()
        console.print("[green]✅ Organization complete![/green]")
        console.print()
        
        # 5. Save index
        index_file = output_base / "portrait_index.json"
        index_data = {
            "portrait_index": portrait_index,
            "statistics": stats,
            "created_at": datetime.now().isoformat(),
            "total_images": stats["total_images"]
        }
        
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        console.print(f"[green]✅ Index saved to {index_file}[/green]")
        console.print()
        
        # 6. Display statistics
        console.print("[bold cyan]Statistics[/bold cyan]")
        console.print()
        
        # Summary table
        table = Table(title="Portrait Organization Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Total Images", str(stats["total_images"]))
        table.add_row("Valid Images", str(stats["valid_images"]))
        table.add_row("Invalid Images", str(stats["invalid_images"]))
        table.add_row("", "")
        table.add_row("Male Images", str(stats["by_gender"]["male"]))
        table.add_row("Female Images", str(stats["by_gender"]["female"]))
        
        console.print(table)
        console.print()
        
        # By age group
        table = Table(title="Images by Age Group")
        table.add_column("Age Group", style="cyan")
        table.add_column("Count", style="green", justify="right")
        
        for age_group, count in stats["by_age_group"].items():
            table.add_row(age_group, str(count))
        
        console.print(table)
        console.print()
        
        # By gender and age group
        table = Table(title="Images by Gender and Age Group")
        table.add_column("Gender", style="cyan")
        table.add_column("18-25", style="green", justify="right")
        table.add_column("26-40", style="green", justify="right")
        table.add_column("41-65", style="green", justify="right")
        table.add_column("Total", style="yellow", justify="right")
        
        for gender in ["male", "female"]:
            counts = [
                len(portrait_index[gender]["18-25"]),
                len(portrait_index[gender]["26-40"]),
                len(portrait_index[gender]["41-65"])
            ]
            total = sum(counts)
            table.add_row(gender.capitalize(), str(counts[0]), str(counts[1]), str(counts[2]), str(total))
        
        console.print(table)
        console.print()
        
        # Average per category
        total_categories = 6  # 2 genders × 3 age groups
        avg_per_category = stats["total_images"] / total_categories if total_categories > 0 else 0
        console.print(f"[cyan]Average images per category: {avg_per_category:.1f}[/cyan]")
        console.print()
        
        # Warnings
        if stats["warnings"]:
            console.print("[bold yellow]Warnings[/bold yellow]")
            console.print()
            
            error_warnings = [w for w in stats["warnings"] if "error" in w]
            dimension_warnings = [w for w in stats["warnings"] if "warning" in w]
            
            if error_warnings:
                console.print(f"[yellow]⚠️  {len(error_warnings)} files had errors:[/yellow]")
                for warning in error_warnings[:5]:  # Show first 5
                    console.print(f"  - {Path(warning['file']).name}: {warning.get('error', 'Unknown')}")
                if len(error_warnings) > 5:
                    console.print(f"  ... and {len(error_warnings) - 5} more")
                console.print()
            
            if dimension_warnings:
                console.print(f"[yellow]⚠️  {len(dimension_warnings)} files below recommended dimensions:[/yellow]")
                for warning in dimension_warnings[:5]:  # Show first 5
                    console.print(f"  - {Path(warning['file']).name}: {warning.get('dimensions', 'unknown')}")
                if len(dimension_warnings) > 5:
                    console.print(f"  ... and {len(dimension_warnings) - 5} more")
                console.print()
        
        console.print("[bold green]✅ Portrait organization complete![/bold green]")
        console.print()
        console.print(f"Organized structure:")
        console.print(f"  {output_base}/")
        console.print(f"    ├── male/")
        console.print(f"    │   ├── 18-25/")
        console.print(f"    │   ├── 26-40/")
        console.print(f"    │   └── 41-65/")
        console.print(f"    ├── female/")
        console.print(f"    │   ├── 18-25/")
        console.print(f"    │   ├── 26-40/")
        console.print(f"    │   └── 41-65/")
        console.print(f"    └── portrait_index.json")
        console.print()
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()

