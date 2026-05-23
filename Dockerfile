# bot_builder_service Dockerfile - CPU Version
# Flask application with PostgreSQL support (no GPU)

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install torch (rarely changes)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy requirements first for better caching
COPY requirements-cpu.txt ./requirements.txt

# Install Python dependencies (CPU-only PyTorch)
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -r requirements.txt

# Download spaCy models
RUN python -m spacy download en_core_web_sm || true && \
    python -m spacy download en_core_web_lg || true

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads knowledge_bases logs static/routes

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "--timeout", "120", "run:app"]
