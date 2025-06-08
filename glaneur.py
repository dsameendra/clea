import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Set
import time
import random

def crawl_pages(url_list: List[str], max_pages: int = 100) -> Set[str]:
    min_delay: float = 1.0
    max_delay: float = 3.0

    visited_urls = set()
    to_visit = set(url_list)
    all_links = set()
    page_count = 0

    while to_visit and page_count < max_pages:
        current_url = to_visit.pop()
        
        if current_url in visited_urls:
            continue
            
        print(f"Crawling: {current_url}")
        
        try:
            # random delay before each request
            delay = random.uniform(min_delay, max_delay)
            print(f"Waiting {delay:.2f} seconds...")
            time.sleep(delay)
            
            # fetch and parse the webpage
            response = requests.get(current_url, timeout=10)
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
        "https://python.org",
    ]
    
    found_links = crawl_pages(urls_to_crawl, max_pages=5)
    print("\nFound links:")
    for link in sorted(found_links):
        print(link)

