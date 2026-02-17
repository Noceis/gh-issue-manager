"""
kanban — Parse board.kanban.md and show a simple dashboard.

The file uses the VS Code Markdown Kanban extension format:
  ## Column Name       ← H2 headings = columns
  ### Card Title       ← H3 headings = cards
    - key: value       ← indented metadata (due, priority, defaultExpanded)
      ```md            ← fenced body block
      - bullet
      ```
"""

import datetime
import os
import re
import shutil

from .config import WORKSPACE
from .ui import (
    BOLD, CYAN, DIM, GREEN, YELLOW, RED, MAGENTA, RESET,
    BACK, QUIT,
    clear, banner, prompt, pick_one, yn, multiline,
)

KANBAN_PATH = os.path.join(WORKSPACE, "board.kanban.md")

# ═════════════════════════════════════════════════════════════════════════════
# DATA MODEL
# ═════════════════════════════════════════════════════════════════════════════

class Card:
    __slots__ = ("title", "meta", "body")

    def __init__(self, title, meta=None, body=None):
        self.title = title
        self.meta = meta or {}
        self.body = body or ""

    def __repr__(self):
        return f"Card({self.title!r})"


class Board:
    def __init__(self, columns=None):
        self.columns = columns or []  # [(name, [Card, ...]), ...]

    def column_names(self):
        return [name for name, _ in self.columns]

    def get_column(self, name):
        for col_name, cards in self.columns:
            if col_name.lower() == name.lower():
                return cards
        return None

    def column_counts(self):
        return [(name, len(cards)) for name, cards in self.columns]


# ═════════════════════════════════════════════════════════════════════════════
# PARSER
# ═════════════════════════════════════════════════════════════════════════════

def parse_board(path=None):
    """Parse board.kanban.md → Board object."""
    path = path or KANBAN_PATH
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    columns = []
    current_col = None
    current_cards = []
    current_card = None
    card_lines = []

    def _flush_card():
        nonlocal current_card, card_lines
        if current_card is not None:
            meta, body = _parse_card_block(card_lines)
            current_cards.append(Card(current_card, meta, body))
            current_card = None
            card_lines = []

    def _flush_column():
        nonlocal current_col, current_cards
        _flush_card()
        if current_col is not None:
            columns.append((current_col, current_cards))
            current_cards = []
            current_col = None

    for line in text.split("\n"):
        h2 = re.match(r"^## (.+)$", line)
        if h2:
            _flush_column()
            current_col = h2.group(1).strip()
            continue

        h3 = re.match(r"^### (.+)$", line)
        if h3:
            _flush_card()
            current_card = h3.group(1).strip()
            continue

        if current_card is not None:
            card_lines.append(line)

    _flush_column()
    return Board(columns)


def _parse_card_block(lines):
    """Extract metadata dict and body text from the indented lines under a card."""
    meta = {}
    body_lines = []
    in_fence = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        if in_fence:
            body_lines.append(stripped)
        else:
            m = re.match(r"^-\s+(\w[\w\s]*?):\s*(.+)$", stripped)
            if m:
                key = m.group(1).strip().lower()
                val = m.group(2).strip()
                meta[key] = val

    body = "\n".join(body_lines).strip()
    return meta, body


# ═════════════════════════════════════════════════════════════════════════════
# SERIALISER
# ═════════════════════════════════════════════════════════════════════════════

def write_board(board, path=None):
    """Serialise a Board object back to board.kanban.md format."""
    path = path or KANBAN_PATH
    lines = []
    for col_name, cards in board.columns:
        lines.append(f"## {col_name}")
        lines.append("")
        for card in cards:
            lines.append(f"### {card.title}")
            lines.append("")
            if card.meta or card.body:
                for key, value in card.meta.items():
                    lines.append(f"  - {key}: {value}")
                if card.body:
                    lines.append("    ```md")
                    for body_line in card.body.split("\n"):
                        lines.append(f"    {body_line}")
                    lines.append("    ```")
                lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ═════════════════════════════════════════════════════════════════════════════
# CARD OPERATIONS
# ═════════════════════════════════════════════════════════════════════════════

