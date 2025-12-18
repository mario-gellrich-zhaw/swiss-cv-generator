#!/bin/bash

set -e

echo "🚀 Setting up Swiss CV Generator in Codespaces..."

# Wait for MongoDB to be ready
echo "⏳ Waiting for MongoDB to be ready..."
# Try connecting via localhost (port forwarding) or mongo hostname
MONGODB_HOST="${MONGODB_URI:-mongodb://localhost:27017}"
# Extract host from URI
if [[ "$MONGODB_HOST" == *"localhost"* ]] || [[ "$MONGODB_HOST" == *"127.0.0.1"* ]]; then
    until mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
        echo "   MongoDB is not ready yet, waiting..."
        sleep 2
    done
else
    # If using mongo hostname, wait a bit longer
    sleep 5
    until mongosh --host mongo --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
        echo "   MongoDB is not ready yet, waiting..."
        sleep 2
    done
fi
echo "✅ MongoDB is ready!"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cat > .env << EOF
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
pip install -e .

# Verify installation
echo "🔍 Verifying installation..."
python -c "import src; print('✅ Package installed successfully')" || {
    echo "❌ Package installation failed"
    exit 1
}

# Import CV_DATA if JSON file exists
if [ -f "data/CV_DATA.cv_berufsberatung.json" ]; then
    echo "📥 Importing CV_DATA from JSON file..."
    python scripts/import_cv_data.py --input data/CV_DATA.cv_berufsberatung.json || {
        echo "⚠️  CV_DATA import failed (you can run it manually later)"
    }
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

