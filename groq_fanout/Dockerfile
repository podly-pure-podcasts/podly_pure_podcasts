FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5050
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:5050/healthz >/dev/null || exit 1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5050", "--log-level", "info"]
