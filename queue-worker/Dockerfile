FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy queue worker script
COPY queue_worker.py .

# Make script executable
RUN chmod +x queue_worker.py

# Run as non-root user
RUN useradd -m -u 1000 queueworker && \
    chown -R queueworker:queueworker /app
USER queueworker

# Run the queue worker
CMD ["python3", "queue_worker.py"]
