# Cleanup validation ledger

Fresh validation of the current tree, 2026-10-08 (Asia/Calcutta). Earlier results are historical and are not used as evidence for this pass.

| Gate | Current result | Evidence |
| --- | --- | --- |
| Backend pytest | PASS | 105 passed, 0 failed, 1 skipped, 1 warning; final full run 96.03 seconds |
| PostgreSQL/Alembic | PASS | Separate isolated PostgreSQL 16.15: 1 passed, 1 warning; fresh upgrade, downgrade/re-upgrade, model drift/concurrency checks; one head/current revision 0004 |
| Real Redis/Celery/beat | PASS | Authenticated Redis, prefork worker and PostgreSQL; QUEUED/RUNNING/COMPLETED; 3 duplicate deliveries; forged envelope rejected by actual worker; broker outage and beat redispatch recovery; one completion |
| npm ci | PASS | 285 packages installed; 286 audited; 0 vulnerabilities reported |
| Frontend lint | PASS | ESLint, no suppressed errors |
| TypeScript | PASS | Separate tsc --noEmit and build type checking |
| Frontend production build | PASS | Next.js 16.4.0 production compilation and static generation |
| Playwright | PASS | Final full run: 11 passed, 0 failed, 0 skipped (1.3 minutes); affected rerun: 7 passed |
| Docker Compose config | PASS | Standalone Compose v5.6.0 config --quiet, generated ephemeral environment credentials |
| Docker build/startup | BLOCKED | Engine named pipe unavailable; no further retries or startup attempted in this pass |
| Solidity build | PASS | Foundry 1.8.5; current compiler outputs reused (no source changes); compiler/lint check successful |
| Foundry tests | PASS | 9 passed, 0 failed, 0 skipped |
| Actual local EVM | PASS | Anvil deployment, signed receipt, 3-block depth, confirmation rollback, receipt removal and same signed transaction rebroadcast; scientific report preserved |
| Python dependency consistency | PASS | pip check: no broken requirements; reconciled 93-package lock installed successfully on Linux Python 3.12 as well as matching the Windows environment |

The standard suite skips the PostgreSQL-only test because TEST_POSTGRES_URL is not set there; that test passed separately against a generated isolated database. One StarletteDeprecationWarning reports that its httpx TestClient integration is deprecated. npm emitted the ESLint 9 support warning; its compatible installed dependency set audited with zero reported vulnerabilities. Foundry retains an unsafe-typecast lint warning for uint64(block.timestamp); the preserved contract was not changed. Playwright emitted a NO_COLOR/FORCE_COLOR environment warning.

## Runtime identity

Windows backend used the existing parent virtual environment, Python 3.14.3: `..\.venv\Scripts\python` from sciproof. Real broker/browser services used an isolated native WSL Ubuntu Python 3.12 environment installed from requirements.lock.txt. Generated credentials and native temporary PostgreSQL data were used; no existing user database was touched.

All final frontend checks and browser tests used Node **v24.19.0** at:

`C:\Users\Tiesha\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`

The system Node v22.10.0 does not satisfy the project's >=22.13.0 requirement. Its npm shim bypassed the selected PATH during the first lint attempt; that exact project subprocess was stopped. Subsequent checks invoked the Node 24 executable directly, or the npm CLI through it with its bin directory prepended to the child PATH. No global runtime was changed.

## Corrections and fresh regression

The conflict fixture has zero reproducibility/alignment, 20 weighted integrity points and 15 weighted quality points: 35/100 => E. D is a cap on stronger grades when conflicts exist, not a minimum. The test expectation was corrected without changing production scoring.

The initial browser run had 4 passes and 7 failures. Five failure cases used an ambiguous alert locator matching the application's error and Next.js's route announcer. The two remaining failures exposed CORS preflights consuming authentication limits and 429 responses lacking CORS headers. CORS now surrounds the request middleware. Regression coverage verifies preflights do not consume attempts, real login attempts still reach 429 and permitted origins can read that response. Exact application error assertions are retained.

A targeted rerun invoked from the wrong working directory could not locate fixtures; it was rerun from apps/web. Fixture and report paths now also resolve from source locations. The final affected browser rerun passed all 7 tests, then the final full run passed all 11. No tests were deleted or weakened.

