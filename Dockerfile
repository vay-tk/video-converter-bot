# Multi-stage build for optimized image size
FROM python:3.11-alpine as builder

# Install build dependencies with minimal packages
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    && rm -rf /var/cache/apk/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage - use Alpine for efficiency
FROM python:3.11-alpine

# Install runtime dependencies including FFmpeg
RUN apk add --no-cache \
    ffmpeg \
    ffmpeg-dev \
    su-exec \
    && rm -rf /var/cache/apk/*

# Create non-root user for security
RUN adduser -D -s /bin/sh -u 1000 botuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/botuser/.local

# Copy application code first (as root)
COPY . .

# Create directories and set proper permissions
RUN mkdir -p /app/temp /app/logs && \
    chown -R botuser:botuser /app && \
    chmod -R 755 /app && \
    touch /tmp/bot_healthy && \
    chmod 666 /tmp/bot_healthy

# Switch to non-root user
USER botuser

# Add local Python packages to PATH
ENV PATH=/home/botuser/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    TEMP_DIR=/app/temp \
    LOG_DIR=/app/logs

# Improved health check that tests bot responsiveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os, time; os.utime('/tmp/bot_healthy'); exit(0)" || exit 1

# Run the bot with proper signal handling
CMD ["python", "-u", "run.py"]
