# Deployment — GitHub + Cloudflare (status: NOT DEPLOYED)

Nothing has been deployed. Everything below is prepared and tested locally; a deployment needs
your explicit go and the secrets listed here.

## Architecture

```
MT5 terminal ── HinovaBridge.mq5 ──HTTPS (terminal key)──┐
                                                           ▼
Browser ── Cloudflare Pages (web/) ──HTTPS (session)──▶ Cloudflare Worker (workers/accounts-api) ── D1
                                                           │  accounts, trial, terminal keys, configs, signals
                                                           │  HMAC-signed request (ENGINE_SECRET)
                                                           ▼
                                      Python engine container (Dockerfile.engine, src/api/engine_http.py)
                                      stateless: validates configs, computes signals, never stores, never trades
```

- The Worker never computes a signal; the engine never sees credentials or sessions and accepts only
  requests signed by the Worker (60 s window).
- The engine is a standard container: run it on any host you control (Cloudflare Containers, Fly.io,
  Railway, a small VPS). It needs no database and no outbound network.

## What is ready / verified

| Component | Verified how | Deployed |
|---|---|---|
| Engine service | 6 unit tests + real socket test; started with the container's exact command | no |
| Accounts / gateway Worker | 14 unit tests + 2 integration tests against the real engine; full browser run in `wrangler dev` | no |
| D1 schema | migrations 0001–0003 applied to a local D1 by wrangler | no |
| Dashboard + account pages | Chromium run: sign-up → verify link → terminal key → config → EA signal → live dashboard | no |
| Engine image | Dockerfile written; **not built here** (no Docker daemon in this sandbox) | no |
| MT5 EAs | not compiled here (MetaEditor is Windows-only) | — |

## Preview deployment safety gate

The manual workflow requires `D1_PREVIEW_DATABASE_ID` and targets the dedicated database name `hinova-trading-lab-preview` and Worker name `hinova-accounts-api-preview`. Create a separate preview D1 database and set that variable to its ID only; never reuse a production database ID. The workflow validates required secrets/variables and tests before it applies remote migrations. It deploys the Worker and the Pages `preview` branch only. It does **not** build or host the Python engine container, which must already be reachable over HTTPS at `ENGINE_URL`.

## Secrets and variables

| Name | Where | Purpose |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | GitHub secret (environment `preview`) | Workers Scripts Edit, D1 Edit, Pages Edit — one account only |
| `ENGINE_SECRET` | GitHub secret → Worker secret; same value as `HINOVA_ENGINE_SECRET` on the engine host | HMAC between Worker and engine (≥ 32 random chars) |
| `TURNSTILE_SECRET` | GitHub secret → Worker secret | Anti-bot on sign-up and password reset (Cloudflare Turnstile, free) |
| `RESEND_API_KEY` | GitHub secret → Worker secret | Verification and reset e-mails (provider: Resend; replaceable in `email.js`) |
| `CLOUDFLARE_ACCOUNT_ID`, `D1_PREVIEW_DATABASE_ID`, `PAGES_PROJECT` | GitHub variables | Targets |
| `DASHBOARD_ORIGIN`, `ACCOUNTS_API_URL`, `ENGINE_URL`, `EMAIL_FROM`, `TURNSTILE_SITEKEY` | GitHub variables | Public configuration |

Never commit any of these. `.gitignore` excludes `.env*`, `.dev.vars`, `.wrangler/`, `workers/*/wrangler.toml`.
Without `TURNSTILE_SECRET` or the e-mail key, sign-up refuses (fails closed) unless `DEV_MODE=true`,
which must only be used locally.

## First preview deployment (once you approve)

1. Create a dedicated preview D1 database: `npx wrangler d1 create hinova-trading-lab-preview` → set its ID as `D1_PREVIEW_DATABASE_ID`. Do not use the production database ID.
2. Create a Turnstile widget (Cloudflare dashboard → Turnstile) for the dashboard domain → site key + secret.
3. Create a Resend account, verify the sending domain → API key.
4. Run the engine container: `docker build -f Dockerfile.engine -t hinova-engine .` and
   `docker run -e HINOVA_ENGINE_SECRET=… -p 8090:8090 hinova-engine` on your host, behind HTTPS.
5. Fill the GitHub secrets/variables above (environment `preview`).
6. GitHub → Actions → **Deploy preview (manual)** → type `deploy-preview`. The job re-runs all tests,
   applies migrations, deploys the Worker and its secrets, then the dashboard to the Pages `preview` branch.
7. Check: sign-up e-mail arrives, verification link works, terminal key, then the EA on a **demo** MT5 account.

## Local development

```bash
python -m src.api.engine_http                     # with HINOVA_ENGINE_SECRET set
cd workers/accounts-api && cp wrangler.example.toml wrangler.toml   # set DEV_MODE="true", ENGINE_URL=http://127.0.0.1:8090
printf 'ENGINE_SECRET=<same secret>\n' > .dev.vars
npx wrangler d1 migrations apply hinova-trading-lab --local && npx wrangler dev --local
python -m http.server 8765 --directory web       # web/config.js: HINOVA_ACCOUNTS_API = "http://localhost:8787"
```

## Rollback

- Worker: Cloudflare dashboard → Workers → *Deployments* → roll back to the previous version.
- Pages: *Deployments* → previous deployment → *Rollback* (instant).
- D1: migrations are additive; export first: `npx wrangler d1 export hinova-trading-lab --remote --output backup.sql`.
- Engine: redeploy the previous image tag.
- Git: revert the merge commit; never force-push shared branches.

## White-label (client-owned Cloudflare account)

1. The client creates their Cloudflare account and grants a **scoped, time-limited** token (or runs the
   workflow themselves). Never reuse Hinova secrets: new `ENGINE_SECRET`, Turnstile keys, e-mail key, D1.
2. Branding: replace `web/styles/tokens.css`, name and logo; configuration in `web/config.js` and the
   Worker variables — never in core code.
3. Deploy with the same workflow in the client's GitHub environment. Record the release tag.
4. Commercial terms (e.g. the proposed licence fee) live in the signed contract, not in code. Licence
   expiry may disable new signals; it must never touch positions.
