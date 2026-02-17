"""
ai — Copilot SDK integration for AI-assisted issue creation and chat.
"""

import asyncio
import json

from .config import ORG, DEFAULT_REPO, WORKSPACE, BOARDS, AI_MODEL
from .ui import (
    BOLD, CYAN, DIM, GREEN, YELLOW, RED, MAGENTA, RESET,
    BACK, QUIT,
    clear, banner, nav_hint, prompt, pick_one, multiline, yn, run_steps,
)
from .gh import build_body, fetch_labels
from .wizard import (
    execute_create, step_title, step_description, step_criteria,
    step_context, step_labels, step_board_fields, step_review,
)

# Get first board key as default fallback
_DEFAULT_BOARD = next(iter(BOARDS.keys())) if BOARDS else \"main\"


# ── System prompts ───────────────────────────────────────────────────────

def _board_schema_text():
    """Produce a concise text description of all boards and their fields for the system prompt."""
    lines = []
    for key, board in BOARDS.items():
        lines.append(f"Board '{key}' ({board['name']}, project #{board['number']}):")
        for fname, fdata in board["fields"].items():
            if "options" in fdata:
                opts = ", ".join(fdata["options"].keys())
                lines.append(f"  {fname}: {opts}")
            else:
                lines.append(f"  {fname}: (iteration field)")
    return "\n".join(lines)


def _build_ai_system_prompt():
    """Build the AI system prompt dynamically, including available repo labels."""
    # Fetch real labels per repo so the AI only uses ones that exist
    labels_lines = []
    for bkey, bdata in BOARDS.items():
        repo = bdata["repo"]
        labels = fetch_labels(repo)
        if labels:
            label_names = [l["name"] for l in labels]
            labels_lines.append(f"Available labels on {repo}: {', '.join(label_names)}")
        else:
            labels_lines.append(f"Could not fetch labels for {repo}.")
    labels_lines.append("Only use labels from these lists. Do NOT invent labels.")
    labels_text = "\n".join(labels_lines)

    return f"""You are a helpful assistant embedded in the Issue Manager CLI.
You have access to the user's local workspace at {WORKSPACE}.

GitHub organisation: {ORG}

Repository-to-board mapping:
{board_repo_text}
Always set "board" based on which repo the issue belongs to.

{_board_schema_text()}

{labels_text}

SMART FIELD SELECTION — always try to fill in the right fields based on context:

Labels — pick the most appropriate from the available list:
  - "enhancement" for new features or improvements
  - "bug" for defects or broken behaviour
  - "documentation" for docs-only work
  - "epic" for large cross-cutting initiatives
  - If nothing fits well, omit labels rather than forcing a bad match.

Field selection guidelines:
- Use the available field options shown in the board schema above.
- For priority fields: "p0" = critical, "p1" = important, "p2" = normal (default if not specified).
- For size fields: "xs" = trivial, "s" = small, "m" = medium, "l" = large, "xl" = very large.
- For status fields: use what the user specifies, otherwise default to the first option.
- If a field has options, only use values from those options.

When asked to draft issues, always respond with valid JSON — no markdown fences, no preamble, no commentary.

For a SINGLE issue use this schema:
{{
  "title": "<concise issue title>",
  "description": "<detailed description>",
  "criteria": ["<AC 1>", "<AC 2>", ...],
  "board": "<board_key from the list above>",
  "labels": ["<label>", ...],
  "fields": {{"<field_name>": "<option_key>", ...}}
}}

For MULTIPLE issues return a JSON array of objects with the same schema:
[
  {{ "title": "...", "description": "...", ... }},
  {{ "title": "...", "description": "...", ... }}
]

Never ask clarifying questions — make your best judgement and draft the issues.
If a ticket title is ambiguous, use it as-is and write a reasonable description.
When the user lists multiple items, create a separate issue for each distinct item
unless it clearly makes sense to group closely related ones together.
Read the relevant project files to inform your drafting.
"""

