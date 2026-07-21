FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY data/knowledge/advice_rules.json ./data/knowledge/advice_rules.json
COPY main.py .
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x ./docker/entrypoint.sh && mkdir -p /app/data/knowledge/index /app/data/samples

EXPOSE 8000

ENTRYPOINT ["./docker/entrypoint.sh"]
