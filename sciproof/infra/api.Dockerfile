FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY apps apps
COPY packages packages
COPY migrations migrations
COPY alembic.ini .
RUN useradd --uid 10001 --create-home sciproof && mkdir /data && chown sciproof /data
USER sciproof
ENV STORAGE_ROOT=/data/artifacts
CMD ["uvicorn","apps.api.main:app","--host","0.0.0.0","--port","8000"]
