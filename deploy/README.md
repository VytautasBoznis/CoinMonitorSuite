# Running CoinMonitorSuite on k3s

GitHub builds the images and the Helm chart, and your cluster runs them.

| What | Runs | Default |
|---|---|---|
| `timescaledb` | Postgres + TimescaleDB, data on a k3s volume | on |
| `collector` | Bybit liquidation collector (feeds the cascade pane and tape) | on |
| `dashboard` | The web UI + API (terminal and War Room) | on |
| `bot` | The live F8 ladder bot (testnet until you flip it) | **off** |
| `scraper`, `viewer` | Research candle scraper and Streamlit viewer | off |

Commands are single-line so they paste into PowerShell or bash. Run them from any machine that has
`kubectl` access to the cluster.

---

## 1. Push, and let GitHub build everything

Commit and push to `main`. The **Actions** tab shows a `build` run:

1. `test`, `web`, `chart`: the Python tests, the web build, and the chart lint.
2. `images`: three images for amd64 and arm64. The first run takes ~15-20 min; later runs use the cache.
3. `publish-chart`: the Helm chart, pinned to exactly those images.

When it's green you have:
- `ghcr.io/vytautasboznis/coinmon-scraper`, `-dashboard` and `-viewer`, tagged `sha-<commit>` and `latest`.
- The chart at `oci://ghcr.io/vytautasboznis/charts/coinmon`, version `0.1.<run number>`.

Pull requests only run the tests.

## 2. Let the cluster pull them

GHCR packages from a private repo are private. Pick one option:

- **A. Make them public.** Open github.com → your profile → **Packages**. For each of `coinmon-scraper`,
  `coinmon-dashboard`, `coinmon-viewer` and `charts/coinmon`: **Package settings → Change visibility →
  Public**. The images contain no secrets, but anyone could download your code.
- **B. Keep them private.** On GitHub create a classic token (**Settings → Developer settings →
  Personal access tokens → Tokens (classic)**) with only the `read:packages` scope. Then:
  ```
  kubectl create namespace coinmon
  kubectl -n coinmon create secret docker-registry ghcr-pull --docker-server=ghcr.io --docker-username=VytautasBoznis --docker-password=<the token>
  helm registry login ghcr.io -u VytautasBoznis
  ```
  `helm registry login` asks for a password: paste the token. Then add
  `--set "images.pullSecrets[0].name=ghcr-pull"` to the install in step 4.

## 3. Tools on your machine

- **kubectl pointed at k3s:**
  1. Copy `/etc/rancher/k3s/k3s.yaml` from the k3s server to `~/.kube/config`.
  2. In that file, change `127.0.0.1` to the server's IP.
  3. Check with `kubectl get nodes`.
- **Helm:** `winget install Helm.Helm` on Windows; see helm.sh for other systems.

## 4. Install

```
helm upgrade --install coinmon oci://ghcr.io/vytautasboznis/charts/coinmon -n coinmon --create-namespace
kubectl -n coinmon get pods -w
```

Within a couple of minutes (the first image pull is slower), `coinmon-timescaledb-0`, the collector
and the dashboard show `Running`. The collector logs `waiting for the database` until Postgres is
up, then `865 perps over 5 connections`. Check with
`kubectl -n coinmon logs deploy/coinmon-collector`.

## 5. Open the dashboard

**A. Port-forward.** This is the safest option: only your machine can reach the dashboard.
```
kubectl -n coinmon port-forward svc/coinmon-dashboard 8502:8502
```
Then open http://localhost:8502, or http://localhost:8502/#warroom.

**B. From your LAN or phone, behind a login.** This goes through k3s's Traefik. The dashboard has no
login of its own, and anyone who reaches it can press PANIC or DRAIN, so always use the login.
```
kubectl -n coinmon create secret generic coinmon-dashboard-auth --type=kubernetes.io/basic-auth --from-literal=username=vytautas --from-literal=password=<a long password>
helm upgrade coinmon oci://ghcr.io/vytautasboznis/charts/coinmon -n coinmon --reuse-values --set dashboard.ingress.enabled=true --set dashboard.ingress.host=coinmon.lan --set dashboard.ingress.basicAuthSecret=coinmon-dashboard-auth
```
Point `coinmon.lan` at any node's IP, either in your router's DNS or in
`C:\Windows\System32\drivers\etc\hosts`. It's plain HTTP, which is fine at home. **Never expose it
to the internet.**

## 6. Turn on the bot

