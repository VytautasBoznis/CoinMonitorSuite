---
name: session-build-loop
description: "How the build runs each session: read memory, do the next roadmap chunk, ask blockers, deliver a commit message"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d2b51f14-af0b-4701-8a48-a061e92ae8ba
---

Standing working agreement (user, 2026-06-28) for building CoinMonitorSuite to completion
across many sessions:

1. **On session start, read memory** — especially [[build-roadmap]] — and continue from the
   first unfinished chunk. Don't re-ask what the roadmap already decides.
2. **Do roughly one chunk per session.** Chunks are sized in [[build-roadmap]] to fit a session.
3. **Ask intermission questions when genuinely blocked** on a decision only the user can make
   (e.g. which pairs, testnet vs live, capital limits). Otherwise proceed on sensible defaults.
4. **Generate a commit message for every logical part of the work** — the user commits, not me
   (see [[user-commits-themselves]]).
5. **Keep the roadmap current**: tick the chunk done in [[build-roadmap]] and record any
   findings as their own memory before ending.

**Why:** the user wants a self-driving multi-session build where each session lands a coherent,
committable increment without re-deriving context.

**How to apply:** treat [[build-roadmap]] as the source of truth for "what's next"; the
discipline from [[search-overfits-not-strategy]] (validate before scaling, never trust
in-sample) governs the order — search/validation before suggestions, suggestions before any
live execution.
