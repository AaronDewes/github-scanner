FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scheduler script
COPY scheduler.py .

# Make script executable
RUN chmod +x scheduler.py

# Run as non-root user
RUN useradd -m -u 1000 scheduler && \
    chown -R scheduler:scheduler /app
USER scheduler

# Run the scheduler
CMD ["python3", "scheduler.py"]
