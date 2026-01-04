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

cd "$WORKSPACE_DIR" || { echo "❌ Failed to cd to $WORKSPACE_DIR"; exit 1; }
echo "✅ Changed to workspace directory"
echo "📍 Now in: $(pwd)"
umask 0002

# Start MongoDB in background
echo "🔧 Starting MongoDB..."
mkdir -p /tmp/mongodb/db
mongod --dbpath /tmp/mongodb/db --logpath /tmp/mongodb/mongodb.log --fork --bind_ip_all

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
    echo "   mongod --dbpath /tmp/mongodb/db --logpath /tmp/mongodb/mongodb.log --fork --bind_ip_all"
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

# Install package in development mode
echo "📦 Installing package in development mode..."
if [ -f "$WORKSPACE_DIR/pyproject.toml" ] || [ -f "$WORKSPACE_DIR/setup.py" ]; then
    pip install -e "$WORKSPACE_DIR"
else
    echo "⚠️  Warning: pyproject.toml not found at $WORKSPACE_DIR"
    echo "   Listing directory contents:"
    ls -la "$WORKSPACE_DIR"
    exit 1
fi

# Verify installation
echo "🔍 Verifying installation..."
python -c "import src; print('✅ Package installed successfully')" || {
    echo "❌ Package installation failed"
    exit 1
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

# Test database connection
echo "🔍 Testing database connection..."
python scripts/test_db_connection.py || {
    echo "⚠️  Database connection test failed (this is OK if database is not yet initialized)"
}

echo ""
echo "✨ Setup complete!"
echo ""
echo "📚 Next steps:"
if [ -f "data/CV_DATA.cv_berufsberatung.json" ]; then
    echo "   ✅ CV_DATA database imported from JSON file"
    echo ""
    echo "   1. Initialize the database:"
    echo "      python scripts/setup_complete_database.py"
    echo ""
    echo "   2. Generate your first CV:"
    echo "      python -m src.cli.main generate --count 1 --language de"
else
    echo "   1. Import CV_DATA database (if JSON file exists):"
    echo "      python scripts/import_cv_data.py"
    echo ""
    echo "   OR run the scraper to populate CV_DATA database:"
    echo "      cd scraper && python job_scraper.py"
    echo ""
    echo "   2. Initialize the database:"
    echo "      python scripts/setup_complete_database.py"
    echo ""
    echo "   3. Generate your first CV:"
    echo "      python -m src.cli.main generate --count 1 --language de"
fi
echo ""
echo "💡 Tip: MongoDB is running on port 27017 and is accessible from the container"
echo ""

