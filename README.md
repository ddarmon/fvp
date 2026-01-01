# FVP Interactive (TUI)

*A minimalist terminal-based implementation of Mark Forster's "Final
Version Perfected" productivity system.*

------------------------------------------------------------------------

## 🌱 Why this exists

Mark Forster's **Final Version Perfected (FVP)** is a deceptively simple
task-management method built around a few powerful principles:

-   **One long list** --- no reordering, no prioritizing, no multiple
    lists.
-   **Dot-chain scanning** --- you don't pick tasks logically; you
    *compare* them emotionally.
-   **Momentum and readiness** --- you only ever do the *lowest dotted*
    item, which balances importance, urgency, and motivation.
-   **Continual renewal** --- finished or stale tasks are crossed out
    and re-entered at the bottom, keeping the list alive and current.

Most digital tools break these principles by pushing scheduling,
sorting, or tagging. This TUI app keeps FVP pure: it's **one text file,
one list, no databases, no sync, no cloud.**

------------------------------------------------------------------------

## ✨ What this app does

This program lets you manage your FVP list **interactively** from the
terminal. By default it runs in a guided, restrictive flow (Strict Mode)
that mirrors FVP: scan candidates → focus on one → act (done/archive or
stop→bottom) → resume scan.

It opens a **text-based user interface (TUI)** where you can:

-   **Navigate** your list (arrow keys, `j/k`, `PgUp/PgDn`)
-   **Add/edit/delete** tasks inline
-   **Run the "dot-chain scan" interactively** with a focused two-item
    compare: only the two candidates are shown, in list order (upper =
    benchmark, lower = candidate). Use `↓`/`j` to choose the lower item or
    `↑`/`k` to choose the upper; `q`/`ESC` stops the scan.
-   **Mark tasks done** (cross out) or **archive done** (remove from the
    list and append to an `*.archive` file). If you stop early, the task
    is crossed out and re-added to the bottom — preserving momentum.
-   **Work entirely offline**, with a single plaintext file as your
    source of truth

All data lives in `~/.fvp.txt` (or a file you specify). Each line uses
lightweight markers:

    [ ] open
    [.] dotted
    [x] crossed-out

------------------------------------------------------------------------

## 🧭 Quick start

### 1. Installation

``` bash
# Clone the repository
git clone https://github.com/youruser/fvp.git
cd fvp

# Run with uv (recommended)
uv run fvp
```

Or install as a tool:

``` bash
uv tool install .
fvp
```

### 2. Run

``` bash
# Launch TUI (default)
uv run fvp

# Use a custom file
uv run fvp -f ~/projects/mylist.txt

# CLI subcommands
uv run fvp list
uv run fvp add "New task"
uv run fvp done 3
```

The app creates your list file if it doesn't exist:

    # FVP_STATE last_did=-1
    [ ] Write README draft
    [ ] Respond to Sam
    [ ] Clean desk

------------------------------------------------------------------------

## 🎮 Key commands

  Key / Command      Action
  ------------------ --------------------------------------------
  **Navigation**
  ↑ / ↓ / j / k      Move up / down
  PgUp / PgDn        Page scroll
  g / G              Jump to top / bottom
  t                  Jump to root
  n                  Jump to "Do now" (lowest dotted)
  /                  Filter/search tasks
  h                  Hide/show crossed-out `[x]` lines
  **Task actions**
  a                  Add task
  e                  Edit task
  d                  Mark done (cross out)
  D                  Done & archive (remove from list, append to archive)
  S                  Worked on → move to bottom (cross out & re-add)
  r                  Reset dots & scanning state
  c                  Clean crossed-out `[x]` lines
  R                  Reload from disk
  **FVP-specific**
  s                  Run a dot-chain scan (↑/k=top, ↓/j=bottom, q/ESC stops)
  ?                  Show help
  q / ESC            Quit
  **Mode**
  M                  Toggle Strict Mode (default ON). In Strict Mode,
                     focus view shows only the current "Do now" task; only
                     d / D / S are allowed. Filters/hide and most navigation
                     are disabled while focused.

Note: Prompts use Enter to submit and ESC to cancel.

------------------------------------------------------------------------

## 🔁 The FVP logic inside

The TUI directly models the **eight rules** of Final Version Perfected:

  -----------------------------------------------------------------------
  FVP rule                            Implemented in app
  ----------------------------------- -----------------------------------
  1\. Keep one list; new items go at  `add` always appends to the end.
  bottom.

  2\. Root = first live item.         `ensure_root_dotted()` auto-dots
                                      it.

  3\. "Do I want this more than the   `scan()` asks you interactively via
  last dotted?"                       keypress.

  4\. Do the lowest dotted.           After each scan, the app shows "→
                                      Do this now."

  5\. If you stop early, cross out &  `S` key does exactly this.
  re-add.

  6\. After doing one, resume below   `done` + `scan()` sequence
  it.                                 implements this rule.

  7\. When root is done, new top item Detected in
  becomes root.                       `finish_effects_after_action()`.

  8\. If root impossible, cross out & `S` handles this (cross out & re-enter).
  re-enter.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 🧩 App architecture

