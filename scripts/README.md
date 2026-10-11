# Maintenance scripts

Scripts in this directory apply database setup or repository maintenance
operations. Run them from the repository root or use paths shown below.

## File map

| Script | Purpose | Dependencies |
|---|---|---|
| `migrate.py` | Applies `migrations/001_init.sql` to PostgreSQL/Supabase | `python-dotenv`; `psycopg[binary]` preferred or asyncpg fallback |
| `security_audit.sh` | Bandit, pip-audit, npm audit, and detect-secrets checks | Bash, Python audit tools, Node/npm |
| `install.sh` | POSIX bootstrap installer for macOS / Linux (`curl -fsSL https://agentdrift.io/install.sh \| bash`) | POSIX shell, curl, Python 3.12+ (or uv / pipx) |
| `install.ps1` | PowerShell bootstrap installer for Windows (`irm https://agentdrift.io/install.ps1 \| iex`) | PowerShell 5.1+, Python 3.12+ (or uv / pipx) |

## Apply initial daemon migration

Set `SYNC_DATABASE_URL`, `SUPABASE_DB_URL`, or `DATABASE_URL` and run:

```bash
python scripts/migrate.py
```

The runner reads `migrations/001_init.sql`; it uses psycopg when installed and
falls back to asyncpg. It exits with an error if no URL is configured. Review
the selected SQL file and target database before running against production.
The additional cloud MCP migrations have different schemas; see
[`../migrations/README.md`](../migrations/README.md).

## Security audit

```bash
scripts/security_audit.sh
```

The script fails on missing audit tooling or any failed scan. CI installs the
tooling in `.github/workflows/security.yml`. Potential secret findings require
human review and remediation; do not baseline real credentials.

## Seed data

There is no separate seed CLI script. The daemon lifespan seeds a known
two-execution loop fixture to make sentinel behavior observable in demo/local
mode; the hybrid engine has its own `ensure_seed()` routine. Do not confuse
seed telemetry with production agent activity.
