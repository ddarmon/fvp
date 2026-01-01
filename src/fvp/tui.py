"""FVP curses-based terminal user interface."""

import curses
import curses.textpad
import curses.ascii as ascii
import os
from typing import List, Optional, Tuple

from .models import Task, DEFAULT_DIR, DEFAULT_LIST, list_path
from .storage import (
    read_file,
    write_file,
    append_to_archive,
    ensure_file_exists,
    ensure_dir_exists,
    get_available_lists,
)
from .core import (
    first_live_index,
    last_dotted_index,
    previous_dotted_above,
    clear_all_dots,
    finish_effects_after_action,
    ensure_root_dotted,
)

HELP_TEXT = [
    "FVP Interactive - Keymap",
    "Movement:  up/k up   down/j down   PgUp/PgDn page   g top   G bottom   t root   n 'Do now'",
    "Actions:   a add    e edit     d done   D archive-done   S stop->bottom   r reset   c clean   h hide [x]   M strict",
    "Scanning:  s start/resume scan (up/k=top, down/j=bottom, q/ESC stop)",
    "System:    R reload file       ? help    q quit",
    "",
    "Prompts: Enter submits, ESC cancels",
    "Strict mode (default): guided scan -> focus; only d/D/S in focus. Toggle with 'M'.",
    "Markers: [ ] live    [.] dotted    [x] crossed-out",
    "Rule of thumb: dot in the scan only; 'done' crosses out; 'stop' crosses out & re-adds at bottom.",
]


