# Dockerfile
FROM python:3.11-slim

# OS deps if your parser needs them (tweak as needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmagic1 poppler-utils libgl1 libglib2.0-0 tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps
COPY requirements.txt .

#trying to remove cache - 11/13 - 6.38
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY src ./src

# So `import main` resolves to /app/src/main.py
# ENV PYTHONPATH=/app/src
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# IMPORTANT:
#  - --host=0.0.0.0 (binds on all interfaces)
#  - --source=src/main.py (explicit path to your file)
#  - --target=firestore_handler (the CloudEvent function name inside main.py)
#  - --signature-type=cloudevent (Eventarc delivers CloudEvents)
CMD ["functions-framework", \
     "--source=src/main.py", \
     # "--source=main.py", \
     "--target=firestore_handler", \
     "--signature-type=cloudevent", \
     "--host=0.0.0.0", \
     "--port=8080"]