CHAT_SYSTEM_PROMPT = f"""You are a helpful assistant embedded in the Issue Manager CLI.
You have access to the user's local workspace at {WORKSPACE}.
service-fee-review, dependency-track, prodatlas, dns-firewall-zscaler.

You can read any file in the workspace to answer questions.
Keep answers concise and practical.
"""


# ── Copilot helpers ──────────────────────────────────────────────────────

async def _start_copilot(system_prompt):
    """Start a Copilot client + session. Returns (client, session)."""
    try:
        from copilot import CopilotClient
    except ModuleNotFoundError:
        raise RuntimeError(
            "The 'copilot' SDK is not installed in this Python environment. "
            "Use Python 3.11 or install the copilot package."
        )
    client = CopilotClient()
    await client.start()
    session = await client.create_session({
        "model": AI_MODEL,
        "working_directory": WORKSPACE,
        "streaming": True,
        "system_message": {"content": system_prompt},
    })
    return client, session


async def _stream_response(session, user_prompt, *, timeout=120, silent=False):
    """Send a prompt and stream the response. Returns full text.

    When silent=True, output is collected without printing (useful for JSON
    responses). A simple spinner is shown instead.
    """
    from copilot.generated.session_events import SessionEventType

    chunks = []
    done = asyncio.Event()
    tool_in_progress = [False]
    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    frame_idx = [0]

    def on_event(event):
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None) or ""
            if delta:
                chunks.append(delta)
                if not silent:
                    print(delta, end="", flush=True)
                else:
                    # Update spinner
                    frame = spinner_frames[frame_idx[0] % len(spinner_frames)]
                    print(f"\r  {CYAN}{frame}{RESET} {DIM}Drafting... ({len(chunks)} chunks){RESET}  ", end="", flush=True)
                    frame_idx[0] += 1
        elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
            if tool_in_progress[0]:
                if not silent:
                    print(f"{RESET}", end="")
                tool_in_progress[0] = False
        elif event.type == SessionEventType.ASSISTANT_INTENT:
            intent = getattr(event.data, "content", None) or ""
            if intent:
                print(f"\n  {DIM}🔍 {intent}{RESET}", flush=True)
                tool_in_progress[0] = True
        elif event.type == SessionEventType.SESSION_IDLE:
            done.set()
        elif event.type == SessionEventType.SESSION_ERROR:
            error = getattr(event.data, "message", str(event.data))
            print(f"\n  {RED}❌ {error}{RESET}")
            done.set()

    session.on(on_event)
    await session.send({"prompt": user_prompt})

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"\n  {YELLOW}⚠ Timed out after {timeout}s{RESET}")

    if silent:
        print(f"\r  {GREEN}✓{RESET} {DIM}Response received{RESET}                    ")  # clear spinner line
    else:
        print()  # newline after streaming
    return "".join(chunks)


# ── AI issue wizard ──────────────────────────────────────────────────────

async def wizard_ai_issue():
    """AI-assisted issue creation: describe what you need, Copilot drafts it."""
    clear()
    banner()
    print(f"  {MAGENTA}{BOLD}✨ AI-Assisted Issue Creation{RESET}\n")
    print(f"  Describe the issue(s) you need — Copilot will read your project")
    print(f"  documents and draft them with title, description,")
    print(f"  acceptance criteria, and board fields.")
    print(f"  You can request multiple issues at once.\n")
    nav_hint()

    user_input = multiline("What issue(s) do you need?")
    if user_input in (BACK, QUIT) or not user_input:
        return

    print(f"\n  {DIM}⏳ Fetching labels & starting Copilot...{RESET}")
    ai_prompt = _build_ai_system_prompt()
    client, session = await _start_copilot(ai_prompt)

    try:
        print(f"  {DIM}🤖 Copilot is reading your docs and drafting...{RESET}")
        raw = await _stream_response(session, user_input, silent=True)

        # Parse the JSON (always returns a list or None)
        drafts = _parse_ai_draft(raw)
        if not drafts:
            print(f"\n  {RED}Could not parse Copilot's response as valid issue draft(s).{RESET}")
            print(f"  {DIM}You can try again with a more specific prompt.{RESET}")
            prompt("Press enter to return")
            return

        if len(drafts) == 1:
            await _review_single_draft(session, drafts[0])
        else:
            await _review_batch_drafts(session, drafts)

    finally:
        await session.destroy()
        await client.stop()

    prompt("Press enter to return to menu")


