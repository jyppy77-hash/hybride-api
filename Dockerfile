FROM python:3.11-slim

# Variables d'environnement
ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copie et installation des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de tout le code
COPY . .

# Exposition du port (important pour Cloud Run)
EXPOSE 8080

# Démarrage avec uvicorn
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
```

**Changements clés :**
- `COPY . .` au lieu de copier fichier par fichier (plus safe)
- `exec` devant uvicorn (meilleure gestion des signaux sous Cloud Run)
- `EXPOSE 8080` explicite

**Crée un `.dockerignore` pour optimiser :**
```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.git
.gitignore
.vscode
*.md
tests/