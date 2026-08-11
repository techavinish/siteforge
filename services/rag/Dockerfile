FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# bake the embedding model into the image — cold starts must not
# download 130MB from huggingface
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY . .

ENV PORT=8002
CMD exec uvicorn main:app --host 0.0.0.0 --port $PORT
