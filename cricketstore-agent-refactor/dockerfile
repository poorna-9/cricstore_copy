FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libpq-dev && apt-get clean

COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app/
CMD ["gunicorn", "cricketstore.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
EXPOSE 8000
