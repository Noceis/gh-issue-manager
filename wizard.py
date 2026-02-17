"""
wizard — Step-by-step issue creation wizard and execution logic.
"""

import sys

from .config import ORG, BOARDS
from .ui import (
    BOLD, CYAN, DIM, GREEN, YELLOW, RED, RESET,
    BACK, QUIT,
    clear, banner, nav_hint, prompt, pick_one, multiline,
    criteria_input, yn, run_steps,
)
from .gh import (
    gh, set_project_field, fetch_iterations, fetch_current_iteration,
    fetch_labels, build_body,
)


# ═════════════════════════════════════════════════════════════════════════════
# WIZARD: CREATE ISSUE
# ═════════════════════════════════════════════════════════════════════════════

def wizard_create():
    """Step-by-step issue creation with back/forward navigation."""
    state = {
        "board_key": None,
        "repo": None,
        "title": None,
        "description": None,
        "criteria": [],
        "extra_context": None,
        "labels": [],
        "fields": {},  # field_key -> (field_id, value, type_str)
        "confirmed": False,
    }

    steps = [
        ("Repository", step_repo),
        ("Title", step_title),
        ("Description", step_description),
        ("Acceptance Criteria", step_criteria),
        ("Additional Context", step_context),
        ("Labels", step_labels),
        ("Board Fields", step_board_fields),
        ("Review & Confirm", step_review),
    ]

    ok = run_steps(steps, state)
    if ok and state.get("confirmed"):
        execute_create(state)
        prompt("Press enter to return to menu")


# ── Create-wizard steps ─────────────────────────────────────────────────

def step_repo(state):
    """Pick a repository — this also determines the board automatically."""
    print(f"  {BOLD}📦 Repository{RESET}\n")
    for i, (key, board) in enumerate(BOARDS.items(), 1):
        repo = board["repo"]
        url = f"https://github.com/orgs/{ORG}/projects/{board['number']}"
        fields = ", ".join(board["fields"].keys())
        print(f"    {CYAN}{i}{RESET}  {BOLD}{repo.split('/')[-1]}{RESET}  {DIM}→ {board['name']}{RESET}")
        print(f"       {DIM}{url}{RESET}")
        print(f"       Fields: {DIM}{fields}{RESET}\n")
    nav_hint()

    raw = prompt("Choose repo (1/2)")
    if raw in (BACK, QUIT):
        return raw
    keys = list(BOARDS.keys())
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            chosen = keys[idx]
            state["board_key"] = chosen
            state["repo"] = BOARDS[chosen]["repo"]
            return True
    except (ValueError, TypeError):
        if raw:
            for k, b in BOARDS.items():
                if raw.lower() in b["repo"].lower() or k.lower().startswith(raw.lower()):
                    state["board_key"] = k
                    state["repo"] = b["repo"]
                    return True
    return False


def step_title(state):
    print(f"  {BOLD}✏️  Issue Title{RESET}\n")
    if state["title"]:
        print(f"    Current: {YELLOW}{state['title']}{RESET}\n")
    nav_hint()
    raw = prompt("Title", default=state.get("title"))
    if raw in (BACK, QUIT):
        return raw
    if not raw:
        print(f"    {RED}Title is required.{RESET}")
        return False
    state["title"] = raw
    return True


def step_description(state):
    print(f"  {BOLD}📝 Description{RESET}\n")
    if state["description"]:
        print(f"    {DIM}Current:{RESET}")
        for ln in state["description"].split("\n"):
            print(f"      {ln}")
        print()
    nav_hint("type 'b' on first line to go back")
    raw = multiline("Write the description")
    if raw in (BACK, QUIT):
        return raw
    state["description"] = raw or "_(no description)_"
    return True


def step_criteria(state):
    print(f"  {BOLD}☑️  Acceptance Criteria{RESET}\n")
    if state["criteria"]:
        print(f"    {DIM}Current:{RESET}")
        for c in state["criteria"]:
            print(f"      ☐ {c}")
        print()
    nav_hint("type 'b' on first entry to go back")
    raw = criteria_input()
    if raw in (BACK, QUIT):
        return raw
    state["criteria"] = raw
    return True


def step_context(state):
    print(f"  {BOLD}💡 Additional Context{RESET}  {DIM}(optional){RESET}\n")
    nav_hint()
    add = yn("Add extra context?")
    if add in (BACK, QUIT):
        return add
    if not add:
        state["extra_context"] = None
        return True
    raw = multiline("Context")
    if raw in (BACK, QUIT):
        return raw
    state["extra_context"] = raw
    return True


def step_labels(state):
    print(f"  {BOLD}🏷️  Labels{RESET}\n")
    labels = fetch_labels(state["repo"])
    if labels:
        max_name = max(len(l["name"]) for l in labels)
        print(f"    {DIM}Available on {state['repo']}:{RESET}\n")
        for l in labels:
            desc = l.get("description", "") or ""
            print(f"      {l['name']:{max_name + 2}s}{DIM}{desc}{RESET}")
        print()
    nav_hint()
    raw = prompt("Labels (comma-separated, or blank to skip)")
    if raw in (BACK, QUIT):
        return raw
    state["labels"] = [l.strip() for l in raw.split(",") if l.strip()] if raw else []
    return True


def step_board_fields(state):
    """
    Sub-wizard for board-specific fields.
    Each field is a step that the user can navigate through.
    Pressing back on the first field returns to the parent wizard.
    """
    board_key = state["board_key"]
    board = BOARDS[board_key]

    sub_steps = _build_field_steps(board_key)
    sub_idx = 0

    while 0 <= sub_idx < len(sub_steps):
        clear()
        banner()
        fname = sub_steps[sub_idx][0]
        bar = "█" * (sub_idx + 1) + "░" * (len(sub_steps) - sub_idx - 1)
        print(f"  {DIM}Board Fields — {fname.upper()} ({sub_idx + 1}/{len(sub_steps)}){RESET}  {CYAN}{bar}{RESET}\n")

        result = sub_steps[sub_idx][1](state, board)

        if result == QUIT:
            return QUIT
        elif result == BACK:
            if sub_idx == 0:
                return BACK
            sub_idx -= 1
        elif result is True:
            sub_idx += 1

    return True


