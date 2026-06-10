# Dockerfile
FROM python:3.12-slim

# Install system dependencies for Playwright + asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

# Copy source (after deps so code changes don't bust the dep cache)
COPY . .

# Never run as root in production
RUN useradd -m scraper
RUN chown -R scraper:scraper /app
USER scraper

# Create log dir
RUN mkdir -p logs

CMD ["python", "main.py"]
