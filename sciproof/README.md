# SciProof

Verifiable Research. Reproducible Evidence. Programmable Scientific IP.

The project root is now `sciproof/`. The API uses normalized SQLAlchemy entities with PostgreSQL by default, Alembic migrations, encrypted private artifacts and a durable Celery verification lifecycle. The existing Next.js dashboard polls asynchronous runs and downloads auditable reports. Scientific processing remains independent of AI, IPFS, wallets and blockchain.

## Start with containers

From this directory, copy `.env.example` to `.env`. Set strong hexadecimal `POSTGRES_PASSWORD` and `REDIS_PASSWORD` values and a Fernet `STORAGE_ENCRYPTION_KEY`. Generate a key using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in an environment with dependencies installed. Do not commit credentials.

```
docker compose up --build
```

Compose starts PostgreSQL, authenticated Redis, a migration job, API, worker, scheduler and frontend. Open http://localhost:3000 and http://localhost:8000/docs. Compose is configured for local HTTP; production requires HTTPS, `SECURE_COOKIES=true`, correct `WEB_ORIGIN`, managed secrets and the release gates in docs/architecture.md. Compose configuration passes; functional image build/startup is BLOCKED because this machine has no available Docker engine. An earlier build attempt also encountered a Windows context/cache error; nested test caches are now excluded through `.dockerignore`.

## Local development

Python 3.12+ and Node >=22.13.0. From `sciproof/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
$env:DATABASE_URL='postgresql+psycopg://sciproof:YOUR_PASSWORD@localhost:5432/sciproof'
$env:REDIS_URL='redis://:YOUR_REDIS_PASSWORD@localhost:6379/0'
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn apps.api.main:app --reload
```

Run a Celery worker and beat scheduler in separate terminals with the same environment. The supported deployment runtime for Celery workers is Linux (provided by Compose):

```
python -m celery -A apps.api.tasks:celery worker --loglevel=INFO --concurrency=2
python -m celery -A apps.api.tasks:celery beat --loglevel=INFO
```

For a small local demo without Redis, explicitly set `VERIFICATION_MODE=inline` in development. SQLite is an opt-in local/test backend: set `DATABASE_URL=sqlite:///./development.db`, apply Alembic migrations, and use inline mode. SQLite does not provide PostgreSQL row-lock concurrency guarantees.

Frontend:

```powershell
cd apps/web
npm ci
npm run dev
```

The pre-existing virtual environment remains at the parent workspace `.venv/`; it was reused for validation. Use `..\.venv\Scripts\python` from this root to reuse it, or create a fresh environment as shown above. Python does not automatically load `.env`; export variables in each terminal. Compose does load `.env`.

## Research workflow

Register with a password of at least 12 characters, create a project and numbered version, upload PDF and CSV/JSON/Parquet, optionally store Python/notebook analysis, then verify. Uploads default PRIVATE and remain encrypted for all visibility classes. Identical upload retries are idempotent; replacing an artifact requires a new version. Verification seals inputs immediately.

Supported explicit manuscript syntax includes `mean of accuracy = 0.85`, `median age: 32`, `row count = 120`, `correlation of x and y = 0.9`, `percentage of success = 50`. Binary proportions require values 0/1. Unsupported mappings, tied modes and undefined statistics remain unverifiable. Offline extraction is clearly disclosed and is not semantic AI.

The API returns HTTP 202 with a persisted run ID for queued work. `GET /runs/{id}` reports QUEUED/RUNNING/FAILED/COMPLETED. Redis failures leave committed queued work for the scheduler to redispatch. Duplicate delivery does not create duplicate evidence. Failed runs stay sealed; create a new version for corrected evidence. Completed snapshots preserve methods, software versions, findings, scores, weights and provenance.

## Tests and migration

```
python -m pytest tests -q
cd apps/web
npm run build
```

See docs/continuation-validation.md for current results and reproduction commands. The full backend suite passes (105 passed, one separately covered PostgreSQL skip), as do real PostgreSQL migrations, signed authenticated Redis/Celery/beat recovery, eleven browser tests and nine Foundry tests. Docker build/startup remains an unavailable engine gate. Python locking includes S3/Web3 dependencies and a Windows-only marker for pywin32; the same lock is installed by the Linux validation harness and API Dockerfile.

To import an existing legacy SQLite database into an empty migrated destination:

```
python -m scripts.import_legacy PATH_TO_OLD_DB PATH_TO_OLD_ARTIFACT_DIRECTORY
```

Source files are untouched. IDs, password hashes and plaintext artifact hashes are retained; destination encryption may use a different key. Old reports are stored as restricted encrypted REPORT artifacts. They retain original provenance and are not presented as runs from the new engine. Legacy sessions are not imported, and ambiguous duplicate artifact types fail for manual reconciliation. Keep source backups and review the import result before switching deployments.

Read docs/repository-audit.md for the historical baseline audit and docs/architecture.md for current boundaries. Optional semantic gateways, encrypted S3, explicit PUBLIC-only Pinata publication and confirmation-aware EVM attestation are implemented but disabled by default. External provider accounts and production chains are unvalidated. Scientific verification does not depend on them. Submitted code execution, licensing and NFT functionality were not introduced.
