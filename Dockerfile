FROM python:3.11-slim

# Labels
LABEL maintainer="Energy Monitor"
LABEL description="Modbus TCP Energy Dashboard for Wago 762-3405"
LABEL arch="linux/arm64"

# Work dir
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/          ./app/
COPY templates/    ./templates/
COPY static/       ./static/

# Expose port
EXPOSE 5000

# Environment defaults (override via docker run -e or .env)
ENV MODBUS_HOST=192.168.1.100 \
    MODBUS_PORT=502 \
    MODBUS_UNIT_ID=1 \
    POLL_INTERVAL=2.0 \
    FLASK_ENV=production

# Run
CMD ["python", "app/server.py"]
