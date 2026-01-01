#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FVP Interactive (TUI) — Final Version Perfected (dot‑chain) in a single curses app.

Quick facts
- One plain text file on disk (default: ~/.fvp.txt)
- Markers: [ ] live, [.] dotted, [x] crossed-out
- No deps, no DB, no sync; works offline

What it implements (FVP essentials)
- Root selection, pairwise "want more than benchmark?" scan
- Do the lowest dotted ("Do now")
- Stop early: cross out & re‑add at bottom
- Finishing root clears dots; next live item becomes new root

Strict Mode (default)
- App guides the loop: scan → focus → act → resume scan
- Scan is a two‑item comparison (only those two are shown)
- Focus shows only the current "Do now"; allowed actions: d/D/S
- Toggle Strict Mode with M (useful for free exploration)

Keymap (press ? inside the app for the full cheat sheet):
  ↑/k     Move up               a       Add task
  ↓/j     Move down             e       Edit task
  PgUp    Page up               d       Done (cross out)
  PgDn    Page down             D       Done & archive (remove from list)
  g       Jump to top           S       Stop early (cross out & re‑add at bottom)
  G       Jump to bottom        r       Reset dots & scanning state
  t       Jump to root          c       Clean (remove [x] lines)
  n       Jump to "Do now"      R       Reload from disk
  /       Filter (type to find) M       Toggle Strict Mode
  ?       Help                  q/ESC   Quit

