# Dockerfile

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY xml_organizer.py .
COPY credentials.json .

CMD ["python3", "xml_organizer.py"]