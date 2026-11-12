FROM python:3.14-slim AS leitor
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY leitor ./leitor
ENTRYPOINT ["python", "-m", "leitor"]

FROM leitor AS testes
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
ENTRYPOINT ["python", "-m", "pytest", "-q"]
