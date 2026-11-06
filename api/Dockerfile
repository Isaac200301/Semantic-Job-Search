FROM python:3.11-slim

# El contenedor corre como usuario sin privilegios: la API no necesita root para
# nada, y varias plataformas lo exigen. Cloud Run no lo pide, pero no cuesta nada.
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

COPY --chown=user:user requirements.txt .

# PyTorch se instala ANTES que el resto, y desde el índice solo-CPU. La rueda por
# defecto de PyPI empaqueta las librerías de CUDA, inútiles en cualquier plan sin
# GPU, y engordan la imagen de 2,6 GB a casi 13 GB. Al quedar ya satisfecho,
# sentence-transformers no vuelve a bajarlo.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# El modelo de embeddings se descarga AQUÍ, al construir la imagen, y no en la
# primera petición. En Cloud Run importa especialmente: el contenedor escala a
# cero, así que sin esto cada arranque en frío tendría que bajar 90 MB antes de
# poder responder.
ENV HF_HOME=/home/user/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user:user . .

# Cloud Run inyecta PORT (8080 por defecto) y es quien manda. El valor de aquí
# solo sirve para ejecutar la imagen en local.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
