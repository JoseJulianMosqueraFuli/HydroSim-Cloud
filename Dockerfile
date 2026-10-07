FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HYDROSIM_HOST=0.0.0.0 \
    HYDROSIM_DB_PATH=/var/lib/hydrosim/scenarios.sqlite3

WORKDIR /app
COPY pyproject.toml ./
COPY hydrosim ./hydrosim

RUN useradd --system --uid 10001 hydrosim \
    && mkdir -p /var/lib/hydrosim \
    && chown hydrosim:hydrosim /var/lib/hydrosim

USER hydrosim
EXPOSE 8080

CMD ["python", "-m", "hydrosim.api"]
