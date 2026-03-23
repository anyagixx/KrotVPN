# KrotVPN Backend Dockerfile
FROM python:3.11-slim

LABEL maintainer="KrotVPN"
LABEL description="Commercial VPN Service with AmneziaWG"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    ipset \
    iptables \
    qrencode \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash krotvpn

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Create directories
RUN mkdir -p /app/logs /app/data && \
    chown -R krotvpn:krotvpn /app

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
