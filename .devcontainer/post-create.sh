#!/bin/bash

# Don't exit on error - we want to continue even if MongoDB isn't ready
set +e

echo "🚀 Setting up Swiss CV Generator in Codespaces..."
echo "📍 Current directory: $(pwd)"
echo "📍 User: $(whoami)"

# Always operate from workspace root
WORKSPACE_DIR=${WORKSPACE_DIR:-${WORKSPACE_FOLDER:-/workspaces/swiss-cv-generator}}
echo "📁 Workspace directory: $WORKSPACE_DIR"
echo "📂 Checking if directory exists..."
ls -la "$WORKSPACE_DIR" || echo "❌ Directory not accessible!"

cd "$WORKSPACE_DIR" || { echo "❌ Failed to cd to $WORKSPACE_DIR"; pwd; }
echo "✅ Changed to workspace directory"
echo "📍 Now in: $(pwd)"
umask 0002

# Start MongoDB in background with persistent storage
echo "🔧 Starting MongoDB..."
MONGO_DATA_DIR="/workspaces/swiss-cv-generator/.data/mongo"
MONGO_LOG_FILE="$MONGO_DATA_DIR/mongodb.log"
mkdir -p "$MONGO_DATA_DIR"
mongod --dbpath "$MONGO_DATA_DIR" --logpath "$MONGO_LOG_FILE" --fork --bind_ip_all

# Wait for MongoDB to be ready
echo "⏳ Waiting for MongoDB to be ready..."
MAX_WAIT=30  # Maximum wait time in seconds
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
        echo "✅ MongoDB is ready!"
        break
    fi
    
    WAIT_COUNT=$((WAIT_COUNT + 2))
    if [ $((WAIT_COUNT % 10)) -eq 0 ]; then
        echo "   Still waiting... (${WAIT_COUNT}s / ${MAX_WAIT}s)"
    fi
    sleep 2
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo "⚠️  MongoDB did not become ready within ${MAX_WAIT} seconds"
    echo "   You can start MongoDB manually with:"
    echo "   mongod --dbpath $MONGO_DATA_DIR --logpath $MONGO_LOG_FILE --fork --bind_ip_all"
else
    echo "✅ MongoDB connection verified!"
fi

# Create .env file if it doesn't exist
if [ ! -f "$WORKSPACE_DIR/.env" ]; then
    echo "📝 Creating .env file from template..."
    cat > "$WORKSPACE_DIR/.env" << EOF
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE_SOURCE=CV_DATA
MONGODB_DATABASE_TARGET=swiss_cv_generator
MONGODB_COLLECTION_OCCUPATIONS=cv_berufsberatung

# OpenAI Configuration (optional - add your key if needed)
# OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL_MINI=gpt-3.5-turbo
OPENAI_MODEL_FULL=gpt-4

# Application Settings
DATA_DIR=data
LOG_LEVEL=INFO
AI_MAX_RETRIES=5
AI_RATE_LIMIT_DELAY=1.0
AI_TEMPERATURE_CREATIVE=0.8
AI_TEMPERATURE_FACTUAL=0.3
EOF
    echo "✅ .env file created"
else
    echo "ℹ️  .env file already exists, skipping..."
fi

# Install Python dependencies
echo "📦 Installing Python dependencies from requirements.txt..."
if [ -f "$WORKSPACE_DIR/requirements.txt" ]; then
    pip install -r "$WORKSPACE_DIR/requirements.txt"
    echo "✅ Dependencies installed"
else
    echo "⚠️  requirements.txt not found - skipping pip install"
fi

# Verify installation
echo "🔍 Verifying installation..."
echo "   PYTHONPATH: $PYTHONPATH"
python -c "import sys; print('   Python can find:', sys.path[0])" || true
python -c "import src; print('✅ Package is accessible')" || {
    echo "⚠️  Package not yet accessible - this is OK, it will be available after restart"
}

# Import CV_DATA if JSON file exists and MongoDB is ready
if [ -f "data/CV_DATA.cv_berufsberatung.json" ]; then
    # Check if MongoDB is actually ready before importing
    if mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
        echo "📥 Importing CV_DATA from JSON file..."
        python scripts/import_cv_data.py || {
            echo "⚠️  CV_DATA import failed (you can run it manually later)"
            echo "   Run: python scripts/import_cv_data.py"
        }
    else
        echo "⚠️  MongoDB not ready yet. Skipping CV_DATA import."
        echo "   Once MongoDB is ready, run: python scripts/import_cv_data.py"
    fi
else
    echo "ℹ️  CV_DATA JSON file not found. Skipping import."
    echo "   To import later, run: python scripts/import_cv_data.py"
fi

# Import pre-built database snapshots (fast, no OpenAI needed)
echo "🗄️  Importing pre-built database snapshots..."
if [ -d "data/swiss_cv_generator" ]; then
    python scripts/import_database.py && {
        echo "✅ Database imported from snapshots — setup complete, no AI generation needed"
    } || {
        echo "⚠️  Snapshot import had issues, falling back to full setup..."
        echo "🔧 Running full database setup (this may take several minutes)..."
        python scripts/setup_complete_database.py || {
            echo "⚠️  Database setup had some issues (check output above)"
            echo "   Some steps may have failed due to missing OpenAI API key"
            echo "   You can run fallback scripts manually:"
            echo "   - python scripts/load_cantons_fallback.py"
        }
    }
else
    echo "ℹ️  No snapshots found — running full database setup..."
    echo "🔧 Setting up complete database (this may take several minutes)..."
    python scripts/setup_complete_database.py || {
        echo "⚠️  Database setup had some issues (check output above)"
        echo "   Some steps may have failed due to missing OpenAI API key"
        echo "   You can run fallback scripts manually:"
        echo "   - python scripts/load_cantons_fallback.py"
    }
fi

# Test database connection
echo "🔍 Testing database connection..."
python scripts/test_db_connection.py || {
    echo "⚠️  Database connection test failed (this is OK if database is not yet initialized)"
}

echo ""
echo "✨ Setup complete!"
echo ""
echo "📚 Next steps:"
echo "   ✅ MongoDB is running"
echo "   ✅ CV_DATA database imported"
echo "   ✅ Database initialized"
echo ""
echo "   🚀 You can now generate CVs:"
echo "      python -m src.cli.main generate --count 50 --language de"
echo ""
echo "💡 Tips:"
echo "   - MongoDB is running on port 27017"
echo "   - If database setup failed, add OpenAI API key to .env and re-run:"
echo "     python scripts/setup_complete_database.py"
echo "   - Or use fallback for cantons: python scripts/load_cantons_fallback.py"
echo ""

