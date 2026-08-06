# syntax=docker/dockerfile:1

FROM python:3.13-slim AS dependencies

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md alembic.ini ./
COPY src/ src/
COPY alembic/ alembic/

RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.13-slim AS runtime

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY --from=dependencies /opt/venv /opt/venv
COPY --from=dependencies /build/alembic.ini /home/appuser/alembic.ini
COPY --from=dependencies /build/alembic /home/appuser/alembic

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser
WORKDIR /home/appuser

EXPOSE 8000

CMD ["uvicorn", "ai_runtime.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
