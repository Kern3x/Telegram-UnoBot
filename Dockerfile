FROM python:3.11-slim

# system optimizations/variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Let's set up dependencies. If psycopg2 (not binary) is available, libpq-dev and build-essential are required.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /var/app_data && chmod -R 777 /var/app_data

# (optional) create a non-root user
RUN useradd -m appuser
USER appuser

CMD ["python", "start_bot.py"]
