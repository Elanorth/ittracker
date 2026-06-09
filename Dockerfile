# ════════════════════════════════════════════════════════════════════
# Stage 1 — builder: Python bağımlılıklarını izole prefix'e kur
# gcc + dev header'lar SADECE burada; runtime image'a sızmaz (boyut tasarrufu).
# ════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS builder

WORKDIR /app

# Bazı paketler (psycopg2 dahil bir kısmı) sdist'ten derlenirse gerekli.
# psycopg2-binary çoğu zaman wheel; yine de güvenli derleme için gcc + libffi-dev.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --prefix=/install: paketleri taşınabilir bir ağaca kurar; runtime stage'e
# tek COPY ile alınır. pip/setuptools/wheel cache runtime'a gitmez.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ════════════════════════════════════════════════════════════════════
# Stage 2 — runtime: sadece çalışma-zamanı sistem kütüphaneleri + kurulu paketler
# WeasyPrint runtime'da libpango/libgdk-pixbuf .so'larına ihtiyaç duyar (build değil).
# ════════════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# WeasyPrint runtime kütüphaneleri + fontlar (libffi8 = runtime, libffi-dev değil)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi8 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Builder'da kurulmuş Python paketlerini al (/install → /usr/local)
COPY --from=builder /install /usr/local

COPY . .

# Backup ve instance klasörleri
RUN mkdir -p /srv/it_tracker/backups /app/instance

EXPOSE 5000

CMD ["python", "app.py"]
