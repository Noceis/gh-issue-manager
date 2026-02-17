"""
browse — Fetch, browse, and edit existing GitHub issues.
"""

from .config import ORG, BOARDS
from .ui import (
    BOLD, CYAN, DIM, GREEN, YELLOW, RED, MAGENTA, RESET,
    BACK, QUIT,
    clear, banner, nav_hint, prompt, pick_one, multiline, yn,
)
from .gh import (
    fetch_issues, fetch_issue_detail, update_issue,
    close_issue, reopen_issue, add_issue_comment, fetch_labels,
)


# ═════════════════════════════════════════════════════════════════════════════
# ISSUE BROWSER — entry point
# ═════════════════════════════════════════════════════════════════════════════

def browse_issues():
    """Main entry: pick a repo, list issues, drill into one."""
    clear()
    banner()

    # ── Pick repo ────────────────────────────────────────────────────────
    print(f"  {BOLD}📦 Browse Issues — Choose Repository{RESET}\n")
    for i, (key, board) in enumerate(BOARDS.items(), 1):
        repo = board["repo"]
        print(f"    {CYAN}{i}{RESET}  {BOLD}{repo.split('/')[-1]}{RESET}  {DIM}→ {board['name']}{RESET}")
    print()
    nav_hint()

    raw = prompt("Choose repo (1/2)")
    if raw in (BACK, QUIT):
        return
    keys = list(BOARDS.keys())
    board_key = None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            board_key = keys[idx]
    except (ValueError, TypeError):
        if raw:
            for k, b in BOARDS.items():
                if raw.lower() in b["repo"].lower() or k.lower().startswith(raw.lower()):
                    board_key = k
                    break
    if not board_key:
        return

    repo = BOARDS[board_key]["repo"]
    _issue_list_loop(repo, board_key)


# ═════════════════════════════════════════════════════════════════════════════
# ISSUE LIST
# ═════════════════════════════════════════════════════════════════════════════

def _issue_list_loop(repo, board_key):
    """Show a paginated/filtered list of issues; let user pick one."""
    state_filter = "open"
    search_term = None
    limit = 30

    while True:
        clear()
        banner()
        board = BOARDS[board_key]
        print(f"  {BOLD}📋 Issues — {repo.split('/')[-1]}{RESET}  {DIM}→ {board['name']}{RESET}")
        filter_parts = [f"state={state_filter}"]
        if search_term:
            filter_parts.append(f"search=\"{search_term}\"")
        print(f"  {DIM}Filters: {', '.join(filter_parts)}{RESET}\n")

        print(f"  {DIM}⏳ Fetching issues...{RESET}")
        issues = fetch_issues(repo, state=state_filter, limit=limit, search=search_term)

        if not issues:
            print(f"\n    {DIM}No issues found.{RESET}\n")
        else:
            _print_issue_table(issues)

        # ── Actions ──────────────────────────────────────────────────────
        print(f"  {DIM}─────────────────────────────────────────────────────{RESET}")
        print(f"    {CYAN}#N{RESET}  Open issue by number    "
              f"{CYAN}s{RESET}  Search    "
              f"{CYAN}f{RESET}  Toggle state filter")
        print(f"    {CYAN}r{RESET}   Refresh                 "
              f"{CYAN}b{RESET}  Back      "
              f"{CYAN}q{RESET}  Quit")
        print()

        raw = prompt("Action or issue #")
        if raw in (QUIT, None):
            return
        if raw == BACK:
            return

        low = raw.lower().strip() if raw else ""

        if low == "r":
            continue  # refresh

        elif low == "s":
            term = prompt("Search term (blank to clear)")
            if term in (BACK, QUIT):
                continue
            search_term = term if term else None
            continue

        elif low == "f":
            state_filter = "closed" if state_filter == "open" else "open"
            continue

        else:
            # Try to parse as issue number
            num = _parse_issue_number(raw)
            if num:
                result = _issue_detail_loop(repo, board_key, num)
                if result == QUIT:
                    return
                continue  # back to list after detail view

            # Try to match a table row number (1-based index)
            if issues:
                try:
                    row = int(raw) - 1
                    if 0 <= row < len(issues):
                        num = issues[row]["number"]
                        result = _issue_detail_loop(repo, board_key, num)
                        if result == QUIT:
                            return
                        continue
                except (ValueError, TypeError):
                    pass

            print(f"    {DIM}Enter an issue number (e.g. 42 or #42){RESET}")
            prompt("Press enter")


