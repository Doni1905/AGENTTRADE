#!/bin/bash

echo "Stopping any existing processes on ports 8000 and 5678..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5678 | xargs kill -9 2>/dev/null

echo "Starting n8n in the background..."
N8N_SECURE_COOKIE="false" npx n8n > n8n.log 2>&1 &
echo "n8n is starting up (logs are being written to n8n.log)"

echo "Starting FastAPI development server..."
N8N_URL="http://127.0.0.1:5678" fastapi dev app/main.py
