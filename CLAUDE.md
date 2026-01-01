# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working
with code in this repository.

## Overview

FVP is a minimalist implementation of Mark Forster's "Final Version
Perfected" task management system. The codebase provides two interfaces:

-   **fvp.py**: CLI for scripted/shell usage
-   **fvp_tui.py**: Interactive curses-based TUI (primary interface)

Both share the same plain-text file format and FVP logic. No external
dependencies---pure Python 3 with only standard library modules
(`curses`, `argparse`, `dataclasses`).

## Running the Applications

``` bash
# TUI (interactive, default)
python3 fvp_tui.py
python3 fvp_tui.py -f ~/mylist.txt

# CLI
python3 fvp.py list
python3 fvp.py add "Task text"
python3 fvp.py next    # interactive scan
python3 fvp.py done 3
python3 fvp.py stop 3  # cross out and re-add at bottom
```

## Architecture

### File Format

Single plain-text file (default: `~/.fvp.txt`):

    # FVP_STATE last_did=5
    [ ] open task
    [.] dotted task
    [x] crossed-out task

-   First line: state header tracking `last_did` (1-based index of last
    acted task, or -1)
-   Task markers: `[ ]` live, `[.]`dotted, `[x]` done

### Code Organization (both files follow same pattern)

1.  **Data model**: `Task` dataclass with `text` and `status`
    ("open"\|"dotted"\|"done")

2.  **File I/O**: `read_file()` parses header + tasks; `write_file()`
    serializes back

3.  **FVP helpers** (implement the 8 FVP rules):

    -   `first_live_index()` --- find root (first non-\[x\])
    -   `last_dotted_index()` --- find "do now" target (lowest dotted)
    -   `previous_dotted_above()` --- find benchmark for resume scanning
    -   `finish_effects_after_action()` --- post-action bookkeeping: if
        no dots above acted item, root was completed → clear all dots
    -   `clear_all_dots()` --- reset for new pass

4.  **TUI-specific** (fvp_tui.py):

    -   `TUI` class manages curses rendering and input
    -   `scan()` --- pairwise comparison flow with popup modal
    -   Strict Mode state machine: `idle` → `scanning` → `focus`
    -   Archive sidecar: completed tasks optionally written to
        `<file>.archive`

### Key FVP Concepts

-   **Root**: First live (non-crossed-out) task; always gets dotted at
    scan start
-   **Benchmark**: Last dotted item above current position; used for
    pairwise comparison
-   **Scan**: Walk down list asking "want this more than benchmark?" →
    dot if yes
-   **Do now**: Lowest dotted task
-   **Stop early**: Cross out and re-add same text at bottom (preserves
    momentum)
