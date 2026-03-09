FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data

ENV PORT=5000
EXPOSE ${PORT}

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 2
