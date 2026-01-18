FROM python:3.11-slim

# Cloud Run fournit le port via la variable d’environnement PORT
ENV PORT=8080

# Dossier de travail dans le conteneur
WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY main.py .
COPY engine ./engine

# Lancement FastAPI (compatible Cloud Run)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
