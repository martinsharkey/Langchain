# Security & Secrets

## Threat model (current)

All MT5 / account data in this project is **DEMO / test data** (VT Markets demo
account, GBP, no real funds). The exposure of demo credentials in earlier commits
(`env.txt` / `env_out.txt`, and previously a demo password in `.env.example`) is
therefore **low risk** and **key rotation is not required** (decision recorded in
project memory, ref issue #45). If this project is ever pointed at a **real-money**
account, that decision MUST be revisited: rotate immediately and scrub history.

## Rules (always)

- **Never commit real secret values.** `.env`, `.env.*`, and
  `cryptorti/.env.cryptorti` are gitignored; only `.env.example` (placeholders
  only) is tracked.
- `.env.example` documents the *shape* of configuration. It must contain
  placeholders (`your_mt5_password`), never live values.
- Secrets at rest live in exactly one of:
  1. a local, gitignored `.env` (developer machine), or
  2. **GitHub Actions Secrets** (CI) / environment secrets (VPS deploy).

## GitHub Secrets approach (CI / VPS)

Store each secret in the repo's **Settings → Secrets and variables → Actions**:

| Secret name | Purpose |
|---|---|
| `MT5_ACCOUNT` | MT5 demo login |
| `MT5_PASSWORD` | MT5 demo password |
| `MT5_SERVER` | MT5 server (e.g. `VTMarkets-Demo`) |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` … | LLM providers (optional; `USE_KILO_GATEWAY=true` needs none) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | CryptoRTI S3 (optional) |

CI reads them from the `secrets` context and exposes them as env vars to the job.
Nothing is written to disk in CI. For a VPS, inject the same names via the host's
environment / a secrets manager, not a committed file.

> **Note:** the ready-made workflow lives at `ci_templates/ci.yml.template`. Adding
> it under `.github/workflows/` requires a token with the `workflow` OAuth scope, so
> copy it into place manually:
> `mkdir -p .github/workflows && cp ci_templates/ci.yml.template .github/workflows/ci.yml`
> then commit with a `workflow`-scoped credential.

### Local developer setup

```
cp .env.example .env       # then fill in real DEMO values locally
```

`.env` stays on your machine and is never committed.

## If this ever becomes real-money

1. Rotate the MT5 password and every API key.
2. Scrub git history (`git filter-repo`) to remove any historically committed
   secret files, then force-push and re-clone everywhere.
3. Move to short-lived, least-privilege credentials.
