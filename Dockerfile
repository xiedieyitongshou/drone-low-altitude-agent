FROM python:3.11-slim

# This image intentionally contains only public application code and tooling.
# Runtime secrets, .env files, databases, backups, and server-local state must
# be injected by Docker Compose or mounted volumes, not baked into the image.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai
ENV LLM_ENABLED=false
ENV LLM_PROVIDER=none
ENV LLM_MODEL=
ENV LLM_BASE_URL=
ENV LLM_TIMEOUT_SECONDS=20
ENV LLM_MAX_TOKENS=600
ENV NL_PARSER_MODE=rule
ENV AGENT_RUNTIME_MODE=loop
ENV AGENT_LOG_RAW_PAYLOAD=false
ENV SESSION_MEMORY_BACKEND=database
ENV SESSION_MEMORY_MAXSIZE=1024
ENV SESSION_MEMORY_REDIS_KEY_PREFIX=drone_agent:session:
ENV ADVICE_KNOWLEDGE_PATH=data/knowledge/advice_rules.json
ENV KNOWLEDGE_SOURCE_PATH=
ENV KNOWLEDGE_RETRIEVER=bm25
ENV KNOWLEDGE_EMBEDDING_MIN_SCORE=0.25
ENV RAG_CONFIDENCE_THRESHOLD=0.2

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=

RUN if [ -n "$PIP_TRUSTED_HOST" ]; then \
      pip install --no-cache-dir -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" --upgrade pip; \
    else \
      pip install --no-cache-dir -i "$PIP_INDEX_URL" --upgrade pip; \
    fi

COPY requirements.txt .
RUN if [ -n "$PIP_TRUSTED_HOST" ]; then \
      pip install --no-cache-dir -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" -r requirements.txt; \
    else \
      pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; \
    fi

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY data/knowledge ./data/knowledge
RUN mkdir -p /app/data/knowledge/index /app/data/samples /app/scripts /app/evals/reports
COPY scripts ./scripts
COPY evals ./evals
COPY tests ./tests
COPY pytest.ini .
COPY main.py .
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x ./docker/entrypoint.sh

EXPOSE 8000

# The entrypoint runs `python -m alembic upgrade head` before starting FastAPI.
# On a fresh PostgreSQL volume this creates an empty schema; historical SQLite
# data migration is a separate, explicit operation.
ENTRYPOINT ["./docker/entrypoint.sh"]
