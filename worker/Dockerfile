FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY octoscan /usr/local/bin/octoscan

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker script
COPY worker.py .

# Make script executable
RUN chmod +x worker.py

# Run as non-root user
RUN useradd -m -u 1000 scanner && \
    chown -R scanner:scanner /app
USER scanner

# Run the worker
CMD ["python3", "worker.py"]
