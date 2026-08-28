# Multi-stage build for optimized image size
FROM python:3.12-slim as builder

WORKDIR /app

# Use a venv so installed packages aren't tied to the builder's root home dir
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
# CPU-only torch wheel (project uses EMBEDDING_DEVICE=cpu) avoids ~3GB of unused CUDA packages
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Copy the venv (readable/usable regardless of which user runs the process)
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN useradd -m -u 1000 chatbot && \
    chown -R chatbot:chatbot /app /opt/venv

USER chatbot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Run the application
CMD ["python", "-m", "api.main"]
