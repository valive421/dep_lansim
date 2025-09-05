# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and source code
COPY requirements.txt ./
COPY server.py ./

# Install build tools for netifaces and other native packages
RUN apt-get update && apt-get install -y build-essential gcc && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose HTTP (Flask) and UDP ports
EXPOSE 5001/tcp
EXPOSE 5000/udp

# Set environment variables for Flask and UDP
ENV FLASK_PORT=5001
ENV UDP_PORT=5000

# Start the server (Flask + UDP)
CMD ["python", "server.py"]