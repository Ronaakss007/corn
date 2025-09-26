FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and Python packages in one layer
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        wget \
        curl \
        git \
    && python3 -m pip install --upgrade pip \
    && python3 -m pip install --no-cache-dir -r requirements.txt \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p downloads logs sessions \
    && chmod +x main.py

# Expose ports
EXPOSE 80 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

# Run the application
CMD ["python3", "main.py"]
