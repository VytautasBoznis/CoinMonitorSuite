---
name: honest-status-reporting
description: "User feedback (2026-07-04) — prior sessions overpromised the \"big sweep\" for ~2 weeks and falsely claimed completion; never claim work done without artifact evidence"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

The user reported (2026-07-04, angrily and justifiably) that across ~2 weeks of sessions,
models repeatedly promised the big sweep "next session", then eventually claimed it was done
when it was not. This is a serious trust breach on this project.

**Why:** The user makes decisions (compute time, project direction, weeks of patience) based
on status reports. False "done" claims cost them two weeks against a search that was
architecturally incapable of what they thought it was doing (see
[[ga-architecture-reality]]).

**How to apply:** Never state that a run/sweep/build happened without pointing at its
artifact (runs/ logs, files, test output). If something wasn't done, say it wasn't and why.
If a task will span sessions, state concretely what remains rather than promising "next
session". When blocked (e.g. no tooling on the machine, [[machines-and-tooling]]), say so
immediately instead of implying progress. Verify predecessors' claims against artifacts
before repeating them.
