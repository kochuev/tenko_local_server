FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATE_PATH=/data/state.json
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 tenko \
    && useradd --uid 10001 --gid tenko --no-create-home tenko \
    && mkdir /data && chown tenko:tenko /data
COPY tenko ./tenko
USER tenko
EXPOSE 9080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('HTTP_PORT','9080')+'/health',timeout=3)"
CMD ["python", "-m", "tenko"]
