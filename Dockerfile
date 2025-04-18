# Basisimage verwenden
FROM python:3.10-slim

# Arbeitsverzeichnis setzen
WORKDIR /app

# Abhängigkeiten installieren
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsm6 libxext6 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Anwendungscode kopieren
COPY main.py .
COPY web /web

# Flask-Port freigeben
EXPOSE 5000

# Hauptbefehl
CMD ["python", "main.py"]