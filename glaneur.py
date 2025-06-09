# Clawler - To crawl web pages and extract links

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Set, Dict
import time
import random
import sqlite3
from robotexclusionrulesparser import RobotExclusionRulesParser

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

if __name__ == "__main__":
    urls_to_crawl = [
        "https://www.python.org",
    ]

    # init if not already
    from init_db import init_database
    init_database()

    found_links = crawl_pages(urls_to_crawl, max_pages=1)

    print("\nFound links:")
    for link in sorted(found_links):
        print(link)
    
    # Save links to database instead of text file
    save_urls_to_database(found_links)
    print(f"\n{len(found_links)} links saved to database")
