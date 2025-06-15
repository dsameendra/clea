# Indexer - Handles Webpage Indexing
import sqlite3
import requests
from bs4 import BeautifulSoup
from nltk.stem import PorterStemmer
from nltk.corpus import stopwords
from typing import List, Tuple
import re
import json
import time
import random

# try:
#     nltk.data.find('corpora/stopwords')
# except LookupError:
#     nltk.download('stopwords')

# Init stemmer and stopwords
stemmer = PorterStemmer()
STOP_WORDS = set(stopwords.words('english'))

def clean_title(text: str) -> str:
    """Clean title keeping capitalization."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove extra whitespaces
    text = ' '.join(text.split())
    return text

def clean_text(text: str) -> str:
    """Clean text and prepare it for tokenization."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove special chars and digits
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', '', text)
    # Remove extra whitespace
    text = ' '.join(text.split())
    return text.lower()

def tokenize_and_stem(text: str) -> List[str]:
    """Tokenize text, remove stopwords, and apply stemming."""
    # Clean the text first
    text = clean_text(text)
    
    # Split into words
    words = text.split()
    
    processed_words = [
        stemmer.stem(word) for word in words # Apply stemming
        if word.lower() not in STOP_WORDS  # Remove stopwords
        and len(word) > 1  # Skip single char words
    ]
    
    return processed_words

def find_best_snippet(text: str, max_length: int = 200) -> str:
    """Find the most relevant snippet from text"""
    # Split text into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if not sentences:
        return ""
        
    best_sentences = []
    for sentence in sentences:
        if len(sentence.split()) > 5:
            best_sentences.append(sentence)
            if len(best_sentences) == 3:
                break
    if not best_sentences:
        best_sentences = [sentences[0]]
    
    snippet = ""
    for sentence in best_sentences:
        sentence = sentence.strip()
        if not snippet:
            snippet = sentence
        else:
            if len(snippet + " " + sentence) <= max_length:
                snippet += " " + sentence
            else:
                # Truncate at word boundary
                remaining_length = max_length - len(snippet) - 4  # -4 for " ..."
                if remaining_length > 20:
                    words = sentence.split()
                    for word in words:
                        if len(snippet + " " + word) > max_length - 3:  # -3 for "..."
                            break
                        snippet = (snippet + " " + word).strip()
                break
    
    return snippet + "..." if len(snippet) < len(" ".join(best_sentences)) else snippet

def extract_page_info(url: str, query_words: List[str] = None) -> Tuple[str, str, str]:
    """Fetch and extract information from a webpage."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get title
        title = soup.title.string if soup.title else ""
        title = clean_title(title)
        
        # Get all text with paragraph structure
        paragraphs = []
        for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = p.get_text().strip()
            if text and len(text.split()) > 3: # Avoid short paragraphs
                paragraphs.append(text)
        
        text = ' '.join(paragraphs)
        text = re.sub(r'[\n\r\t]+', ' ', text)
        text = ' '.join(text.split())
        
        snippet = find_best_snippet(text)
        
        return title, snippet, text
        
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
        return "", "", ""

def update_word_index(word: str, webpage_id: int, frequency: int, conn: sqlite3.Connection) -> None:
    """Update the word index for a single word."""
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT webpage_ids, webpage_frequencies FROM word_index WHERE word = ?', (word,))
        row = cursor.fetchone()

        if row:
            # Update existing entry
            webpage_ids = json.loads(row[0])
            frequencies = json.loads(row[1])
            
            if str(webpage_id) not in webpage_ids:
                webpage_ids.append(str(webpage_id))
            frequencies[str(webpage_id)] = frequency

            cursor.execute('''
            UPDATE word_index 
            SET webpage_ids = ?, webpage_frequencies = ?
            WHERE word = ?
            ''', (json.dumps(webpage_ids), json.dumps(frequencies), word))
        else:
            # Create new entry
            webpage_ids = [str(webpage_id)]
            frequencies = {str(webpage_id): frequency}

            cursor.execute('''
            INSERT INTO word_index (word, webpage_ids, webpage_frequencies)
            VALUES (?, ?, ?)
            ''', (word, json.dumps(webpage_ids), json.dumps(frequencies)))

    except Exception as e:
        print(f"Error updating word index for {word}: {str(e)}")
        raise

def index_webpage(url: str, db_path: str = 'clea_db.db') -> None:
    """Index a webpage: extract information, process text, and store in database."""
    title, snippet, full_text = extract_page_info(url)
    if not full_text:
        return

    words = tokenize_and_stem(full_text)
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Insert webpage info
        cursor.execute('''
        INSERT OR REPLACE INTO webpages (url, title, snippet)
        VALUES (?, ?, ?)
        ''', (url, title, snippet))
        
        webpage_id = cursor.lastrowid
        
        # Update word index entries
        for word, freq in word_freq.items():
            update_word_index(word, webpage_id, freq, conn)
        
        # Mark URL as indexed in crawled_urls table
        cursor.execute('''
        UPDATE crawled_urls SET indexed = TRUE WHERE url = ?
        ''', (url,))
        
        conn.commit()
        print(f"Indexed: {url}")
        
    except Exception as e:
        print(f"Error indexing {url}: {str(e)}")
        conn.rollback()
    
    finally:
        conn.close()

def get_unindexed_urls(db_path: str = 'clea_db.db') -> List[str]:
    """Get URLs from the database that haven't been indexed yet."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT url FROM crawled_urls WHERE indexed = FALSE
        ''')
        urls = [row[0] for row in cursor.fetchall()]
        return urls
    except Exception as e:
        print(f"Error retrieving URLs from database: {str(e)}")
        return []
    finally:
        conn.close()

def batch_index_urls(urls: List[str], max_pages: int = 100, min_delay: float = 0.5, max_delay: float = 2.0, db_path: str = 'clea_db.db') -> int:
    """Index multiple URLs in batch with a delay between requests.
    
    Args:
        urls: List of URLs to index
        max_pages: Maximum number of pages to index
        min_delay: Minimum delay between indexing requests
        max_delay: Maximum delay between indexing requests
        db_path: Path to database
        
    Returns:
        Number of successfully indexed pages
    """
    if not urls:
        print("No URLs to index.")
        return 0
    
    print(f"Starting batch indexing of {len(urls)} URLs (max: {max_pages})...")
    indexed_count = 0
    
    for url in urls[:max_pages]:
        if url.strip():
            print(f"Indexing URL: {url}")
            try:
                index_webpage(url, db_path)
                indexed_count += 1
            except Exception as e:
                print(f"Error during batch indexing of {url}: {str(e)}")
            
            # Add delay between requests
            delay = random.uniform(min_delay, max_delay)
            print(f"Waiting {delay:.2f} seconds...")
            time.sleep(delay)
    
    print(f"\nBatch indexing completed. Successfully indexed {indexed_count} pages.")
    return indexed_count

if __name__ == "__main__":
    # Get URLs from database instead of text file
    urls = get_unindexed_urls()
    
    if not urls:
        print("No unindexed URLs found in database. Run the crawler first.")
    else:
        print(f"Found {len(urls)} URLs to index")
        for url in urls:
            if url.strip():
                index_webpage(url)
                delay = random.uniform(0.5, 2.0)
                time.sleep(delay)
