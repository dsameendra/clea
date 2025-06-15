# Backend Server - Search API that handles search queries and returns results
from flask import Flask, request, jsonify
from flask_cors import CORS
from servir import search_pages
from classeur import get_unindexed_urls, batch_index_urls
from glaneur import (
    add_urls_to_sitemap, 
    get_sitemap_urls, 
    remove_url_from_sitemap,
    crawl_from_sitemap
)
import sqlite3
import re
import math

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/api/search')
def api_search():
    """API endpoint for searching pages."""
    query = request.args.get('q', '')
    max_results = int(request.args.get('max_results', '10'))
    
    try:
        # Check if the query is a math expression
        if is_math_query(query):
            math_result = solve_math_query(query)
            if math_result:
                # If it's a valid math expression, return the calculation result
                return jsonify({
                    'query': query,
                    'calculation': math_result,
                    'results': [],  # Empty list for regular search results
                    'total': 0
                })
        
        # If not a math query or calculation failed, perform regular search
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
        min_delay = float(data.get('min_delay', 1.0))
        max_delay = float(data.get('max_delay', 3.0))
        
        found_links = crawl_from_sitemap(
            force_crawl=True,
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
        min_delay = float(data.get('min_delay', 1.0))
        max_delay = float(data.get('max_delay', 3.0))
        
        found_links = crawl_from_sitemap(
            force_crawl=False,
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
        max_pages = int(data.get('max_pages', 10))
        min_delay = float(data.get('min_delay', 0.5))
        max_delay = float(data.get('max_delay', 2.0))
        
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
        max_pages = int(data.get('max_pages', 10))
        min_delay = float(data.get('min_delay', 0.5))
        max_delay = float(data.get('max_delay', 2.0))
        
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

def is_math_query(query):
    """
    Check if the query is a mathematical expression.
    This function looks for patterns that indicate a math problem:
    - Contains numbers and operators
    - No excess text that would suggest it's not a calculation
    """
    # Remove whitespace and convert to lowercase
    cleaned_query = query.strip().lower()
    
    # Basic pattern matching for math expressions
    # Looks for: numbers, operators, parentheses, common math functions
    math_pattern = r'^[\s0-9+\-*/().,%^√πe\s]+$'
    
    # Check for specific math keywords
    math_keywords = ['sqrt', 'sin', 'cos', 'tan', 'log', 'ln']
    has_math_keyword = any(keyword in cleaned_query for keyword in math_keywords)
    
    # Check if query matches the pattern or contains math keywords
    is_math_expression = bool(re.match(math_pattern, cleaned_query)) or has_math_keyword
    
    # Ensure it contains at least one number and one operator
    has_number = bool(re.search(r'\d', cleaned_query))
    has_operator = bool(re.search(r'[+\-*/^]', cleaned_query))
    
    return is_math_expression and (has_number and (has_operator or has_math_keyword))

def safe_eval(expr):
    """
    Safely evaluate a mathematical expression.
    Uses a whitelist approach to only allow specific math operations.
    """
    # Replace common math notations with Python equivalents
    expr = expr.replace('^', '**')  # Convert caret to Python power operator
    expr = expr.replace('√', 'math.sqrt')  # Convert root symbol
    expr = expr.replace('π', 'math.pi')  # Convert pi symbol
    expr = expr.replace('pi', 'math.pi')  # Convert pi text
    
    # Replace common math functions
    expr = re.sub(r'sqrt\(', 'math.sqrt(', expr)
    expr = re.sub(r'sin\(', 'math.sin(', expr)
    expr = re.sub(r'cos\(', 'math.cos(', expr)
    expr = re.sub(r'tan\(', 'math.tan(', expr)
    expr = re.sub(r'log\(', 'math.log10(', expr)
    expr = re.sub(r'ln\(', 'math.log(', expr)
    
    # Create a safe local scope with only math functions
    safe_locals = {
        'math': math,
        'abs': abs,
        'round': round,
        'min': min,
        'max': max
    }
    
    try:
        # Use eval in a limited scope
        result = eval(expr, {'__builtins__': {}}, safe_locals)
        return result
    except Exception as e:
        # If evaluation fails, return None
        return None

def solve_math_query(query):
    """
    Solve a mathematical query and format the result.
    """
    # Clean the query
    query = query.strip()
    
    try:
        # Evaluate the expression
        result = safe_eval(query)
        
        if result is not None:
            # Format the result
            if isinstance(result, int) or result.is_integer():
                formatted_result = str(int(result))
            else:
                # Round to a reasonable number of decimal places for display
                formatted_result = str(round(result, 10)).rstrip('0').rstrip('.')
            
            return {
                'type': 'calculation',
                'expression': query,
                'result': formatted_result
            }
    except Exception:
        pass
    
    return None

@app.route('/api/solve', methods=['POST'])
def api_solve():
    """API endpoint for solving mathematical expressions."""
    data = request.get_json() or {}
    query = data.get('q', '')
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Check if it's a math query
        if is_math_query(query):
            # Solve the math query
            solution = solve_math_query(query)
            
            return jsonify({
                'query': query,
                'solution': solution
            })
        else:
            return jsonify({
                'query': query,
                'solution': 'Not a mathematical query'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6942)