File format (auto‑managed)
- First line:  # FVP_STATE last_did=<1-based index or -1>
- Then one task per line: [ ] text, [.] text, or [x] text
"""

import curses
import curses.textpad
import curses.ascii as ascii
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

DEFAULT_PATH = os.path.expanduser("~/.fvp.txt")
STATE_RE = re.compile(r"^#\s*FVP_STATE\s+last_did=(\-?\d+)\s*$")
TASK_RE = re.compile(r"^\s*\[(.?)\]\s*(.*\S)?\s*$")  # [ ], [.], [x]

@dataclass
class Task:
    text: str
    status: str  # "open" | "dotted" | "done"

# ----------------------------
# Storage (file I/O)
# ----------------------------

def read_file(path: str) -> Tuple[Optional[int], List[Task]]:
    """Load the FVP list file.

    Returns a tuple of:
      - last_did: 1-based index for the last acted task (None if not set)
      - tasks: list of Task objects parsed from the file

    Notes
    - Creates the file with a default header if it does not exist.
    - Accepts free-form lines; non-matching lines are treated as open tasks.
    """
    last_did = None
    tasks: List[Task] = []

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# FVP_STATE last_did=-1\n")
        return None, []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if lines and lines[0].startswith("# FVP_STATE"):
        m = STATE_RE.match(lines[0])
        if m:
            val = int(m.group(1))
            last_did = None if val < 1 else val
    else:
        lines.insert(0, "# FVP_STATE last_did=-1\n")

    for line in lines[1:]:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        m = TASK_RE.match(line)
        if not m:
            tasks.append(Task(text=line.strip(), status="open"))
            continue
        mark, text = m.group(1), (m.group(2) or "").strip()
        if mark in ("x", "X"):
            tasks.append(Task(text=text, status="done"))
        elif mark == ".":
            tasks.append(Task(text=text, status="dotted"))
        else:
            tasks.append(Task(text=text, status="open"))

    return last_did, tasks

def write_file(path: str, last_did: Optional[int], tasks: List[Task]) -> None:
    """Rewrite the file from in-memory state (header + tasks)."""
    with open(path, "w", encoding="utf-8") as f:
        header_val = last_did if (last_did and 1 <= last_did <= len(tasks)) else -1
        f.write(f"# FVP_STATE last_did={header_val}\n")
        for t in tasks:
            if t.status == "open":
                f.write(f"[ ] {t.text}\n")
            elif t.status == "dotted":
                f.write(f"[.] {t.text}\n")
            else:
                f.write(f"[x] {t.text}\n")

# ----------------------------
# FVP helpers
# ----------------------------

def first_live_index(tasks: List[Task]) -> Optional[int]:
    """Return the 1-based index of the first non-[x] (live) item, or None."""
    for i, t in enumerate(tasks, start=1):
        if t.status != "done":
            return i
    return None

def last_dotted_index(tasks: List[Task]) -> Optional[int]:
    """Return the 1-based index of the lowest dotted item, or None."""
    idx = None
    for i, t in enumerate(tasks, start=1):
        if t.status == "dotted":
            idx = i
    return idx

def previous_dotted_above(tasks: List[Task], index: int) -> Optional[int]:
    """Find the nearest dotted item strictly above a given index; else None."""
    for i in range(index - 1, 0, -1):
        if tasks[i - 1].status == "dotted":
            return i
    return None

def clear_all_dots(tasks: List[Task]) -> None:
    """Clear all dotted markers from the task list (set back to open)."""
    for t in tasks:
        if t.status == "dotted":
            t.status = "open"

def finish_effects_after_action(tasks: List[Task], acted_index: int) -> Tuple[Optional[int], bool]:
    """FVP bookkeeping after a task is acted on (done/stop).

    Effects
    - If there is no dotted item above the acted_index, we just completed the
      root: clear all dots and reset last_did (return None, True).
    - Otherwise, return (acted_index, False) so scanning can resume below it.
    """
    prev_dot = previous_dotted_above(tasks, acted_index)
    if prev_dot is None:
        clear_all_dots(tasks)
        return None, True
    return acted_index, False

# ----------------------------
# TUI utilities
# ----------------------------

HELP_TEXT = [
    "FVP Interactive — Keymap",
    "Movement:  ↑/k up   ↓/j down   PgUp/PgDn page   g top   G bottom   t root   n 'Do now'",
    "Actions:   a add    e edit     d done   D archive-done   S stop→bottom   r reset   c clean   h hide [x]   M strict",
    "Scanning:  s start/resume scan (y=yes, n=no, q/ESC stop)",
    "System:    R reload file       ? help    q quit",
    "",
    "Prompts: Enter submits, ESC cancels",
    "Strict mode (default): guided scan → focus; only d/D/S in focus. Toggle with 'M'.",
    "Markers: [ ] live    [.] dotted    [x] crossed-out",
    "Rule of thumb: dot in the scan only; 'done' crosses out; 'stop' crosses out & re-adds at bottom.",
]

class TUI:
    """Curses TUI for managing a single FVP text file.

    Structure
    - Storage: loads/saves plain text list with a header line.
    - Core logic: dot-chain helpers + FVP bookkeeping.
    - TUI: drawing, input prompts, scan flow, and Strict Mode gating.

    Strict Mode (default)
    - Drives a simple state machine: idle → scanning → focus.
    - Scanning compares two items at a time; Focus shows a single "Do now".
    - Only d/D/S are allowed during Focus to keep momentum.
    """
    def __init__(self, stdscr, path: str):
        self.stdscr = stdscr
        self.path = path
        self.last_did, self.tasks = read_file(self.path)
        self.archive_path = self.path + ".archive"
        self.cursor = 1  # 1-based index into tasks (even if done)
        self.scroll = 0
        self.filter_text = ""
        self.hide_done = False
        self.scan_highlight: Optional[Tuple[int, Optional[int]]] = None  # (candidate_idx, benchmark_idx)
        self.scan_only_two = False
        # Strict Mode (default): guided flow scan -> focus -> act
        self.strict_mode = True
        self.phase = 'idle'  # 'idle' | 'scanning' | 'focus'
        self.focus_idx: Optional[int] = None
        self.focus_only_one: bool = False
        self.status = "Press ? for help. s to scan; a to add; d to mark done; S to stop & re-add."
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.height, self.width = self.stdscr.getmaxyx()

        # Colors (optional): pick distinct colors for dotted, root,
        # and transient scan highlights (candidate/benchmark).
        self.has_colors = curses.has_colors()
        if self.has_colors:
            curses.start_color()
            try:
                curses.use_default_colors()
            except Exception:
                pass
            # 1: dotted (green), 2: root (yellow), 3: scan candidate (cyan), 4: scan benchmark (magenta)
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_MAGENTA, -1)
            self.COL_DOTTED = curses.color_pair(1)
            self.COL_ROOT = curses.color_pair(2)
            self.COL_CAND = curses.color_pair(3)
            self.COL_BENCH = curses.color_pair(4)
        else:
            self.COL_DOTTED = curses.A_STANDOUT
            self.COL_ROOT = curses.A_BOLD | curses.A_UNDERLINE
            self.COL_CAND = curses.A_UNDERLINE
            self.COL_BENCH = curses.A_BOLD

    # ---- rendering ----

    def draw(self):
        """Render header, subheader, task list (possibly filtered/reduced), and status line."""
        self.stdscr.erase()
        self.height, self.width = self.stdscr.getmaxyx()

        # Header
        header = f"FVP Interactive  —  File: {os.path.abspath(self.path)}"
        self.stdscr.addnstr(0, 0, header, self.width - 1, curses.A_BOLD)

        # Subheader with context flags
        flags = []
        root = first_live_index(self.tasks)
        if root is not None:
            flags.append(f"ROOT:{root}")
        if self.last_did:
            flags.append(f"JUST-DID:{self.last_did}")
            pd = previous_dotted_above(self.tasks, self.last_did)
            if pd:
                flags.append(f"BENCHMARK:{pd}")
        ld = last_dotted_index(self.tasks)
        if ld:
            flags.append(f"LOWEST-DOTTED:{ld}")
        if self.filter_text:
            flags.append(f"/{self.filter_text}")
        if self.hide_done:
            flags.append("HIDE-[x]")
        if self.strict_mode:
            flags.append("STRICT")
            flags.append(f"PHASE:{self.phase.upper()}")
        sub = "  ".join(flags) if flags else "No tasks yet — press 'a' to add."
        self.stdscr.addnstr(1, 0, sub, self.width - 1, curses.A_DIM)

        # Body
        top = 2
        body_h = self.height - top - 2  # leave space for status bar
        if body_h < 1:
            return

        # Determine which indices to render:
        #  - Focus-only (strict): just the "Do now" index
        #  - Scan-only: just the two compared items (in list order)
        #  - Otherwise: the full filtered list (optionally hiding [x])
        if self.focus_only_one and self.strict_mode and self.focus_idx:
            idx = max(1, min(len(self.tasks), self.focus_idx))
            indices = [idx]
        elif self.scan_only_two and self.scan_highlight:
            cand_idx = self.scan_highlight[0]
            bench_idx = self.scan_highlight[1]
            indices = []
            if bench_idx:
                if bench_idx < cand_idx:
                    indices = [bench_idx, cand_idx]
                elif cand_idx < bench_idx:
                    indices = [cand_idx, bench_idx]
                else:
                    indices = [cand_idx]
            else:
                indices = [cand_idx]
        else:
            indices = []
            f = self.filter_text.lower()
            for i in range(1, len(self.tasks) + 1):
                t = self.tasks[i - 1]
                if f in t.text.lower() and (not self.hide_done or t.status != "done"):
                    indices.append(i)

        # Ensure cursor is on a valid filtered index
        if indices:
            if self.cursor not in indices:
                # Move to closest visible
                self.cursor = indices[0]
        else:
            self.cursor = 1

        # Scroll management
        visible_idx_positions = {idx: pos for pos, idx in enumerate(indices)}
        cur_pos = visible_idx_positions.get(self.cursor, 0)
        if cur_pos < self.scroll:
            self.scroll = cur_pos
        elif cur_pos >= self.scroll + body_h:
            self.scroll = cur_pos - body_h + 1

        # Render lines
        for i in range(self.scroll, min(self.scroll + body_h, len(indices))):
            idx = indices[i]
            t = self.tasks[idx - 1]
            marker = "[ ]" if t.status == "open" else "[.]" if t.status == "dotted" else "[x]"
            left = f"{idx:>4}. {marker} "
            right = t.text
            # Ellipsis for long lines
            avail = max(0, self.width - 1 - len(left))
            if len(right) > avail:
                right_disp = (right[: max(avail - 1, 0)] + ("…" if avail > 0 else ""))
            else:
                right_disp = right
            line = left + right_disp
            y = top + (i - self.scroll)
            # Flags: decide style for this row
            attrs = curses.A_NORMAL
            # Choose exactly one color/highlight: scan candidate > scan bench > root > dotted
            root_idx = first_live_index(self.tasks)
            cand_idx = self.scan_highlight[0] if self.scan_highlight else None
            bench_idx = self.scan_highlight[1] if self.scan_highlight else None
            if cand_idx == idx:
                attrs |= self.COL_CAND
            elif bench_idx == idx:
                attrs |= self.COL_BENCH
            elif root_idx == idx:
                attrs |= self.COL_ROOT
            elif t.status == "dotted":
                attrs |= self.COL_DOTTED
            # Other visual modifiers
            if t.status == "done":
                attrs |= curses.A_DIM
            if idx == self.cursor:
                attrs |= curses.A_REVERSE
            self.stdscr.addnstr(y, 0, line, self.width - 1, attrs)

        # Status line
        self.stdscr.hline(self.height - 2, 0, curses.ACS_HLINE, self.width)
        self.stdscr.addnstr(self.height - 1, 0, self.status[: self.width - 1], self.width - 1)

        self.stdscr.refresh()

    # ---- input helpers ----

    def prompt(self, prompt: str, initial: str = "") -> Optional[str]:
        """Inline text input (Enter submits, ESC cancels).

        Notes
        - Normalizes Backspace/Delete across terminals.
        - Uses insert mode to make KEY_DC act as forward delete.
        """
        curses.curs_set(1)
        win = curses.newwin(3, self.width, self.height - 4, 0)
        win.erase()
        win.border()
        win.addnstr(0, 2, " Input (Enter submits, ESC cancels) ", self.width - 4, curses.A_DIM)
        win.addnstr(1, 2, (prompt + " ").ljust(self.width - 4), self.width - 4)
        edit = curses.newwin(1, self.width - 4 - len(prompt) - 1, self.height - 3, len(prompt) + 3)
        edit.keypad(True)
        tb = curses.textpad.Textbox(edit, insert_mode=True)
        edit.addstr(0, 0, initial)
        self.stdscr.refresh()

        cancelled = {"value": False}

        def validator(ch: int) -> int:
            # Enter -> submit
            if ch in (10, 13):
                return ascii.BEL
            # ESC -> cancel
            if ch == 27:
                cancelled["value"] = True
                return ascii.BEL
            # Normalize common delete/backspace keys across terminals
            if ch in (curses.KEY_BACKSPACE, 127, 8):  # 127=DEL/backspace on many, 8=BS
                return ascii.BS  # treat as Backspace (delete before cursor)
            if ch == curses.KEY_DC:  # forward delete
                return curses.KEY_DC
            return ch

        s = tb.edit(validator)
        curses.curs_set(0)
        if cancelled["value"]:
            return None
        s = (s or "").strip()
        if s == "":
            return None
        return s

    def confirm(self, prompt: str, default_no: bool = True) -> bool:
        """One-line Y/N prompt on the status bar (ESC = default)."""
        msg = f"{prompt} [{'y/N' if default_no else 'Y/n'}]: "
        curses.curs_set(1)
        self.stdscr.addnstr(self.height - 1, 0, msg.ljust(self.width - 1), self.width - 1)
        self.stdscr.refresh()
        ch = self.stdscr.getch()
        curses.curs_set(0)
        if default_no:
            return chr(ch).lower() in ("y",)
        return chr(ch).lower() not in ("n", "\x1b")  # ESC -> treat as 'no' if default yes

    def message(self, text: str):
        self.status = text

    def reload(self):
        """Reload tasks from disk (discarding in-memory edits)."""
        self.last_did, self.tasks = read_file(self.path)
        self.message("Reloaded from disk.")

    # ---- actions ----

    def move_cursor(self, delta: int):
        """Move the selection up/down by delta within the current (possibly reduced) view."""
        if not self.tasks:
            return
        self.cursor = max(1, min(len(self.tasks), self.cursor + delta))

    def jump_top(self):
        """Jump cursor to the top of the list."""
        if self.tasks:
            self.cursor = 1

    def jump_bottom(self):
        """Jump cursor to the bottom of the list."""
        if self.tasks:
            self.cursor = len(self.tasks)

    def jump_root(self):
        """Jump to the current root (first non-[x])."""
        ridx = first_live_index(self.tasks)
        if ridx:
            self.cursor = ridx
            self.message(f"Jumped to root: {ridx}.")

    def jump_do_now(self):
        """Jump to the lowest dotted or the benchmark, whichever is relevant."""
        if not self.tasks:
            return
        ld = last_dotted_index(self.tasks)
        if self.last_did:
            bench = previous_dotted_above(self.tasks, self.last_did)
            target = ld if (ld and (ld > (self.last_did))) else bench or ld
        else:
            target = ld
        if target:
            self.cursor = target
            self.message(f"'Do now' target: {target}.")
        else:
            self.message("No dotted target yet — press 's' to run a scan.")

    def add_task(self):
        """Append a new open task to the bottom (plain text)."""
        s = self.prompt("Add task:")
        if s is None or not s.strip():
            self.message("Add cancelled.")
            return
        self.tasks.append(Task(text=s.strip(), status="open"))
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = len(self.tasks)
        self.message(f"Added: {s.strip()}")

    def edit_task(self):
        """Edit the text of the current task in place."""
        if not self.tasks:
            return
        t = self.tasks[self.cursor - 1]
        s = self.prompt("Edit task:", t.text)
        if s is None:
            self.message("Edit cancelled.")
            return
        t.text = s.strip()
        write_file(self.path, self.last_did, self.tasks)
        self.message(f"Edited {self.cursor}.")

    def mark_done(self):
        """Cross out the current task ([x]). In strict mode, returns to scanning."""
        if not self.tasks:
            return
        idx = self.cursor
        self.tasks[idx - 1].status = "done"
        self.last_did, cleared = finish_effects_after_action(self.tasks, idx)
        write_file(self.path, self.last_did, self.tasks)
        self.message(f"Marked done: {idx}. {'(root finished → dots reset)' if cleared else ''}")
        if self.strict_mode:
            self.phase = 'idle'
            self.focus_idx = None
            self.focus_only_one = False

    def stop_and_readd(self):
        """Stop early: cross out & re-add the same text as a new open task at bottom."""
        if not self.tasks:
            return
        idx = self.cursor
        text = self.tasks[idx - 1].text
        self.tasks[idx - 1].status = "done"
        self.tasks.append(Task(text=text, status="open"))
        self.last_did, cleared = finish_effects_after_action(self.tasks, idx)
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = len(self.tasks)
        self.message(f"Stopped and re-added: {idx} → {len(self.tasks)}. {'(root finished → dots reset)' if cleared else ''}")
        if self.strict_mode:
            self.phase = 'idle'
            self.focus_idx = None
            self.focus_only_one = False

    def reset_dots(self):
        """Clear all dotted markers and the scanning state (last_did)."""
        clear_all_dots(self.tasks)
        self.last_did = None
        write_file(self.path, self.last_did, self.tasks)
        self.message("Cleared dots & scanning state.")
        if self.strict_mode:
            self.phase = 'idle'
            self.focus_idx = None
            self.focus_only_one = False

    def clean_done(self):
        """Remove all crossed-out lines from the file (with confirmation)."""
        if not self.tasks:
            return
        if not self.confirm("Remove all crossed-out [x] lines?"):
            self.message("Clean cancelled.")
            return
        self.tasks = [t for t in self.tasks if t.status != "done"]
        self.last_did = None
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = min(self.cursor, len(self.tasks)) if self.tasks else 1
        self.message("Removed crossed-out tasks. (Scanning state reset.)")
        if self.strict_mode:
            self.phase = 'idle'
            self.focus_idx = None
            self.focus_only_one = False

    def _append_to_archive(self, text: str) -> None:
        """Append a crossed-out line to the sidecar archive file (best-effort)."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.archive_path)), exist_ok=True)
            with open(self.archive_path, "a", encoding="utf-8") as f:
                f.write(f"[x] {text}\n")
        except Exception:
            # Non-fatal; ignore archive errors to not block flow
            pass

    def archive_done(self):
        """Mark done and remove from the active list, appending to the archive.

        In strict mode, returns to scanning to select the next focus.
        """
        if not self.tasks:
            return
        idx = self.cursor
        text = self.tasks[idx - 1].text
        # Mark done to compute finish effects correctly
        self.tasks[idx - 1].status = "done"
        new_last, cleared = finish_effects_after_action(self.tasks, idx)
        # Append to archive and remove from active list
        self._append_to_archive(text)
        del self.tasks[idx - 1]
        # Adjust last_did for resumed scanning position
        if new_last is None:
            self.last_did = None
        else:
            # Resume below the removed position: set to idx-1 (clamp to list)
            self.last_did = min(idx - 1, len(self.tasks)) if (idx - 1) >= 1 else None
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = min(idx, len(self.tasks)) if self.tasks else 1
        self.message(f"Archived and removed task. {'(root finished → dots reset)' if cleared else ''}")
        if self.strict_mode:
            self.phase = 'idle'
            self.focus_idx = None
            self.focus_only_one = False

    def filter_mode(self):
        """Set a substring filter for the list (disabled in strict mode)."""
        s = self.prompt("Filter (/…):", self.filter_text)
        if s is None:
            self.message("Filter cleared." if self.filter_text else "Filter cancelled.")
            self.filter_text = ""
            return
        self.filter_text = s
        self.message(f"Filter: /{self.filter_text}")

    def help_popup(self):
        """Centered help window with keymap and quick tips."""
        h, w = self.height, self.width
        win_h = min(len(HELP_TEXT) + 2, h - 2)
        win_w = min(max(len(line) for line in HELP_TEXT) + 4, w - 2)
        win = curses.newwin(win_h, win_w, (h - win_h)//2, (w - win_w)//2)
        win.border()
        for i, line in enumerate(HELP_TEXT[: win_h - 2], start=1):
            win.addnstr(i, 2, line, win_w - 4)
        win.addnstr(win_h - 1, 2, "Press any key…", win_w - 4, curses.A_DIM)
        win.refresh()
        win.getch()

    # ---- FVP scan (pairwise comparisons) ----

    def ensure_root_dotted(self) -> Optional[int]:
        """Ensure the root item is dotted at the start of a scan; return its index."""
        ridx = first_live_index(self.tasks)
        if ridx is None:
            return None
        if self.tasks[ridx - 1].status != "dotted":
            self.tasks[ridx - 1].status = "dotted"
        return ridx

    def scan(self) -> Optional[int]:
        """Run the dot-chain pass (fresh or resume) and return the "Do now" index.

        Behavior
        - Fresh pass: ensure root dotted, then compare sequential candidates to the current
          benchmark (the last dotted), asking y/n. Dots accumulate downward.
        - Resume pass: continue below last_did using the previous dotted benchmark.
        - Returns the lowest dotted index ("Do now") if any, else None.
        """
        if not self.tasks or first_live_index(self.tasks) is None:
            self.message("No live tasks to scan.")
            return None

        # If last_did is invalid (after manual edits), reset
        if self.last_did and (self.last_did < 1 or self.last_did > len(self.tasks)):
            self.last_did = None

        # Helper prompt inside scan on status bar
        def ask_compare(i_idx: int, bench_idx: int) -> Optional[bool]:
            # Highlight the two items in the main list
            self.scan_highlight = (i_idx, bench_idx)
            self.scan_only_two = True
            self.draw()
            # Modal popup for comparison
            cand_text = f"[{i_idx}] {self.tasks[i_idx - 1].text}"
            bench_text = f"[{bench_idx}] {self.tasks[bench_idx - 1].text}" if bench_idx else "(none)"

            # Determine window size
            max_w = self.width - 2
            title = "Scan Compare"
            prompt = "y = choose bottom, n = choose top, q/ESC = stop"

            def elide(s: str, limit: int) -> str:
                if len(s) <= limit:
                    return s
                return s[: max(limit - 1, 0)] + ("…" if limit > 0 else "")

            content_w = max(len(title), len(cand_text), len(bench_text), len(prompt)) + 4
            win_w = min(max(32, content_w), max_w)
            win_h = 6
            y0 = max(1, (self.height - win_h) // 2)
            x0 = max(1, (self.width - win_w) // 2)

            win = curses.newwin(win_h, win_w, y0, x0)
            win.border()
            win.addnstr(0, 2, f" {title} ", win_w - 4, curses.A_BOLD)
            # Show in list order: upper (benchmark) first, lower (candidate) second
            win.addnstr(1, 2, elide(bench_text, win_w - 4), win_w - 4)
            win.addnstr(2, 2, "vs.", win_w - 4, curses.A_DIM)
            win.addnstr(3, 2, elide(cand_text, win_w - 4), win_w - 4)
            win.addnstr(4, 2, elide(prompt, win_w - 4), win_w - 4, curses.A_DIM)
            win.refresh()

            ch = self.stdscr.getch()
            # Clear popup and highlight before acting
            try:
                win.clear()
                win.refresh()
            except Exception:
                pass
            self.scan_highlight = None
            self.scan_only_two = False
            self.draw()
            if ch in (ord('q'), 27):
                return None
            if chr(ch).lower() == 'y':
                return True
            if chr(ch).lower() == 'n':
                return False
            # Default to 'no' for other keys
            return False

        dotted_any = False

        if not self.last_did:
            # Fresh pass
            root_idx = self.ensure_root_dotted()
            if root_idx is None:
                self.message("No live tasks.")
                return None
            bench_idx = last_dotted_index(self.tasks) or root_idx
            start_from = bench_idx + 1
            i = start_from
            while i <= len(self.tasks):
                if self.tasks[i - 1].status != "done":
                    ans = ask_compare(i, last_dotted_index(self.tasks) or bench_idx)
                    if ans is None:
                        break
                    if ans:
                        self.tasks[i - 1].status = "dotted"
                        dotted_any = True
                i += 1

            write_file(self.path, self.last_did, self.tasks)
            target = last_dotted_index(self.tasks)
            if target:
                self.cursor = target
                self.message(f"→ Do this now: [{target}] {self.tasks[target-1].text}")
            else:
                self.message("No dotted items — try scan again.")
            return target

        # Resume below what was just done
        bench_idx = previous_dotted_above(self.tasks, self.last_did)
        if bench_idx is None:
            # Dots stale or root finished previously; reset safely
            clear_all_dots(self.tasks)
            self.last_did = None
            write_file(self.path, self.last_did, self.tasks)
            self.message("Dots were stale; reset. Start a fresh scan (press 's').")
            return None

        i = self.last_did + 1
        while i <= len(self.tasks):
            if self.tasks[i - 1].status != "done":
                ans = ask_compare(i, bench_idx)
                if ans is None:
                    break
                if ans:
                    self.tasks[i - 1].status = "dotted"
                    bench_idx = i
                    dotted_any = True
            i += 1

        write_file(self.path, self.last_did, self.tasks)
        target = last_dotted_index(self.tasks) if dotted_any else bench_idx
        if target:
            self.cursor = target
            self.message(f"→ Do this now: [{target}] {self.tasks[target-1].text}")
        else:
            self.message("No dotted candidate — benchmark missing; try a fresh scan.")
        return target

    # ---- main loop ----

    def run(self):
        """Main event loop. In Strict Mode, drives the idle → scanning → focus cycle."""
        while True:
            # Strict Mode automation and gating
            if self.strict_mode:
                # Enforce clean view in strict
                if self.filter_text:
                    self.filter_text = ""
                self.hide_done = True

                if self.phase in (None, 'idle'):
                    self.phase = 'scanning'
                    target = self.scan()
                    if target:
                        self.focus_idx = target
                        self.cursor = target
                        self.phase = 'focus'
                        self.focus_only_one = True
                    else:
                        self.focus_idx = None
                        self.focus_only_one = False
                        self.phase = 'idle'
                    # restart loop to render updated state
                    continue
                elif self.phase == 'focus':
                    self.focus_only_one = True
                else:
                    self.focus_only_one = False

            self.draw()
            ch = self.stdscr.getch()

            if ch in (ord('q'), 27):  # q or ESC
                break

            elif ch in (curses.KEY_UP, ord('k')):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.move_cursor(-1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.move_cursor(+1)
            elif ch == curses.KEY_PPAGE:
                if not (self.strict_mode and self.phase == 'focus'):
                    self.move_cursor(-(self.height - 5))
            elif ch == curses.KEY_NPAGE:
                if not (self.strict_mode and self.phase == 'focus'):
                    self.move_cursor(+(self.height - 5))
            elif ch == ord('g'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.jump_top()
            elif ch == ord('G'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.jump_bottom()
            elif ch == ord('t'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.jump_root()
            elif ch == ord('n'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.jump_do_now()

            elif ch == ord('a'):
                self.add_task()
            elif ch == ord('e'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.edit_task()
            elif ch == ord('d'):
                self.mark_done()
            elif ch == ord('D'):
                self.archive_done()
            elif ch == ord('S'):
                self.stop_and_readd()

            elif ch == ord('s'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.scan()
            elif ch == ord('r'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.reset_dots()
            elif ch == ord('c'):
                if not (self.strict_mode and self.phase == 'focus'):
                    self.clean_done()
            elif ch == ord('R'):
                self.reload()
            elif ch == ord('/'):
                if not self.strict_mode:
                    self.filter_mode()
            elif ch == ord('h'):
                if not self.strict_mode:
                    self.hide_done = not self.hide_done
                    self.message("Hide crossed-out ON." if self.hide_done else "Hide crossed-out OFF.")
            elif ch == ord('M'):
                # Toggle strict mode
                self.strict_mode = not self.strict_mode
                if self.strict_mode:
                    self.phase = 'idle'
                    self.focus_idx = None
                    self.focus_only_one = False
                    self.hide_done = True
                    self.filter_text = ""
                    self.message("Strict mode ON. Guided flow enabled.")
                else:
                    self.phase = 'idle'
                    self.focus_idx = None
                    self.focus_only_one = False
                    self.message("Strict mode OFF. Free navigation.")
            elif ch == ord('?'):
                self.help_popup()
            else:
                # ignore unknown keys; keep current status
                pass

def start_curses(path: str):
    def _main(stdscr):
        tui = TUI(stdscr, path)
        tui.run()
    curses.wrapper(_main)

# ----------------------------
# Entry point
# ----------------------------

def main():
    path = DEFAULT_PATH
    if len(sys.argv) > 1:
        # Allow: fvp_tui.py <path>   OR   fvp_tui.py -f <path>
        if sys.argv[1] in ("-f", "--file") and len(sys.argv) >= 3:
            path = sys.argv[2]
        else:
            path = sys.argv[1]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    # Ensure file exists
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# FVP_STATE last_did=-1\n")
    start_curses(path)

if __name__ == "__main__":
    main()
