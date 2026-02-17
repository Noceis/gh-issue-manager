"""
cli — Argparse entry point, quick mode, and interactive main menu.
"""

import argparse
import asyncio
import sys
import textwrap

from .config import ORG, DEFAULT_REPO, BOARDS
from .ui import (
    BOLD, CYAN, DIM, MAGENTA, RESET,
    QUIT, clear, banner, prompt,
)
from .wizard import wizard_create, execute_create
from .views import view_boards, view_labels, view_iterations
from .browse import browse_issues
from .gh import fetch_current_iteration


# ═════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═════════════════════════════════════════════════════════════════════════════

def main_menu():
    """Top-level interactive menu loop."""
    # AI features are optional — they require the `copilot` SDK which may
    # not be installed in every Python environment.
    try:
        import copilot as _copilot_mod  # noqa: F401 — probe only
        from .ai import wizard_ai_issue, copilot_chat
        from .analyse import analyse_backlog
        _has_ai = True
    except (ImportError, ModuleNotFoundError):
        _has_ai = False

    while True:
        clear()
        banner()
        print(f"  {BOLD}What would you like to do?{RESET}\n")
        print(f"    {CYAN}1{RESET}  Create an issue")
        print(f"    {CYAN}2{RESET}  Browse & edit issues")
        print(f"    {CYAN}3{RESET}  View boards & fields")
        print(f"    {CYAN}4{RESET}  View labels")
        print(f"    {CYAN}5{RESET}  View iterations")
        print(f"    {CYAN}6{RESET}  📋 This week / top todos  {DIM}(kanban dashboard){RESET}")
        print(f"    {CYAN}0{RESET}  🌐 Open kanban board  {DIM}(web UI){RESET}")
        print(f"  {DIM}────── AI ──────{RESET}")
        if _has_ai:
            print(f"    {MAGENTA}7{RESET}  {MAGENTA}✨ AI-assisted issue{RESET}  {DIM}(Copilot reads your docs){RESET}")
            print(f"    {MAGENTA}8{RESET}  {MAGENTA}💬 Ask Copilot{RESET}  {DIM}(chat about your projects){RESET}")
            print(f"    {MAGENTA}9{RESET}  {MAGENTA}🔬 Analyse backlog{RESET}  {DIM}(duplicates, priorities, risks){RESET}")
        else:
            print(f"    {DIM}7   ✨ AI-assisted issue  (copilot SDK not available){RESET}")
            print(f"    {DIM}8   💬 Ask Copilot        (copilot SDK not available){RESET}")
            print(f"    {DIM}9   🔬 Analyse backlog    (copilot SDK not available){RESET}")
        print(f"    {CYAN}q{RESET}  Quit")
        print()

        choice = prompt("Choose")
        if choice in (QUIT, None, "q"):
            print(f"\n  {DIM}Goodbye!{RESET}\n")
            return
        elif choice == "1":
            wizard_create()
        elif choice == "2":
            browse_issues()
        elif choice == "3":
            view_boards()
        elif choice == "4":
            view_labels()
        elif choice == "5":
            view_iterations()
        elif choice == "6":
            from .kanban import kanban_menu
            kanban_menu()
        elif choice == "0":
            try:
                from .server import start as start_board
                start_board()
            except ImportError:
                from .ui import RED
                print(f"\n  {RED}Web board requires: pip install fastapi uvicorn{RESET}")
                prompt("Press enter to return")
        elif choice == "7":
            if _has_ai:
                asyncio.run(wizard_ai_issue())
            else:
                from .ui import RED
                print(f"\n  {RED}The copilot SDK is not installed in this Python environment.{RESET}")
                print(f"  {DIM}Install it or use Python 3.11 where it's available.{RESET}\n")
                prompt("Press enter to return")
        elif choice == "8":
            if _has_ai:
                asyncio.run(copilot_chat())
            else:
                from .ui import RED
                print(f"\n  {RED}The copilot SDK is not installed in this Python environment.{RESET}")
                print(f"  {DIM}Install it or use Python 3.11 where it's available.{RESET}\n")
                prompt("Press enter to return")
        elif choice == "9":
            if _has_ai:
                asyncio.run(analyse_backlog())
            else:
                from .ui import RED
                print(f"\n  {RED}The copilot SDK is not installed in this Python environment.{RESET}")
                print(f"  {DIM}Install it or use Python 3.11 where it's available.{RESET}\n")
                prompt("Press enter to return")


# ═════════════════════════════════════════════════════════════════════════════
# QUICK MODE (non-interactive, for scripting / Copilot)
# ═════════════════════════════════════════════════════════════════════════════

def quick_create(args):
    """Create from CLI arguments without prompts."""
    board_key = args.board
    if not board_key:
        from .ui import RED
        print(f"{RED}❌ --board is required in quick mode.{RESET}")
        sys.exit(1)
    board = BOARDS[board_key]
    repo = args.repo
    if "/" not in repo:
        repo = f"{ORG}/{repo}"

    state = {
        "board_key": board_key,
        "repo": repo,
        "title": args.title,
        "description": args.description or "_(no description)_",
        "criteria": args.criteria or [],
        "extra_context": None,
        "labels": args.labels or [],
        "fields": {},
    }

    flag_map = {
        "priority": args.priority,
        "size": args.size,
        "epic": args.epic,
        "status": args.status,
        "team": args.team,
    }
    for fkey, fval in flag_map.items():
        if fval and fkey in board["fields"]:
            v = fval.lower()
            opts = board["fields"][fkey]["options"]
            if v in opts:
                state["fields"][fkey] = (board["fields"][fkey]["id"], opts[v], "single_select")

    if args.current_iteration and "iteration" in board["fields"]:
        iter_id, iter_title = fetch_current_iteration(board_key)
        if iter_id:
            state["fields"]["iteration"] = (board["fields"]["iteration"]["id"], iter_id, "iteration")

    state["confirmed"] = True
    execute_create(state)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="GitHub Issue CLI for GitHub project boards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Run without arguments for the interactive guided menu.

            Quick create example:
              python3 -m issue create \\
                --board main --title "Fix monitoring" \\
                --description "Add alerts for AKS clusters" \\
                --criteria "Alerts fire on CPU > 80%%" "Dashboard updated" \\
                --epic kubernetes --priority p1 --size m \\
                --current-iteration
        """),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("board", help="Open the kanban board web UI")

    p_create = sub.add_parser("create", help="Create a new issue (quick mode with flags)")
    p_create.add_argument("--board", choices=list(BOARDS.keys()))
    p_create.add_argument("--repo", default=DEFAULT_REPO)
    p_create.add_argument("--title")
    p_create.add_argument("--description")
    p_create.add_argument("--criteria", nargs="*")
    p_create.add_argument("--labels", nargs="*")
    p_create.add_argument("--status")
    p_create.add_argument("--priority")
    p_create.add_argument("--size")
    p_create.add_argument("--epic")
    p_create.add_argument("--team")
    p_create.add_argument("--current-iteration", action="store_true")

    args = parser.parse_args()

    if args.command == "board":
        from .server import start as start_board
        start_board()
    elif args.command == "create" and args.title:
        quick_create(args)
    else:
        main_menu()
