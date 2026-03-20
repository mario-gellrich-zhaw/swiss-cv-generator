"""
MongoDB connection manager using singleton pattern.
Manages connections to both source (read-only) and target (read/write) databases.
"""
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ConfigurationError

from ..config import get_settings


class MongoDBManager:
    """
    MongoDB connection manager (singleton pattern).
    Manages MongoDB client connections and provides access to both source and target databases.
    """
    
    _instance: Optional['MongoDBManager'] = None
    _client: Optional[MongoClient] = None
    _source_database: Optional[Database] = None
    _target_database: Optional[Database] = None
    
    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize MongoDB manager (only once due to singleton)."""
        if self._client is None:
            self._settings = get_settings()
            self._client = None
            self._source_database = None
            self._target_database = None
    
    def connect(self) -> None:
        """
        Connect to MongoDB using settings configuration.
        
        Raises:
            ConnectionFailure: If connection to MongoDB fails.
            ConfigurationError: If MongoDB configuration is invalid.
        """
        if self._client is None:
            try:
                self._client = MongoClient(
                    self._settings.mongodb_uri,
                    serverSelectionTimeoutMS=5000,  # 5 second timeout
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000
                )
                # Test connection
                self._client.admin.command('ping')
                
                # Get source database (read-only, existing scraper DB)
                self._source_database = self._client[self._settings.mongodb_database_source]
                
                # Get target database (read/write, new app DB)
                self._target_database = self._client[self._settings.mongodb_database_target]
                
            except ConnectionFailure as e:
                raise ConnectionFailure(
                    f"Failed to connect to MongoDB at {self._settings.mongodb_uri}: {e}"
                ) from e
            except Exception as e:
                raise ConfigurationError(
                    f"Invalid MongoDB configuration: {e}"
                ) from e
    
    def get_source_collection(self, collection_name: str) -> Collection:
        """
        Get a collection from the source database (read-only).
        
        Args:
            collection_name: Name of the collection to retrieve.
        
        Returns:
            Collection instance from source database.
        
        Raises:
            ConnectionFailure: If not connected to MongoDB.
        """
        if self._client is None or self._source_database is None:
            self.connect()
        
        return self._source_database[collection_name]
    
    def get_target_collection(self, collection_name: str) -> Collection:
        """
        Get a collection from the target database (read/write).
        
        Args:
            collection_name: Name of the collection to retrieve.
        
        Returns:
            Collection instance from target database.
        
        Raises:
            ConnectionFailure: If not connected to MongoDB.
        """
        if self._client is None or self._target_database is None:
            self.connect()
        
        return self._target_database[collection_name]
    
    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._source_database = None
            self._target_database = None
            MongoDBManager._client = None
            MongoDBManager._source_database = None
            MongoDBManager._target_database = None
    
    @property
    def source_db(self) -> Database:
        """
        Get the source database instance (read-only, CV_DATA).
        
        Returns:
            Source Database instance.
        
        Raises:
            ConnectionFailure: If not connected to MongoDB.
        """
        if self._source_database is None:
            self.connect()
        return self._source_database
    
    @property
    def target_db(self) -> Database:
        """
        Get the target database instance (read/write, swiss_cv_generator).
        
        Returns:
            Target Database instance.
        
        Raises:
            ConnectionFailure: If not connected to MongoDB.
        """
        if self._target_database is None:
            self.connect()
        return self._target_database
    
    @property
    def client(self) -> MongoClient:
        """
        Get the MongoDB client instance.
        
        Returns:
            MongoClient instance.
        
        Raises:
            ConnectionFailure: If not connected to MongoDB.
        """
        if self._client is None:
            self.connect()
        return self._client


# Singleton instance accessor
_db_manager: Optional[MongoDBManager] = None


def get_db_manager() -> MongoDBManager:
    """
    Get the singleton MongoDB manager instance.
    
    Returns:
        MongoDBManager singleton instance.
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = MongoDBManager()
    return _db_manager