def _build_field_steps(board_key):
    board = BOARDS[board_key]
    steps = []
    order = ["status", "priority", "size", "epic", "team", "budget_category", "iteration"]
    for f in order:
        if f in board["fields"]:
            steps.append((f, _make_field_func(f)))
    return steps


def _make_field_func(field_key):
    """Return a step function for the given field key."""
    handlers = {
        "status":          _field_select,
        "priority":        _field_select,
        "size":            _field_select,
        "epic":            _field_select,
        "team":            _field_select,
        "budget_category": _field_select,
        "iteration":       _field_iteration,
    }
    base = handlers.get(field_key, _field_select)
    def step_func(state, board):
        return base(state, board, field_key)
    return step_func


def _field_select(state, board, field_key):
    """Generic picker for a single-select board field."""
    fdata = board["fields"][field_key]
    display = field_key.replace("_", " ").title()
    result = pick_one(display, fdata["options"])
    if result in (BACK, QUIT):
        return result
    if result:
        state["fields"][field_key] = (fdata["id"], fdata["options"][result], "single_select")
    else:
        state["fields"].pop(field_key, None)
    return True


def _field_iteration(state, board, field_key):
    board_key = state["board_key"]
    print(f"  {BOLD}Iteration{RESET}\n")

    iterations = fetch_iterations(board_key)
    for it in iterations:
        marker = f"  {GREEN}← current{RESET}" if it["current"] else ""
        print(f"    {it['title']:20s}  {DIM}{it['start']} → {it['end']}{RESET}{marker}")
    print()
    nav_hint()

    result = yn("Assign to current iteration?")
    if result in (BACK, QUIT):
        return result
    if result:
        iter_id, iter_title = fetch_current_iteration(board_key)
        if iter_id:
            fdata = board["fields"]["iteration"]
            state["fields"]["iteration"] = (fdata["id"], iter_id, "iteration")
            print(f"    {GREEN}→ {iter_title}{RESET}")
        else:
            print(f"    {YELLOW}⚠ No current iteration found{RESET}")
    else:
        state["fields"].pop("iteration", None)
    return True


def step_review(state):
    """Full preview before creating."""
    board = BOARDS[state["board_key"]]
    body = build_body(state["description"], state["criteria"], state["extra_context"])

    print(f"  {BOLD}🔍 Review & Confirm{RESET}\n")
    print(f"    {BOLD}Board:{RESET}   {board['name']}")
    print(f"    {BOLD}Repo:{RESET}    {state['repo']}")
    print(f"    {BOLD}Title:{RESET}   {YELLOW}{state['title']}{RESET}")
    if state["labels"]:
        print(f"    {BOLD}Labels:{RESET}  {', '.join(state['labels'])}")

    field_names = []
    for k in state["fields"]:
        display = k.replace("_", " ").title()
        field_names.append(display)
        print(f"    {BOLD}{display:{10}}{RESET} ✓")

    print(f"\n  {DIM}{'─' * 44}{RESET}")
    for line in body.split("\n"):
        print(f"  {DIM}│{RESET} {line}")
    print(f"  {DIM}{'─' * 44}{RESET}\n")

    result = yn(f"{BOLD}Create this issue?{RESET}")
    if result == QUIT:
        return QUIT
    if result == BACK:
        return BACK
    if result:
        state["confirmed"] = True
        return True
    return BACK  # 'no' goes back so they can edit


# ═════════════════════════════════════════════════════════════════════════════
# EXECUTION
# ═════════════════════════════════════════════════════════════════════════════

def execute_create(state):
    """Create the issue, add to board, set fields."""
    board = BOARDS[state["board_key"]]
    body = build_body(state["description"], state["criteria"], state["extra_context"])

    # Validate labels — filter out any that don't exist on the repo
    requested_labels = state.get("labels", [])
    if requested_labels:
        repo_labels = fetch_labels(state["repo"])
        valid_names = {l["name"].lower() for l in repo_labels} if repo_labels else set()
        valid_labels = [l for l in requested_labels if l.lower() in valid_names]
        skipped = [l for l in requested_labels if l.lower() not in valid_names]
        if skipped:
            print(f"  {YELLOW}⚠ Skipping non-existent labels: {', '.join(skipped)}{RESET}")
    else:
        valid_labels = []

    print(f"\n  ⏳ Creating issue...")
    cmd = ["issue", "create", "--repo", state["repo"],
           "--title", state["title"], "--body", body]
    for lbl in valid_labels:
        cmd.extend(["--label", lbl])

    issue_url = gh(*cmd)
    if not issue_url:
        return
    print(f"  {GREEN}✅ {issue_url}{RESET}")

    print(f"  ⏳ Adding to {board['name']}...")
    item_json = gh(
        "project", "item-add", str(board["number"]),
        "--owner", ORG, "--url", issue_url, "--format", "json",
        json_output=True,
    )
    if not item_json:
        return
    item_id = item_json["id"]
    print(f"  {GREEN}✅ Added to board{RESET}")

    for key, (field_id, value, field_type) in state["fields"].items():
        set_project_field(board["project_id"], item_id, field_id, value, field_type)
        display = key.replace("_", " ").title()
        print(f"  {GREEN}✅ {display}{RESET}")

    print(f"\n  🎉 Done! {issue_url}\n")
