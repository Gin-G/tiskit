# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PORT=8080

# Non-root user with a fixed UID so the Pod securityContext can pin runAsUser.
RUN groupadd -g 10001 tiskit && \
    useradd -u 10001 -g 10001 -M -s /sbin/nologin tiskit

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=tiskit:tiskit app ./

USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status==200 else 1)"

ENTRYPOINT ["uvicorn"]
CMD ["main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--no-server-header", \
     "--no-access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
