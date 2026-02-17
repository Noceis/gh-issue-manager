"""
analyse — AI-powered backlog analysis: duplicates, priorities, risks, staleness.

Fetches all open issues from both boards, sends them to Copilot for
structured analysis, and presents actionable findings.
"""

import asyncio
import json

from .config import ORG, BOARDS, WORKSPACE, AI_MODEL
from .ui import (
    BOLD, CYAN, DIM, GREEN, YELLOW, RED, MAGENTA, RESET,
    BACK, QUIT,
    clear, banner, nav_hint, prompt, pick_one, yn,
)
from .gh import fetch_issues, close_issue


# ═════════════════════════════════════════════════════════════════════════════
# ANALYSIS SYSTEM PROMPT
# ═════════════════════════════════════════════════════════════════════════════

_ANALYSIS_SYSTEM_PROMPT = f"""You are a senior engineering manager and product owner
reviewing a development team's backlog.

Organisation: {ORG}
Workspace: {WORKSPACE}

You will receive a JSON array of all open issues across two repositories/boards.
Analyse them thoroughly and produce a structured JSON report.

Respond ONLY with valid JSON — no markdown, no commentary.

Use this exact schema:

{{
  "summary": {{
    "total_issues": <int>,
    "by_repo": {{ "<repo>": <int>, ... }},
    "oldest_issue": {{ "number": <int>, "repo": "<repo>", "title": "<str>", "created": "<date>" }},
    "avg_age_days": <int>
  }},
  "duplicates": [
    {{
      "group": "<short label for the duplicate cluster>",
      "issues": [
        {{ "number": <int>, "repo": "<repo>", "title": "<str>" }}
      ],
      "recommendation": "<which to keep & which to close>"
    }}
  ],
  "stale": [
    {{
      "number": <int>,
      "repo": "<repo>",
      "title": "<str>",
      "age_days": <int>,
      "recommendation": "close | deprioritise | needs-update"
    }}
  ],
  "priority_assessment": [
    {{
      "category": "critical | high | medium | low",
      "issues": [
        {{ "number": <int>, "repo": "<repo>", "title": "<str>", "reason": "<why this priority>" }}
      ]
    }}
  ],
  "risks_and_blockers": [
    {{
      "issue_number": <int>,
      "repo": "<repo>",
      "title": "<str>",
      "risk": "<description of risk or blocker>"
    }}
  ],
  "quick_wins": [
    {{
      "number": <int>,
      "repo": "<repo>",
      "title": "<str>",
      "reason": "<why this is a quick win>"
    }}
  ],
  "recommendations": [
    "<actionable recommendation as a sentence>"
  ]
}}

Rules:
- "stale" = issues older than 60 days with no recent activity.
- For duplicates, look at semantic similarity in titles AND descriptions, not just exact matches.
- Priority assessment should consider urgency cues, security implications, and user impact.
- Quick wins are small-scope items that can be done rapidly and clear the backlog.
- Recommendations should be concrete, actionable sentences.
- Use British English.
- If there are no items for a category, return an empty array.
"""


# ═════════════════════════════════════════════════════════════════════════════
# FETCH ALL ISSUES
# ═════════════════════════════════════════════════════════════════════════════

def _fetch_all_issues():
    """Fetch all open issues from every configured board repo."""
    all_issues = []
    for bkey, board in BOARDS.items():
        repo = board["repo"]
        issues = fetch_issues(repo, state="open", limit=200)
        for issue in issues:
            issue["_repo"] = repo
            issue["_board"] = bkey
        all_issues.extend(issues)
    return all_issues


def _issues_to_prompt(issues):
    """Convert issues list to a compact JSON string for the AI prompt."""
    compact = []
    for i in issues:
        labels = [l["name"] for l in i.get("labels", [])] if i.get("labels") else []
        assignees = [a["login"] for a in i.get("assignees", [])] if i.get("assignees") else []
        compact.append({
            "number": i["number"],
            "repo": i["_repo"],
            "board": i["_board"],
            "title": i["title"],
            "state": i["state"],
            "labels": labels,
            "assignees": assignees,
            "created": i.get("createdAt", "")[:10],
            "updated": i.get("updatedAt", "")[:10],
        })
    return json.dumps(compact, indent=2)


# ═════════════════════════════════════════════════════════════════════════════
# RUN ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════

