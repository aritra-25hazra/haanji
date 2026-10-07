# Built from the repository root, not from engine/, because the vertical packs
# live outside this directory and the image has to be self contained: a managed
# host gives you an image and a port, not a volume to mount.
#
#   docker build -f engine/Dockerfile .
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY engine/pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[live,web]"

COPY engine/haanji ./haanji
COPY engine/tests ./tests

# haanji.vertical resolves the pack directory three levels up from itself,
# which is /packs once the package sits at /app/haanji.
COPY packs /packs

# The engine never runs as root: it terminates untrusted audio from the public
# telephone network.
RUN useradd --create-home --uid 10001 haanji && chown -R haanji /app
USER haanji

EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD python -c "import haanji; print('ok')" || exit 1

# A managed host tells you which port to listen on through $PORT; locally there
# is no such variable and 8090 is what the README promises.
CMD ["sh", "-c", "python -m haanji.cli serve --host 0.0.0.0 --port ${PORT:-8090}"]
