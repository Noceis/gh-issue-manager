"""
gh — GitHub CLI wrappers, GraphQL helpers, and data fetchers.
"""

import datetime
import json
import subprocess
import sys

from .config import ORG, BOARDS
from .ui import RED, GREEN, RESET


# ── Low-level gh CLI ─────────────────────────────────────────────────────

def gh(*args, json_output=False):
    cmd = ["gh"] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  {RED}❌ gh error: {r.stderr.strip()}{RESET}", file=sys.stderr)
        return None
    if json_output:
        return json.loads(r.stdout)
    return r.stdout.strip()


def gh_graphql(query):
    r = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  {RED}❌ GraphQL error: {r.stderr.strip()}{RESET}", file=sys.stderr)
        return None
    return json.loads(r.stdout)


# ── Project field mutations ──────────────────────────────────────────────

def set_project_field(project_id, item_id, field_id, value, field_type):
    if field_type == "single_select":
        val_str = f'singleSelectOptionId: "{value}"'
    elif field_type == "iteration":
        val_str = f'iterationId: "{value}"'
    else:
        return
    gh_graphql(f"""
    mutation {{
      updateProjectV2ItemFieldValue(input: {{
        projectId: "{project_id}"
        itemId: "{item_id}"
        fieldId: "{field_id}"
        value: {{ {val_str} }}
      }}) {{ projectV2Item {{ id }} }}
    }}
    """)


# ── Iteration queries ────────────────────────────────────────────────────

def fetch_iterations(board_key):
    board = BOARDS[board_key]
    data = gh_graphql(f"""
    {{
      organization(login: "{ORG}") {{
        projectV2(number: {board["number"]}) {{
          field(name: "Iteration") {{
            ... on ProjectV2IterationField {{
              configuration {{
                iterations {{ id title startDate duration }}
              }}
            }}
          }}
        }}
      }}
    }}
    """)
    if not data:
        return []
    today = datetime.date.today()
    field = data["data"]["organization"]["projectV2"]["field"]
    results = []
    for it in field["configuration"]["iterations"]:
        start = datetime.date.fromisoformat(it["startDate"])
        end = start + datetime.timedelta(days=it["duration"])
        results.append({
            "id": it["id"], "title": it["title"],
            "start": it["startDate"], "end": end.isoformat(),
            "current": start <= today <= end,
        })
    return results


def fetch_current_iteration(board_key):
    for it in fetch_iterations(board_key):
        if it["current"]:
            return it["id"], it["title"]
    return None, None


# ── Label queries ────────────────────────────────────────────────────────

def fetch_labels(repo):
    if "/" not in repo:
        repo = f"{ORG}/{repo}"
    labels = gh("label", "list", "--repo", repo, "--json",
                "name,description", "--limit", "100", json_output=True)
    return sorted(labels or [], key=lambda x: x["name"])


# ── Body builder ─────────────────────────────────────────────────────────

# ── Issue queries ─────────────────────────────────────────────────────────

def fetch_issues(repo, *, state="open", limit=30, labels=None, search=None, assignee=None):
    """List issues from a repo. Returns a list of dicts.

    Supports filtering by state, labels, assignee, and a free-text search term.
    """
    if "/" not in repo:
        repo = f"{ORG}/{repo}"

    cmd = [
        "issue", "list", "--repo", repo,
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,state,labels,assignees,url,createdAt,updatedAt",
    ]
    if labels:
        for lbl in labels:
            cmd.extend(["--label", lbl])
    if assignee:
        cmd.extend(["--assignee", assignee])
    if search:
        cmd.extend(["--search", search])

    return gh(*cmd, json_output=True) or []


def fetch_issue_detail(repo, number):
    """Fetch full details for a single issue."""
    if "/" not in repo:
        repo = f"{ORG}/{repo}"
    return gh(
        "issue", "view", str(number), "--repo", repo,
        "--json", "number,title,body,state,labels,assignees,url,comments,milestone",
        json_output=True,
    )


def update_issue(repo, number, *, title=None, body=None,
                 add_labels=None, remove_labels=None, state=None, add_assignees=None):
    """Edit an existing issue via `gh issue edit`."""
    if "/" not in repo:
        repo = f"{ORG}/{repo}"
    cmd = ["issue", "edit", str(number), "--repo", repo]
    if title:
        cmd.extend(["--title", title])
    if body:
        cmd.extend(["--body", body])
    if add_labels:
        cmd.extend(["--add-label", ",".join(add_labels)])
    if remove_labels:
        cmd.extend(["--remove-label", ",".join(remove_labels)])
    if state:
        # gh uses --state for issue edit (open/closed)
        # Actually gh issue edit doesn't have --state; use gh issue close/reopen
        pass
    if add_assignees:
        cmd.extend(["--add-assignee", ",".join(add_assignees)])
    return gh(*cmd)


def close_issue(repo, number):
    """Close an issue."""
    if "/" not in repo:
        repo = f"{ORG}/{repo}"
    return gh("issue", "close", str(number), "--repo", repo)


def reopen_issue(repo, number):
    """Reopen a closed issue."""
    if "/" not in repo:
        repo = f"{ORG}/{repo}"
    return gh("issue", "reopen", str(number), "--repo", repo)


def add_issue_comment(repo, number, comment_body):
    """Add a comment to an issue."""
    if "/" not in repo:
        repo = f"{ORG}/{repo}"
    return gh("issue", "comment", str(number), "--repo", repo, "--body", comment_body)


# ── Body builder ─────────────────────────────────────────────────────────

def build_body(description, criteria, extra_context=None):
    body = f"## Description\n\n{description}\n"
    if criteria:
        body += "\n## Acceptance Criteria\n\n"
        for ac in criteria:
            body += f"- [ ] {ac}\n"
    if extra_context:
        body += f"\n## Additional Context\n\n{extra_context}\n"
    return body
