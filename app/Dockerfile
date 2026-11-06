# Una sola immagine per API e worker (D0012): cosa fa il processo lo decidono MODE e ROLE.
# La base è fissata all'indice multi-architettura: stessa base su arm64 (Mac, kind) e amd64 (AWS).
FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY *.py .
# Bytecode compilato in build: dopo un crash il riavvio non lo ricompila.
RUN python -m compileall -q . && useradd --uid 10001 --no-create-home kintsugi
USER kintsugi

EXPOSE 8000
# Forma exec: uvicorn è il processo 1 e riceve direttamente SIGKILL e SIGSTOP dal nodo (D0016).
CMD ["uvicorn", "--factory", "main:crea_app", "--host", "0.0.0.0", "--port", "8000"]
