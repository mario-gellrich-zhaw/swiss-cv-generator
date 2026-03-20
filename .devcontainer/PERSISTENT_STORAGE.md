# MongoDB Persistent Storage Setup

## Overview

MongoDB in this Codespace is configured to store data persistently in the workspace directory, ensuring that your data survives Codespace restarts.

## Storage Location

- **Data Directory**: `/workspaces/swiss-cv-generator/.data/mongo/`
- **Log File**: `/workspaces/swiss-cv-generator/.data/mongo/mongodb.log`

This directory is stored in the workspace, which means:
✅ Data persists across Codespace stops/starts
✅ Data is preserved when rebuilding the container
✅ Data is excluded from git commits (via `.gitignore`)

## How It Works

1. **Automatic Startup**: The `post-start.sh` script automatically starts MongoDB with persistent storage every time your Codespace starts.

2. **Manual Control**: You can also manually manage MongoDB using:
   ```bash
   # Start MongoDB with persistent storage
   bash /workspaces/swiss-cv-generator/.devcontainer/start-mongodb.sh
   
   # Check MongoDB status
   mongosh --quiet --eval "db.adminCommand('ping')"
   
   # View MongoDB logs
   cat /workspaces/swiss-cv-generator/.data/mongo/mongodb.log
   ```

3. **Data Initialization**: After MongoDB starts, the `init_mongodb_on_startup.py` script runs to ensure all collections and data are properly initialized.

## Testing Persistence

To verify data persistence:

```bash
# Insert test data
mongosh --eval "db.getSiblingDB('test').mytest.insertOne({test: 'persistence check', date: new Date()})"

# Stop and restart Codespace (or rebuild container)

# Check if data still exists
mongosh --eval "db.getSiblingDB('test').mytest.find().toArray()"
```

## Important Notes

- The `.data/` directory is already in `.gitignore` to prevent committing database files
- The workspace storage is persistent but tied to your Codespace instance
- If you delete the Codespace entirely, the data will be lost
- For long-term backups, consider exporting important data using `mongodump`

## Backup & Restore

### Create a backup
```bash
mongodump --out=/workspaces/swiss-cv-generator/backup/$(date +%Y%m%d)
```

### Restore from backup
```bash
mongorestore /workspaces/swiss-cv-generator/backup/YYYYMMDD/
```

## Troubleshooting

If MongoDB doesn't start automatically:

1. Check if MongoDB is running:
   ```bash
   ps aux | grep mongod
   ```

2. Manually start MongoDB:
   ```bash
   bash /workspaces/swiss-cv-generator/.devcontainer/start-mongodb.sh
   ```

3. Check logs for errors:
   ```bash
   tail -n 50 /workspaces/swiss-cv-generator/.data/mongo/mongodb.log
   ```
