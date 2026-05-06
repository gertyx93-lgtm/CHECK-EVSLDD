FROM python:3.11-slim
WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium
COPY . .
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data
CMD ["python", "evslddcheck.py"]