def _print_issue_table(issues):
    """Print a numbered table of issues."""
    max_num = max(len(str(i["number"])) for i in issues)
    for idx, issue in enumerate(issues, 1):
        num = issue["number"]
        title = issue["title"]
        labels = [l["name"] for l in issue.get("labels", [])] if issue.get("labels") else []
        label_str = f"  {DIM}[{', '.join(labels)}]{RESET}" if labels else ""
        state_icon = f"{GREEN}●{RESET}" if issue["state"] == "OPEN" else f"{RED}●{RESET}"
        print(f"    {DIM}{idx:>3}{RESET}  {state_icon}  {CYAN}#{num:<{max_num}}{RESET}  {title}{label_str}")
    print()


def _parse_issue_number(raw):
    """Extract an issue number from input like '42', '#42', etc."""
    if not raw:
        return None
    raw = raw.strip().lstrip("#")
    try:
        return int(raw)
    except ValueError:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# ISSUE DETAIL
# ═════════════════════════════════════════════════════════════════════════════

def _issue_detail_loop(repo, board_key, number):
    """Show full issue detail and allow editing."""
    while True:
        clear()
        banner()

        issue = fetch_issue_detail(repo, number)
        if not issue:
            print(f"\n  {RED}Could not fetch issue #{number}.{RESET}\n")
            prompt("Press enter to return")
            return BACK

        _print_issue_detail(issue)

        # ── Action menu ──────────────────────────────────────────────────
        is_open = (issue.get("state", "").upper() == "OPEN")
        print(f"\n  {BOLD}Actions:{RESET}\n")
        print(f"    {CYAN}t{RESET}  Edit title")
        print(f"    {CYAN}d{RESET}  Edit description (body)")
        print(f"    {CYAN}l{RESET}  Edit labels")
        print(f"    {CYAN}c{RESET}  Add comment")
        if is_open:
            print(f"    {RED}x{RESET}  Close issue")
        else:
            print(f"    {GREEN}o{RESET}  Reopen issue")
        print(f"    {CYAN}w{RESET}  Open in browser")
        print(f"    {CYAN}b{RESET}  Back to list")
        print()

        action = prompt("Action")
        if action in (QUIT, None):
            return QUIT
        if action == BACK:
            return BACK

        low = action.lower().strip()

        if low == "t":
            _edit_title(repo, number, issue)
        elif low == "d":
            _edit_body(repo, number, issue)
        elif low == "l":
            _edit_labels(repo, board_key, number, issue)
        elif low == "c":
            _add_comment(repo, number)
        elif low == "x" and is_open:
            _close_issue(repo, number)
        elif low == "o" and not is_open:
            _reopen_issue(repo, number)
        elif low == "w":
            url = issue.get("url", "")
            if url:
                import subprocess
                subprocess.run(["open", url], capture_output=True)
        elif low == "b":
            return BACK


