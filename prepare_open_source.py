#!/usr/bin/env python3
"""
Create a clean open-source export of the issue tool.

Sanitises Sandvik-specific content from ai.py and analyse.py during export.

Usage:
  python3 scripts/issue/prepare_open_source.py /tmp/issue-manager-cli
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

EXCLUDE = {
    "__pycache__",
    ".DS_Store",
    "node_modules",
}

# Files that need sanitisation during export
SANITISE_FILES = {"ai.py", "analyse.py", "cli.py"}


def should_exclude(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE:
        return True
    # Do not export local/private runtime data
    if name == "config.json" and path.parent.name == ".issue":
        return True
    return False


def sanitise_ai_py(content: str) -> str:
    """Remove Sandvik-specific content from ai.py."""
    
    # Add _DEFAULT_BOARD constant after imports
    content = re.sub(
        r"(from \.wizard import \([^)]+\))",
        r"\1\n\n# Get first board key as default fallback\n_DEFAULT_BOARD = next(iter(BOARDS.keys())) if BOARDS else \"main\"",
        content,
    )
    
    # Replace hardcoded 'devx' with _DEFAULT_BOARD
    content = re.sub(r"'devx'", "_DEFAULT_BOARD", content)
    content = re.sub(r'"devx"', "_DEFAULT_BOARD", content)
    
    # Replace the Sandvik system prompt intro
    content = re.sub(
        r'You are a helpful assistant embedded in the Sandvik Issue Manager CLI\.',
        'You are a helpful assistant embedded in the Issue Manager CLI.',
        content,
    )
    
    # Remove PARA method mention and active project folders
    content = re.sub(
        r"The workspace is organised using the PARA method \(Projects, Areas, Resources, Archive\)\.\n\n"
        r"Active project folders: [^\n]+\n[^\n]+\n[^\n]+\n",
        "",
        content,
    )
    content = re.sub(
        r"The workspace uses the PARA method \(Projects, Areas, Resources, Archive\)\.\n\n"
        r"Active projects: [^\n]+\n[^\n]+\n",
        "",
        content,
    )
    
    # Replace hardcoded repo-to-board mapping with dynamic version
    content = re.sub(
        r"Repository-to-board mapping:\n  - \{ORG\}/github-maintenance → devx board\n  - \{ORG\}/devx-prod-atlas → prodatlas board",
        "Repository-to-board mapping:\n{board_repo_text}",
        content,
    )
    
    # Remove the epic-specific instructions block
    content = re.sub(
        r'Epic \(devx board only\) — match the issue to the closest epic:.*?If the issue clearly belongs to one epic, set it\. If ambiguous, omit\.\n\n',
        '',
        content,
        flags=re.DOTALL,
    )
    
    # Remove the priority/size/budget instructions
    content = re.sub(
        r'Priority \(devx board only\) — infer from urgency cues:.*?Status — use what the user specifies, otherwise default to "new" \(devx\) or "todo" \(prodatlas\)\.',
        'Field selection guidelines:\n- Use the available field options shown in the board schema above.\n- For priority fields: "p0" = critical, "p1" = important, "p2" = normal (default if not specified).\n- For size fields: "xs" = trivial, "s" = small, "m" = medium, "l" = large, "xl" = very large.\n- For status fields: use what the user specifies, otherwise default to the first option.\n- If a field has options, only use values from those options.',
        content,
        flags=re.DOTALL,
    )
    
    # Make JSON schema board field generic
    content = re.sub(
        r'"board": "devx" or "prodatlas"',
        '"board": "<board_key from the list above>"',
        content,
    )
    content = re.sub(
        r'"board": _DEFAULT_BOARD or "prodatlas"',
        '"board": "<board_key from the list above>"',
        content,
    )
    
    # Remove "Use British English" (keep it neutral)
    content = re.sub(r'\nUse British English\.', '', content)
    content = re.sub(r' Use British English\.', '', content)
    
    return content


def sanitise_analyse_py(content: str) -> str:
    """Remove Sandvik-specific content from analyse.py."""
    content = re.sub(
        r'reviewing the backlog for the DevX & ProdAtlas teams at Sandvik\.',
        "reviewing a development team's backlog.",
        content,
    )
    return content


def sanitise_cli_py(content: str) -> str:
    """Make the CLI example generic."""
    content = re.sub(
        r'--board devx --title "Fix monitoring"',
        '--board main --title "Fix monitoring"',
        content,
    )
    return content


def sanitise_file(src_file: Path, dst_file: Path) -> None:
    """Copy file, sanitising content if needed."""
    content = src_file.read_text()
    
    if src_file.name == "ai.py":
        content = sanitise_ai_py(content)
    elif src_file.name == "analyse.py":
        content = sanitise_analyse_py(content)
    elif src_file.name == "cli.py":
        content = sanitise_cli_py(content)
    
    dst_file.write_text(content)
    # Preserve permissions
    shutil.copystat(src_file, dst_file)


def copy_tree(src: Path, dst: Path) -> None:
    for root, dirs, files in os.walk(src):
        root_path = Path(root)

        dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]

        rel = root_path.relative_to(src)
        out_dir = dst / rel
        out_dir.mkdir(parents=True, exist_ok=True)

        for fname in files:
            src_file = root_path / fname
            if should_exclude(src_file):
                continue
            
            dst_file = out_dir / fname
            if fname in SANITISE_FILES:
                sanitise_file(src_file, dst_file)
            else:
                shutil.copy2(src_file, dst_file)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: prepare_open_source.py <output_dir>")
        return 1

    output = Path(sys.argv[1]).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copy_tree(HERE, output)

    print(f"✅ Open-source export created: {output}")
    print("   Next: review config.example.json, then publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
