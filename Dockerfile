FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system partyforge && adduser --system --ingroup partyforge partyforge \
    && mkdir -p /data/uploads && chown -R partyforge:partyforge /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R partyforge:partyforge /app

USER partyforge
EXPOSE 5050

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5050} --workers 1 --threads 4 --timeout 60 'partyforge:create_app()'"]
