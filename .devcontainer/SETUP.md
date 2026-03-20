# Dev Container Setup for GitHub Codespaces

This directory contains the configuration for running the Swiss CV Generator in GitHub Codespaces.

## What Happens Automatically

When you create a Codespace, the following happens automatically:

### 1. Container Build (Dockerfile)
- ✅ Python 3.11 is installed
- ✅ MongoDB 7.0 server and shell (mongosh) are installed
- ✅ All Python dependencies from `requirements.txt` are installed
- ✅ Development tools (black, pylint, mypy) are installed

### 2. Post-Create Setup (post-create.sh)
Runs once when the container is first created:
- ✅ Starts MongoDB service on port 27017
- ✅ Creates `.env` file with default configuration
- ✅ Installs the package in development mode (`pip install -e .`)
- ✅ Imports CV_DATA from JSON file (if exists)
- ✅ Tests database connection

### 3. Post-Start Setup (post-start.sh)
Runs every time the container starts:
- ✅ Checks MongoDB status and restarts if needed

## Manual Steps After Container Starts

### Step 1: Add OpenAI API Key (Optional but Recommended)

Edit `.env` file and add your OpenAI API key:
```bash
OPENAI_API_KEY=sk-your-actual-key-here
```

**Without OpenAI key:** Some features will use fallback data (like canton generation).

### Step 2: Initialize Database

Run the complete database setup:
```bash
python scripts/setup_complete_database.py
```

**If OpenAI key is not available**, the script will fail on name/company generation. Use fallback scripts:
```bash
# Load cantons without OpenAI
python scripts/load_cantons_fallback.py

# You can still generate CVs, but with limited data
```

### Step 3: Generate CVs

```bash
# Generate 50 German CVs with random designs
python -m src.cli.main generate \
  --count 50 \
  --language de \
  --format pdf \
  --output-dir output/my_cvs \
  --verbose
```

## Database Information

- **MongoDB**: Runs on `localhost:27017`
- **Data Directory**: `/tmp/mongodb/db` (persistent within container lifetime)
- **Source Database**: `CV_DATA` (contains ~1,851 occupations)
- **Target Database**: `swiss_cv_generator` (generated CVs and metadata)

## Troubleshooting

### MongoDB not running

If MongoDB is not running, start it manually:
```bash
mongod --dbpath /tmp/mongodb/db --logpath /tmp/mongodb/mongodb.log --fork --bind_ip_all
```

### Check MongoDB status

```bash
mongosh --eval "db.adminCommand('ping')"
```

### Test database connection

```bash
python scripts/test_db_connection.py
```

### Reset everything

```bash
# Stop MongoDB
pkill mongod

# Remove data
rm -rf /tmp/mongodb/db

# Restart MongoDB
mongod --dbpath /tmp/mongodb/db --logpath /tmp/mongodb/mongodb.log --fork --bind_ip_all

# Re-import data
python scripts/import_cv_data.py
python scripts/setup_complete_database.py
```

## What's Different from Local Setup

| Aspect | Codespaces | Local |
|--------|-----------|-------|
| MongoDB | Installed in container | Docker Compose or manual install |
| Python | Pre-installed 3.11 | User's local version |
| Dependencies | Auto-installed | Manual `pip install -r requirements.txt` |
| CV_DATA | Auto-imported | Manual import or scraper |
| .env file | Auto-created | Manual copy from template |

## Files in This Directory

- **devcontainer.json**: Main configuration for VS Code Dev Container
- **Dockerfile**: Container image definition
- **post-create.sh**: Runs once after container creation
- **post-start.sh**: Runs every time container starts
- **README.md**: This file
