#!/usr/bin/env python3
"""
FVP (Final Version Perfected) CLI — "dot chain" method
- One plain text file on disk (default: ~/.fvp.txt)
- Markers: [ ] live, [.] dotted, [x] crossed-out
- Faithfully implements the 8 rules + key edge cases.

Commands:
  list              Show tasks (default hides [x])
  add "text"        Append a new live task
  next              Interactive scan to dot and recommend the next task
  done INDEX        Cross out the task at INDEX (you finished it)
  stop INDEX        You stopped early: cross out old entry and re-add at bottom
  bump INDEX        Alias of stop (useful for “root impossible now”)
  edit INDEX "txt"  Edit task text in place
  reset             Wipe all dots and scanning state
  clean             Remove all crossed-out lines ([x]) from the file
  path              Print the path to the tasks file

INDEX numbers are exactly what `list` shows (1-based, counting every task line).
"""

import argparse
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

def read_file(path: str) -> Tuple[Optional[int], List[Task]]:
    """
    Returns (last_did_index or None, tasks)
    - last_did_index is 1-based index into tasks list referring to the task you just did (now [x]),
      or None if not set.
    """
    last_did = None
    tasks: List[Task] = []

    if not os.path.exists(path):
        # Create an empty file with a state header.
        with open(path, "w", encoding="utf-8") as f:
            f.write("# FVP_STATE last_did=-1\n")
        return None, []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Parse first non-empty line for state
    if lines and lines[0].startswith("# FVP_STATE"):
        m = STATE_RE.match(lines[0])
        if m:
            val = int(m.group(1))
            last_did = None if val < 1 else val
        else:
            # malformed header: reset it
            last_did = None
    else:
        # insert header if missing
        lines.insert(0, "# FVP_STATE last_did=-1\n")

    # Parse tasks
    for line in lines[1:]:
        line = line.rstrip("\n")
        if not line.strip():
            # Skip empty lines (don’t persist them back)
            continue
        m = TASK_RE.match(line)
        if not m:
            # Treat arbitrary text as a live task for simplicity
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
    with open(path, "w", encoding="utf-8") as f:
        header_val = last_did if (last_did is not None and 1 <= last_did <= len(tasks)) else -1
        f.write(f"# FVP_STATE last_did={header_val}\n")
        for t in tasks:
            if t.status == "open":
                f.write(f"[ ] {t.text}\n")
            elif t.status == "dotted":
                f.write(f"[.] {t.text}\n")
            else:
                f.write(f"[x] {t.text}\n")

def first_live_index(tasks: List[Task]) -> Optional[int]:
    for i, t in enumerate(tasks, start=1):
        if t.status != "done":
            return i
    return None

def last_dotted_index(tasks: List[Task]) -> Optional[int]:
    idx = None
    for i, t in enumerate(tasks, start=1):
        if t.status == "dotted":
            idx = i
    return idx

def previous_dotted_above(tasks: List[Task], index: int) -> Optional[int]:
    """Find the nearest dotted task strictly above `index`."""
    for i in range(index - 1, 0, -1):
        if tasks[i - 1].status == "dotted":
            return i
    return None

def clear_all_dots(tasks: List[Task]) -> None:
    for t in tasks:
        if t.status == "dotted":
            t.status = "open"

def print_list(tasks: List[Task], show_done: bool, last_did: Optional[int]) -> None:
    root = first_live_index(tasks)
    prev_dot = previous_dotted_above(tasks, last_did) if last_did else None

    for i, t in enumerate(tasks, start=1):
        if not show_done and t.status == "done":
            continue
        marker = "[ ]" if t.status == "open" else "[.]" if t.status == "dotted" else "[x]"
        flags = []
        if root == i:
            flags.append("ROOT")
        if last_did and (i == last_did):
            flags.append("JUST-DID")
        if prev_dot and (i == prev_dot):
            flags.append("BENCHMARK")
        suffix = f"  ← {', '.join(flags)}" if flags else ""
        print(f"{i:>3}. {marker} {t.text}{suffix}")

def cmd_list(args):
    last_did, tasks = read_file(args.file)
    if not tasks:
        print("(no tasks yet)")
        return
    print_list(tasks, show_done=args.all, last_did=last_did)

def cmd_add(args):
    last_did, tasks = read_file(args.file)
    tasks.append(Task(text=args.text.strip(), status="open"))
    write_file(args.file, last_did, tasks)
    print(f"Added: {args.text.strip()}")

