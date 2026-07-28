FROM python:3.11-slim

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

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY data/knowledge/advice_rules.json ./data/knowledge/advice_rules.json
RUN mkdir -p /app/data/knowledge/index /app/data/samples /app/scripts
COPY scripts/create_initial_admin.py ./scripts/create_initial_admin.py
COPY tests ./tests
COPY pytest.ini .
COPY main.py .
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x ./docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker/entrypoint.sh"]