# ── Single-issue review ─────────────────────────────────────────────────

async def _review_single_draft(session, draft):
    """Review and act on a single drafted issue."""
    _print_draft(draft)

    action = pick_one("What would you like to do?", {
        "create": "Create this issue as-is",
        "edit": "Edit in the manual wizard",
        "refine": "Ask Copilot to refine it",
        "cancel": "Discard",
    }, allow_skip=False)

    if action == "create":
        await _create_from_draft(draft)
    elif action == "edit":
        _load_draft_into_wizard(draft)
    elif action == "refine":
        await _refine_loop(session, [draft])


# ── Batch review ─────────────────────────────────────────────────────────

async def _review_batch_drafts(session, drafts):
    """Review and act on multiple drafted issues."""
    _print_batch_summary(drafts)

    while True:
        action = pick_one("What would you like to do?", {
            "create_all": f"Create all {len(drafts)} issues",
            "review": "Review each issue in detail",
            "refine": "Ask Copilot to refine all drafts",
            "cancel": "Discard all",
        }, allow_skip=False)

        if action in (BACK, QUIT, "cancel"):
            return
        elif action == "create_all":
            confirm = yn(f"{BOLD}Create all {len(drafts)} issues?{RESET}")
            if confirm is True:
                await _create_batch(drafts)
            return
        elif action == "review":
            drafts = await _review_each(session, drafts)
            if not drafts:
                return
            _print_batch_summary(drafts)
            continue
        elif action == "refine":
            drafts = await _refine_loop(session, drafts)
            if not drafts:
                return
            _print_batch_summary(drafts)
            continue


def _print_draft(draft, index=None):
    """Pretty-print a single draft."""
    prefix = f"  {BOLD}Issue {index}:{RESET}\n" if index else ""
    print(f"\n  {DIM}{'─' * 50}{RESET}")
    if prefix:
        print(prefix, end="")
    print(f"    {BOLD}Title:{RESET}   {YELLOW}{draft.get('title', '(untitled)')}{RESET}")
    board_key = draft.get('board', _DEFAULT_BOARD)
    board_cfg = BOARDS.get(board_key, BOARDS[_DEFAULT_BOARD])
    print(f"    {BOLD}Repo:{RESET}    {board_cfg['repo']}")
    print(f"    {BOLD}Board:{RESET}   {board_cfg['name']}")
    if draft.get("labels"):
        print(f"    {BOLD}Labels:{RESET}  {', '.join(draft['labels'])}")
    if draft.get("fields"):
        for k, v in draft["fields"].items():
            display = k.replace('_', ' ').title()
            print(f"    {BOLD}{display}:{RESET}  {v}")
    print(f"\n    {BOLD}Description:{RESET}")
    for ln in draft.get("description", "").split("\n"):
        print(f"      {ln}")
    if draft.get("criteria"):
        print(f"\n    {BOLD}Acceptance Criteria:{RESET}")
        for c in draft["criteria"]:
            print(f"      ☐ {c}")
    print(f"  {DIM}{'─' * 50}{RESET}")


