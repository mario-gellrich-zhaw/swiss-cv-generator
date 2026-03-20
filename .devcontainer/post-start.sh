#!/bin/bash

# This script runs every time the container starts
# Use it to restart MongoDB if needed

set +e

echo "🔄 Post-start: Checking MongoDB status..."

# Use persistent data directory in workspace
MONGO_DATA_DIR="/workspaces/swiss-cv-generator/.data/mongo"
MONGO_LOG_FILE="$MONGO_DATA_DIR/mongodb.log"

# Check if MongoDB is running
if mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "✅ MongoDB is already running"
else
    echo "🔧 Starting MongoDB with persistent storage..."
    # Create MongoDB data directory if it doesn't exist
    mkdir -p "$MONGO_DATA_DIR"
    mongod --dbpath "$MONGO_DATA_DIR" --logpath "$MONGO_LOG_FILE" --fork --bind_ip_all
    
    # Wait a bit for MongoDB to start
    sleep 3
    
    if mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
        echo "✅ MongoDB started successfully"
        echo "   Data directory: $MONGO_DATA_DIR (persistent across restarts)"
    else
        echo "⚠️  MongoDB failed to start. You can start it manually with:"
        echo "   mongod --dbpath $MONGO_DATA_DIR --logpath $MONGO_LOG_FILE --fork --bind_ip_all"
    fi
fi

# Initialize MongoDB data if needed
echo ""
echo "🗄️  Initializing MongoDB data..."
cd /workspaces/swiss-cv-generator

# Check if CV_DATA needs to be imported
echo ""
echo "📥 Checking CV_DATA..."
CV_DATA_COUNT=$(mongosh CV_DATA --quiet --eval "db.getCollectionNames().length || 0" 2>/dev/null || echo "0")

if [ "$CV_DATA_COUNT" = "0" ]; then
    echo "⚠️  CV_DATA is empty, importing from JSON..."
    python3 scripts/import_cv_data.py
else
    echo "✅ CV_DATA already loaded"
fi

# Check if swiss_cv_generator needs to be imported
echo ""
echo "📥 Checking swiss_cv_generator..."
SWISS_CV_COUNT=$(mongosh swiss_cv_generator --quiet --eval "db.getCollectionNames().length || 0" 2>/dev/null || echo "0")

if [ "$SWISS_CV_COUNT" = "0" ] || [ "$SWISS_CV_COUNT" = "undefined" ]; then
    echo "⚠️  swiss_cv_generator is empty, importing from JSON snapshots..."
    python3 scripts/import_database.py
else
    echo "✅ swiss_cv_generator already loaded ($SWISS_CV_COUNT collections)"
fi

echo "✨ Container is ready!"
