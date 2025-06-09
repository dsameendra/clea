# Backend Server - Search API that handles search queries and returns results
from flask import Flask, request, jsonify
from flask_cors import CORS
from servir import search_pages

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6942)
