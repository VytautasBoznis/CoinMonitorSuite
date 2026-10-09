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

**BUILT 2026-10-10 (owner: "I'll literally use the images and helm charts on my k3s cluster"):**
- **Chart:** `deploy/helm/coinmon`, with an owner's guide in `deploy/README.md`.
  - TimescaleDB is a StatefulSet with a volume on local-path. Its password Secret is generated once
    (looked up, `resource-policy: keep`), so the volume and password survive uninstall and reinstall.
  - Collector and dashboard are on by default. The dashboard Ingress is optional, with a Traefik
    basic-auth Middleware (`traefik.io/v1alpha1`).
  - The bot is OFF by default: replicas 1, Recreate, its Hyperliquid Secret required (keys
    `address`, `agentKey`).
  - Scraper and viewer are off by default.
  - The DSN is spliced together from the Secret via k8s `$(VAR)` expansion. A `wait-for-db` init
    container fixes the collector/bot startup crash race.
- **CI:** `.github/workflows/build.yml`.
  - test (py3.12) + web build + helm lint run on everything. Ruff runs in advisory mode, because of 4
    pre-existing findings.
  - On main and `v*` tags, multi-arch (amd64+arm64) images go to `ghcr.io/vytautasboznis/coinmon-{scraper,dashboard,viewer}`,
    and the chart goes to `oci://ghcr.io/vytautasboznis/charts/coinmon` as `0.1.<run>` with
    appVersion `sha-<7>` = that commit's image tag.
- **Verified locally:**
  - CI tests in a clean python:3.12 container: 454 passed.
  - Throwaway k3s v1.34 in Docker with Helm 4.3 (alpine/helm): install, uninstall/reinstall (password
    and volume kept), collector storing prints, dashboard API, Traefik basic-auth 401/401/200.
  - The bot with fake creds reached the venue and refused on cross margin, as designed.
  - Gotcha on this machine: Git Bash rewrites `/paths`, so docker commands need `MSYS_NO_PATHCONV=1`.
- **NOT verified:** the GitHub Actions run itself, which needs a push, and GHCR package visibility.
  Action majors used: checkout@v5, setup-python@v6, setup-node@v5, docker/*@v3/v5/v6, azure/setup-helm@v4.
