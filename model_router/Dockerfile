FROM python:3.14-slim

WORKDIR /app

COPY model_router/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY model_router/__init__.py model_router/app.py /app/model_router/

RUN useradd --create-home --uid 10001 router && chown -R router:router /app

EXPOSE 8181

CMD ["uvicorn", "model_router.app:app", "--host", "0.0.0.0", "--port", "8181"]
