# Backend Server - Search API that handles search queries and returns results
from flask import Flask, request, jsonify
from flask_cors import CORS
from servir import search_pages
from classeur import get_unindexed_urls, batch_index_urls
from glaneur import (
    add_url_to_sitemap, 
    add_urls_to_sitemap, 
    get_sitemap_urls, 
    remove_url_from_sitemap,
    crawl_from_sitemap
)
import sqlite3

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/api/search')
def api_search():
    """API endpoint for searching pages."""
    query = request.args.get('q', '')
    max_results = int(request.args.get('max_results', '10'))
    
    try:
        results = search_pages(query, max_results=max_results) if query else []
        return jsonify({
            'query': query,
            'results': results,
            'total': len(results)
        })
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok'})

@app.route('/api/sitemap', methods=['GET'])
def get_sitemap():
    """Get all URLs in sitemap with their status."""
    try:
        status_filter = request.args.get('status')
        urls = get_sitemap_urls(status=status_filter)
        return jsonify({
            'sitemap': urls,
            'total': len(urls)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sitemap', methods=['POST'])
def add_to_sitemap():
    """Add URL(s) to sitemap."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        urls = data.get('urls', [])
        url = data.get('url')
        
        if url:
            urls = [url]
        
        if not urls:
            return jsonify({'error': 'No URLs provided'}), 400
        
        added_count = add_urls_to_sitemap(urls)
        return jsonify({
            'message': f'Added {added_count} URLs to sitemap',
            'added_count': added_count,
            'total_provided': len(urls)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sitemap/<path:url>', methods=['DELETE'])
def remove_from_sitemap(url):
    """Remove URL from sitemap."""
    try:
        success = remove_url_from_sitemap(url)
        if success:
            return jsonify({'message': 'URL removed from sitemap'})
        else:
            return jsonify({'error': 'URL not found in sitemap'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crawl/force', methods=['POST'])
def force_crawl():
    """Force crawl all URLs in sitemap."""
    try:
        data = request.get_json() or {}
        max_pages = data.get('max_pages', 10)
        min_delay = data.get('min_delay', 1.0)
        max_delay = data.get('max_delay', 3.0)
        
        found_links = crawl_from_sitemap(
            force_crawl=True, 
            max_pages=max_pages,
            min_delay=min_delay,
            max_delay=max_delay
        )
        
        return jsonify({
            'message': 'Force crawl completed',
            'links_found': len(found_links),
            'crawl_type': 'force'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crawl/new', methods=['POST'])
def crawl_new():
    """Crawl only pending URLs in sitemap."""
    try:
        data = request.get_json() or {}
        max_pages = data.get('max_pages', 10)
        min_delay = data.get('min_delay', 1.0)
        max_delay = data.get('max_delay', 3.0)
        
        found_links = crawl_from_sitemap(
            force_crawl=False, 
            max_pages=max_pages,
            min_delay=min_delay,
            max_delay=max_delay
        )
        
        return jsonify({
            'message': 'New URL crawl completed',
            'links_found': len(found_links),
            'crawl_type': 'new_only'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/index/force', methods=['POST'])
def force_index():
    """Force index all URLs in the crawled_urls table regardless of previous indexing status."""
    try:
        data = request.get_json() or {}
        max_pages = data.get('max_pages', 10)
        min_delay = data.get('min_delay', 0.5)
        max_delay = data.get('max_delay', 2.0)
        
        # Get all URLs from the crawled_urls table
        conn = sqlite3.connect('clea_db.db')
        cursor = conn.cursor()
        cursor.execute('SELECT url FROM crawled_urls')
        all_urls = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        indexed_count = batch_index_urls(
            urls=all_urls,
            max_pages=max_pages,
            min_delay=min_delay,
            max_delay=max_delay
        )
        
        return jsonify({
            'message': 'Force indexing completed',
            'indexed_count': indexed_count,
            'index_type': 'force'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/index/new', methods=['POST'])
def index_new():
    """Index only URLs that have been crawled but not yet indexed."""
    try:
        data = request.get_json() or {}
        max_pages = data.get('max_pages', 10)
        min_delay = data.get('min_delay', 0.5)
        max_delay = data.get('max_delay', 2.0)
        
        # Get unindexed URLs using classeur's function
        unindexed_urls = get_unindexed_urls()
        
        indexed_count = batch_index_urls(
            urls=unindexed_urls,
            max_pages=max_pages,
            min_delay=min_delay,
            max_delay=max_delay
        )
        
        return jsonify({
            'message': 'New URL indexing completed',
            'indexed_count': indexed_count,
            'index_type': 'new_only'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6942)