def _pick_card(board, exclude_columns=("Done",)):
    """Interactive card picker. Returns (col_name, card_idx, card) or BACK/QUIT/None."""
    options = []
    for col_name, cards in board.columns:
        if exclude_columns and col_name in exclude_columns:
            continue
        for i, card in enumerate(cards):
            options.append((col_name, i, card))

    if not options:
        print(f"    {DIM}No cards to choose from.{RESET}")
        prompt("Press enter to return")
        return None

    print(f"\n  {BOLD}Pick a card:{RESET}\n")
    for i, (col_name, _, card) in enumerate(options, 1):
        due = _parse_due(card)
        due_str = f"  {DIM}{due:%d/%m}{RESET}" if due else ""
        print(f"    {CYAN}{i:>2}{RESET}  {card.title}{due_str}  {DIM}[{col_name}]{RESET}")
    print()

    while True:
        raw = prompt("Card number")
        if raw in (BACK, QUIT):
            return raw
        if raw is None:
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except (ValueError, TypeError):
            pass
        print(f"    {DIM}Enter 1–{len(options)}{RESET}")


def add_card(board):
    """Interactively add a new card to the board."""
    clear()
    banner()
    col_names = board.column_names()
    col = pick_one("Add to which column?", col_names, allow_skip=False)
    if col in (BACK, QUIT):
        return

    title = prompt("Card title")
    if title in (BACK, QUIT, None):
        return

    due = prompt("Due date (YYYY-MM-DD, or skip)")
    if due in (BACK, QUIT):
        return

    body_text = multiline("Card body (optional)")
    if body_text == QUIT:
        return
    if body_text == BACK:
        body_text = ""

    meta = {}
    if due and due.lower() != "skip":
        meta["due"] = due
    if body_text:
        meta["defaultExpanded"] = "false"

    card = Card(title, meta, body_text)
    target = board.get_column(col)
    target.append(card)
    write_board(board)
    print(f"\n  {GREEN}✓ Added '{title}' to {col}{RESET}")
    prompt("Press enter to continue")


def move_card(board):
    """Interactively move a card between columns."""
    clear()
    banner()
    result = _pick_card(board, exclude_columns=None)
    if result in (BACK, QUIT, None):
        return

    from_col, card_idx, card = result
    other_cols = [n for n in board.column_names() if n != from_col]

    print(f"\n  Moving: {BOLD}{card.title}{RESET}  {DIM}(from {from_col}){RESET}\n")
    to_col = pick_one("Move to which column?", other_cols, allow_skip=False)
    if to_col in (BACK, QUIT):
        return

    board.get_column(from_col).pop(card_idx)
    board.get_column(to_col).append(card)
    write_board(board)
    print(f"\n  {GREEN}✓ Moved '{card.title}' → {to_col}{RESET}")
    prompt("Press enter to continue")


def edit_card(board):
    """Interactively edit a card's title, due date, or body."""
    clear()
    banner()
    result = _pick_card(board)
    if result in (BACK, QUIT, None):
        return

    _, _, card = result

    print(f"\n  Editing: {BOLD}{card.title}{RESET}\n")

    new_title = prompt("New title", default=card.title)
    if new_title == QUIT:
        return
    if new_title not in (BACK, None):
        card.title = new_title

    current_due = card.meta.get("due", "")
    new_due = prompt("Due date (YYYY-MM-DD, or 'none' to clear)", default=current_due or "none")
    if new_due == QUIT:
        return
    if new_due not in (BACK, None):
        if new_due.lower() == "none" and "due" in card.meta:
            del card.meta["due"]
        elif new_due.lower() != "none":
            card.meta["due"] = new_due

    if card.body:
        print(f"\n  {DIM}Current body:{RESET}")
        for line in card.body.split("\n"):
            print(f"    {DIM}{line}{RESET}")
        print()

    if yn("Edit body?") is True:
        new_body = multiline("New body")
        if new_body not in (BACK, QUIT):
            card.body = new_body
            if card.body and "defaultExpanded" not in card.meta:
                card.meta["defaultExpanded"] = "false"

    write_board(board)
    print(f"\n  {GREEN}✓ Card updated{RESET}")
    prompt("Press enter to continue")


def archive_card(board):
    """Move a card to the Done column."""
    clear()
    banner()
    done_cards = board.get_column("Done")
    if done_cards is None:
        print(f"  {RED}No 'Done' column found.{RESET}")
        prompt("Press enter to return")
        return

    result = _pick_card(board, exclude_columns=("Done",))
    if result in (BACK, QUIT, None):
        return

    from_col, card_idx, card = result

    if yn(f"Archive '{card.title}' → Done?") is True:
        board.get_column(from_col).pop(card_idx)
        done_cards.append(card)
        write_board(board)
        print(f"\n  {GREEN}✓ Archived '{card.title}'{RESET}")
    prompt("Press enter to continue")


