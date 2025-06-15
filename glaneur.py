# Clawler - To crawl web pages and extract links

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Set, Dict, Optional
import time
import random
import sqlite3
from datetime import datetime
from robotexclusionrulesparser import RobotExclusionRulesParser
from classeur import index_webpage, get_unindexed_urls

robots_parser_cache: Dict[str, RobotExclusionRulesParser] = {}
visited_urls: Set[str] = set()
USER_AGENT = "CleaGlaneur/1.0"
HEADERS = {"User-Agent": USER_AGENT}

# get the robots.txt parser for a given URL
def get_robots_parser(url: str) -> RobotExclusionRulesParser:
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    
    if domain not in robots_parser_cache:
        parser = RobotExclusionRulesParser()
        try:
            robots_url = f"{domain}/robots.txt"
            response = requests.get(robots_url, headers=HEADERS, timeout=10)
            parser.parse(response.text)
        except Exception as e:
            print(f"Error fetching robots.txt for {domain}: {str(e)}")
            # can't fetch robots.txt, assume everything is allowed
            parser.parse("")
        
        robots_parser_cache[domain] = parser
        
    return robots_parser_cache[domain]

# check if the URL is allowed by robots.txt
def is_allowed(url: str) -> bool:
    parser = get_robots_parser(url)
    return parser.is_allowed(USER_AGENT, url)

