ARG PYTHON_VERSION=3.8

FROM python:${PYTHON_VERSION}

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    python3-wheel

RUN mkdir -p /app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080

# replace APP_NAME with module name
CMD ["uvicorn", "mentos.py.main:app", "--port", "8080", "--workers", "2", "--host", "0.0.0.0"]