def delete_card(board):
    """Permanently delete a card from the board."""
    clear()
    banner()
    result = _pick_card(board, exclude_columns=None)
    if result in (BACK, QUIT, None):
        return

    col_name, card_idx, card = result

    if yn(f"{RED}Delete '{card.title}' permanently?{RESET}") is True:
        board.get_column(col_name).pop(card_idx)
        write_board(board)
        print(f"\n  {GREEN}✓ Deleted{RESET}")
    prompt("Press enter to continue")


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

def kanban_menu():
    """Kanban dashboard with card management."""
    view = "dashboard"  # or "board"
    while True:
        board = parse_board()
        if view == "dashboard":
            _show_dashboard(board)
        else:
            _show_board(board)

        choice = prompt("Action")
        if choice in (BACK, QUIT):
            return
        if not choice:
            continue
        choice = choice.lower()
        if choice.startswith("v"):
            view = "board" if view == "dashboard" else "dashboard"
        elif choice.startswith("a"):
            add_card(board)
        elif choice.startswith("m"):
            move_card(board)
        elif choice.startswith("e"):
            edit_card(board)
        elif choice.startswith("d"):
            archive_card(board)
        elif choice.startswith("x"):
            delete_card(board)


def _show_dashboard(board):
    """Render the kanban dashboard: this week's focus, top todos, and action bar."""
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    clear()
    banner()
    print(f"  {BOLD}📋 Kanban Dashboard{RESET}  {DIM}week of {week_start:%d/%m} – {week_end:%d/%m/%Y}{RESET}\n")

    # ── Section 1: This Week ─────────────────────────────────────────────
    focus_items = []  # (card, column_name, tag, sort_date)

    for col_name, cards in board.columns:
        if col_name.lower() == "done":
            continue

        is_wip = col_name.lower() in ("in progress",)

        for card in cards:
            due = _parse_due(card)

            if is_wip:
                tag = f"{MAGENTA}in progress{RESET}"
                if due and due < today:
                    tag = f"{RED}in progress · {(today - due).days}d overdue{RESET}"
                focus_items.append((card, col_name, tag, due or datetime.date.max))
            elif due:
                if due < today:
                    tag = f"{RED}{(today - due).days}d overdue{RESET}"
                    focus_items.append((card, col_name, tag, due))
                elif due <= week_end:
                    delta = (due - today).days
                    if delta == 0:
                        tag = f"{YELLOW}due today{RESET}"
                    elif delta == 1:
                        tag = f"{YELLOW}due tomorrow{RESET}"
                    else:
                        tag = f"{GREEN}due {due:%a %d/%m}{RESET}"
                    focus_items.append((card, col_name, tag, due))

    focus_items.sort(key=lambda x: x[3])

    print(f"  {BOLD}{YELLOW}🔥 This Week{RESET}\n")
    if focus_items:
        for i, (card, col_name, tag, _) in enumerate(focus_items, 1):
            col_hint = f"  {DIM}[{col_name}]{RESET}" if col_name.lower() != "in progress" else ""
            print(f"    {CYAN}{i:>2}{RESET}  {card.title}  {tag}{col_hint}")
    else:
        print(f"    {GREEN}Nothing urgent this week! 🎉{RESET}")
    print()

    # ── Section 2: Top Todos ─────────────────────────────────────────────
    todo_cards = board.get_column("To Do") or []

    dated = []
    undated = []
    for card in todo_cards:
        due = _parse_due(card)
        if due:
            dated.append((card, due))
        else:
            undated.append(card)

    dated.sort(key=lambda x: x[1])
    top = [(c, d) for c, d in dated] + [(c, None) for c in undated]
    top = top[:15]

    print(f"  {BOLD}{CYAN}📋 Top Todos{RESET}  {DIM}({len(todo_cards)} total in backlog){RESET}\n")
    if top:
        for i, (card, due) in enumerate(top, 1):
            due_str = ""
            if due:
                delta = (due - today).days
                if delta < 0:
                    due_str = f"  {RED}⚠ {abs(delta)}d overdue{RESET}"
                elif delta == 0:
                    due_str = f"  {YELLOW}today{RESET}"
                elif delta <= 7:
                    due_str = f"  {YELLOW}{due:%a %d/%m}{RESET}"
                else:
                    due_str = f"  {DIM}{due:%d/%m}{RESET}"
            body_hint = f"  {DIM}📝{RESET}" if card.body else ""
            print(f"    {CYAN}{i:>2}{RESET}  {card.title}{due_str}{body_hint}")
    else:
        print(f"    {DIM}(backlog is empty){RESET}")
    print()

    # ── Board summary bar ────────────────────────────────────────────────
    counts = board.column_counts()
    summary = "  ·  ".join(f"{name}: {n}" for name, n in counts)
    print(f"  {DIM}{summary}{RESET}\n")

    # ── Action bar ────────────────────────────────────────────────────────
    print(f"  {BOLD}Actions:{RESET}  {CYAN}v{RESET}iew board · {CYAN}a{RESET}dd · {CYAN}m{RESET}ove · {CYAN}e{RESET}dit · {CYAN}d{RESET}one · {RED}x{RESET} delete · {DIM}↩ return{RESET}\n")