def pick_list(stdscr) -> Optional[str]:
    """Curses-based list picker. Returns list name or None if cancelled."""
    curses.curs_set(0)
    stdscr.keypad(True)

    lists = get_available_lists()
    if not lists:
        # No lists exist - return default to create it
        return DEFAULT_LIST

    if len(lists) == 1:
        # Only one list - use it directly
        return lists[0]

    # Multiple lists - show picker
    cursor = 0
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()

        # Header
        header = "Select a task list"
        stdscr.addnstr(0, 0, header, width - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, f"Lists in {DEFAULT_DIR}/", width - 1, curses.A_DIM)

        # List items
        top = 3
        body_h = height - top - 2
        scroll = max(0, cursor - body_h + 1)

        for i, name in enumerate(lists[scroll : scroll + body_h]):
            idx = scroll + i
            path = list_path(name)
            try:
                _, tasks = read_file(path)
                live = sum(1 for t in tasks if t.status != "done")
                info = f"{live} live"
            except Exception:
                info = "?"

            line = f"  {name:20} ({info})"
            y = top + i
            attrs = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
            stdscr.addnstr(y, 0, line, width - 1, attrs)

        # Status
        stdscr.hline(height - 2, 0, curses.ACS_HLINE, width)
        status = "up/down: select | Enter: open | n: new list | q/ESC: quit"
        stdscr.addnstr(height - 1, 0, status, width - 1)

        stdscr.refresh()
        ch = stdscr.getch()

        if ch in (ord("q"), 27):
            return None
        elif ch in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            cursor = min(len(lists) - 1, cursor + 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            return lists[cursor]
        elif ch == ord("n"):
            # Create new list
            name = prompt_new_list_name(stdscr)
            if name:
                return name


def prompt_new_list_name(stdscr) -> Optional[str]:
    """Prompt for a new list name."""
    curses.curs_set(1)
    height, width = stdscr.getmaxyx()

    win = curses.newwin(3, min(50, width - 4), height // 2 - 1, max(2, (width - 50) // 2))
    win.erase()
    win.border()
    win.addnstr(0, 2, " New list name ", 15, curses.A_BOLD)
    win.addnstr(1, 2, "Name: ", 6)
    win.refresh()

    edit = curses.newwin(1, min(40, width - 12), height // 2, max(2, (width - 50) // 2) + 8)
    edit.keypad(True)
    tb = curses.textpad.Textbox(edit, insert_mode=True)

    cancelled = {"value": False}

    def validator(ch: int) -> int:
        if ch in (10, 13):
            return ascii.BEL
        if ch == 27:
            cancelled["value"] = True
            return ascii.BEL
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            return ascii.BS
        return ch

    s = tb.edit(validator)
    curses.curs_set(0)

    if cancelled["value"]:
        return None

    s = (s or "").strip()
    # Sanitize: only allow alphanumeric, dash, underscore
    s = "".join(c for c in s if c.isalnum() or c in "-_")
    return s if s else None


class TUI:
    """Curses TUI for managing a single FVP text file."""

    def __init__(self, stdscr, path: str, list_name: Optional[str] = None):
        self.stdscr = stdscr
        self.path = path
        self.list_name = list_name  # For display in header
        self.last_did, self.tasks = read_file(self.path)
        self.archive_path = self.path + ".archive"
        self.cursor = 1
        self.scroll = 0
        self.filter_text = ""
        self.hide_done = False
        self.scan_highlight: Optional[Tuple[int, Optional[int]]] = None
        self.scan_only_two = False
        self.strict_mode = True
        self.phase = "idle"
        self.focus_idx: Optional[int] = None
        self.focus_only_one: bool = False
        self.status = "Press ? for help. s to scan; a to add; d to mark done; S to stop & re-add."
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.height, self.width = self.stdscr.getmaxyx()

        self.has_colors = curses.has_colors()
        if self.has_colors:
            curses.start_color()
            try:
                curses.use_default_colors()
            except Exception:
                pass
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

    def draw(self):
        """Render header, subheader, task list, and status line."""
        self.stdscr.erase()
        self.height, self.width = self.stdscr.getmaxyx()
        self.update_status_for_phase()

        header = f"FVP: {self.list_name}" if self.list_name else "FVP"
        self.stdscr.addnstr(0, 0, header, self.width - 1, curses.A_BOLD)

        # Subheader: minimal in strict mode, detailed in free mode
        if self.strict_mode:
            if self.phase == "focus":
                sub = ">>> WORK ON THIS <<<"
            elif not self.tasks or first_live_index(self.tasks) is None:
                sub = "No tasks. Press 'a' to add."
            else:
                sub = ""
        else:
            # Free mode: show technical details for debugging
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
            sub = "  ".join(flags) if flags else "No tasks yet - press 'a' to add."
        self.stdscr.addnstr(1, 0, sub, self.width - 1, curses.A_DIM)

        top = 2
        body_h = self.height - top - 2
        if body_h < 1:
            return

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

        if indices:
            if self.cursor not in indices:
                self.cursor = indices[0]
        else:
            self.cursor = 1

        visible_idx_positions = {idx: pos for pos, idx in enumerate(indices)}
        cur_pos = visible_idx_positions.get(self.cursor, 0)
        if cur_pos < self.scroll:
            self.scroll = cur_pos
        elif cur_pos >= self.scroll + body_h:
            self.scroll = cur_pos - body_h + 1

        # Focus mode in strict: show just the task text centered
        if self.focus_only_one and self.strict_mode and self.focus_idx and indices:
            t = self.tasks[self.focus_idx - 1]
            # Center the task text
            task_text = t.text
            if len(task_text) > self.width - 4:
                task_text = task_text[: self.width - 7] + "..."
            y = top + (body_h // 3)  # Position task in upper third
            self.stdscr.addnstr(y, 0, task_text.center(self.width), self.width - 1, curses.A_BOLD)
        else:
            # Normal rendering with markers and indices
            for i in range(self.scroll, min(self.scroll + body_h, len(indices))):
                idx = indices[i]
                t = self.tasks[idx - 1]
                marker = "[ ]" if t.status == "open" else "[.]" if t.status == "dotted" else "[x]"
                left = f"{idx:>4}. {marker} "
                right = t.text
                avail = max(0, self.width - 1 - len(left))
                if len(right) > avail:
                    right_disp = right[: max(avail - 1, 0)] + ("..." if avail > 0 else "")
                else:
                    right_disp = right
                line = left + right_disp
                y = top + (i - self.scroll)
                attrs = curses.A_NORMAL
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
                if t.status == "done":
                    attrs |= curses.A_DIM
                if idx == self.cursor:
                    attrs |= curses.A_REVERSE
                self.stdscr.addnstr(y, 0, line, self.width - 1, attrs)

        self.stdscr.hline(self.height - 2, 0, curses.ACS_HLINE, self.width)
        self.stdscr.addnstr(self.height - 1, 0, self.status[: self.width - 1], self.width - 1)

        self.stdscr.refresh()

    def prompt(self, prompt: str, initial: str = "") -> Optional[str]:
        """Inline text input (Enter submits, ESC cancels)."""
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
            if ch in (10, 13):
                return ascii.BEL
            if ch == 27:
                cancelled["value"] = True
                return ascii.BEL
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                return ascii.BS
            if ch == curses.KEY_DC:
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
        """One-line Y/N prompt on the status bar."""
        msg = f"{prompt} [{'y/N' if default_no else 'Y/n'}]: "
        curses.curs_set(1)
        self.stdscr.addnstr(self.height - 1, 0, msg.ljust(self.width - 1), self.width - 1)
        self.stdscr.refresh()
        ch = self.stdscr.getch()
        curses.curs_set(0)
        if default_no:
            return chr(ch).lower() in ("y",)
        return chr(ch).lower() not in ("n", "\x1b")

    def message(self, text: str):
        self.status = text

    def update_status_for_phase(self):
        """Set status bar message based on current phase."""
        if not self.tasks or first_live_index(self.tasks) is None:
            self.status = "No tasks. Press 'a' to add a task."
            return

        if self.strict_mode and self.phase == "focus" and self.focus_idx:
            task_text = self.tasks[self.focus_idx - 1].text
            # Truncate task text to fit
            max_task_len = max(20, self.width - 45)
            if len(task_text) > max_task_len:
                task_text = task_text[: max_task_len - 3] + "..."
            self.status = f"DO NOW: {task_text} | d=done D=archive S=stop"
        elif self.strict_mode and self.phase == "waiting":
            self.status = "'s' scan | 'a' add | '?' help | 'q' quit"
        elif self.strict_mode:
            self.status = "'s' scan | 'a' add | '?' help | 'q' quit"
        else:
            self.status = "'s' scan | 'a' add | 'd' done | 'S' stop | '?' help"

    def reload(self):
        """Reload tasks from disk."""
        self.last_did, self.tasks = read_file(self.path)
        self.message("Reloaded from disk.")

    def move_cursor(self, delta: int):
        if not self.tasks:
            return
        self.cursor = max(1, min(len(self.tasks), self.cursor + delta))

    def jump_top(self):
        if self.tasks:
            self.cursor = 1

    def jump_bottom(self):
        if self.tasks:
            self.cursor = len(self.tasks)

    def jump_root(self):
        ridx = first_live_index(self.tasks)
        if ridx:
            self.cursor = ridx
            self.message(f"Jumped to root: {ridx}.")

    def jump_do_now(self):
        if not self.tasks:
            return
        ld = last_dotted_index(self.tasks)
        if self.last_did:
            bench = previous_dotted_above(self.tasks, self.last_did)
            target = ld if (ld and (ld > self.last_did)) else bench or ld
        else:
            target = ld
        if target:
            self.cursor = target
            self.message(f"'Do now' target: {target}.")
        else:
            self.message("No dotted target yet - press 's' to run a scan.")

    def add_task(self):
        s = self.prompt("Add task:")
        if s is None or not s.strip():
            self.message("Add cancelled.")
            return
        self.tasks.append(Task(text=s.strip(), status="open"))
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = len(self.tasks)
        self.message(f"Added: {s.strip()}")

    def edit_task(self):
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
        if not self.tasks:
            return
        idx = self.cursor
        self.tasks[idx - 1].status = "done"
        self.last_did, cleared = finish_effects_after_action(self.tasks, idx)
        write_file(self.path, self.last_did, self.tasks)
        self.message(f"Marked done: {idx}. {'(root finished -> dots reset)' if cleared else ''}")
        if self.strict_mode:
            self.phase = "idle"
            self.focus_idx = None
            self.focus_only_one = False

    def stop_and_readd(self):
        if not self.tasks:
            return
        idx = self.cursor
        text = self.tasks[idx - 1].text
        self.tasks[idx - 1].status = "done"
        self.tasks.append(Task(text=text, status="open"))
        self.last_did, cleared = finish_effects_after_action(self.tasks, idx)
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = len(self.tasks)
        self.message(
            f"Stopped and re-added: {idx} -> {len(self.tasks)}. "
            f"{'(root finished -> dots reset)' if cleared else ''}"
        )
        if self.strict_mode:
            self.phase = "idle"
            self.focus_idx = None
            self.focus_only_one = False

    def reset_dots(self):
        clear_all_dots(self.tasks)
        self.last_did = None
        write_file(self.path, self.last_did, self.tasks)
        self.message("Cleared dots & scanning state.")
        if self.strict_mode:
            self.phase = "idle"
            self.focus_idx = None
            self.focus_only_one = False

    def clean_done(self):
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
            self.phase = "idle"
            self.focus_idx = None
            self.focus_only_one = False

    def archive_done(self):
        if not self.tasks:
            return
        idx = self.cursor
        text = self.tasks[idx - 1].text
        self.tasks[idx - 1].status = "done"
        new_last, cleared = finish_effects_after_action(self.tasks, idx)
        append_to_archive(self.archive_path, text)
        del self.tasks[idx - 1]
        if new_last is None:
            self.last_did = None
        else:
            self.last_did = min(idx - 1, len(self.tasks)) if (idx - 1) >= 1 else None
        write_file(self.path, self.last_did, self.tasks)
        self.cursor = min(idx, len(self.tasks)) if self.tasks else 1
        self.message(f"Archived and removed task. {'(root finished -> dots reset)' if cleared else ''}")
        if self.strict_mode:
            self.phase = "idle"
            self.focus_idx = None
            self.focus_only_one = False

    def filter_mode(self):
        s = self.prompt("Filter (/...):", self.filter_text)
        if s is None:
            self.message("Filter cleared." if self.filter_text else "Filter cancelled.")
            self.filter_text = ""
            return
        self.filter_text = s
        self.message(f"Filter: /{self.filter_text}")

    def help_popup(self):
        h, w = self.height, self.width
        win_h = min(len(HELP_TEXT) + 2, h - 2)
        win_w = min(max(len(line) for line in HELP_TEXT) + 4, w - 2)
        win = curses.newwin(win_h, win_w, (h - win_h) // 2, (w - win_w) // 2)
        win.border()
        for i, line in enumerate(HELP_TEXT[: win_h - 2], start=1):
            win.addnstr(i, 2, line, win_w - 4)
        win.addnstr(win_h - 1, 2, "Press any key...", win_w - 4, curses.A_DIM)
        win.refresh()
        win.getch()

    def scan(self) -> Optional[int]:
        """Run the dot-chain pass and return the 'Do now' index."""
        if not self.tasks or first_live_index(self.tasks) is None:
            self.message("No live tasks to scan.")
            return None

        if self.last_did and (self.last_did < 1 or self.last_did > len(self.tasks)):
            self.last_did = None

        def ask_compare(i_idx: int, bench_idx: int) -> Optional[bool]:
            self.scan_highlight = (i_idx, bench_idx)
            self.scan_only_two = True
            self.draw()
            cand_text = self.tasks[i_idx - 1].text
            bench_text = self.tasks[bench_idx - 1].text if bench_idx else "(none)"

            max_w = self.width - 2
            title = "Scan Compare"
            prompt_text = "up/k = top, down/j = bottom, q/ESC = stop"

            def elide(s: str, limit: int) -> str:
                if len(s) <= limit:
                    return s
                return s[: max(limit - 1, 0)] + ("..." if limit > 0 else "")

            content_w = max(len(title), len(cand_text), len(bench_text), len(prompt_text)) + 4
            win_w = min(max(32, content_w), max_w)
            win_h = 6
            y0 = max(1, (self.height - win_h) // 2)
            x0 = max(1, (self.width - win_w) // 2)

            win = curses.newwin(win_h, win_w, y0, x0)
            win.border()
            win.addnstr(0, 2, f" {title} ", win_w - 4, curses.A_BOLD)
            win.addnstr(1, 2, elide(bench_text, win_w - 4), win_w - 4)
            win.addnstr(2, 2, "vs.", win_w - 4, curses.A_DIM)
            win.addnstr(3, 2, elide(cand_text, win_w - 4), win_w - 4)
            win.addnstr(4, 2, elide(prompt_text, win_w - 4), win_w - 4, curses.A_DIM)
            win.refresh()

            ch = self.stdscr.getch()
            try:
                win.clear()
                win.refresh()
            except Exception:
                pass
            self.scan_highlight = None
            self.scan_only_two = False
            self.draw()
            if ch in (ord("q"), 27):
                return None
            # down/j = choose bottom (candidate) = True
            if ch in (curses.KEY_DOWN, ord("j")):
                return True
            # up/k = choose top (benchmark) = False
            if ch in (curses.KEY_UP, ord("k")):
                return False
            return False

        dotted_any = False
        cancelled = False

        if not self.last_did:
            root_idx = ensure_root_dotted(self.tasks)
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
                        cancelled = True
                        break
                    if ans:
                        self.tasks[i - 1].status = "dotted"
                        dotted_any = True
                i += 1

            write_file(self.path, self.last_did, self.tasks)
            if cancelled:
                self.message("Scan stopped. Press 's' to resume, 'q' to quit.")
                return None
            target = last_dotted_index(self.tasks)
            if target:
                self.cursor = target
                self.message(f"-> Do this now: [{target}] {self.tasks[target - 1].text}")
            else:
                self.message("No dotted items - try scan again.")
            return target

        bench_idx = previous_dotted_above(self.tasks, self.last_did)
        if bench_idx is None:
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
                    cancelled = True
                    break
                if ans:
                    self.tasks[i - 1].status = "dotted"
                    bench_idx = i
                    dotted_any = True
            i += 1

        write_file(self.path, self.last_did, self.tasks)
        if cancelled:
            self.message("Scan stopped. Press 's' to resume, 'q' to quit.")
            return None
        target = last_dotted_index(self.tasks) if dotted_any else bench_idx
        if target:
            self.cursor = target
            self.message(f"-> Do this now: [{target}] {self.tasks[target - 1].text}")
        else:
            self.message("No dotted candidate - benchmark missing; try a fresh scan.")
        return target

    def run(self):
        """Main event loop."""
        while True:
            if self.strict_mode:
                if self.filter_text:
                    self.filter_text = ""
                self.hide_done = True

                if self.phase in (None, "idle"):
                    self.phase = "scanning"
                    target = self.scan()
                    if target:
                        self.focus_idx = target
                        self.cursor = target
                        self.phase = "focus"
                        self.focus_only_one = True
                        continue  # Only continue when entering focus
                    else:
                        self.focus_idx = None
                        self.focus_only_one = False
                        self.phase = "waiting"  # Don't auto-restart scan
                    # Fall through to draw/getch so user can interact
                elif self.phase == "focus":
                    self.focus_only_one = True
                else:
                    self.focus_only_one = False

            self.draw()
            ch = self.stdscr.getch()

            if ch in (ord("q"), 27):
                break

            elif ch in (curses.KEY_UP, ord("k")):
                if not (self.strict_mode and self.phase == "focus"):
                    self.move_cursor(-1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                if not (self.strict_mode and self.phase == "focus"):
                    self.move_cursor(+1)
            elif ch == curses.KEY_PPAGE:
                if not (self.strict_mode and self.phase == "focus"):
                    self.move_cursor(-(self.height - 5))
            elif ch == curses.KEY_NPAGE:
                if not (self.strict_mode and self.phase == "focus"):
                    self.move_cursor(+(self.height - 5))
            elif ch == ord("g"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.jump_top()
            elif ch == ord("G"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.jump_bottom()
            elif ch == ord("t"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.jump_root()
            elif ch == ord("n"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.jump_do_now()

            elif ch == ord("a"):
                self.add_task()
            elif ch == ord("e"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.edit_task()
            elif ch == ord("d"):
                self.mark_done()
            elif ch == ord("D"):
                self.archive_done()
            elif ch == ord("S"):
                self.stop_and_readd()

            elif ch == ord("s"):
                if not (self.strict_mode and self.phase == "focus"):
                    if self.strict_mode:
                        self.phase = "idle"  # Trigger auto-scan on next iteration
                    else:
                        self.scan()
            elif ch == ord("r"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.reset_dots()
            elif ch == ord("c"):
                if not (self.strict_mode and self.phase == "focus"):
                    self.clean_done()
            elif ch == ord("R"):
                self.reload()
            elif ch == ord("/"):
                if not self.strict_mode:
                    self.filter_mode()
            elif ch == ord("h"):
                if not self.strict_mode:
                    self.hide_done = not self.hide_done
                    self.message("Hide crossed-out ON." if self.hide_done else "Hide crossed-out OFF.")
            elif ch == ord("M"):
                self.strict_mode = not self.strict_mode
                if self.strict_mode:
                    self.phase = "idle"
                    self.focus_idx = None
                    self.focus_only_one = False
                    self.hide_done = True
                    self.filter_text = ""
                    self.message("Strict mode ON. Guided flow enabled.")
                else:
                    self.phase = "idle"
                    self.focus_idx = None
                    self.focus_only_one = False
                    self.message("Strict mode OFF. Free navigation.")
            elif ch == ord("?"):
                self.help_popup()


def start_curses(path: str, list_name: Optional[str] = None):
    """Initialize curses and run TUI."""

    def _main(stdscr):
        tui = TUI(stdscr, path, list_name)
        tui.run()

    curses.wrapper(_main)


def start_with_picker():
    """Start curses with list picker, then run TUI."""

    def _main(stdscr):
        list_name = pick_list(stdscr)
        if list_name is None:
            # User cancelled
            return
        path = list_path(list_name)
        ensure_file_exists(path)
        tui = TUI(stdscr, path, list_name)
        tui.run()

    curses.wrapper(_main)


def main(path: Optional[str] = None) -> None:
    """TUI entry point."""
    ensure_dir_exists()

    if path is None:
        # No explicit path - show picker (or use default if only one/no lists)
        start_with_picker()
    else:
        # Explicit path given - extract list name if it's in ~/.fvp/
        list_name = None
        if path.startswith(DEFAULT_DIR) and path.endswith(".fvp"):
            # Extract list name from path
            basename = os.path.basename(path)
            list_name = basename[:-4]  # strip .fvp
        ensure_file_exists(path)
        start_curses(path, list_name)


if __name__ == "__main__":
    main()
