"""
config — Runtime configuration for the Issue Manager CLI.

Configuration can be provided with a JSON file.
Search order:
1) $ISSUE_CONFIG (explicit path)
2) <workspace>/.issue/config.json
3) ~/.issue/config.json

If no config file exists, built-in defaults are used.
"""

import json
import os
import sys


WORKSPACE = os.getenv(
    "ISSUE_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)


# Built-in defaults for open-source usage.
# Replace with your own IDs via .issue/config.json or ISSUE_CONFIG.
_DEFAULT_CONFIG = {
    "org": "your-org",
    "default_repo": "your-org/your-repo",
    "ai_model": "claude-opus-4.6",
    "boards": {
        "main": {
            "number": 1,
            "name": "Main Project",
            "repo": "your-org/your-repo",
            "project_id": "PVT_xxx",
            "fields": {
                "status": {
                    "id": "PVTSSF_status_xxx",
                    "options": {
                        "todo": "opt_todo",
                        "in progress": "opt_in_progress",
                        "review": "opt_review",
                        "done": "opt_done",
                    },
                },
                "iteration": {"id": "PVTIF_iteration_xxx"},
            },
        }
    },
}


def _candidate_paths():
    env_path = os.getenv("ISSUE_CONFIG")
    return [
        env_path,
        os.path.join(WORKSPACE, ".issue", "config.json"),
        os.path.expanduser("~/.issue/config.json"),
    ]


def _load_config():
    for path in _candidate_paths():
        if not path:
            continue
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Config root must be a JSON object")
            return data
        except Exception as exc:  # pragma: no cover - defensive fallback
            print(f"[issue] Failed to load config at {path}: {exc}", file=sys.stderr)
            break
    return _DEFAULT_CONFIG


_CONFIG = _load_config()

ORG = _CONFIG.get("org", _DEFAULT_CONFIG["org"])
DEFAULT_REPO = _CONFIG.get("default_repo", _DEFAULT_CONFIG["default_repo"])
BOARDS = _CONFIG.get("boards", _DEFAULT_CONFIG["boards"])
AI_MODEL = _CONFIG.get("ai_model", _DEFAULT_CONFIG["ai_model"])
