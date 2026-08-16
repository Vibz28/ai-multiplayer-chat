FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 worker

WORKDIR /app
COPY integrations/telegram_gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY integrations/telegram_gateway/app.py /app/app.py

RUN mkdir -p /data && chown -R worker:worker /data
USER worker

CMD ["python", "/app/app.py"]
