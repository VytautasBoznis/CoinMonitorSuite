---
name: data-package-gitignored
description: "REPO BUG: the whole src/coinmon/data/ package is git-ignored (untracked) by the broad `data/` .gitignore rule — new data/ files won't commit and past data/ chunks were never versioned"
metadata: 
  node_type: memory
  type: project
  originSessionId: bfbc30ac-a578-4007-bccd-f398dc6a44d9
---

Discovered 2026-07-02 while landing chunk V3 (`src/coinmon/data/surrogate.py`): the **entire
`src/coinmon/data/` package is untracked by git**. `git ls-files | grep coinmon/data` → empty;
`git log -- src/coinmon/data/` → empty. Files affected (all on disk, none in version control):
`__init__.py, candles.py, db.py, discovery.py, models.py, ratio.py, store.py` (+ my new
`surrogate.py`, + `adapters/`).

**Cause:** `.gitignore:20` is `data/` (comment: "candle Parquet store — fetched, not versioned").
Unanchored, so it matches ANY directory named `data` at any depth — including the SOURCE package
`src/coinmon/data/`. `git check-ignore -v src/coinmon/data/surrogate.py` → `.gitignore:20:data/`.

**Why it matters:** core modules (candles/ratio/db/models) AND recent "done" chunks that live in
`data/` — chunk T (`discovery.py` `rank_spot`/`coverage`, funding table in `db.py`, `adapters/binance`)
and now chunk V3 (`surrogate.py`) — are NOT actually committed. The code runs (files on disk, tests
pass) but a fresh clone would be missing the whole data layer. **Why:** an unanchored gitignore rule
meant for a repo-root Parquet store is swallowing a same-named source dir.

**How to apply (user's call — I did NOT change `.gitignore`, repo-wide implications):**
- Cleanest: anchor the rule to repo root — change `data/` → `/data/` in `.gitignore` (only ignores
  the top-level Parquet store, un-ignores `src/coinmon/data/`). Then `git add src/coinmon/data/`.
- Or add a negation: `!src/coinmon/data/`.
- Immediate unblock for a single file: `git add -f src/coinmon/data/surrogate.py`.
Verify the top-level Parquet store's real location before anchoring (don't accidentally start
versioning a large `data/` dataset). See [[build-roadmap]], [[user-commits-themselves]].
