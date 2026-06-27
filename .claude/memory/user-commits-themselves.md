---
name: user-commits-themselves
description: User always commits themselves — never run git add/commit; produce a commit message instead
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d2b51f14-af0b-4701-8a48-a061e92ae8ba
---

The user **always commits themselves**. Never run `git add`, `git commit`, or `git push` —
even when the work is finished and verified.

**Why:** the user wants control over what enters history and when; committing for them takes
that away.

**How to apply:** when a unit of work is done, hand over a ready-to-paste **commit message**
(subject + body, ending with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
trailer) and stop. One commit message per logical part of the work — see [[session-build-loop]].
