FROM python:3.12-alpine AS builder
WORKDIR /app
RUN apk add --no-cache gcc musl-dev postgresql-dev
COPY pyproject.toml ./
COPY src ./src
COPY README.md ./
RUN pip install --no-cache-dir --no-compile .

FROM python:3.12-alpine
RUN apk add --no-cache libpq && apk upgrade --no-cache
RUN adduser -D -u 1000 appuser
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
# pip/setuptools are build-time only; the base image's own copies (plus their
# vendored deps, e.g. pip's bundled msgpack) have no runtime role and no
# business shipping in a production image.
RUN find /usr/local/lib/python3.12/site-packages -maxdepth 1 \
    \( -name 'pip' -o -name 'pip-*' -o -name 'setuptools' -o -name 'setuptools-*' \
       -o -name 'pkg_resources' -o -name '_distutils_hack' \) -exec rm -rf {} +
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["python", "-m", "uvicorn", "ansari.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
