

# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (build tools + libxml for bs4/lxml optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install Python deps first (better caching)
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    python -m spacy download en_core_web_sm

# Optional: install spaCy German model at build time (can be skipped with ARG)
ARG INSTALL_SPACY_MODEL=true
RUN if [ "$INSTALL_SPACY_MODEL" = "true" ]; then \
      python -m spacy download de_core_news_md || python -m spacy download de_core_news_sm; \
    fi

# Copy project
COPY . .


# Default command runs the main pipeline
CMD ["python", "-m", "src.main"]