def _print_batch_summary(drafts):
    """Print a numbered summary table of all drafts, with available labels."""
    # Collect labels per repo for validation
    _label_cache = {}

    print(f"\n  {BOLD}Copilot drafted {len(drafts)} issue(s):{RESET}\n")
    for i, d in enumerate(drafts, 1):
        board_key = d.get("board", _DEFAULT_BOARD)
        board_cfg = BOARDS.get(board_key, BOARDS[_DEFAULT_BOARD])
        repo = board_cfg["repo"]
        fields_summary = ", ".join(f"{k}={v}" for k, v in d.get("fields", {}).items())
        labels = d.get("labels", [])

        # Fetch & cache labels per repo
        if repo not in _label_cache:
            repo_labels = fetch_labels(repo)
            _label_cache[repo] = repo_labels
        repo_labels = _label_cache[repo]

        # Mark invalid labels
        if labels and repo_labels:
            valid_set = {l["name"].lower() for l in repo_labels}
            label_parts = []
            for l in labels:
                if l.lower() in valid_set:
                    label_parts.append(f"{GREEN}{l}{RESET}")
                else:
                    label_parts.append(f"{RED}{l} ✗{RESET}")
            label_str = f"  labels=[{', '.join(label_parts)}]"
        elif labels:
            label_str = f"  labels=[{', '.join(labels)}]"
        else:
            label_str = ""
        print(f"    {CYAN}{i:>2}{RESET}  {YELLOW}{d.get('title', '(untitled)')}{RESET}")
        print(f"        {DIM}{repo.split('/')[-1]} → {board_cfg['name']}  {fields_summary}{RESET}{label_str}")
    print()


async def _review_each(session, drafts):
    """Walk through each draft, letting the user keep, edit, or drop it."""
    kept = []
    for i, draft in enumerate(drafts, 1):
        clear()
        banner()
        print(f"  {DIM}Issue {i}/{len(drafts)}{RESET}")
        _print_draft(draft)
        print()

        action = pick_one("Action for this issue", {
            "keep": "Keep as-is",
            "edit": "Edit in manual wizard",
            "drop": "Drop this issue",
        }, allow_skip=False)

        if action in (QUIT, BACK):
            return kept if kept else None
        elif action == "keep":
            kept.append(draft)
        elif action == "edit":
            _load_draft_into_wizard(draft)
            # After wizard, it's either created or discarded — don't add to kept
        # drop = skip

    if kept:
        clear()
        banner()
        print(f"\n  {GREEN}{len(kept)} issue(s) kept.{RESET}")
        confirm = yn(f"{BOLD}Create the {len(kept)} kept issue(s) now?{RESET}")
        if confirm is True:
            await _create_batch(kept)
    return kept


async def _create_batch(drafts):
    """Create multiple issues sequentially."""
    print(f"\n  {BOLD}Creating {len(drafts)} issue(s)...{RESET}\n")
    for i, draft in enumerate(drafts, 1):
        print(f"  {DIM}── Issue {i}/{len(drafts)} ──{RESET}")
        print(f"  {YELLOW}{draft.get('title', '(untitled)')}{RESET}")
        await _create_from_draft(draft)
        print()
    print(f"  {GREEN}🎉 All {len(drafts)} issue(s) created!{RESET}\n")


