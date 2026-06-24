#!/usr/bin/env bash
#
# Links Claude Code's per-project memory directory to this repo's committed
# .claude/memory folder, so recall reads/writes the version-controlled files.
#
# Run ONCE per machine after cloning (and after Claude Code has been opened in
# this repo at least once, so the projects/<key> folder exists):
#
#     bash .claude/memory/link-memory.sh
#
# Both paths are derived at runtime, so this survives a different username,
# clone location, or OS. Overrides if the derivation is ever wrong:
#     PROJECT_KEY=<exact-folder-name>  CLAUDE_CONFIG_DIR=<path>  bash link-memory.sh
#
set -euo pipefail

# This script lives in <repo>/.claude/memory — that folder IS the link target.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_MEM="$SCRIPT_DIR"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
PROJECTS="$CLAUDE_HOME/projects"

is_windows() { case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0;; *) return 1;; esac; }

# Derive Claude's project-key folder name from the repo's absolute path.
# Claude replaces the path separators ( : \ / ) with '-'.
derive_keys() {
  if is_windows; then
    local win; win="$(cygpath -w "$REPO_ROOT")"          # e.g. C:\Dev\PracticalApps\CartFees
    local k;   k="$(printf '%s' "$win" | sed 's/[:\\/]/-/g')"
    # try both as-is and lowercased drive letter (Claude uses the cwd's casing)
    printf '%s\n' "$k"
    printf '%s\n' "$(printf '%s' "$k" | sed 's/^\(.\)/\L\1/')"
  else
    printf '%s\n' "$(printf '%s' "$REPO_ROOT" | sed 's#[/]#-#g')"
  fi
}

# Pick the project key: explicit override > an existing projects/<key> dir > best guess.
pick_key() {
  if [ -n "${PROJECT_KEY:-}" ]; then printf '%s' "$PROJECT_KEY"; return; fi
  local guess=""
  while IFS= read -r k; do
    [ -z "$guess" ] && guess="$k"
    if [ -d "$PROJECTS/$k" ]; then printf '%s' "$k"; return; fi
  done < <(derive_keys)
  printf '%s' "$guess"   # nothing matched yet (Claude may not have run here) — use first guess
}

KEY="$(pick_key)"
TARGET="$PROJECTS/$KEY/memory"

echo "Repo memory : $REPO_MEM"
echo "Link path   : $TARGET"

mkdir -p "$PROJECTS/$KEY"

# Already a link (symlink or Windows junction)? Done.
if [ -L "$TARGET" ]; then
  echo "A link already exists at the target; leaving it in place."
  exit 0
fi

# A real (non-link) directory already there → don't clobber; let the user merge.
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
  if find "$TARGET" -mindepth 1 -print -quit | grep -q .; then
    echo "ERROR: $TARGET already exists and is NOT empty."
    echo "Back up/merge its contents into $REPO_MEM, delete it, then re-run."
    exit 1
  fi
  rmdir "$TARGET"
fi

if is_windows; then
  # Junction (no admin needed). PowerShell handles Windows paths cleanly.
  powershell -NoProfile -Command \
    "New-Item -ItemType Junction -Path '$(cygpath -w "$TARGET")' -Target '$(cygpath -w "$REPO_MEM")' | Out-Null"
else
  ln -s "$REPO_MEM" "$TARGET"
fi

echo "Linked. Recall now reads/writes $REPO_MEM"
