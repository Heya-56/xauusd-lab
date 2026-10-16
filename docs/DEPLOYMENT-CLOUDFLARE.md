# Deployment — GitHub + Cloudflare (status: NOT DEPLOYED)

Nothing has been deployed. This document is the procedure to follow once reviewed.

## What is deployable today

| Component | Target | State |
|---|---|---|
| `web/` dashboard (static) | Cloudflare Pages | Ready as static files; runs in demo mode on the synthetic snapshot |
| Deterministic core + research | GitHub Actions | Ready (`daily-research.yml`, `smoke-test.yml`) |
| API (`src/api/service.py`) | — | Service layer + tests only. **No HTTP runtime yet** |
| D1 schema | Cloudflare D1 | `migrations/0001_init.sql` ready, not applied |

### Gap: API runtime

The core is Python (stdlib only). Options to evaluate before building the API:
1. Cloudflare Python Workers (verify current GA status, limits and stdlib support first);
2. a small container/VM API (FastAPI) behind Cloudflare, with D1 or SQLite/Postgres;
3. port `src/core` to TypeScript — rejected for now: two implementations would break parity.
Recommendation: option 1 if verified suitable, else option 2. Decision pending.

## Environments & secrets

| Name | Where | Purpose |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | GitHub Actions secret (per environment) | Pages/D1 deploy — scope: *Pages Edit*, *D1 Edit* on one account only |
| `CLOUDFLARE_ACCOUNT_ID` | GitHub Actions variable | Target account |
| `HINOVA_API_KEY_HASHES` | Worker/API secret | JSON map `sha256(key) → tenant_id`; raw keys never stored |
| `D1 database_id` | wrangler config outside git / CI variable | Per environment and per client |
| `LLM_PROVIDER_API_KEY` | API secret, optional | Only if an LLM adapter is enabled; core works without it |
| Payment webhook secret | API secret, future | Provider **not selected**; no integration exists |

Never commit any of these. `.gitignore` excludes `.env*`, `.dev.vars`, `.wrangler/`.

## Procedure (Hinova account)

1. Merge request reviewed and CI green (`smoke-test`, `daily-research` fixture step).
2. `npx wrangler pages deploy web --project-name <project> --branch <env>` (preview first).
3. Check the preview URL: banner, NO_TRADE default, toggles, no console errors.
4. Promote preview → production in the Pages dashboard.

## Rollback

- Pages: *Deployments → previous deployment → Rollback* (instant, no rebuild).
- D1: migrations are additive; keep a `wrangler d1 export` before each migration.
- Git: revert the merge commit; never force-push shared branches.

## White-label (client-owned Cloudflare account)

1. Client creates their own Cloudflare account and grants a **scoped, time-limited** token
   (or runs the deploy themselves). Never reuse Hinova secrets.
2. Fork/release tag → client config: branding = replace `web/styles/tokens.css` + name/logo;
   separate D1 database; separate API key hashes.
3. Deploy with the steps above into the client account. Record the release tag.
4. Commercial terms (e.g. the proposed white-label licence fee) live in the signed contract,
   not in code or config. Licence expiry may disable new signals; it must never touch positions.