The program is a **single file** organized in modular sections:

### 1. **File storage**

Handles reading and writing the plain-text `.fvp` file.

-   `read_file()` --- parses `# FVP_STATE` header and tasks
-   `write_file()` --- rewrites the file with markers
-   `Task` dataclass stores text and status

### 2. **Core FVP logic**

Implements the dot-chain and state rules.

-   `first_live_index()` --- find root
-   `last_dotted_index()` --- find lowest dotted
-   `previous_dotted_above()` --- benchmark lookup
-   `finish_effects_after_action()` --- post-action bookkeeping
-   `clear_all_dots()` --- resets a pass

### 3. **TUI (curses-based)**

Manages all interaction:

-   `TUI.draw()` --- renders header, body, footer
-   `TUI.run()` --- main loop with key bindings
-   `TUI.scan()` --- implements dot-chain scanning (two-item compare)
-   `TUI.add_task()`, `mark_done()`, `stop_and_readd()` --- handle FVP
    rules
-   `TUI.prompt()` and `TUI.confirm()` --- inline pop-ups for user input
-   `TUI.help_popup()` --- shows key reference
-   All color and layout handled by standard `curses` calls

Strict Mode adds a lightweight state machine (`idle` → `scanning` →
`focus`) that auto-starts scans and then focuses you on a single
"Do now" item until you act (d/D/S). You can toggle Strict Mode with
`M`.

### 4. **Entry point**

-   `main()` --- handles `-f/--file` flag
-   Ensures file exists, then calls `start_curses()`

The logic is pure Python: **no dependencies**, **no config files**, **no
databases**.

------------------------------------------------------------------------

## ⚙️ Internal flow

Here's the lifecycle in Strict Mode:

``` text

1. Add → [ ] New task at bottom
2. Scan (s auto-starts) → pairwise compare; some become [.]
3. Focus → "Do now" shows alone
4. Act →
   - d: [x] crosses out (remains until hidden/cleaned)
   - D: archive (remove from list; append to `~/.fvp.txt.archive`)
   - S: stop early → [x] + re-add [ ] at bottom
5. Auto-resume scan below last action; repeat
```

The file always remains a valid FVP list; you can open and edit it
manually if desired.

Archived items live in a plain text file next to your list (e.g.,
`~/.fvp.txt.archive`). Each archived task is appended as `[x] <task>`.
No databases — still plain text.

------------------------------------------------------------------------

## ⏱️ 60‑Second Strict Mode Walkthrough

A quick end‑to‑end of the guided flow.

1.  Start
    -   Run `uv run fvp`.
    -   Strict Mode is ON by default. The app auto‑starts a scan.
2.  Compare (two‑item view)
    -   A modal shows two tasks: upper vs lower.
    -   Press `↓`/`j` to choose the lower item or `↑`/`k` to choose the upper.
        `q`/`ESC` stops scanning.
3.  Focus (single‑item view)
    -   After scanning, your "Do now" task appears centered on screen.
    -   The status bar shows: `d=done D=archive S=stop`
4.  Auto‑resume
    -   After `d`/`D`/`S`, the app resumes scanning below your last
        action and finds the next task.
5.  Optional: Free mode
    -   Press `M` to toggle Strict Mode OFF if you want free navigation,
        filtering, and the full list view with markers.

Example flow:

``` text
Scan modal:
  "Respond to Sam" vs "Clean desk" → press ↑/k (choose upper)

Focus view:
  >>> WORK ON THIS <<<

           Respond to Sam

  DO NOW: Respond to Sam | d=done D=archive S=stop

→ press D (archive‑done) → auto-resumes scan
```

This keeps you in the FVP rhythm: compare → decide → focus → act →
resume.

------------------------------------------------------------------------

## 🧠 Design philosophy

-   **Plain text as the API.** The list file is both your data store
    *and* your interface. You can version it with Git, edit in Vim, or
    sync via cloud storage.

-   **Faithful to Forster's psychology.** The scan process mirrors how
    your brain weighs "want" in context --- urgency, readiness, energy
    --- without external prioritization.

-   **No distractions.** No timestamps, no tags, no due dates. Just your
    attention and your honest sense of *want*.

-   **Curses, not GUI.** Keeps cognitive friction low and makes the app
    scriptable and composable with other CLI tools.

------------------------------------------------------------------------

## 📁 File structure example

``` bash
~/.fvp.txt
┌──────────────────────────────────────┐
│ # FVP_STATE last_did=5               │
│ [.] Draft intro                      │
│ [ ] Reply to Sam                     │
│ [ ] Clean whiteboard                 │
│ [.] Outline slides                   │
│ [x] Back up laptop                   │
└──────────────────────────────────────┘
```

Each `[.]` marks a dotted task; `[x]` marks a crossed-out one. You can
open this in any text editor; it's entirely human-readable.

------------------------------------------------------------------------
