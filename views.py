"""
views — Read-only view screens (boards, labels, iterations).
"""

from .config import ORG, DEFAULT_REPO, BOARDS
from .ui import BOLD, CYAN, DIM, GREEN, RESET, QUIT, BACK, clear, banner, prompt
from .gh import fetch_iterations, fetch_labels


def view_boards():
    clear()
    banner()
    print(f"  {BOLD}📋 Project Boards{RESET}\n")
    for key, board in BOARDS.items():
        url = f"https://github.com/orgs/{ORG}/projects/{board['number']}"
        print(f"    {BOLD}{key}{RESET}  →  {board['name']}")
        print(f"    {DIM}{url}{RESET}")
        fields = board["fields"]
        print(f"    Fields: {', '.join(fields.keys())}")
        for fname, fdata in fields.items():
            if "options" in fdata:
                opts = ", ".join(fdata["options"].keys())
                display = fname.replace("_", " ").title()
                print(f"      {DIM}{display}: {opts}{RESET}")
        print()
    prompt("Press enter to return")


def view_labels():
    clear()
    banner()
    print(f"  {BOLD}🏷️  Labels{RESET}\n")
    repo = prompt("Repository", default=DEFAULT_REPO)
    if repo in (QUIT, BACK):
        return

    labels = fetch_labels(repo)
    if not labels:
        print(f"\n    {DIM}No labels found.{RESET}")
    else:
        print()
        max_name = max(len(l["name"]) for l in labels)
        for l in labels:
            desc = l.get("description", "") or ""
            print(f"    {l['name']:{max_name + 2}s}{DIM}{desc}{RESET}")
    print()
    prompt("Press enter to return")


def view_iterations():
    clear()
    banner()
    print(f"  {BOLD}🔄 Iterations{RESET}\n")
    for board_key, board in BOARDS.items():
        print(f"  {BOLD}{board['name']}{RESET}  {DIM}({board_key}){RESET}\n")
        iterations = fetch_iterations(board_key)
        for it in iterations:
            marker = f"  {GREEN}← CURRENT{RESET}" if it["current"] else ""
            print(f"    {it['title']:20s}  {DIM}{it['start']} → {it['end']}{RESET}{marker}")
        print()
    prompt("Press enter to return")
