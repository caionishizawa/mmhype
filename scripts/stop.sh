#!/bin/bash
# Stop the market maker

set -e

echo "Stopping Hyperliquid Market Maker..."

docker-compose down

echo "Stopped successfully"