def _parse_ai_draft(raw):
    """Extract JSON from Copilot's response. Always returns a list of drafts, or None."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON array first, then object
        for open_ch, close_ch in [("[", "]"), ("{", "}")]:
            start = text.find(open_ch)
            end = text.rfind(close_ch) + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end])
                    break
                except json.JSONDecodeError:
                    continue

    if parsed is None:
        return None
    if isinstance(parsed, list):
        return parsed if parsed else None
    if isinstance(parsed, dict):
        return [parsed]
    return None


async def _create_from_draft(draft):
    """Convert an AI draft dict to state and create the issue."""
    board_key = draft.get("board", _DEFAULT_BOARD)
    if board_key not in BOARDS:
        board_key = _DEFAULT_BOARD
    board = BOARDS[board_key]

    state = {
        "board_key": board_key,
        "repo": board["repo"],
        "title": draft["title"],
        "description": draft.get("description", ""),
        "criteria": draft.get("criteria", []),
        "extra_context": None,
        "labels": draft.get("labels", []),
        "fields": {},
        "confirmed": True,
    }

    # Map field values from the draft
    for fkey, fval in draft.get("fields", {}).items():
        if fkey in board["fields"] and "options" in board["fields"][fkey]:
            opts = board["fields"][fkey]["options"]
            v = fval.lower()
            if v in opts:
                state["fields"][fkey] = (board["fields"][fkey]["id"], opts[v], "single_select")

    execute_create(state)


def _load_draft_into_wizard(draft):
    """Load an AI draft into the manual wizard for editing."""
    board_key = draft.get("board", _DEFAULT_BOARD)
    if board_key not in BOARDS:
        board_key = _DEFAULT_BOARD
    board = BOARDS[board_key]

    state = {
        "board_key": board_key,
        "repo": board["repo"],
        "title": draft.get("title", ""),
        "description": draft.get("description", ""),
        "criteria": draft.get("criteria", []),
        "extra_context": None,
        "labels": draft.get("labels", []),
        "fields": {},
        "confirmed": False,
    }

    # Pre-fill fields
    for fkey, fval in draft.get("fields", {}).items():
        if fkey in board["fields"] and "options" in board["fields"][fkey]:
            opts = board["fields"][fkey]["options"]
            v = fval.lower()
            if v in opts:
                state["fields"][fkey] = (board["fields"][fkey]["id"], opts[v], "single_select")

    # Jump straight to title step (board + repo pre-filled)
    steps = [
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


async def _refine_loop(session, drafts):
    """Let the user ask Copilot to refine the drafts in a chat loop. Returns updated drafts list."""
    while True:
        print(f"\n  {MAGENTA}Ask Copilot to refine (or type 'done' to finish, 'cancel' to discard):{RESET}")
        feedback = prompt("Feedback")
        if feedback in (QUIT, BACK) or (feedback and feedback.lower() == "cancel"):
            return drafts
        if feedback and feedback.lower() == "done":
            return drafts
        if not feedback:
            continue

        current = drafts if len(drafts) > 1 else drafts[0]
        refinement_prompt = (
            f"The user wants to refine the issue(s). Here are the current draft(s):\n"
            f"{json.dumps(current, indent=2)}\n\n"
            f"User feedback: {feedback}\n\n"
            f"Output the updated issue(s) as valid JSON in the same schema "
            f"({'array' if len(drafts) > 1 else 'object'})."
        )

        print(f"\n  {DIM}🤖 Refining...{RESET}")
        raw = await _stream_response(session, refinement_prompt, silent=True)
        new_drafts = _parse_ai_draft(raw)
        if new_drafts:
            drafts = new_drafts
            print(f"\n  {GREEN}✅ Draft(s) updated.{RESET}")
            _print_batch_summary(drafts)
        else:
            print(f"\n  {YELLOW}⚠ Could not parse the refinement. Try again.{RESET}")
    return drafts


# ── Copilot chat ─────────────────────────────────────────────────────────

async def copilot_chat():
    """Open-ended Copilot chat that can read workspace files."""
    clear()
    banner()
    print(f"  {MAGENTA}{BOLD}💬 Copilot Chat{RESET}\n")
    print(f"  Ask anything about your projects. Copilot can read your")
    print(f"  workspace files to answer questions.")
    print(f"  Type {DIM}'exit'{RESET} or {DIM}'q'{RESET} to return to the menu.\n")

    print(f"  {DIM}⏳ Starting Copilot...{RESET}")
    client, session = await _start_copilot(CHAT_SYSTEM_PROMPT)

    try:
        while True:
            print()
            user_input = prompt(f"{MAGENTA}You{RESET}")
            if user_input in (QUIT, BACK) or (user_input and user_input.lower() in ("exit", "quit")):
                break
            if not user_input:
                continue

            print(f"\n  {DIM}🤖 Copilot:{RESET}\n")
            await _stream_response(session, user_input)

    finally:
        await session.destroy()
        await client.stop()