# ═════════════════════════════════════════════════════════════════════════════
# BOARD VIEW
# ═════════════════════════════════════════════════════════════════════════════

_COL_COLOURS = {
    "to do":            CYAN,
    "in progress":      MAGENTA,
    "review":           YELLOW,
    "done":             GREEN,
    "blocked/waiting":  RED,
}


def _show_board(board):
    """Render a column-based kanban board in the terminal."""
    today = datetime.date.today()
    term_width = shutil.get_terminal_size((120, 40)).columns

    # Filter columns — hide Done by default (too noisy)
    visible = [(n, c) for n, c in board.columns if n.lower() != "done"]
    if not visible:
        return

    clear()
    banner()

    n_cols = len(visible)
    gutter = 2                                    # space between columns
    left_margin = 2
    usable = term_width - left_margin - (gutter * (n_cols - 1))
    col_w = max(18, usable // n_cols)             # min 18 chars per column

    # ── Header row ────────────────────────────────────────────────────────
    headers = []
    dividers = []
    for col_name, cards in visible:
        colour = _COL_COLOURS.get(col_name.lower(), CYAN)
        label = f"{col_name} ({len(cards)})"
        if len(label) > col_w:
            label = label[:col_w - 1] + "…"
        headers.append(f"{colour}{BOLD}{label:<{col_w}}{RESET}")
        dividers.append(f"{DIM}{'─' * col_w}{RESET}")

    sep = " " * gutter
    print(f"{' ' * left_margin}{sep.join(headers)}")
    print(f"{' ' * left_margin}{sep.join(dividers)}")

    # ── Card rows ─────────────────────────────────────────────────────────
    max_rows = max(len(cards) for _, cards in visible)
    # Cap at a sensible height so the board doesn't scroll forever
    display_rows = min(max_rows, 30)

    for row in range(display_rows):
        cells = []
        for col_name, cards in visible:
            if row < len(cards):
                card = cards[row]
                colour = _COL_COLOURS.get(col_name.lower(), CYAN)
                cell = _format_board_card(card, col_w, today, colour)
            else:
                cell = " " * col_w
            cells.append(cell)
        print(f"{' ' * left_margin}{sep.join(cells)}")

    # ── Overflow indicator ────────────────────────────────────────────────
    overflow = []
    for col_name, cards in visible:
        extra = len(cards) - display_rows
        if extra > 0:
            overflow.append(f"{DIM}+{extra} more in {col_name}{RESET}")
    if overflow:
        print(f"\n{' ' * left_margin}{('  ·  ').join(overflow)}")
    print()

    # ── Action bar ────────────────────────────────────────────────────────
    print(f"  {BOLD}Actions:{RESET}  {CYAN}v{RESET}iew dashboard · {CYAN}a{RESET}dd · {CYAN}m{RESET}ove · {CYAN}e{RESET}dit · {CYAN}d{RESET}one · {RED}x{RESET} delete · {DIM}↩ return{RESET}\n")


def _format_board_card(card, width, today, colour):
    """Format a single card cell for the board view."""
    due = _parse_due(card)
    indicator = ""
    if due:
        delta = (due - today).days
        if delta < 0:
            indicator = f" {RED}⚠{RESET}"
        elif delta <= 2:
            indicator = f" {YELLOW}●{RESET}"
        elif delta <= 7:
            indicator = f" {GREEN}·{RESET}"

    # Reserve space for indicator (2 visible chars) + body hint (2 chars)
    body_hint = f" {DIM}📝{RESET}" if card.body else ""
    # Visible width budget for the title
    # indicator occupies ~2 visible chars, body_hint ~2
    reserved = (2 if indicator else 0) + (2 if card.body else 0)
    title_w = width - reserved

    title = card.title
    if len(title) > title_w:
        title = title[:title_w - 1] + "…"

    # Pad the visible portion to fill the column
    visible_len = len(title) + reserved
    padding = max(0, width - visible_len)

    return f"{colour}{title}{RESET}{indicator}{body_hint}{' ' * padding}"


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _parse_due(card):
    """Return a datetime.date for the card's due field, or None."""
    raw = card.meta.get("due")
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None
