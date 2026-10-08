# Current development status

Updated 2026-10-08. This replaces the historical in-progress ledger. Only executed checks count as passing; current evidence is in `continuation-validation.md`.

## Implemented scope

- A: normalized PostgreSQL/Alembic domain, durable runs and isolated real infrastructure validation.
- B: seventeen explicit deterministic rules, numerical policy, relational evidence and versioned provenance.
- C: optional schema-constrained semantic gateway with deterministic failure isolation, disabled by default.
- D: encrypted local/S3 provider boundaries and explicit owner-consented PUBLIC-only Pinata publication, disabled by default.
- E: preserved registry, nine contract tests and optional recoverable EVM attestation with actual confirmation checks.
- F/current cleanup: versioned API, structured safe errors, bounded paging, throttling, production configuration validation, body limits, upload parser subprocess isolation, signed verification envelopes and real browser workflow/failure tests.

## Bounded cleanup

The conflicting manuscript fixture correctly scores 35/100 (grade E). The browser test was corrected; production scoring was unchanged. Error locators target the application main region, avoiding Next.js's route announcer. Fixture/report paths resolve against source locations rather than the invocation directory. CORS now surrounds throttling: legitimate preflights do not consume authentication attempts and permitted origins can read 429 responses. The 30/min authentication limit remains enforced.

The Python lock is reconciled against the actual environment, including boto3/web3 and a Windows-only pywin32 marker. The Linux validation harness and API Dockerfile use this lock. Existing Node v24.19.0 was used without changing the global Node installation. Nested Docker test caches and generated outputs are excluded; dotenv secrets remain ignored while `.env.example` is available for staging.

## Current validation

Backend full suite: 105 passed, zero failed, one PostgreSQL-only skip and one dependency deprecation warning. The separate fresh PostgreSQL gate passed, with one intended head `0004`, no model drift and migration/concurrency checks. Frontend lint, strict TypeScript and production build passed. Foundry: nine passed, zero failed/skipped. Actual isolated Anvil confirmations/rollback/rebroadcast passed. Real signed Redis/Celery/beat passed, including actual-worker forged-envelope rejection and Redis outage/beat recovery. Final browser suite: eleven passed, zero failed/skipped.

Docker Compose configuration passes. Image build/startup remains BLOCKED because the engine named pipe is unavailable. The earlier Windows cache/context failure was addressed through ignore rules, but an engine-backed build is required to validate that correction.

## Boundaries and stop state

Provider adapter tests do not claim live S3, Pinata or semantic gateway validation. Anvil is a local chain, not a production deployment. Parser subprocess isolation is not a complete OS sandbox. Scores do not certify scientific validity. No submitted code execution, licensing/NFT features or deployment work was added.

This run was cleanup and validation only. The previous project harness and all newly started validation services were shut down. Unrelated Codex and IDE processes were left untouched. No next development milestone is authorized. No Git commit was created. Work stops after the final report.
