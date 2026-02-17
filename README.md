# Issue Manager CLI

> A fast, terminal-first GitHub issue manager with Projects V2 field support and a local markdown kanban board.

---

## Why this tool?

GitHub's web UI is great for one-off issue creation, but it falls short when you need to:

- **Set project fields during creation** — status, priority, size, iteration, epics — without clicking through multiple dropdowns after the fact.
- **Work from the terminal** — stay in your flow without context-switching to a browser.
- **Maintain a personal kanban board** — a local markdown file you own, not locked inside GitHub's UI.
- **Drag-and-drop cards** — with a lightweight web UI that syncs to that same markdown file.

This CLI bridges the gap between `gh issue create` (too basic) and the GitHub web UI (too clicky).

---

## Features

| Feature | Description |
|---------|-------------|
| **Guided issue creation** | Step-by-step wizard: repo → title → description → acceptance criteria → labels → project fields. Back/forward navigation throughout. |
| **Projects V2 field support** | Set status, priority, size, iteration, epic, team, and custom fields at creation time — not after. |
| **Quick mode** | Non-interactive CLI flags for scripting: `issue create --board main --title "..." --priority p1 --size m` |
| **Backlog browser** | List, search, filter, and edit existing issues from the terminal. |
| **Markdown kanban board** | A local `board.kanban.md` file using the VS Code Markdown Kanban format. Add, move, edit, archive cards from the CLI. |
| **Web kanban UI** | A drag-and-drop board served locally. Changes persist to the same markdown file. |
| **AI-assisted drafting** *(optional)* | If the Copilot SDK is available, describe what you want and let AI draft the issue. |

---

## Quick start

### 1. Install

```bash
# Clone or copy the issue/ folder into your project
pip install -e .            # optional: install as a package
pip install fastapi uvicorn # optional: for the web board
```

### 2. Authenticate

```bash
gh auth login
```

### 3. Configure

Create `.issue/config.json` (or `~/.issue/config.json`) with your GitHub org, repos, and project field IDs.  
See [config.example.json](config.example.json) for the full schema.

### 4. Run

```bash
# Interactive menu
python3 -m issue

# Quick create
python3 -m issue create --board main --title "Fix login bug" --priority p1

# Web kanban board
python3 -m issue board
```

---

## Requirements

- Python 3.10+
- `gh` CLI (authenticated)
- Node.js 18+ *(only if you want to rebuild the web board frontend)*

Optional:
- `fastapi` + `uvicorn` *(for the web board server)*
- Copilot SDK *(for AI-assisted issue drafting)*

---
 
## Configuration

The CLI loads config from the first path that exists:

1. `$ISSUE_CONFIG` environment variable
2. `<workspace>/.issue/config.json`
3. `~/.issue/config.json`

### Minimal config

```json
{
  "org": "your-org",
  "default_repo": "your-org/your-repo",
  "boards": {
    "main": {
      "number": 1,
      "name": "Main Board",
      "repo": "your-org/your-repo",
      "project_id": "PVT_xxx",
      "fields": {
        "status": {
          "id": "PVTSSF_xxx",
          "options": { "todo": "opt_a", "in progress": "opt_b", "done": "opt_c" }
        }
      }
    }
  }
}
```

Use [config.example.json](config.example.json) as your starting point.

---

## Web kanban board

The web UI is a lightweight Vite + TypeScript + SortableJS app.

### Build

```bash
cd web && npm install && npm run build
```

### Run

```bash
python3 -m issue board
# Opens http://localhost:3333
```

Features:
- Drag-and-drop cards between columns
- Click to edit title, due date, notes
- Due-date badges with overdue/soon/upcoming highlighting
- All changes persist to `board.kanban.md`

---

## CLI reference

| Command | Description |
|---------|-------------|
| `issue` | Interactive menu |
| `issue board` | Launch web kanban board |
| `issue create --help` | Quick-create flags reference |

---

## How it compares

| Tool | Issue creation | Project fields | Local kanban | Web UI |
|------|---------------|----------------|--------------|--------|
| `gh issue create` | ✓ basic | ✗ | ✗ | ✗ |
| GitHub web UI | ✓ | ✓ (manual) | ✗ | ✓ |
| **Issue Manager CLI** | ✓ guided | ✓ at creation | ✓ markdown | ✓ drag-drop |

---

## License

MIT
