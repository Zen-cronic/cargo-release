FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 cargo
USER cargo
EXPOSE 8080
CMD ["uvicorn", "cargo_release.api:app", "--host", "0.0.0.0", "--port", "8080"]