First do the Hyperliquid wallet steps (fund the wallet, create an API wallet, testnet faucet), then
set **Isolated** margin on every coin in the Hyperliquid UI. The bot refuses to start on cross margin.

**Stop any bot running on your PC first: one bot per account, ever.**

```
kubectl -n coinmon create secret generic coinmon-hyperliquid --from-literal=address=0xYourWalletAddress --from-literal=agentKey=0xYourApiWalletPrivateKey
helm upgrade coinmon oci://ghcr.io/vytautasboznis/charts/coinmon -n coinmon --reuse-values --set bot.enabled=true
kubectl -n coinmon rollout restart deploy/coinmon-dashboard
kubectl -n coinmon logs deploy/coinmon-bot -f
```

- `address` is your public wallet address. `agentKey` is the **API wallet's** key. Never use your
  secret phrase.
- These lines land in your shell history, so clear it afterwards.
- The restart makes the dashboard pick up the Secret: it shows your account, and PANIC is armed.

The log should end with `leverage {...}, 12 USDC per rung, mode HALT`. The bot is up but idle. Arm it:
```
kubectl -n coinmon exec deploy/coinmon-bot -- coinmon bot resume
```

**Stopping:**
- Use PANIC or DRAIN in the dashboard, or `kubectl -n coinmon exec deploy/coinmon-bot -- coinmon stop --now`.
- To switch the bot off, DRAIN first, then run `helm upgrade ... --reuse-values --set bot.enabled=false`.
  Switching off cancels the resting bids, but nothing would close an open position at 60 minutes.

The bot keeps its mode across restarts and upgrades. HALT stays HALT; RUN goes back to hunting.

## 7. Updating

Push to `main`, wait for the green run, then:
```
helm upgrade coinmon oci://ghcr.io/vytautasboznis/charts/coinmon -n coinmon --reuse-values
```
The newest chart points at that commit's images. To go back to an older build, add
`--version 0.1.<run number>`.

## 8. Real money (only after the testnet checks pass)

1. In the **mainnet** Hyperliquid app, create an API wallet and set Isolated margin on all 6 coins.
2. Replace the Secret and flip the flag:
   ```
   kubectl -n coinmon create secret generic coinmon-hyperliquid --from-literal=address=0xYourWalletAddress --from-literal=agentKey=0xMainnetApiWalletKey --dry-run=client -o yaml | kubectl apply -f -
   helm upgrade coinmon oci://ghcr.io/vytautasboznis/charts/coinmon -n coinmon --reuse-values --set hyperliquid.testnet=false
   ```
3. The bot and dashboard restart with the new setting. The War Room badge turns red: **LIVE MONEY**.

## Handy

- **Database from your PC:** run `kubectl -n coinmon port-forward svc/coinmon-timescaledb 15432:5432`,
  then connect as user `coinmon` to db `coinmon` on `localhost:15432`. Get the password in PowerShell:
  `[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n coinmon get secret coinmon-db -o jsonpath='{.data.password}')))`
- **Starting data:** the cluster database starts empty. Your PC's history stays on your PC.
- **Collectors:** your PC's docker-compose collector can keep running alongside the cluster one. Two
  collectors are harmless, because rows dedupe. Two bots are not.
- **Uninstall:** `helm uninstall coinmon -n coinmon` keeps the database volume and its password, and
  reinstalling picks them up again. To wipe everything:
  `kubectl -n coinmon delete pvc data-coinmon-timescaledb-0` and
  `kubectl -n coinmon delete secret coinmon-db`.
- **All settings:** see `deploy/helm/coinmon/values.yaml`. Use `--set key=value` to override one.

## Troubleshooting

| You see | Cause and fix |
|---|---|
| `ImagePullBackOff` | The packages are private and there's no pull secret. Do step 2. |
| Bot `CreateContainerConfigError` | The `coinmon-hyperliquid` Secret doesn't exist yet. Do step 6. |
| Bot restarting; log says `isolated margin required` | Set Isolated margin per coin in the Hyperliquid UI. |
| `coinmon-timescaledb-0` stuck `Pending` | There's no default StorageClass. Add `--set database.storageClass=<yours>` (`kubectl get storageclass`). |
| PANIC greyed out in the dashboard | The Secret has no `agentKey`, or the dashboard wasn't restarted after you created it (step 6). |
| Pipeline `images` job: `denied` on push | Repo **Settings → Actions → General → Workflow permissions → Read and write**. If a package already exists: **Package settings → Manage Actions access**, then add this repo with Write. |
