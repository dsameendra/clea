from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

# HTML template with modern styling
HTML_TEMPLATE = """
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clea Search Engine</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f7;
        }
        .search-container {
            text-align: center;
            margin: 50px 0;
        }
        .logo {
            font-size: 2.5em;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 20px;
        }
        .search-box {
            display: flex;
            max-width: 600px;
            margin: 0 auto;
        }
        .search-input {
            flex: 1;
            padding: 12px 20px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 24px 0 0 24px;
            outline: none;
            transition: all 0.3s;
        }
        .search-input:focus {
            border-color: #2c3e50;
        }
        .search-button {
            padding: 12px 24px;
            font-size: 16px;
            color: white;
            background-color: #2c3e50;
            border: none;
            border-radius: 0 24px 24px 0;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        .search-button:hover {
            background-color: #34495e;
        }
        .results {
            margin-top: 40px;
        }
        .result-item {
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .result-title {
            color: #1a0dab;
            font-size: 1.2em;
            text-decoration: none;
            margin-bottom: 8px;
            display: block;
        }
        .result-title:hover {
            text-decoration: underline;
        }
        .result-url {
            color: #006621;
            font-size: 0.9em;
            margin-bottom: 8px;
            display: block;
        }
        .result-snippet {
            color: #545454;
            font-size: 0.95em;
        }
        .result-meta {
            font-size: 0.85em;
            color: #666;
            margin-top: 8px;
        }
        .no-results {
            text-align: center;
            color: #666;
            margin-top: 40px;
        }
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            .search-container {
                margin: 30px 0;
            }
            .logo {
                font-size: 2em;
            }
            .search-box {
                flex-direction: column;
            }
            .search-input {
                border-radius: 24px;
                margin-bottom: 10px;
            }
            .search-button {
                border-radius: 24px;
            }
        }
    </style>
</head>
<body>
    <div class="search-container">
        <div class="logo">Clea</div>
        <form action="/" method="get" class="search-box">
            <input type="text" name="q" class="search-input" value="{{ query }}" 
                   placeholder="Search the web..." autofocus>
            <button type="submit" class="search-button">Search</button>
        </form>
    </div>

    {% if results %}
        <div class="results">
            {% for result in results %}
                <div class="result-item">
                    <a href="{{ result.url }}" class="result-title">{{ result.title or result.url }}</a>
                    <span class="result-url">{{ result.url }}</span>
                    <p class="result-snippet">{{ result.snippet }}</p>
                    <div class="result-meta">
                        Relevance score: {{ result.relevance_score }} | 
                        Matching terms: {{ result.matching_terms }}
                    </div>
                </div>
            {% endfor %}
        </div>
    {% elif query %}
        <div class="no-results">
            No results found for "{{ query }}"
        </div>
    {% endif %}
</body>
</html>
"""

@app.route('/')
def search():
    query = request.args.get('q', '')
    results = []
    
    error_message = None
    if query:
        try:
            # Call the search API endpoint
            response = requests.get(
                'http://localhost:6942/api/search',
                params={'q': query, 'max_results': 10},
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            if data.get('error'):
                error_message = data['error']
        except requests.exceptions.ConnectionError:
            error_message = "Unable to connect to search server. Please make sure servir.py is running."
        except Exception as e:
            error_message = f"Error performing search: {str(e)}"
            print(f"Error calling search API: {str(e)}")
    
    return render_template_string(
        HTML_TEMPLATE,
        query=query,
        results=results,
        error_message=error_message
    )

if __name__ == '__main__':
    # Run on a different port than the API server
    app.run(debug=True, host='0.0.0.0', port=5001)