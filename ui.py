"""
ui — Terminal UI primitives for the Issue Manager CLI.

Colours, prompts, pickers, multi-line input, and step runner.
"""

import sys

# ── Colour constants ─────────────────────────────────────────────────────

CYAN    = "\033[36m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
RESET   = "\033[0m"
CLEAR   = "\033[2J\033[H"

BACK = "__BACK__"
QUIT = "__QUIT__"


# ── Screen helpers ───────────────────────────────────────────────────────

def clear():
    print(CLEAR, end="")


def banner():
    print(f"""
{BOLD}{CYAN}  ┌──────────────────────────────────────────────┐
    │            📋  Issue Manager CLI              │
    │         GitHub Projects + Kanban Board         │
  └──────────────────────────────────────────────┘{RESET}
""")


def nav_hint(extra=""):
    parts = [f"{DIM}↩ enter = confirm", "b = back", f"q = quit{RESET}"]
    if extra:
        parts.insert(0, extra)
    print(f"  {' · '.join(parts)}\n")


# ── Input primitives ─────────────────────────────────────────────────────

def prompt(text, default=None):
    """Prompt for text input. Returns BACK on 'b', QUIT on 'q'."""
    suffix = f" {DIM}[{default}]{RESET}" if default else ""
    try:
        raw = input(f"  {CYAN}▸{RESET} {text}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return QUIT
    if raw.lower() == "q":
        return QUIT
    if raw.lower() == "b":
        return BACK
    return raw if raw else default


def pick_one(title, options, allow_skip=True):
    """
    Display numbered options. Returns the chosen key, or:
      - None if skipped
      - BACK / QUIT for navigation
    """
    keys = list(options.keys()) if isinstance(options, dict) else options
    print(f"  {BOLD}{title}{RESET}\n")
    for i, k in enumerate(keys, 1):
        print(f"    {CYAN}{i:>2}{RESET}  {k}")
    if allow_skip:
        print(f"    {DIM} 0  (skip){RESET}")
    print()
    nav_hint()

    while True:
        raw = prompt("Choose")
        if raw in (BACK, QUIT):
            return raw
        if raw is None and allow_skip:
            return None
        if raw == "0" and allow_skip:
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(keys):
                return keys[idx]
        except (ValueError, TypeError):
            if raw:
                lower = raw.lower()
                for k in keys:
                    if k.lower().startswith(lower):
                        return k
        print(f"    {DIM}Enter a number (1-{len(keys)}) or name prefix{RESET}")


def multiline(title, hint="blank line to finish"):
    """Multi-line input. First line 'b' = back, 'q' = quit."""
    print(f"  {BOLD}{title}{RESET}  {DIM}({hint}){RESET}\n")
    lines = []
    first = True
    while True:
        try:
            line = input(f"    {DIM}│{RESET} ")
        except (EOFError, KeyboardInterrupt):
            return QUIT
        if first:
            first = False
            if line.strip().lower() == "b":
                return BACK
            if line.strip().lower() == "q":
                return QUIT
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def criteria_input():
    """Collect acceptance criteria. First entry 'b' = back."""
    print(f"  {BOLD}Acceptance Criteria{RESET}  {DIM}(one per line, blank to finish){RESET}\n")
    items = []
    first = True
    while True:
        try:
            raw = input(f"    {DIM}☐{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            return QUIT
        if first:
            first = False
            if raw.lower() == "b":
                return BACK
            if raw.lower() == "q":
                return QUIT
        if raw == "":
            break
        items.append(raw)
    return items


def yn(text):
    """Yes/no confirmation. Returns True, False, BACK, or QUIT."""
    raw = prompt(f"{text} (y/n)", default="y")
    if raw in (BACK, QUIT):
        return raw
    return raw and raw.lower().startswith("y")


# ── Step runner ──────────────────────────────────────────────────────────

def run_steps(steps, state, *, show_progress=True, step_label="Step"):
    """
    Run a list of (name, func) tuples in sequence.
    Each func(state) must return True (advance), BACK, QUIT, or False (stay).
    The runner redraws the screen and shows progress before every step.
    Returns True if all steps completed, False if user quit.
    """
    idx = 0
    while 0 <= idx < len(steps):
        clear()
        banner()
        if show_progress:
            step_count = f"{DIM}{step_label} {idx + 1}/{len(steps)}{RESET}"
            bar = "█" * (idx + 1) + "░" * (len(steps) - idx - 1)
            print(f"  {step_count}  {CYAN}{bar}{RESET}\n")

        name, func = steps[idx]
        result = func(state)

        if result == QUIT:
            abandon = yn(f"{YELLOW}Abandon and return to menu?{RESET}")
            if abandon is True:
                return False
            continue  # redraw current step
        elif result == BACK:
            idx = max(0, idx - 1)
        elif result is True:
            idx += 1
        # False = stay on same step

    return True
