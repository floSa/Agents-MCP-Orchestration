# Image de l'application (interface Streamlit + agents).
# Ollama tourne dans un conteneur séparé (voir docker-compose.yml).
FROM python:3.11-slim

# uv : gestionnaire d'environnement/dépendances
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 1) Dépendances d'abord (cache Docker tant que pyproject ne change pas)
COPY pyproject.toml ./
RUN uv sync --no-install-project

# 2) Code de l'application
COPY usine ./usine
COPY docs ./docs
RUN uv sync

EXPOSE 8501

# Streamlit accessible depuis l'extérieur du conteneur
CMD ["uv", "run", "streamlit", "run", "usine/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
