#!/usr/bin/env python3
"""
LexiBoost Deployment Script
Handles database setup and data seeding for different deployment environments
"""

import argparse
import os
import sys
from db_manager import DatabaseManager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_database(db_path='lexiboost.db', data_dir=None, force_recreate=False):
    """
    Setup database with initialization and data loading
    
    Args:
        db_path: Path to SQLite database file
        data_dir: Directory containing CSV data files
        force_recreate: Whether to recreate database if it exists
    """
    logger.info(f"Setting up database at: {db_path}")
    
    # Remove existing database if force recreate is requested
    if force_recreate and os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"Removed existing database: {db_path}")
    
    # Initialize database manager
    db_manager = DatabaseManager(db_path)
    
    # Test connection
    if not db_manager.test_connection():
        logger.error("Database connection test failed")
        return False
    
    # Initialize database schema
    logger.info("Initializing database schema...")
    db_manager.init_db()
    
    # Load data from CSV files if data directory is provided
    total_words_loaded = 0
    if data_dir and os.path.exists(data_dir):
        logger.info(f"Loading data from directory: {data_dir}")
        total_words_loaded = db_manager.load_words_from_directory(data_dir)
    else:
        if data_dir:
            logger.warning(f"Data directory not found: {data_dir}")
        logger.info("Using fallback data seeding...")
        total_words_loaded = db_manager.seed_fallback_data()
    
    # Verify setup
    word_count = db_manager.get_word_count()
    logger.info(f"Database setup complete. Total words in database: {word_count}")
    
    if word_count == 0:
        logger.warning("No words were loaded into the database!")
        return False
    
    return True

def main():
    """Main deployment script entry point"""
    parser = argparse.ArgumentParser(description='LexiBoost Deployment Script')
    parser.add_argument(
        '--db-path', 
        default='lexiboost.db',
        help='Path to SQLite database file (default: lexiboost.db)'
    )
    parser.add_argument(
        '--data-dir', 
        help='Directory containing CSV data files (e.g., ./data/extracted)'
    )
    parser.add_argument(
        '--force-recreate', 
        action='store_true',
        help='Force recreation of database if it exists'
    )
    parser.add_argument(
        '--environment',
        choices=['local', 'azure', 'vscode'],
        default='local',
        help='Deployment environment (default: local)'
    )
    
    args = parser.parse_args()
    
    # Environment-specific configurations
    if args.environment == 'azure':
        logger.info("Configuring for Azure deployment...")
        # Azure-specific settings can be added here
    elif args.environment == 'vscode':
        logger.info("Configuring for VSCode local deployment...")
        # VSCode-specific settings can be added here
    else:
        logger.info("Configuring for local deployment...")
    
    # Use provided data directory or try common locations
    data_directory = args.data_dir
    if not data_directory:
        # Try common data directory locations
        possible_dirs = [
            './data/extracted',
            '../data/extracted',
            '/home/liand/LexiBoost/data/extracted'
        ]
        
        for possible_dir in possible_dirs:
            if os.path.exists(possible_dir):
                data_directory = possible_dir
                logger.info(f"Found data directory: {data_directory}")
                break
    
    # Setup database
    success = setup_database(
        db_path=args.db_path,
        data_dir=data_directory,
        force_recreate=args.force_recreate
    )
    
    if success:
        logger.info("✅ Database deployment completed successfully!")
        return 0
    else:
        logger.error("❌ Database deployment failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())