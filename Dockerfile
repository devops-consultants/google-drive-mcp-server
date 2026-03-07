FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY google_drive_mcp_server/ google_drive_mcp_server/

EXPOSE 8080

CMD ["python", "-m", "google_drive_mcp_server"]
