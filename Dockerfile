FROM python:3.12-slim

# Install system dependencies including locale support
RUN apt-get update && apt-get install -y \
    locales \
    && rm -rf /var/lib/apt/lists/* \
    && localedef -i ro_RO -c -f UTF-8 -A /usr/share/locale/locale.alias ro_RO.UTF-8

# Set locale
ENV LANG ro_RO.utf8

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/2025

EXPOSE 5005

CMD ["python", "app.py"]
