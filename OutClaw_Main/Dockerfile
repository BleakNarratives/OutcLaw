FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY . .

# Expose port 5000 for the dashboard
EXPOSE 5000

# Set environment variable for the app
ENV FLASK_APP=dashboard/web_app.py
ENV PYTHONPATH=/app

CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]
