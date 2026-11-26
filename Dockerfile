FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# libzbar0: native decoder used by pyzbar; libglib2.0-0: required by OpenCV
RUN apt-get update \
 && apt-get install -y --no-install-recommends libzbar0 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --system --uid 10001 appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# Apply migrations, then serve. --proxy-headers so rate limiting sees the real client IP behind a proxy.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
