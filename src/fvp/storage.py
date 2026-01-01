"""File I/O for FVP task lists."""

import os
from typing import List, Optional, Tuple

from .models import Task, STATE_RE, TASK_RE


def read_file(path: str) -> Tuple[Optional[int], List[Task]]:
    """Load FVP list file.

    Returns a tuple of:
      - last_did: 1-based index for the last acted task (None if not set)
      - tasks: list of Task objects parsed from the file

    Creates the file with a default header if it does not exist.
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


def append_to_archive(archive_path: str, text: str) -> None:
    """Append a completed task to the archive sidecar file."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(archive_path)), exist_ok=True)
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(f"[x] {text}\n")
    except Exception:
        # Non-fatal; ignore archive errors
        pass


def ensure_file_exists(path: str) -> None:
    """Ensure the directory and file exist with valid header."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# FVP_STATE last_did=-1\n")
