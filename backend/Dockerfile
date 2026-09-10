FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

# TODO: run as non-root user before production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
