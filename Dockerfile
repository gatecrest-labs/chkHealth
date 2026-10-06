FROM python:3.12-slim

RUN addgroup --gid 1000 app \
 && adduser --uid 1000 --gid 1000 --no-create-home --disabled-password app

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
 && uv sync --no-dev --extra prod

COPY app/ app/
COPY wsgi.py manage_users.py ./

ENV PYTHONUNBUFFERED=1 \
    USERS_FILE=/app/data/users.json \
    GROUPS_FILE=/app/data/groups.json \
    APP_SETTINGS_FILE=/app/data/app_settings.json \
    METRICS_DB_PATH=/app/data/metrics.db

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"

USER app

CMD ["uv", "run", "gunicorn", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120", \
     "wsgi:application"]
