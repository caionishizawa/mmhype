#!/bin/bash
# Deploy the market maker using Docker

set -e

echo "Deploying Hyperliquid Market Maker..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    echo "Copy .env.example to .env and configure your credentials"
    exit 1
fi

# Build Docker image
echo "Building Docker image..."
docker-compose build

# Start services
echo "Starting services..."
docker-compose up -d

# Show logs
echo "Deployment complete. Showing logs..."
docker-compose logs -f
