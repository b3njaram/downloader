FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (e.g., ffmpeg if downloading audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt-get/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose app port and set base path environment variable
EXPOSE 8080
ENV BASE_PATH=/downloader

CMD ["python", "spotify_to_navidrome.py"]