Added hardening coverage exercises actual child parsing, malformed input rejection, child credential stripping/deadline and a 22 MiB body without Content-Length. One new test initially assumed row counts were returned by the upload metadata protocol; its assertion was corrected to verify the documented MIME, byte size and original hash. The hardening suite passed all 16 tests; the full backend suite was rerun after the CORS fix and passed as recorded above.

The same locked Linux runtime ran the final real broker check after these corrections. It verifies rejection of an actual forged delivery and completion of legitimate signed deliveries, duplicate persistence counts and actual Redis outage/beat recovery. Scientific processing was not simulated inline for this gate or the browser happy path.

## Browser coverage

Registration/login, project/version creation, PDF/dataset upload, real queued processing, completion/grade, claim/evidence details, report download, provenance, logout/login and persisted history all passed. Other tests cover account isolation, invalid/oversized uploads, missing dataset, conflicting/unverifiable/unsupported claims, transport outage, authenticated artifact corruption and actual worker process loss. The loss test kills a genuine RUNNING worker and advances the stored start time past the existing 300-second policy to avoid waiting five minutes; beat persists FAILED/WORKER_TIMEOUT with no partial report.

Ignored raw browser results: `.runtime/e2e-results.json`; report screenshot: `.runtime/e2e-report.png`. Safe committed evidence summaries are `async-validation-result.json` and `blockchain-validation-result.json` in this directory. Neither contains account credentials, encryption keys or private artifacts.

## Reproduction

From sciproof, using an environment installed from requirements.lock.txt:

```powershell
python -m pytest tests -q
python -m scripts.validate_postgres --bin-dir .runtime/pgsql/bin
```

The PostgreSQL harness creates and shuts down a temporary loopback-only server. It prints heads/current/history and uses a fresh test database for downgrade checks. It does not destroy a user database.

With the existing ignored WSL binaries and pip.pyz, run bootstrap and validation within the same WSL invocation:

```text
python3 -m scripts.bootstrap_linux_python --validate-async
```

For real browser validation, keep `python3 -m scripts.bootstrap_linux_python --serve-e2e` running in WSL, start the built frontend, and run from apps/web with the compatible Node runtime:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
npm run start
# Separate terminal, same apps/web directory:
npm run e2e
```

Use the available Node 24 executable to invoke the npm CLI if the system npm shim selects an incompatible runtime. The harness has filesystem-only controls under `.runtime/e2e-control`; it adds no production test-control endpoint. Shut down the harness using its `shutdown` control and stop the owned frontend after validation.

```powershell
.\.runtime\foundry\forge.exe build --root packages/contracts
.\.runtime\foundry\forge.exe test --root packages/contracts -vv
python -m scripts.validate_blockchain --anvil .runtime/foundry/anvil.exe
```

Docker configuration requires POSTGRES_PASSWORD, REDIS_PASSWORD and STORAGE_ENCRYPTION_KEY. Do not print resolved configuration containing secrets; use config --quiet. Exact unavailable-engine error:

```text
failed to connect to the docker API at npipe:////./pipe/docker_engine; check if the path is correct and if the daemon is running: open //./pipe/docker_engine: The system cannot find the file specified.
```

Nested .pytest_cache and generated browser/contract output exclusions were added to .dockerignore. The earlier Windows cache/context failure cannot be retested through a functional image build until the engine is available. The API Dockerfile now installs the tested Python lock; an actual container build/startup is still unvalidated.

## Security and readiness limits

No tracked files or commits exist yet, so no secrets have been committed. A source private-key/token pattern scan found no matches, and manual configuration review found only placeholders in .env.example. Git ignores real dotenv files, keys/private artifacts, runtime files, caches, frontend dependencies/build outputs and generated browser artifacts. Important source/tests/docs and .env.example are available for staging.

Current tests pass ownership isolation, PRIVATE/RESTRICTED publication denial, AI deterministic failure isolation, blockchain scientific failure isolation, confirmation/rollback checks, task signing and parser/body boundaries. This is not an independent security certification. Parser isolation has no complete filesystem/network sandbox and Windows lacks the Linux memory/CPU rlimits. Live semantic gateway, S3, Pinata and production-chain accounts were not validated. Provider adapter tests use injected transports; actual Anvil is a local chain.

Docker engine availability remains the only blocked requested validation gate. The source tree can be reviewed for its first baseline commit with that limitation documented; no production readiness claim or automatic commit is made.
