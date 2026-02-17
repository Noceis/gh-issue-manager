"""
issue — Interactive CLI for managing GitHub issues on GitHub Project boards.

Usage:
    python3 scripts/issue              # launch interactive menu
    python3 scripts/issue create ...   # quick mode (non-interactive)
    python3 scripts/issue --help       # CLI flags reference

Requires: gh CLI authenticated (gh auth login).
"""

from .cli import main
