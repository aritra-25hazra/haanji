FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[live,web]"

COPY haanji ./haanji
COPY tests ./tests

# The engine never runs as root: it terminates untrusted audio from the public
# telephone network.
RUN useradd --create-home --uid 10001 haanji && chown -R haanji /app
USER haanji

EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD python -c "import haanji; print('ok')" || exit 1

CMD ["python", "-m", "haanji.cli", "serve", "--host", "0.0.0.0", "--port", "8090"]
