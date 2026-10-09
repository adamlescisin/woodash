FROM python:3.13-slim
WORKDIR /app
COPY api/ api/
COPY db/ db/
COPY tenants/ tenants/
COPY scripts/ scripts/
RUN pip install --no-cache-dir -e api/
ENV TENANT_DIR=/app/tenants
CMD ["uvicorn", "app.main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000"]
