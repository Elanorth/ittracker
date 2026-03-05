FROM python:3.12-slim

WORKDIR /app

# Sistem bağımlılıkları (WeasyPrint için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Backup ve instance klasörlerini oluştur
RUN mkdir -p /srv/it_tracker/backups /app/instance

EXPOSE 5000

CMD ["python", "app.py"]
