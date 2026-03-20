#!/bin/bash
# Start MongoDB with persistent data directory in workspace
# This ensures data survives Codespaces restarts

MONGO_DATA_DIR="/workspaces/swiss-cv-generator/.data/mongo"
MONGO_LOG_FILE="$MONGO_DATA_DIR/mongodb.log"

# Create data directory if it doesn't exist
mkdir -p "$MONGO_DATA_DIR"

# Check if MongoDB is already running
if pgrep -f "mongod --dbpath $MONGO_DATA_DIR" > /dev/null; then
    echo "MongoDB is already running with persistent storage at $MONGO_DATA_DIR"
else
    echo "Starting MongoDB with persistent storage at $MONGO_DATA_DIR"
    mongod --dbpath "$MONGO_DATA_DIR" \
           --logpath "$MONGO_LOG_FILE" \
           --fork \
           --bind_ip_all
    
    if [ $? -eq 0 ]; then
        echo "✅ MongoDB started successfully"
        echo "   Data directory: $MONGO_DATA_DIR"
        echo "   Log file: $MONGO_LOG_FILE"
        echo "   Connection URI: mongodb://localhost:27017"
    else
        echo "❌ Failed to start MongoDB"
        exit 1
    fi
fi
