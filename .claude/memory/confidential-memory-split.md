---
name: confidential-memory-split
description: "RULE (owner, 2026-10-14): before persisting anything, filter it. The owner's private facts (infra, network, identities, balances) go ONLY to the gitignored memory/confidential/ folder"
metadata:
  type: feedback
---

The owner asked for a dedicated folder for confidential memory, kept out of git, and for everything
they tell me to be filtered before I write it down for persistence. Memory lives in the repo
(`.claude/memory` is committed), so anything written to ordinary memory gets pushed.

**Why:** the repo is shared through GitHub. Earlier sessions had written the owner's router IP, cluster
details, wallet addresses and balance into committed memory, which later had to be scrubbed by hand.

**How to apply:** classify each fact before writing it.
- **Confidential**: goes to `memory/confidential/` (gitignored by `/.claude/memory/confidential/`), indexed
  in `confidential/INDEX.md`.
  - The owner's machines, cluster, node names, kubeconfig and access paths.
  - IPs, DNS and router details.
  - Wallet and API-wallet addresses or names, balances, position sizes, per-account settings.
  - Anything personally identifying.
- **Shared**: committed memory or docs. Generic, reusable lessons and project facts, written without
  those details. E.g. "an upstream resolver that intermittently timed out", not the router's IP.
- Never put confidential values into code, docs, commit messages, Helm values or test fixtures. Use
  placeholders such as `0xYourWalletAddress`.
- Never store secrets at all, not even here: private keys, seed phrases, API keys, passwords.