def save_urls_to_database(urls: Set[str], db_path: str = 'clea_db.db') -> None:
    """Save crawled URLs to the database."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        for url in urls:
            cursor.execute('''
            INSERT OR IGNORE INTO crawled_urls (url)
            VALUES (?)
            ''', (url,))
        
        conn.commit()
        print(f"Saved {len(urls)} URLs to database")
        
    except Exception as e:
        print(f"Error saving URLs to database: {str(e)}")
        conn.rollback()
    
    finally:
        conn.close()

# crawl a list of URLs and extract links
def crawl_pages(url_list: List[str], max_pages: int = 100, min_delay: float = 1.0, max_delay: float = 3.0) -> Set[str]:
    to_visit = set(url_list)
    all_links = set()
    page_count = 0

    while to_visit and page_count < max_pages:
        current_url = to_visit.pop()
        
        if current_url in visited_urls:
            continue
        
        if not is_allowed(current_url):
            print(f"Skipping {current_url} (not allowed by robots.txt)")
            continue
            
        print(f"Crawling: {current_url}")
        
        try:
            # random delay before each request
            delay = random.uniform(min_delay, max_delay)
            print(f"Waiting {delay:.2f} seconds...")
            time.sleep(delay)
            
            # fetch and parse the webpage
            response = requests.get(current_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # mark as visited
            visited_urls.add(current_url)
            page_count += 1
            
            # find all links
            for link in soup.find_all('a'):
                href = link.get('href')
                if not href:
                    continue

                absolute_url = urljoin(current_url, href)
                
                # keep http(s) only
                if not absolute_url.startswith(('http://', 'https://')):
                    continue

                all_links.add(absolute_url)
                to_visit.add(absolute_url)

        except Exception as e:
            print(f"Error crawling {current_url}: {str(e)}")

    print(f"\nCrawling completed. Visited {page_count} pages.")
    return all_links

# Sitemap Management Functions

def add_url_to_sitemap(url: str, db_path: str = 'clea_db.db') -> bool:
    """Add a URL to the sitemap for crawling."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT OR IGNORE INTO sitemap_urls (url)
        VALUES (?)
        ''', (url,))
        
        success = cursor.rowcount > 0
        conn.commit()
        return success
        
    except Exception as e:
        print(f"Error adding URL to sitemap: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

def add_urls_to_sitemap(urls: List[str], db_path: str = 'clea_db.db') -> int:
    """Add multiple URLs to the sitemap for crawling."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        added_count = 0
        
        for url in urls:
            cursor.execute('''
            INSERT OR IGNORE INTO sitemap_urls (url)
            VALUES (?)
            ''', (url,))
            if cursor.rowcount > 0:
                added_count += 1
        
        conn.commit()
        return added_count
        
    except Exception as e:
        print(f"Error adding URLs to sitemap: {str(e)}")
        conn.rollback()
        return 0
    finally:
        conn.close()

def get_sitemap_urls(status: Optional[str] = None, db_path: str = 'clea_db.db') -> List[Dict]:
    """Get URLs from sitemap, optionally filtered by status."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        if status:
            cursor.execute('''
            SELECT id, url, added_timestamp, last_crawled, crawl_status, active
            FROM sitemap_urls
            WHERE crawl_status = ? AND active = TRUE
            ORDER BY added_timestamp ASC
            ''', (status,))
        else:
            cursor.execute('''
            SELECT id, url, added_timestamp, last_crawled, crawl_status, active
            FROM sitemap_urls
            WHERE active = TRUE
            ORDER BY added_timestamp ASC
            ''')
        
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'url': row[1],
                'added_timestamp': row[2],
                'last_crawled': row[3],
                'crawl_status': row[4],
                'active': row[5]
            }
            for row in rows
        ]
        
    except Exception as e:
        print(f"Error getting sitemap URLs: {str(e)}")
        return []
    finally:
        conn.close()

def update_crawl_status(url: str, status: str, db_path: str = 'clea_db.db') -> None:
    """Update the crawl status of a URL in the sitemap."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        current_time = datetime.now().isoformat()
        cursor.execute('''
        UPDATE sitemap_urls
        SET crawl_status = ?, last_crawled = ?
        WHERE url = ?
        ''', (status, current_time, url))
        
        conn.commit()
        
    except Exception as e:
        print(f"Error updating crawl status: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

def remove_url_from_sitemap(url: str, db_path: str = 'clea_db.db') -> bool:
    """Remove a URL from the sitemap (mark as inactive)."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE sitemap_urls
        SET active = FALSE
        WHERE url = ?
        ''', (url,))
        
        success = cursor.rowcount > 0
        conn.commit()
        return success
        
    except Exception as e:
        print(f"Error removing URL from sitemap: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

def crawl_from_sitemap(force_crawl: bool = False, max_pages: int = 100, 
                      min_delay: float = 1.0, max_delay: float = 3.0, 
                      db_path: str = 'clea_db.db') -> Set[str]:
    """Crawl URLs from sitemap based on their status."""
    global visited_urls
    
    if force_crawl:
        # Crawl all active URLs regardless of status
        urls_to_crawl = get_sitemap_urls(db_path=db_path)
        print(f"Force crawling {len(urls_to_crawl)} URLs from sitemap...")
    else:
        # Only crawl pending URLs
        urls_to_crawl = get_sitemap_urls(status='pending', db_path=db_path)
        print(f"Crawling {len(urls_to_crawl)} pending URLs from sitemap...")
    
    if not urls_to_crawl:
        print("No URLs to crawl from sitemap.")
        return set()
    
    # Convert to list of URL strings
    url_list = [item['url'] for item in urls_to_crawl]
    
    all_links = set()
    crawled_count = 0
    
    for url in url_list:
        if crawled_count >= max_pages:
            break
            
        if not force_crawl and url in visited_urls:
            continue
        
        if not is_allowed(url):
            print(f"Skipping {url} (not allowed by robots.txt)")
            update_crawl_status(url, 'error', db_path)
            continue
            
        print(f"Crawling sitemap URL: {url}")
        
        try:
            # Random delay before each request
            delay = random.uniform(min_delay, max_delay)
            print(f"Waiting {delay:.2f} seconds...")
            time.sleep(delay)
            
            # Fetch and parse the webpage
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Mark as visited and update status
            visited_urls.add(url)
            update_crawl_status(url, 'crawled', db_path)
            crawled_count += 1
            
            # Find all links
            page_links = set()
            for link in soup.find_all('a'):
                href = link.get('href')
                if not href:
                    continue

                absolute_url = urljoin(url, href)
                
                # Keep http(s) only
                if not absolute_url.startswith(('http://', 'https://')):
                    continue

                page_links.add(absolute_url)
                all_links.add(absolute_url)
            
            print(f"Found {len(page_links)} links on {url}")

        except Exception as e:
            print(f"Error crawling {url}: {str(e)}")
            update_crawl_status(url, 'error', db_path)

    print(f"\nSitemap crawling completed. Crawled {crawled_count} pages, found {len(all_links)} total links.")
    
    # Save discovered links to crawled_urls table
    if all_links:
        save_urls_to_database(all_links, db_path)
    
    return all_links

# Indexing Functions

# This function has been replaced by using classeur.batch_index_urls directly

def get_crawled_urls_from_sitemap(db_path: str = 'clea_db.db') -> List[str]:
    """Get URLs from sitemap that have been crawled but may need indexing."""
    return [item['url'] for item in get_sitemap_urls(status='crawled', db_path=db_path)]

if __name__ == "__main__":
    # Initialize database
    from init_db import init_database
    init_database()
    
    # Example usage - add some URLs to sitemap
    example_urls = [
        "https://www.python.org",
        "https://docs.python.org",
        "https://pypi.org"
    ]
    
    # Add URLs to sitemap if they don't exist
    added_count = add_urls_to_sitemap(example_urls)
    print(f"Added {added_count} new URLs to sitemap")
    
    # Show current sitemap status
    sitemap_urls = get_sitemap_urls()
    print(f"\nCurrent sitemap contains {len(sitemap_urls)} URLs:")
    for item in sitemap_urls[:5]:  # Show first 5
        print(f"  {item['url']} - Status: {item['crawl_status']}")
    
    # Crawl pending URLs from sitemap
    found_links = crawl_from_sitemap(force_crawl=False, max_pages=3)
    print(f"\nDiscovered {len(found_links)} total links from sitemap crawling")
    
    # Note: Indexing is now done directly using classeur.batch_index_urls
