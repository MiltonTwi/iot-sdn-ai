FROM python:3.11-slim
WORKDIR /app
COPY dashboard/requirements.txt /app/dashboard/requirements.txt
RUN pip install --no-cache-dir -r /app/dashboard/requirements.txt
COPY dashboard /app/dashboard
COPY iot/zones.yaml /app/iot/zones.yaml
ENV DASH_HOST=0.0.0.0 DASH_PORT=8000
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