def _print_issue_detail(issue):
    """Pretty-print a full issue."""
    num = issue["number"]
    title = issue["title"]
    state = issue.get("state", "UNKNOWN").upper()
    state_badge = f"{GREEN}OPEN{RESET}" if state == "OPEN" else f"{RED}CLOSED{RESET}"
    url = issue.get("url", "")

    labels = [l["name"] for l in issue.get("labels", [])] if issue.get("labels") else []
    assignees = [a["login"] for a in issue.get("assignees", [])] if issue.get("assignees") else []

    print(f"  {BOLD}#{num}  {YELLOW}{title}{RESET}  [{state_badge}]")
    print(f"  {DIM}{url}{RESET}\n")

    if labels:
        print(f"    {BOLD}Labels:{RESET}    {', '.join(labels)}")
    if assignees:
        print(f"    {BOLD}Assignees:{RESET} {', '.join(assignees)}")
    if issue.get("milestone"):
        ms = issue["milestone"]
        ms_title = ms.get("title", "") if isinstance(ms, dict) else str(ms)
        if ms_title:
            print(f"    {BOLD}Milestone:{RESET} {ms_title}")

    body = issue.get("body", "") or "_(no body)_"
    print(f"\n  {DIM}{'─' * 50}{RESET}")
    for line in body.split("\n"):
        print(f"  {DIM}│{RESET} {line}")
    print(f"  {DIM}{'─' * 50}{RESET}")

    comments = issue.get("comments", [])
    if comments:
        print(f"\n  {BOLD}💬 Comments ({len(comments)}):{RESET}\n")
        for cm in comments[-5:]:  # show last 5
            author = cm.get("author", {}).get("login", "unknown") if isinstance(cm.get("author"), dict) else "unknown"
            created = cm.get("createdAt", "")[:10]
            cm_body = cm.get("body", "")
            # Truncate long comments
            lines = cm_body.split("\n")
            preview = "\n      ".join(lines[:4])
            if len(lines) > 4:
                preview += f"\n      {DIM}... ({len(lines) - 4} more lines){RESET}"
            print(f"    {CYAN}{author}{RESET}  {DIM}{created}{RESET}")
            print(f"      {preview}")
            print()


# ═════════════════════════════════════════════════════════════════════════════
# EDIT ACTIONS
# ═════════════════════════════════════════════════════════════════════════════

def _edit_title(repo, number, issue):
    """Edit the issue title."""
    clear()
    banner()
    print(f"  {BOLD}✏️  Edit Title — #{number}{RESET}\n")
    print(f"    Current: {YELLOW}{issue['title']}{RESET}\n")
    nav_hint()

    new_title = prompt("New title", default=issue["title"])
    if new_title in (BACK, QUIT) or not new_title:
        return
    if new_title == issue["title"]:
        print(f"    {DIM}No change.{RESET}")
        return

    confirm = yn(f"Update title to \"{new_title}\"?")
    if confirm is True:
        result = update_issue(repo, number, title=new_title)
        if result is not None:
            print(f"  {GREEN}✅ Title updated.{RESET}")
        else:
            print(f"  {RED}❌ Failed to update title.{RESET}")
        prompt("Press enter to continue")


def _edit_body(repo, number, issue):
    """Edit the issue body/description."""
    clear()
    banner()
    print(f"  {BOLD}📝 Edit Body — #{number}{RESET}\n")
    body = issue.get("body", "") or ""
    if body:
        print(f"    {DIM}Current body:{RESET}")
        for ln in body.split("\n")[:15]:
            print(f"      {ln}")
        if body.count("\n") > 15:
            print(f"      {DIM}... ({body.count(chr(10)) - 15} more lines){RESET}")
        print()

    print(f"  {DIM}Options:{RESET}")
    action = pick_one("How would you like to edit?", {
        "replace": "Replace entire body",
        "append": "Append text to body",
    }, allow_skip=True)

    if action in (BACK, QUIT, None):
        return

    if action == "replace":
        nav_hint("type 'b' on first line to go back")
        new_body = multiline("New body")
        if new_body in (BACK, QUIT) or not new_body:
            return
    elif action == "append":
        nav_hint("type 'b' on first line to go back")
        addition = multiline("Text to append")
        if addition in (BACK, QUIT) or not addition:
            return
        new_body = body + "\n\n" + addition if body else addition

    confirm = yn("Update the issue body?")
    if confirm is True:
        result = update_issue(repo, number, body=new_body)
        if result is not None:
            print(f"  {GREEN}✅ Body updated.{RESET}")
        else:
            print(f"  {RED}❌ Failed to update body.{RESET}")
        prompt("Press enter to continue")


