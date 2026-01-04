#!/bin/bash

# This script runs every time the container starts
# Use it to restart MongoDB if needed

set +e

echo "🔄 Post-start: Checking MongoDB status..."

# Check if MongoDB is running
if mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "✅ MongoDB is already running"
else
    echo "🔧 Starting MongoDB..."
    mkdir -p /tmp/mongodb/db
    mongod --dbpath /tmp/mongodb/db --logpath /tmp/mongodb/mongodb.log --fork --bind_ip_all
    
    # Wait a bit for MongoDB to start
    sleep 3
    
    if mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
        echo "✅ MongoDB started successfully"
    else
        echo "⚠️  MongoDB failed to start. You can start it manually with:"
        echo "   mongod --dbpath /tmp/mongodb/db --logpath /tmp/mongodb/mongodb.log --fork --bind_ip_all"
    fi
fi

echo "✨ Container is ready!"
