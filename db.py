import mysql.connector
from mysql.connector import pooling
import os
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', 3306))
}

# Create connection pool
connection_pool = None

def create_connection_pool():
    """Create and return a connection pool"""
    global connection_pool
    if connection_pool is None:
        max_retries = 5
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                connection_pool = pooling.MySQLConnectionPool(
                    pool_name="api_pool",
                    pool_size=5,
                    **DB_CONFIG
                )
                return connection_pool
            except mysql.connector.Error as err:
                if attempt < max_retries - 1:
                    print(f"Connection attempt {attempt + 1} failed: {err}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    raise Exception(f"Failed to connect to MySQL after {max_retries} attempts: {err}")
    
    return connection_pool

def get_db_connection():
    """Get a connection from the pool"""
    global connection_pool
    if connection_pool is None:
        connection_pool = create_connection_pool()
    
    return connection_pool.get_connection()

def init_db():
    """Initialize the database with required tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {str(e)}")
        raise