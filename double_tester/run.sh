#!/bin/bash

# Start the Backend in the background
echo "📡 Starting Backend API (Port 5000) & Mimic Server (Port 5001)..."
python3 backend/main.py &
BACKEND_PID=$!

# Start the Frontend
echo "💻 Starting Svelte Dashboard (Port 5173)..."
cd frontend
npm run dev &
FRONTEND_PID=$!

# Handle shutdown
trap "kill $BACKEND_PID $FRONTEND_PID; exit" SIGINT SIGTERM

echo "✨ All systems go!"
echo "Dashboard: http://localhost:5173"
echo "Mimic Server: http://localhost:5001"
echo "Press Ctrl+C to stop."

wait
