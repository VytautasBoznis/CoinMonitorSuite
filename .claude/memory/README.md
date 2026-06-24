# Project memory

These `*.md` files are Claude Code's long-term memory for this repo (see
`MEMORY.md` for the index). They live in the repo so they're version-controlled
and shared, but Claude's recall actually reads them from a per-machine path:

```
<home>/.claude/projects/<project-key>/memory
```

`<project-key>` is Claude's encoding of the repo's **absolute path** (separators
`:` `\` `/` replaced with `-`). Both `<home>` and `<project-key>` change with the
user, the clone location, and the OS — so the link can't be hardcoded. Instead we
**link** that per-machine path to this folder.

## Setup on a new machine (once)

After cloning and opening Claude Code in this repo at least once:

```bash
bash .claude/memory/link-memory.sh
```

The script derives both paths itself and creates a Windows **junction** or a Unix
**symlink** as appropriate. It's safe to re-run (no-ops if already linked, and
refuses to clobber a non-empty real folder).

If recall still can't find memories, the derived `<project-key>` was probably
wrong — look in `~/.claude/projects/` for the real folder name and pass it
explicitly:

```bash
PROJECT_KEY=the-actual-folder-name bash .claude/memory/link-memory.sh
```

## Manual fallback

If you'd rather not run the script:

- **Windows** (no admin needed):
  ```
  powershell -NoProfile -Command "New-Item -ItemType Junction -Path '<home>\.claude\projects\<project-key>\memory' -Target '<repo>\.claude\memory'"
  ```
- **macOS / Linux**:
  ```
  ln -s <repo>/.claude/memory <home>/.claude/projects/<project-key>/memory
  ```

Note: the junction/symlink itself is machine-local and is **not** committed — only
these memory files are.
