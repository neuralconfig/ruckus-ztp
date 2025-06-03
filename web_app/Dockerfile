FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy web_app requirements and install
COPY web_app/requirements.txt web_app/
RUN pip install --no-cache-dir -r web_app/requirements.txt

# Copy main requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Install the ZTP agent package
RUN pip install -e .

# Create directories for uploads and configs
RUN mkdir -p /app/uploads /app/config /app/logs

# Set environment variables for Cloud Run
ENV PYTHONPATH=/app
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Create a non-root user (required for Cloud Run)
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/api/status')" || exit 1

# Command to run the application
CMD ["python", "-m", "uvicorn", "web_app.main:app", "--host", "0.0.0.0", "--port", "8080"]