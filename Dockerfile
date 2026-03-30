FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor/ ./monitor/

# config.yml and /app/data are provided at runtime via volume mounts —
# see docker-compose.yml. Nothing config-related is baked into the image.
CMD ["python", "-m", "monitor.main"]