async def analyse_backlog():
    """Fetch all issues, send to Copilot for analysis, display results."""
    clear()
    banner()
    print(f"  {MAGENTA}{BOLD}🔬 AI Backlog Analysis{RESET}\n")
    print(f"  Fetches all open issues from both boards and asks Copilot to")
    print(f"  find duplicates, stale items, priority gaps, risks, and quick wins.\n")

    # ── Fetch ────────────────────────────────────────────────────────────
    print(f"  {DIM}⏳ Fetching issues from all boards...{RESET}")
    issues = _fetch_all_issues()
    if not issues:
        print(f"\n  {YELLOW}No open issues found across any board.{RESET}")
        prompt("Press enter to return")
        return

    # Print summary of what was fetched
    by_repo = {}
    for i in issues:
        r = i["_repo"].split("/")[-1]
        by_repo[r] = by_repo.get(r, 0) + 1
    parts = [f"{v} from {k}" for k, v in by_repo.items()]
    print(f"  {GREEN}✓ {len(issues)} open issues{RESET}  ({', '.join(parts)})\n")

    proceed = yn("Run AI analysis on these issues?")
    if proceed is not True:
        return

    # ── Start Copilot ────────────────────────────────────────────────────
    from .ai import _start_copilot, _stream_response

    print(f"\n  {DIM}⏳ Starting Copilot...{RESET}")
    client, session = await _start_copilot(_ANALYSIS_SYSTEM_PROMPT)

    try:
        issues_json = _issues_to_prompt(issues)
        user_prompt = (
            f"Here are {len(issues)} open issues across our boards. "
            f"Analyse them and produce the JSON report.\n\n{issues_json}"
        )

        print(f"  {DIM}🤖 Analysing {len(issues)} issues...{RESET}")
        raw = await _stream_response(session, user_prompt, timeout=180, silent=True)

        report = _parse_report(raw)
        if not report:
            print(f"\n  {RED}Could not parse Copilot's analysis.{RESET}")
            print(f"  {DIM}Raw response:{RESET}\n")
            for line in raw.split("\n")[:20]:
                print(f"    {line}")
            prompt("\nPress enter to return")
            return

        # ── Display results ──────────────────────────────────────────────
        _display_report(report, issues)

        # ── Follow-up actions ────────────────────────────────────────────
        await _action_menu(session, report, issues)

    finally:
        await session.destroy()
        await client.stop()

    prompt("Press enter to return to menu")


# ═════════════════════════════════════════════════════════════════════════════
# PARSE & DISPLAY
# ═════════════════════════════════════════════════════════════════════════════

