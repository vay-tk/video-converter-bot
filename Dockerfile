# Multi-stage build for optimized image size
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ffprobe \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --user-group --uid 1000 botuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/botuser/.local

# Copy application code
COPY --chown=botuser:botuser . .

# Create temp directory with proper permissions
RUN mkdir -p /app/temp && chown -R botuser:botuser /app/temp

# Switch to non-root user
USER botuser

# Add local Python packages to PATH
ENV PATH=/home/botuser/.local/bin:$PATH

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TEMP_DIR=/app/temp

# Expose port (if needed for health checks)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import psutil; exit(0 if psutil.cpu_percent() < 100 else 1)" || exit 1

# Run the bot
CMD ["python", "run.py"]
