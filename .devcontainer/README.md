# GitHub Codespaces Configuration

This directory contains the configuration files for GitHub Codespaces, allowing you to develop the Swiss CV Generator in a fully configured cloud environment.

## What's Included

### devcontainer.json
- Python 3.11 development environment
- MongoDB service pre-configured
- VS Code extensions for Python development
- Automatic port forwarding for MongoDB (27017)

### docker-compose.yml
- MongoDB 7.0 service
- Persistent data volume
- Health checks

### Dockerfile
- Python 3.11 base image
- System dependencies (build tools, MongoDB shell)
- Python packages from requirements.txt
- Development tools (black, pylint, mypy, pytest)

### post-create.sh
- Automatic environment setup
- .env file creation
- Package installation
- Database connection test

## Features

✅ **Automatic Setup**: All dependencies installed automatically  
✅ **MongoDB Ready**: Database service starts automatically  
✅ **VS Code Extensions**: Python development tools pre-installed  
✅ **Port Forwarding**: MongoDB accessible on port 27017  
✅ **Environment Variables**: Pre-configured with sensible defaults  

## Usage

1. Open repository in GitHub Codespaces
2. Wait for container to build (2-3 minutes)
3. Start developing!

The container automatically:
- Installs all Python dependencies
- Starts MongoDB service
- Creates `.env` file with defaults
- Sets up Python development environment

## Next Steps After Container Starts

The container automatically imports the CV_DATA database from `data/CV_DATA.cv_berufsberatung.json` during setup, so you can skip the scraper!

1. **Verify CV_DATA import** (optional):
   ```bash
   python scripts/test_db_connection.py
   ```

2. **Initialize database**:
   ```bash
   python scripts/setup_complete_database.py
   ```

3. **Generate your first CV**:
   ```bash
   python -m src.cli.main generate --count 1 --language de
   ```

**Note:** If you need to re-import CV_DATA, run:
```bash
python scripts/import_cv_data.py
```

## Customization

### Adding Environment Variables

Edit `.devcontainer/devcontainer.json` and add to `remoteEnv`:
```json
"remoteEnv": {
  "YOUR_VAR": "value"
}
```

### Adding VS Code Extensions

Edit `.devcontainer/devcontainer.json` and add to `extensions`:
```json
"extensions": [
  "extension.id"
]
```

### Modifying MongoDB Configuration

Edit `.devcontainer/docker-compose.yml` to change MongoDB settings.

## Troubleshooting

### MongoDB Not Starting
- Check container logs: `docker compose -f .devcontainer/docker-compose.yml logs mongo`
- Verify port 27017 is not in use

### Python Package Issues
- Rebuild container: Codespaces menu → Rebuild Container
- Check requirements.txt for version conflicts

### Database Connection Errors
- Ensure MongoDB service is running: `docker compose -f .devcontainer/docker-compose.yml ps`
- Verify MONGODB_URI in .env file

