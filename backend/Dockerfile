FROM python:3.11-slim

WORKDIR /app

# Set INSTALL_ML=false for a small image without the CrossEncoder reranker and Docling
# (PDFs then use pypdf and search uses fused hybrid ranking without reranking).
ARG INSTALL_ML=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir hatchling
RUN if [ "$INSTALL_ML" = "true" ]; then \
        pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu ".[ml]"; \
    else \
        pip install --no-cache-dir .; \
    fi
COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
