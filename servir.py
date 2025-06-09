# Server - Serves search queries 
import sqlite3
from typing import List, Dict
import json
from classeur import tokenize_and_stem

def search_pages(query: str, db_path: str = 'clea_db.db', max_results: int = 100) -> List[Dict]:
    """Search indexed pages using a text query."""
    query_words = tokenize_and_stem(query)
    
    if not query_words:
        return []

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # get matching webpage IDs for each word
        matching_pages = {}
        for word in query_words:
            cursor.execute('''
            SELECT webpage_ids, webpage_frequencies
            FROM word_index
            WHERE word = ?
            ''', (word,))
            
            row = cursor.fetchone()
            if row:
                webpage_ids = json.loads(row[0])
                frequencies = json.loads(row[1])
                
                for webpage_id in webpage_ids:
                    if webpage_id not in matching_pages:
                        matching_pages[webpage_id] = {
                            'matching_terms': 0,
                            'total_frequency': 0
                        }
                    matching_pages[webpage_id]['matching_terms'] += 1
                    matching_pages[webpage_id]['total_frequency'] += frequencies[webpage_id]

        # Sort by matching terms and frequency
        sorted_pages = sorted(
            matching_pages.items(),
            key=lambda x: (x[1]['matching_terms'], x[1]['total_frequency']),
            reverse=True
        )[:max_results]

        results = []
        for webpage_id, scores in sorted_pages:
            cursor.execute('''
            SELECT url, title
            FROM webpages
            WHERE id = ?
            ''', (webpage_id,))
            
            row = cursor.fetchone()
            if row:
                url = row[0]
                title = row[1]
                
                cursor.execute('SELECT snippet FROM webpages WHERE id = ?', (webpage_id,))
                snippet = cursor.fetchone()[0]
                
                results.append({
                    'url': url,
                    'title': title,
                    'snippet': snippet,
                    'matching_terms': scores['matching_terms'],
                    'relevance_score': scores['total_frequency']
                })
        
        return results
        
    finally:
        conn.close()