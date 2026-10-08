# Current architecture and release boundaries

## Domain and persistence

PostgreSQL is the default; SQLite is an explicit development/test alternative with foreign keys enabled. Eighteen normalized SQLAlchemy tables hold UUID identities, ownership, sessions, numbered versions, artifacts and subtypes, scientific evidence/checks/findings/scores, provenance, publication and attestation audits. Alembic owns schema changes; the API never creates tables on startup. The intended head is `0004`.

PostgreSQL row locks serialize version allocation and sealing/upload mutations. Constraints reject duplicate identities. Scientific rows, scores, provenance and immutable report snapshots commit atomically. Direct database writes need a restricted operational role; append-only database triggers are not implemented. SQLite does not provide PostgreSQL concurrency guarantees.

## API and authentication

FastAPI exposes `/api/v1` routes and retained legacy aliases. Ownership checks protect projects, versions, artifacts, reports, publication and attestation. Argon2 passwords and eight-hour opaque sessions use HttpOnly/SameSite cookies; logout revokes the session. Origin checks include authentication endpoints. Production startup requires PostgreSQL, Celery, explicit encryption keys, HTTPS origin, secure cookies and authenticated Redis.

Requests have server-generated IDs, structured safe errors and per-process throttling (30 authentication, 60 writes, 240 reads per minute/IP). This bounded in-memory limiter is not a distributed rate limit. Paginated project/version/run lists cap at 100. Request bodies cap at 21 MiB, including chunked input; individual artifacts cap at 20 MiB. Logs contain IDs and safe error types, not passwords, tokens or artifact contents. Metrics, distributed throttling, account recovery/verification, session cleanup and operational alerting remain production work.

## Processing lifecycle

Verification persists QUEUED and seals inputs before dispatch. Domain-separated HMAC envelopes authenticate run IDs; invalid signatures are rejected before database access. JSON serialization is the only accepted task format. Atomic run claims and terminal-state checks make duplicate delivery idempotent. Workers authenticate encrypted artifacts and hashes, parse evidence, extract explicit claims, calculate deterministic statistics and commit a complete report or a safe FAILED state.

Celery beat redispatches queued runs every 30 seconds. Broker exceptions leave queued work intact. Worker hard/soft limits are 120/110 seconds; genuine RUNNING jobs older than 300 seconds become FAILED with WORKER_TIMEOUT. Failed versions remain sealed and are not automatically retried. Real PostgreSQL/authenticated Redis/prefork worker/beat validation checks QUEUED to RUNNING to COMPLETED, duplicates and outage recovery. Browser validation additionally exercises actual worker loss; exact current results are in `continuation-validation.md`.

## Scientific evidence

Seventeen deterministic rules cover row count, mean, median, min/max, sample/population variance, sample standard deviation, numeric sample size, unique mode, binary proportion/percentage, Pearson correlation and explicit binary accuracy/precision/recall/F1. Classification inputs are truth then prediction, with positive class 1. Missing observations are excluded explicitly; paired correlation uses complete pairs. Undefined computations, absent columns, tied modes and unsupported claims are UNVERIFIABLE. P-values, confidence intervals, regression and broader classification methodology remain unsupported.

Comparisons use unrounded values and absolute tolerance plus relative tolerance times absolute reported value. Reports preserve rule context, differences, policy, artifact/evidence IDs, software versions and numerical conventions. Profiles report missing cells, duplicate rows and IQR outliers without changing data.

Five configurable dimension weights sum to one. Integrity means authenticated stored bytes/hash evidence, not fraud detection. Method transparency remains zero. Contradictions take precedence, and grades cannot exceed D when a check conflicts; a score below 40 remains E. The conflicting browser fixture scores 35. Scores summarize performed checks, not scientific validity.

## Parser and storage boundaries

Upload format validation runs in a child Python process with a 25-second wall deadline and no database, Redis, encryption, signing or provider secrets in its environment. Linux additionally applies 2 GiB address-space and 20-second CPU limits. Windows has the subprocess/deadline boundary but no equivalent native memory limit. JSON nesting, PDF pages, CSV headers/dimensions and Parquet expanded metadata are bounded. This is process isolation, not a complete filesystem/network sandbox or malware scanner. Workers have task deadlines; deployment container limits remain an unvalidated Docker gate.

All visibility classes stay encrypted. Local and S3 adapters provide immutable writes, authenticated reads/hash checks and bounded authenticated streaming. Writes precede database commit with rollback cleanup; crash orphan reconciliation, retention and quotas remain operational work. Fernet requires whole-object authentication. Preserve keys and backups; production key rotation/KMS and Windows ACL policy remain deployment requirements.

## Optional layers and provenance

Disabled-by-default semantic providers use bounded schemas, HTTPS/timeouts and conservative proposal acceptance. Private remote processing is withheld unless explicitly configured. No raw dataset observations are sent by the pipeline. AI errors and proposals cannot overwrite deterministic values, scores or outcomes. Provider tests use injected transport; no live gateway was validated.

Explicit owner consent permits Pinata publication only for PUBLIC artifacts. PRIVATE/RESTRICTED publication is rejected before provider calls. CID and raw SHA-256 are separate. Tests cover encrypted S3 and publication through injected clients/transports; live accounts remain unvalidated.

Optional EVM attestation persists signed transactions before broadcast, reserves nonces under PostgreSQL advisory locks and confirms only verified canonical receipts, matching events/registry records and configured depth. Refresh can revoke CONFIRMED after depth/receipt rollback. Chain failures never fail scientific verification. Actual isolated Anvil validation is separate from production-chain deployment; signer coordination, KMS, fee replacement and automatic finality monitoring remain operational limitations.

Canonical sorted compact JSON includes identifiers, original hashes/protected references, versions, conventions, scores and weights. SHA-256 provenance is Python canonicalization, not RFC 8785. Attestation is a live audit overlay; scientific snapshots remain immutable. Submitted analysis code is stored but never executed. ORCID/DOI, licensing and NFTs were not added.

See `continuation-validation.md` for the executed checks. Container build/startup and live external services are not claimed validated.
