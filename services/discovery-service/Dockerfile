FROM python:3.11-slim

WORKDIR /app

# Copy shared module FIRST (critical for imports)
COPY shared ./shared

# Copy service requirements and install
COPY services/discovery-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/discovery-service/app ./app
COPY services/discovery-service/core ./core

# Set environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV LOG_LEVEL=INFO
ENV SERVICE_PORT=8001

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health')" || exit 1

# Run service
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
