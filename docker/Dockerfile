FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY bot/ bot/
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r bot/requirements.txt

COPY docker/entrypoint.sh . 
RUN chmod +x entrypoint.sh

USER nobody
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["./entrypoint.sh"]
