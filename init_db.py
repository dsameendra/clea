import sqlite3

# Init the SQLite database
def init_database(db_path: str = 'clea_db.db') -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS webpages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        title TEXT,
        snippet TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS word_index (
        word TEXT PRIMARY KEY,
        webpage_ids TEXT,  -- JSON array of webpage IDs
        webpage_frequencies TEXT  -- JSON object mapping webpage_id to frequency
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crawled_urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        discovered_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        indexed BOOLEAN DEFAULT FALSE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sitemap_urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        added_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_crawled DATETIME,
        crawl_status TEXT DEFAULT 'pending',  -- 'pending', 'crawled', 'error'
        active BOOLEAN DEFAULT TRUE
    )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_database()
    print("Database initialized successfully.")