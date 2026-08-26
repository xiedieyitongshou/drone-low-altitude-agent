# Load Test Scripts

This directory contains k6 scripts for Day155 local load-test baselines.

## Scripts

- `k6-smoke.js`: one-shot smoke test for `/health`, `/auth/login`, `/agent/query`, and `/cruise/evaluate`.
- `k6-api.js`: deterministic weighted API baseline test covering health, Agent query, structured evaluation, task list, and trace detail.

Both scripts create random low-privilege users through `/auth/register` and then log in through `/auth/login` to obtain JWT access tokens. They do not use admin accounts.

`k6-api.js` uses a fixed 10-step request cycle instead of random branching: 10% health, 30% Agent query, 20% evaluation, 20% task list, and 20% trace detail. This keeps small local runs reproducible.

## Run Against Local Docker Compose

Start the app first:

```powershell
docker compose up -d
```

Run smoke test through the Compose network:

```powershell
docker run --rm `
  --network drone-low-altitude-agent_default `
  -v ${PWD}\scripts\load:/scripts `
  -v ${PWD}\evals\reports\load:/reports `
  -e BASE_URL=http://app:8000 `
  grafana/k6:latest run `
  --summary-export /reports/k6-smoke-summary.json `
  /scripts/k6-smoke.js
```

Or run the same smoke test with one local command through the host-mapped backend port:

```powershell
.\scripts\load\run-local-baseline.ps1 -Smoke
```

Run local baseline:

```powershell
docker run --rm `
  --network drone-low-altitude-agent_default `
  -v ${PWD}\scripts\load:/scripts `
  -v ${PWD}\evals\reports\load:/reports `
  -e BASE_URL=http://app:8000 `
  -e VUS=3 `
  -e USER_COUNT=3 `
  -e HOLD=45s `
  grafana/k6:latest run `
  --summary-export /reports/k6-local-baseline-summary.json `
  /scripts/k6-api.js
```

Or run the local baseline with one local command:

```powershell
.\scripts\load\run-local-baseline.ps1 -Vus 3 -UserCount 3 -Hold 45s
```

The one-command helper defaults to `BASE_URL=http://host.docker.internal:8000`, which works for Docker Desktop when the Compose backend publishes `8000:8000`.

## Useful Environment Variables

- `BASE_URL`: target backend URL. Use `http://app:8000` inside the Compose network.
- `RUN_ID`: optional run identifier. Defaults to current timestamp.
- `VUS`: virtual users for `k6-api.js`.
- `USER_COUNT`: random test users created during setup.
- `LOAD_TEST_PASSWORD`: password for random test users. Defaults to `LoadTestAa12`.
- `RAMP_UP`: ramp-up duration. Defaults to `15s`.
- `HOLD`: hold duration. Defaults to `45s`.
- `RAMP_DOWN`: ramp-down duration. Defaults to `10s`.
- `SLEEP_SECONDS`: sleep between iterations. Defaults to `1`.
- `REQ_P95_MS`: global request P95 threshold. Defaults to `20000`.
- `HEALTH_P95_MS`: `/health` P95 threshold. Defaults to `500`.
- `AGENT_P95_MS`: `/agent/query` P95 threshold. Defaults to `12000`.
- `EVALUATE_P95_MS`: `/cruise/evaluate` P95 threshold. Defaults to `20000`.
- `QUERY_P95_MS`: read API P95 threshold. Defaults to `1500`.

Do not commit real tokens, passwords, public server IPs, or API keys in load-test reports.
