FROM python:3.11-slim

WORKDIR /app

# Copy shared module FIRST (critical for imports)
COPY shared ./shared

# Copy service requirements and install
COPY services/execution-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/execution-service/app ./app
COPY services/execution-service/core ./core

# Set environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV LOG_LEVEL=INFO
ENV SERVICE_PORT=8006

EXPOSE 8006

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8006/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
