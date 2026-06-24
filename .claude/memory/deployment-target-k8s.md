---
name: deployment-target-k8s
description: "Deployment target is a Kubernetes cluster; every component must ship as a Docker image"
metadata:
  type: project
---

**Deployment target (firm, user 2026-06-24):** everything runs in a **Kubernetes cluster**, so **every component must ship as a Docker image** — the Phase 1 backtester CLI, the future FastAPI control plane, the React/TS UI, and any scanner/executor workers. "Docker images are required for everything."

**Why:** containerization is a hard deployment constraint, not optional packaging — it shapes how each component is built, configured, and run.

**How to apply:**
- Default every new runnable component to a `Dockerfile` (multi-stage; small final image). A k8s manifest / Helm chart follows when a component actually deploys.
- Config must be **env-var / file driven** so it maps to ConfigMaps + Secrets — already true: `config.py` uses `pydantic-settings` with the `COINMON_` env prefix and `.env` support. Secrets (exchange API keys, later) go through k8s Secrets, never baked into images.
- The local Parquet `data/` store (Phase 1) is ephemeral in a container — real data needs a mounted volume / PVC, or the Phase 2+ Postgres/Timescale move. See [[project-direction]].
- Not built yet (no Dockerfile in repo as of scaffold step 1); add per component when there's something runnable to containerize.
