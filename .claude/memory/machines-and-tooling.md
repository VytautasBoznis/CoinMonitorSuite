---
name: machines-and-tooling
description: Sessions run on multiple machines — the machine used on 2026-07-04 has the repo checkout but NO tooling (cannot run the stack); verify environment before attempting runs
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

The user works across multiple machines. The machine used in the 2026-07-04 session
(repo at /Users/vytautasboznis/Dev/CoinMonitoringSuite/CoinMonitorSuite, macOS) has the
source checkout and sweep result logs in runs/, but the user states it has NO tooling —
do not assume you can run sweeps, the scraper, tests, or the DB stack on it.

**Why:** Prevents wasted turns attempting `pytest`/sweep/docker runs that can't work, and
explains why some sessions are analysis/planning-only (like the 2026-07-04 pivot session).

**How to apply:** At session start, if work requires executing the stack, first check the
environment (python env, docker, DB reachability) before promising runs. Planning, code
edits, and memory work are always fine. The 2026-07-04 session's purpose was explicitly to
prepare memory so a different model on a properly tooled machine can execute
[[execution-plan-2026-07]] without re-deriving context.
