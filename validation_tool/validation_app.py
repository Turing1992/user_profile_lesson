#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify
from opensearchpy import OpenSearch
import json
import os
from datetime import datetime

app = Flask(__name__)

# OpenSearch configuration
opensearch_config = {
    "hosts": ['https://opensearch-o-00o160its7w7.escloud.ivolces.com:9200'],
    "http_auth": ('admin', 'Zhxg09z11@'),
    "use_ssl": True,
    "verify_certs": True,
    "ca_certs": 'ca.cer',
    "timeout": 30
}

# Initialize OpenSearch client
es_client = OpenSearch(**opensearch_config)

# Statistics storage (in production, use a database)
stats_file = 'validation_stats.json'

def load_stats():
    """Load validation statistics from file"""
    if os.path.exists(stats_file):
        with open(stats_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'correct': 0, 'incorrect': 0, 'total_queries': 0}

def save_stats(stats):
    """Save validation statistics to file"""
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_uid():
    """Search for UID in media_* indices"""
    try:
        data = request.get_json()
        uid = data.get('uid', '').strip()
        
        if not uid:
            return jsonify({'error': 'UID不能为空'}), 400
        
        # Search query
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"uid": uid}}
                    ]
                }
            }
            # Return all fields by not specifying _source
        }
        
        # Search in media_* indices
        response = es_client.search(
            index="media_*",
            body=query,
            size=10  # Limit results
        )
        
        # Extract all fields
        results = []
        for hit in response['body']['hits']['hits']:
            source = hit['_source']
            result = {
                'uid': source.get('uid', ''),
                'index': hit['_index'],
                'score': hit['_score'],
                'all_fields': source  # Include all fields
            }
            results.append(result)
        
        # Update total queries count
        stats = load_stats()
        stats['total_queries'] += 1
        save_stats(stats)
        
        return jsonify({
            'success': True,
            'results': results,
            'total_found': response['body']['hits']['total']['value']
        })
        
    except Exception as e:
        return jsonify({'error': f'查询失败: {str(e)}'}), 500

@app.route('/validate', methods=['POST'])
def validate_result():
    """Record validation result (correct/incorrect)"""
    try:
        data = request.get_json()
        is_correct = data.get('is_correct', False)
        
        stats = load_stats()
        if is_correct:
            stats['correct'] += 1
        else:
            stats['incorrect'] += 1
        
        save_stats(stats)
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        return jsonify({'error': f'记录失败: {str(e)}'}), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get current statistics"""
    stats = load_stats()
    
    # Calculate rates
    total = stats['total_queries']
    correct = stats['correct']
    incorrect = stats['incorrect']
    
    recall_rate = (correct / total * 100) if total > 0 else 0
    accuracy_rate = (correct / (correct + incorrect) * 100) if (correct + incorrect) > 0 else 0
    
    return jsonify({
        'stats': stats,
        'recall_rate': round(recall_rate, 2),
        'accuracy_rate': round(accuracy_rate, 2)
    })

@app.route('/reset', methods=['POST'])
def reset_stats():
    """Reset all statistics"""
    stats = {'correct': 0, 'incorrect': 0, 'total_queries': 0}
    save_stats(stats)
    return jsonify({'success': True, 'stats': stats})

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)