def _parse_report(raw):
    """Extract JSON report from Copilot response."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


def _display_report(report, issues):
    """Render the analysis report to the terminal."""
    clear()
    banner()

    # ── Summary ──────────────────────────────────────────────────────────
    summary = report.get("summary", {})
    print(f"  {MAGENTA}{BOLD}🔬 Backlog Analysis Report{RESET}\n")
    print(f"  {BOLD}Summary{RESET}")
    print(f"    Total open issues:  {CYAN}{summary.get('total_issues', len(issues))}{RESET}")
    by_repo = summary.get("by_repo", {})
    for repo, count in by_repo.items():
        repo_short = repo.split("/")[-1] if "/" in repo else repo
        print(f"    {repo_short:25s} {count}")
    avg_age = summary.get("avg_age_days")
    if avg_age:
        print(f"    Average age:        {avg_age} days")
    oldest = summary.get("oldest_issue")
    if oldest:
        repo_short = oldest.get("repo", "").split("/")[-1]
        print(f"    Oldest:             #{oldest.get('number')} {DIM}({repo_short}, {oldest.get('created', '?')}){RESET}")
        print(f"                        {DIM}{oldest.get('title', '')}{RESET}")

    # ── Duplicates ───────────────────────────────────────────────────────
    dupes = report.get("duplicates", [])
    print(f"\n  {BOLD}{'🔁 Potential Duplicates' if dupes else '🔁 No Duplicates Found'}{RESET}")
    if dupes:
        print(f"  {DIM}Found {len(dupes)} group(s) of similar issues{RESET}\n")
    for group in dupes:
        label = group.get("group", "unnamed")
        print(f"    {YELLOW}{BOLD}{label}{RESET}")
        for iss in group.get("issues", []):
            repo_short = iss.get("repo", "").split("/")[-1]
            print(f"      {CYAN}#{iss['number']}{RESET}  {iss.get('title', '')}  {DIM}({repo_short}){RESET}")
        rec = group.get("recommendation", "")
        if rec:
            print(f"      {DIM}→ {rec}{RESET}")
        print()

    # ── Stale ────────────────────────────────────────────────────────────
    stale = report.get("stale", [])
    print(f"  {BOLD}{'🕸️  Stale Issues' if stale else '🕸️  No Stale Issues'}{RESET}")
    if stale:
        print(f"  {DIM}Issues older than 60 days with no recent activity{RESET}\n")
    for s in stale:
        repo_short = s.get("repo", "").split("/")[-1]
        age = s.get("age_days", "?")
        rec = s.get("recommendation", "")
        colour = RED if rec == "close" else YELLOW
        print(f"    {colour}#{s['number']}{RESET}  {s.get('title', '')}  "
              f"{DIM}({repo_short}, {age}d old){RESET}")
        print(f"      {DIM}→ {rec}{RESET}")
    if stale:
        print()

    # ── Priority Assessment ──────────────────────────────────────────────
    priorities = report.get("priority_assessment", [])
    print(f"  {BOLD}📊 Priority Assessment{RESET}\n")
    priority_colours = {
        "critical": RED,
        "high": YELLOW,
        "medium": CYAN,
        "low": DIM,
    }
    for cat in priorities:
        category = cat.get("category", "unknown")
        colour = priority_colours.get(category, RESET)
        cat_issues = cat.get("issues", [])
        if not cat_issues:
            continue
        print(f"    {colour}{BOLD}{category.upper()}{RESET}  ({len(cat_issues)} issues)")
        for iss in cat_issues:
            repo_short = iss.get("repo", "").split("/")[-1]
            print(f"      {CYAN}#{iss['number']}{RESET}  {iss.get('title', '')}  {DIM}({repo_short}){RESET}")
            reason = iss.get("reason", "")
            if reason:
                print(f"        {DIM}{reason}{RESET}")
        print()

    # ── Risks & Blockers ─────────────────────────────────────────────────
    risks = report.get("risks_and_blockers", [])
    print(f"  {BOLD}{'⚠️  Risks & Blockers' if risks else '⚠️  No Risks or Blockers Identified'}{RESET}")
    if risks:
        print()
    for r in risks:
        repo_short = r.get("repo", "").split("/")[-1]
        print(f"    {RED}#{r.get('issue_number', '?')}{RESET}  {r.get('title', '')}  {DIM}({repo_short}){RESET}")
        print(f"      {YELLOW}{r.get('risk', '')}{RESET}")
    if risks:
        print()

    # ── Quick Wins ───────────────────────────────────────────────────────
    wins = report.get("quick_wins", [])
    print(f"  {BOLD}{'⚡ Quick Wins' if wins else '⚡ No Quick Wins Identified'}{RESET}")
    if wins:
        print()
    for w in wins:
        repo_short = w.get("repo", "").split("/")[-1]
        print(f"    {GREEN}#{w['number']}{RESET}  {w.get('title', '')}  {DIM}({repo_short}){RESET}")
        reason = w.get("reason", "")
        if reason:
            print(f"      {DIM}{reason}{RESET}")
    if wins:
        print()

    # ── Recommendations ──────────────────────────────────────────────────
    recs = report.get("recommendations", [])
    if recs:
        print(f"  {BOLD}💡 Recommendations{RESET}\n")
        for i, rec in enumerate(recs, 1):
            print(f"    {CYAN}{i}.{RESET} {rec}")
        print()


# ═════════════════════════════════════════════════════════════════════════════
# FOLLOW-UP ACTIONS
# ═════════════════════════════════════════════════════════════════════════════

async def _action_menu(session, report, issues):
    """Let the user act on the analysis findings."""
    from .ai import _stream_response

    while True:
        print(f"\n  {DIM}{'─' * 50}{RESET}")
        action = pick_one("What would you like to do?", {
            "close_dupes": "Close duplicate issues",
            "close_stale": "Close stale issues",
            "ask": "Ask Copilot a follow-up question",
            "done": "Return to menu",
        }, allow_skip=False)

        if action in (BACK, QUIT, "done", None):
            return

        elif action == "close_dupes":
            await _close_duplicates(report)

        elif action == "close_stale":
            await _close_stale(report)

        elif action == "ask":
            nav_hint()
            question = prompt("Question")
            if question in (BACK, QUIT) or not question:
                continue
            context = (
                f"The user has just reviewed a backlog analysis. Here is the report:\n"
                f"{json.dumps(report, indent=2)}\n\n"
                f"User question: {question}"
            )
            print(f"\n  {DIM}🤖 Copilot:{RESET}\n")
            await _stream_response(session, context)


async def _close_duplicates(report):
    """Offer to close issues identified as duplicates."""
    dupes = report.get("duplicates", [])
    if not dupes:
        print(f"  {DIM}No duplicates to close.{RESET}")
        return

    for group in dupes:
        label = group.get("group", "unnamed")
        group_issues = group.get("issues", [])
        rec = group.get("recommendation", "")

        print(f"\n  {YELLOW}{BOLD}{label}{RESET}")
        for iss in group_issues:
            repo_short = iss.get("repo", "").split("/")[-1]
            print(f"    {CYAN}#{iss['number']}{RESET}  {iss.get('title', '')}  {DIM}({repo_short}){RESET}")
        if rec:
            print(f"    {DIM}Recommendation: {rec}{RESET}")

        raw = prompt(f"Issue numbers to close (comma-separated, blank to skip)")
        if raw in (BACK, QUIT):
            return
        if not raw:
            continue

        numbers = []
        for part in raw.split(","):
            part = part.strip().lstrip("#")
            try:
                numbers.append(int(part))
            except ValueError:
                pass

        for num in numbers:
            # Find the repo for this issue number
            repo = None
            for iss in group_issues:
                if iss["number"] == num:
                    repo = iss.get("repo")
                    break
            if not repo:
                print(f"  {YELLOW}⚠ #{num} not found in this group, skipping.{RESET}")
                continue

            confirm = yn(f"  Close #{num} in {repo.split('/')[-1]}?")
            if confirm is True:
                result = close_issue(repo, num)
                if result is not None:
                    print(f"  {GREEN}✅ #{num} closed.{RESET}")
                else:
                    print(f"  {RED}❌ Failed to close #{num}.{RESET}")


async def _close_stale(report):
    """Offer to close issues identified as stale."""
    stale = report.get("stale", [])
    if not stale:
        print(f"  {DIM}No stale issues to close.{RESET}")
        return

    # Only show items recommended for closing
    closeable = [s for s in stale if s.get("recommendation") == "close"]
    if not closeable:
        print(f"  {DIM}No stale issues recommended for closing.{RESET}")
        other = [s for s in stale if s.get("recommendation") != "close"]
        if other:
            print(f"  {DIM}{len(other)} issue(s) recommended for deprioritisation or update only.{RESET}")
        return

    print(f"\n  {BOLD}Stale issues recommended for closing:{RESET}\n")
    for s in closeable:
        repo_short = s.get("repo", "").split("/")[-1]
        print(f"    {RED}#{s['number']}{RESET}  {s.get('title', '')}  {DIM}({repo_short}, {s.get('age_days', '?')}d){RESET}")
    print()

    confirm_all = yn(f"Close all {len(closeable)} stale issues?")
    if confirm_all is True:
        for s in closeable:
            repo = s.get("repo", "")
            num = s["number"]
            result = close_issue(repo, num)
            if result is not None:
                print(f"  {GREEN}✅ #{num} closed.{RESET}")
            else:
                print(f"  {RED}❌ Failed to close #{num}.{RESET}")
    elif confirm_all is False:
        # Let them pick individually
        raw = prompt("Issue numbers to close (comma-separated, blank to skip)")
        if raw in (BACK, QUIT) or not raw:
            return
        numbers = set()
        for part in raw.split(","):
            part = part.strip().lstrip("#")
            try:
                numbers.add(int(part))
            except ValueError:
                pass

        for s in closeable:
            if s["number"] in numbers:
                repo = s.get("repo", "")
                result = close_issue(repo, s["number"])
                if result is not None:
                    print(f"  {GREEN}✅ #{s['number']} closed.{RESET}")
                else:
                    print(f"  {RED}❌ Failed to close #{s['number']}.{RESET}")
