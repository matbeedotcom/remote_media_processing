# RemoteMedia Remote Execution Service
# Multi-stage build for security and efficiency

# Build stage - compile gRPC and dependencies
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create build directory
WORKDIR /build

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy proto files and generate gRPC code
COPY protos/ ./protos/
RUN python -m grpc_tools.protoc \
    --proto_path=protos \
    --python_out=. \
    --grpc_python_out=. \
    protos/*.proto

# Runtime stage - minimal runtime environment
FROM python:3.11-slim as runtime

# Install runtime dependencies and security tools
RUN apt-get update && apt-get install -y \
    # Security and sandboxing tools
    bubblewrap \
    firejail \
    # System monitoring tools
    procps \
    psmisc \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for service
RUN groupadd -r remotemedia && \
    useradd -r -g remotemedia -d /app -s /bin/bash remotemedia

# Create application directories
RUN mkdir -p /app/src /app/sandbox /app/logs /app/config && \
    chown -R remotemedia:remotemedia /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/remotemedia/.local

# Copy generated gRPC code
COPY --from=builder /build/*.py /app/src/

# Copy application source code
COPY src/ /app/src/
COPY config/ /app/config/

# Set up Python path
ENV PYTHONPATH=/app/src:/home/remotemedia/.local/lib/python3.11/site-packages
ENV PATH=/home/remotemedia/.local/bin:$PATH

# Configure security settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Service configuration
ENV GRPC_PORT=50051
ENV LOG_LEVEL=INFO
ENV SANDBOX_ENABLED=true
ENV MAX_WORKERS=4
ENV SANDBOX_TYPE=bubblewrap

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python /app/src/health_check.py || exit 1

# Switch to non-root user
USER remotemedia
WORKDIR /app

# Expose gRPC port
EXPOSE 50051

# Start the service
CMD ["python", "/app/src/server.py"] 