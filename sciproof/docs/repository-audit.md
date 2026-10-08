# Repository audit — continuation baseline

Completed before refactoring. Existing source is preserved in `baseline_api.py.txt`; Git contains no tracked application baseline, so no user changes were discarded.

This is a historical audit of the original implementation, not the current project status. Its unavailable/pending checks and proposed changes are superseded by `architecture.md`, `continuation-validation.md` and the current status in `phase-progress.md`.

## Current architecture

Next.js 16.4 / React 19 single-page dashboard; FastAPI API; SQLite `records` table containing typed JSON; local Fernet storage; pandas deterministic engine; Pydantic-constrained regex claim extractor; standalone immutable Solidity registry. Synchronous verification, no workers or migrations.

## Working components

Re-ran 13 pytest tests successfully, including manuscript PDF extraction to report, dataset calculations, authorization boundaries, malformed filenames/content, and upload rejection after verification. Frontend production compilation and TypeScript succeeded. Local provider clearly discloses semantic AI unavailability; uploaded code execution is disabled.

## Technical debt

All domain data is embedded in JSON without foreign keys. Version numbers, consistent timestamps, complete artifact MIME/storage metadata, evidence entities and migration history are absent. Report scoring mislabels data readability as integrity assurance; mean tolerance lacks method-specific explanation. No durable run lifecycle. Backend module initializes database/storage on import. Frontend expects immediate completion and has no historical runs.

## Security risks

Concurrent upload and verification can change inputs; database-first writes can leave orphan metadata. PDF/Parquet decompression and parser CPU/memory are not bounded. Local generated key is unsafe as a production default. Login has no throttling or recovery/verification. Cookie origins do not protect auth endpoints. Multiple artifact types can ambiguously select the last uploaded file. Files are private but PUBLIC/RESTRICTED policies have no domain constraints.

## Broken or unverified components

Docker and Foundry executables are unavailable. Container builds, PostgreSQL migrations, browser E2E and Solidity compilation were not tested. Prior contract tests exist but event tests are absent. Live semantic providers, storage publication and real attestations are intentionally unavailable.

## Next changes

Move source under `sciproof/`; SQLAlchemy UUID entities, PostgreSQL default, Alembic initial schema; migrate legacy records with a separate explicit non-destructive importer; transactional version locks and numbered versions; encrypted artifact abstraction and visibility metadata; queued Celery verification with DB-backed recovery; relational checks/evidence/findings/scores and provenance snapshots. Preserve synchronous test execution and dashboard response fields. Add migration, constraints, failure and async lifecycle tests. No licensing/NFT or uploaded-code execution.
