FROM python:3.12-slim

RUN useradd --create-home --uid 1000 framed
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER framed
VOLUME ["/data"]
ENV FRAMED_CONFIG=/config/config.yaml FRAMED_DATA_DIR=/data
EXPOSE 8090
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/healthz', timeout=5).status == 200 else 1)"
CMD ["framed"]
