"""FVP command-line interface."""

import argparse
import sys
from typing import List, Optional

from .models import Task, DEFAULT_PATH
from .storage import read_file, write_file, ensure_file_exists
from .core import (
    first_live_index,
    last_dotted_index,
    previous_dotted_above,
    clear_all_dots,
    finish_effects_after_action,
)


def print_list(
    tasks: List[Task], show_done: bool, last_did: Optional[int]
) -> None:
    """Print task list with markers and flags."""
    root = first_live_index(tasks)
    prev_dot = previous_dotted_above(tasks, last_did) if last_did else None

    for i, t in enumerate(tasks, start=1):
        if not show_done and t.status == "done":
            continue
        marker = (
            "[ ]" if t.status == "open" else "[.]" if t.status == "dotted" else "[x]"
        )
        flags = []
        if root == i:
            flags.append("ROOT")
        if last_did and (i == last_did):
            flags.append("JUST-DID")
        if prev_dot and (i == prev_dot):
            flags.append("BENCHMARK")
        suffix = f"  <- {', '.join(flags)}" if flags else ""
        print(f"{i:>3}. {marker} {t.text}{suffix}")


def prompt_yes_no(question: str) -> bool:
    """Simple y/N terminal prompt."""
    try:
        ans = input(f"{question} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def cmd_list(args: argparse.Namespace) -> None:
    last_did, tasks = read_file(args.file)
    if not tasks:
        print("(no tasks yet)")
        return
    print_list(tasks, show_done=args.all, last_did=last_did)


def cmd_add(args: argparse.Namespace) -> None:
    last_did, tasks = read_file(args.file)
    tasks.append(Task(text=args.text.strip(), status="open"))
    write_file(args.file, last_did, tasks)
    print(f"Added: {args.text.strip()}")


def cmd_edit(args: argparse.Namespace) -> None:
    last_did, tasks = read_file(args.file)
    idx = args.index
    if idx < 1 or idx > len(tasks):
        sys.exit("Index out of range.")
    tasks[idx - 1].text = args.text.strip()
    write_file(args.file, last_did, tasks)
    print(f"Edited {idx}.")


def cmd_done(args: argparse.Namespace) -> None:
    last_did, tasks = read_file(args.file)
    idx = args.index
    if idx < 1 or idx > len(tasks):
        sys.exit("Index out of range.")
    tasks[idx - 1].status = "done"
    last_did, reset = finish_effects_after_action(tasks, idx)
    write_file(args.file, last_did, tasks)
    print(f"Marked done: {idx}. {'(root finished -> dots reset)' if reset else ''}")


def cmd_stop(args: argparse.Namespace) -> None:
    """Cross out old, re-add at bottom."""
    last_did, tasks = read_file(args.file)
    idx = args.index
    if idx < 1 or idx > len(tasks):
        sys.exit("Index out of range.")
    text = tasks[idx - 1].text
    tasks[idx - 1].status = "done"
    tasks.append(Task(text=text, status="open"))
    last_did, reset = finish_effects_after_action(tasks, idx)
    write_file(args.file, last_did, tasks)
    print(
        f"Stopped and re-added at bottom: {idx} -> {len(tasks)}. "
        f"{'(root finished -> dots reset)' if reset else ''}"
    )


def cmd_reset(args: argparse.Namespace) -> None:
    last_did, tasks = read_file(args.file)
    clear_all_dots(tasks)
    last_did = None
    write_file(args.file, last_did, tasks)
    print("Cleared dots and scanning state.")


def cmd_clean(args: argparse.Namespace) -> None:
    """Remove crossed-out lines."""
    last_did, tasks = read_file(args.file)
    tasks = [t for t in tasks if t.status != "done"]
    last_did = None
    write_file(args.file, last_did, tasks)
    print("Removed all crossed-out tasks. (Scanning state reset.)")


def cmd_path(args: argparse.Namespace) -> None:
    import os

    print(os.path.abspath(args.file))


def cmd_next(args: argparse.Namespace) -> None:
    """Interactive scan to find the next task."""
    last_did, tasks = read_file(args.file)
    if not tasks or first_live_index(tasks) is None:
        print("(no live tasks)")
        return

    if last_did and (last_did < 1 or last_did > len(tasks)):
        last_did = None

    def show_task(i: int) -> str:
        return f"[{i}] {tasks[i - 1].text}"

    def ensure_root_dotted_local() -> Optional[int]:
        ridx = first_live_index(tasks)
        if ridx is None:
            return None
        if tasks[ridx - 1].status != "dotted":
            tasks[ridx - 1].status = "dotted"
        return ridx

    if last_did:
        prev_dot = previous_dotted_above(tasks, last_did)
        if prev_dot is None:
            last_did = None

    if not last_did:
        root_idx = ensure_root_dotted_local()
        if root_idx is None:
            print("(no live tasks)")
            return
        benchmark_idx = last_dotted_index(tasks) or root_idx
        start_from = benchmark_idx + 1
        i = start_from
        while i <= len(tasks):
            t = tasks[i - 1]
            if t.status == "done":
                i += 1
                continue
            current_bench = last_dotted_index(tasks)
            bench_txt = tasks[current_bench - 1].text if current_bench else "(none)"
            if prompt_yes_no(
                f"Do you want to do {show_task(i)} more than [{current_bench}] {bench_txt}?"
            ):
                if t.status != "dotted":
                    t.status = "dotted"
            i += 1

        to_do = last_dotted_index(tasks)
        write_file(args.file, last_did, tasks)
        if to_do:
            print(f"\n-> Do this now: {show_task(to_do)}")
        return

    benchmark_idx = previous_dotted_above(tasks, last_did)
    if benchmark_idx is None:
        clear_all_dots(tasks)
        last_did = None
        write_file(args.file, last_did, tasks)
        print("Dots were stale; reset. Run `next` again.")
        return

    i = last_did + 1
    dotted_any = False
    while i <= len(tasks):
        t = tasks[i - 1]
        if t.status == "done":
            i += 1
            continue
        bench_txt = tasks[benchmark_idx - 1].text
        if prompt_yes_no(
            f"Do you want to do {show_task(i)} more than [{benchmark_idx}] {bench_txt}?"
        ):
            if t.status != "dotted":
                t.status = "dotted"
            benchmark_idx = i
            dotted_any = True
        i += 1

    write_file(args.file, last_did, tasks)

    if dotted_any:
        to_do = last_dotted_index(tasks)
        print(f"\n-> Do this now: {show_task(to_do)}")
    else:
        print(f"\n-> Do this now: {show_task(benchmark_idx)}")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    p = argparse.ArgumentParser(
        prog="fvp", description="Mark Forster FVP CLI (dot-chain)."
    )
    p.add_argument(
        "-f",
        "--file",
        default=DEFAULT_PATH,
        help=f"Path to tasks file (default: {DEFAULT_PATH})",
    )
    sub = p.add_subparsers(dest="cmd")

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

    s_bump = sub.add_parser("bump", help="Alias of `stop`")
    s_bump.add_argument("index", type=int)
    s_bump.set_defaults(func=cmd_stop)

    s_reset = sub.add_parser("reset", help="Wipe all dots and scanning state")
    s_reset.set_defaults(func=cmd_reset)

    s_clean = sub.add_parser("clean", help="Remove all crossed-out lines ([x])")
    s_clean.set_defaults(func=cmd_clean)

    s_path = sub.add_parser("path", help="Show the absolute path to the tasks file")
    s_path.set_defaults(func=cmd_path)

    return p


def main() -> None:
    """CLI entry point. Launches TUI if no subcommand given."""
    parser = build_parser()
    args = parser.parse_args()

    ensure_file_exists(args.file)

    if args.cmd is None:
        # No subcommand: launch TUI
        from .tui import main as tui_main

        tui_main(args.file)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
