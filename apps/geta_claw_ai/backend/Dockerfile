FROM python:3.11-slim

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install system dependencies (ffmpeg and libgl1 are required for video editing/OpenCV)
RUN apt-get update && apt-get install -y curl ffmpeg libgl1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy pyproject.toml for dependency installation
COPY pyproject.toml .

# Create virtual environment and install dependencies using uv
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -r pyproject.toml

# Install Playwright (ensure it uses the virtual environment)
RUN . /opt/venv/bin/activate && \
    pip install playwright && playwright install --with-deps chromium

WORKDIR /app

# Copy the backend source code
COPY backend .
COPY scripts ./scripts
COPY zalocrm ./zalocrm

# Expose virtual environment to path
ENV PATH="/opt/venv/bin:$PATH"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
