FROM python:3.12-slim-bookworm

# LibreOffice: one-time .xls -> .xlsx conversion of the template (tests: recalculation)
# poppler-utils: PDF scans -> page images
# tesseract: reads the PRINTED page titles (classification) and the page orientation - no handwriting
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-calc-nogui poppler-utils fonts-dejavu-core \
       tesseract-ocr tesseract-ocr-deu tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY VERSION ./
COPY app ./app

ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
