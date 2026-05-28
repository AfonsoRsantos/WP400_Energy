FROM python:3.11-slim
LABEL description="Energy Monitor v2 - Wago 762-3405"
WORKDIR /app
RUN mkdir -p /data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY templates/ ./templates/
EXPOSE 5000
ENV MODBUS_HOST=192.168.1.100 \
    MODBUS_PORT=502 \
    MODBUS_UNIT_ID=1 \
    POLL_INTERVAL=2.0
CMD ["python", "app/server.py"]