def cmd_edit(args):
    last_did, tasks = read_file(args.file)
    idx = args.index
    if idx < 1 or idx > len(tasks):
        sys.exit("Index out of range.")
    tasks[idx - 1].text = args.text.strip()
    write_file(args.file, last_did, tasks)
    print(f"Edited {idx}.")

def finish_effects_after_action(tasks: List[Task], acted_index: int) -> Tuple[Optional[int], bool]:
    """
    Implements rule 6 + rule 7 housekeeping after you 'done'/'stop':
      - last_did becomes acted_index
      - If there is NO dotted task above acted_index, we have just completed the root.
        -> clear dots, reset last_did to None (new pass will start from next root).
      - Otherwise, keep dots and keep last_did set (so the next scan resumes below).
    Returns (last_did or None, cleared_root_pass: bool)
    """
    prev_dot = previous_dotted_above(tasks, acted_index)
    if prev_dot is None:
        # Just did the root — reset dots and signal a fresh pass.
        clear_all_dots(tasks)
        return None, True
    return acted_index, False

def cmd_done(args):
    last_did, tasks = read_file(args.file)
    idx = args.index
    if idx < 1 or idx > len(tasks):
        sys.exit("Index out of range.")
    tasks[idx - 1].status = "done"
    last_did, reset = finish_effects_after_action(tasks, idx)
    write_file(args.file, last_did, tasks)
    print(f"Marked done: {idx}. {'(root finished → dots reset)' if reset else ''}")

def cmd_stop(args):
    # Cross out old, re-add at bottom (same text), as per rule 5 (and rule 8 for impossible root).
    last_did, tasks = read_file(args.file)
    idx = args.index
    if idx < 1 or idx > len(tasks):
        sys.exit("Index out of range.")
    text = tasks[idx - 1].text
    tasks[idx - 1].status = "done"
    tasks.append(Task(text=text, status="open"))
    last_did, reset = finish_effects_after_action(tasks, idx)
    write_file(args.file, last_did, tasks)
    print(f"Stopped and re-added at bottom: {idx} → {len(tasks)}. {'(root finished → dots reset)' if reset else ''}")

def cmd_reset(args):
    last_did, tasks = read_file(args.file)
    clear_all_dots(tasks)
    last_did = None
    write_file(args.file, last_did, tasks)
    print("Cleared dots and scanning state.")

def cmd_clean(args):
    # Remove crossed-out lines to keep the file tidy. Also resets last_did (since indexes shift).
    last_did, tasks = read_file(args.file)
    tasks = [t for t in tasks if t.status != "done"]
    last_did = None
    write_file(args.file, last_did, tasks)
    print("Removed all crossed-out tasks. (Scanning state reset.)")

def cmd_path(args):
    print(os.path.abspath(args.file))

def prompt_yes_no(question: str) -> bool:
    try:
        ans = input(f"{question} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")

