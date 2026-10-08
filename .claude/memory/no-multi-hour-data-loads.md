---
name: no-multi-hour-data-loads
description: "USER RULE 2026-10-08: no multi-hour data backfills on the test machine — skip any test that needs one (killed a 2-3h Bybit 1m REST backfill). Estimate load time BEFORE launching."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 4238af7c-0366-4df9-991c-17ffbd36d05d
  modified: 2026-10-08T18:01:04.672Z
---

On 2026-10-08 the owner killed the ~2-3h Bybit 1m REST backfill for the F8 Bybit-native rerun
("2 or 3h on a fuckin test machine? ... skip any tests that require this").

**Why:** the test machine is not a data farm; a probe whose data takes hours to land is not worth
the wall-clock, however clean its pre-registration.

**How to apply:** before starting any data pull, estimate its wall time (one timed call x number of
calls). If it is hours, do not launch it: skip that test, or propose a proxy on data already stored.
Say the estimate up front. Long collection belongs in the user's k8s/collector plans
([[user-infra-ui-plans]]), not in a probe run. First casualty: [[f8-cascade-ladder-result]]'s
Bybit-native rerun.
