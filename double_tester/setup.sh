#!/bin/bash

echo "🚀 Setting up Double Tester..."

# Backend setup
echo "📦 Installing Python dependencies..."
pip3 install -r backend/requirements.txt

# Frontend setup
echo "📦 Installing Frontend dependencies..."
cd frontend
npm install

echo "✅ Setup complete!"
echo "Run ./run.sh to start the servers."