def cmd_next(args):
    """
    Interactive scan implementing rules 2–4 and 6:

    - If we just finished something previously (last_did set), resume below it:
        benchmark = previous dotted above last_did (must exist, or we reset)
        scan only items AFTER last_did; dot anything you want more than benchmark
        if dotted something: do the lowest dotted
        if dotted nothing: do the benchmark

    - Else (fresh or after finishing a root):
        dot the first live item (root) if not already dotted
        scan from the item after the root to the end; dot anything you want more than the last dotted
        do the lowest dotted
    """
    last_did, tasks = read_file(args.file)
    if not tasks or first_live_index(tasks) is None:
        print("(no live tasks)")
        return

    # If last_did points to a line that no longer exists (after manual edits), reset it.
    if last_did and (last_did < 1 or last_did > len(tasks)):
        last_did = None

    def show_task(i: int) -> str:
        return f'[{i}] {tasks[i-1].text}'

    def ensure_root_dotted():
        ridx = first_live_index(tasks)
        if ridx is None:
            return None
        if tasks[ridx - 1].status != "dotted":
            tasks[ridx - 1].status = "dotted"
        return ridx

    if last_did:
        # Resume below what you just did
        prev_dot = previous_dotted_above(tasks, last_did)
        if prev_dot is None:
            # We must have completed the root earlier, so start a fresh pass.
            last_did = None

    if not last_did:
        # Fresh pass: dot the root and scan to the end.
        root_idx = ensure_root_dotted()
        if root_idx is None:
            print("(no live tasks)")
            return
        benchmark_idx = last_dotted_index(tasks)  # should be root_idx now
        # Scan from the item after the current benchmark (root or later dots) down to end
        start_from = benchmark_idx + 1 if benchmark_idx else root_idx + 1
        i = start_from
        while i <= len(tasks):
            t = tasks[i - 1]
            if t.status == "done":
                i += 1
                continue
            # Compare to latest dotted (benchmark is always the last dotted)
            current_bench = last_dotted_index(tasks)
            bench_txt = tasks[current_bench - 1].text if current_bench else "(none)"
            if prompt_yes_no(f'Do you want to do {show_task(i)} more than [{current_bench}] {bench_txt}?'):
                if t.status != "dotted":
                    t.status = "dotted"
            i += 1

        to_do = last_dotted_index(tasks)
        write_file(args.file, last_did, tasks)
        print("\n→ Do this now:", show_task(to_do))
        return

    # Here: last_did is set and previous_dotted_above existed earlier
    # Resume below last_did with benchmark = previous dotted above
    benchmark_idx = previous_dotted_above(tasks, last_did)
    if benchmark_idx is None:
        # Safety net: start a fresh pass.
        clear_all_dots(tasks)
        last_did = None
        write_file(args.file, last_did, tasks)
        print("Dots were stale; reset. Run `next` again.")
        return

    # Scan only items AFTER the one you just did
    i = last_did + 1
    dotted_any = False
    while i <= len(tasks):
        t = tasks[i - 1]
        if t.status == "done":
            i += 1
            continue
        bench_txt = tasks[benchmark_idx - 1].text
        if prompt_yes_no(f'Do you want to do {show_task(i)} more than [{benchmark_idx}] {bench_txt}?'):
            if t.status != "dotted":
                t.status = "dotted"
            benchmark_idx = i
            dotted_any = True
        i += 1

    write_file(args.file, last_did, tasks)

    if dotted_any:
        to_do = last_dotted_index(tasks)
        print("\n→ Do this now:", show_task(to_do))
    else:
        # Do the previous dotted (the benchmark)
        print("\n→ Do this now:", show_task(benchmark_idx))

def build_parser():
    p = argparse.ArgumentParser(prog="fvp", description="Mark Forster FVP CLI (dot-chain).")
    p.add_argument("-f", "--file", default=DEFAULT_PATH, help=f"Path to tasks file (default: {DEFAULT_PATH})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_list = sub.add_parser("list", help="Show tasks (default hides [x])")
    s_list.add_argument("--all", action="store_true", help="Show crossed-out tasks too")
    s_list.set_defaults(func=cmd_list)

    s_add = sub.add_parser("add", help="Append a new task")
    s_add.add_argument("text", help="Task text, quoted if it has spaces")
    s_add.set_defaults(func=cmd_add)

    s_edit = sub.add_parser("edit", help="Edit task text in place")
    s_edit.add_argument("index", type=int, help="Task index from `list`")
    s_edit.add_argument("text", help="New text")
    s_edit.set_defaults(func=cmd_edit)

    s_next = sub.add_parser("next", help="Interactive scan to recommend the next task")
    s_next.set_defaults(func=cmd_next)

    s_done = sub.add_parser("done", help="Mark a task done ([x])")
    s_done.add_argument("index", type=int)
    s_done.set_defaults(func=cmd_done)

    s_stop = sub.add_parser("stop", help="Stop early: cross out & re-add at bottom")
    s_stop.add_argument("index", type=int)
    s_stop.set_defaults(func=cmd_stop)

    s_bump = sub.add_parser("bump", help="Alias of `stop` (handy for “root impossible now”)")
    s_bump.add_argument("index", type=int)
    s_bump.set_defaults(func=cmd_stop)

    s_reset = sub.add_parser("reset", help="Wipe all dots and scanning state")
    s_reset.set_defaults(func=cmd_reset)

    s_clean = sub.add_parser("clean", help="Remove all crossed-out lines ([x])")
    s_clean.set_defaults(func=cmd_clean)

    s_path = sub.add_parser("path", help="Show the absolute path to the tasks file")
    s_path.set_defaults(func=cmd_path)

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(args.file)), exist_ok=True)
    args.func(args)

if __name__ == "__main__":
    main()