def _edit_labels(repo, board_key, number, issue):
    """Add or remove labels on an issue."""
    clear()
    banner()
    print(f"  {BOLD}🏷️  Edit Labels — #{number}{RESET}\n")

    current = [l["name"] for l in issue.get("labels", [])] if issue.get("labels") else []
    if current:
        print(f"    {BOLD}Current:{RESET} {', '.join(current)}\n")
    else:
        print(f"    {DIM}No labels set.{RESET}\n")

    # Show all available labels
    all_labels = fetch_labels(repo)
    if all_labels:
        current_set = {l.lower() for l in current}
        print(f"    {DIM}Available on {repo}:{RESET}")
        for l in all_labels:
            name = l["name"]
            marker = f"  {GREEN}✓{RESET}" if name.lower() in current_set else ""
            desc = l.get("description", "") or ""
            print(f"      {name:20s}{marker}  {DIM}{desc}{RESET}")
        print()

    action = pick_one("Action", {
        "add": "Add labels",
        "remove": "Remove labels",
    }, allow_skip=True)

    if action in (BACK, QUIT, None):
        return

    if action == "add":
        raw = prompt("Labels to add (comma-separated)")
        if raw in (BACK, QUIT) or not raw:
            return
        add = [l.strip() for l in raw.split(",") if l.strip()]
        if add:
            confirm = yn(f"Add labels: {', '.join(add)}?")
            if confirm is True:
                result = update_issue(repo, number, add_labels=add)
                if result is not None:
                    print(f"  {GREEN}✅ Labels added.{RESET}")
                else:
                    print(f"  {RED}❌ Failed to add labels.{RESET}")
                prompt("Press enter to continue")

    elif action == "remove":
        if not current:
            print(f"    {DIM}No labels to remove.{RESET}")
            prompt("Press enter to continue")
            return
        raw = prompt("Labels to remove (comma-separated)")
        if raw in (BACK, QUIT) or not raw:
            return
        remove = [l.strip() for l in raw.split(",") if l.strip()]
        if remove:
            confirm = yn(f"Remove labels: {', '.join(remove)}?")
            if confirm is True:
                result = update_issue(repo, number, remove_labels=remove)
                if result is not None:
                    print(f"  {GREEN}✅ Labels removed.{RESET}")
                else:
                    print(f"  {RED}❌ Failed to remove labels.{RESET}")
                prompt("Press enter to continue")


def _add_comment(repo, number):
    """Add a comment to the issue."""
    clear()
    banner()
    print(f"  {BOLD}💬 Add Comment — #{number}{RESET}\n")
    nav_hint("type 'b' on first line to go back")

    body = multiline("Comment")
    if body in (BACK, QUIT) or not body:
        return

    confirm = yn("Post this comment?")
    if confirm is True:
        result = add_issue_comment(repo, number, body)
        if result is not None:
            print(f"  {GREEN}✅ Comment added.{RESET}")
        else:
            print(f"  {RED}❌ Failed to add comment.{RESET}")
        prompt("Press enter to continue")


def _close_issue(repo, number):
    """Close an issue with confirmation."""
    confirm = yn(f"{RED}Close issue #{number}?{RESET}")
    if confirm is True:
        result = close_issue(repo, number)
        if result is not None:
            print(f"  {GREEN}✅ Issue #{number} closed.{RESET}")
        else:
            print(f"  {RED}❌ Failed to close issue.{RESET}")
        prompt("Press enter to continue")


def _reopen_issue(repo, number):
    """Reopen an issue with confirmation."""
    confirm = yn(f"Reopen issue #{number}?")
    if confirm is True:
        result = reopen_issue(repo, number)
        if result is not None:
            print(f"  {GREEN}✅ Issue #{number} reopened.{RESET}")
        else:
            print(f"  {RED}❌ Failed to reopen issue.{RESET}")
        prompt("Press enter to continue")
