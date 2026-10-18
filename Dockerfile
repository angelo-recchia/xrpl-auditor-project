FROM python:3.11-slim

# Instalar dependencias del sistema y navegadores para soporte de Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar archivos de dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Comando de ejecución por defecto del Sentinel 24/7
CMD ["python", "run_sentinel.py"]
