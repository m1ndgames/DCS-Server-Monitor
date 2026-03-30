FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor/ ./monitor/

# State is persisted to /app/data
VOLUME ["/app/data"]

CMD ["python", "-m", "monitor.main"]
