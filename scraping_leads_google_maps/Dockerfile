# Usamos una imagen ligera de Python
FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y permitir logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Instalar dependencias del sistema necesarias para Playwright, navegadores y proxy
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar archivos de dependencias e instalar
COPY scraping_leads_google_maps/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar los navegadores de Playwright (solo chromium para ahorrar espacio)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copiar el resto de la aplicación
COPY scraping_leads_google_maps/ .

# Variables del proxy y del scraper (rotación, lotes y back-off)
ENV PROXY_ENABLED=0
ENV PROXY_PORTS=0
ENV PROXY_UPSTREAMS=
ENV PROXY_ROTATE_EVERY=10
ENV BATCH_SIZE=10
ENV ROTATE_EVERY=10
ENV MAX_RETRIES=3
ENV BACKOFF_BASE=2.0

# Exponer el puerto de Flask y el rango de puertos dinámicos del proxy
EXPOSE 5000 8000-8010

# Comando para ejecutar la aplicación
CMD ["python", "app.py"]
