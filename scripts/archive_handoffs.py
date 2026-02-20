"""
Handoff Archive Script
======================

Archives old handoff and prompt files from weeks 1-35.
Keeps only recent and relevant handoffs in the main handoffs/ directory.

Usage:
    python scripts/archive_handoffs.py

What it does:
1. Creates handoffs/archive/ subdirectory
2. Moves old W1-W35 handoffs to archive/
3. Keeps only recent/current handoffs in main directory
4. Creates an index of archived files
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def main():
    handoffs_dir = Path("handoffs")
    archive_dir = handoffs_dir / "archive"
    
    # Create archive directory
    archive_dir.mkdir(exist_ok=True)
    print(f"📁 Archive directory: {archive_dir}")
    
    # Patterns for old files to archive
    old_patterns = [
        # Week-based handoffs (w1-w35)
        "HANDOFF_*_w[0-9]*.md",
        "HANDOFF_*_w[0-9][0-9]*.md",
        "PROMPT_*_w[0-9]*.md",
        "PROMPT_*_w[0-9][0-9]*.md",
        # Core-to-agent handoffs (older pattern)
        "HANDOFF_20260215_*.md",
        "HANDOFF_20260216_*.md",
        "HANDOFF_20260217_*.md", 
        "HANDOFF_20260218_*.md",
        # Old prompts
        "PROMPT_20260215_*.md",
        "PROMPT_20260216_*.md",
        "PROMPT_20260217_*.md",
        "PROMPT_20260218_*.md",
    ]
    
    # Keep these (current/relevant)
    keep_patterns = [
        "HANDOFF_EXPORT_FOUNDATION_*.md",
        "HANDOFF_ERROR_DIAGNOSTICS_*.md", 
        "HANDOFF_CONSTRAINT_DIAGNOSTICS_*.md",
    ]
    
    # Categorize files
    to_archive = []
    to_keep = []
    
    for file in handoffs_dir.glob("*.md"):
        file_str = str(file.name)
        
        # Check if it matches keep patterns
        should_keep = any(
            file.match(pattern) for pattern in keep_patterns
        )
        
        if should_keep:
            to_keep.append(file)
        else:
            # Check if it matches archive patterns
            should_archive = any(
                file.match(pattern) for pattern in old_patterns
            )
            if should_archive:
                to_archive.append(file)
            else:
                to_keep.append(file)
    
    # Statistics
    print(f"\n📊 Statistics:")
    print(f"   Files to archive: {len(to_archive)}")
    print(f"   Files to keep: {len(to_keep)}")
    
    # Group by type for reporting
    archived_by_type = defaultdict(list)
    for file in to_archive:
        if "HANDOFF" in file.name:
            archived_by_type["Handoffs"].append(file.name)
        elif "PROMPT" in file.name:
            archived_by_type["Prompts"].append(file.name)
        elif "PLAN" in file.name:
            archived_by_type["Plans"].append(file.name)
        else:
            archived_by_type["Other"].append(file.name)
    
    print(f"\n📦 Archiving breakdown:")
    for type_name, files in sorted(archived_by_type.items()):
        print(f"   {type_name}: {len(files)} files")
    
    # Archive files
    print(f"\n🚚 Moving files to archive...")
    moved = 0
    for file in to_archive:
        dest = archive_dir / file.name
        try:
            shutil.move(str(file), str(dest))
            moved += 1
        except Exception as e:
            print(f"   ❌ Error moving {file.name}: {e}")
    
    print(f"   ✅ Moved {moved} files")
    
    # Create index
    index_file = archive_dir / "README.md"
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write("# Archived Handoffs & Prompts\n\n")
        f.write(f"**Archive Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write("This directory contains historical handoffs and prompts from weeks 1-35.\n")
        f.write("These are kept for reference but are no longer actively maintained.\n\n")
        
        f.write("## Archive Contents\n\n")
        for type_name, files in sorted(archived_by_type.items()):
            f.write(f"### {type_name} ({len(files)} files)\n\n")
            # List first 10 as examples
            for fname in sorted(files)[:10]:
                f.write(f"- `{fname}`\n")
            if len(files) > 10:
                f.write(f"- ... and {len(files) - 10} more\n")
            f.write("\n")
        
        f.write("## Current Handoffs\n\n")
        f.write("See parent directory (`../`) for current active handoffs:\n\n")
        for file in sorted(to_keep):
            f.write(f"- `{file.name}`\n")
    
    print(f"   📝 Created archive index: {index_file}")
    
    # Create main handoffs README
    main_readme = handoffs_dir / "README.md"
    with open(main_readme, 'w', encoding='utf-8') as f:
        f.write("# MashCAD Handoffs\n\n")
        f.write("This directory contains handoff documents for the MashCAD project.\n\n")
        
        f.write("## Current Active Handoffs\n\n")
        for file in sorted(to_keep):
            f.write(f"- **[{file.stem}]({file.name})**\n")
        
        f.write("\n## Archive\n\n")
        f.write(f"Older handoffs from weeks 1-35 are archived in [`archive/`](archive/).\n")
        f.write(f"The archive contains {len(to_archive)} historical documents.\n\n")
        
        f.write("## Structure\n\n")
        f.write("```\nhandoffs/\n")
        f.write("├── README.md          # This file\n")
        f.write("├── HANDOFF_*          # Current active handoffs\n")
        f.write("└── archive/           # Historical handoffs (w1-w35)\n")
        f.write("    ├── README.md      # Archive index\n")
        f.write("    └── ...            # Old handoffs and prompts\n")
        f.write("```\n")
    
    print(f"   📝 Updated main handoffs README: {main_readme}")
    
    print(f"\n✅ Archive complete!")
    print(f"   Archive location: {archive_dir}")
    print(f"   Archived files: {moved}")
    print(f"   Active handoffs: {len(to_keep)}")


if __name__ == "__main__":
    main()
