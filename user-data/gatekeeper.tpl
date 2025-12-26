#!/bin/bash
set -e

exec > >(tee -a /var/log/user-data.log)
exec 2>&1

echo "Starting Gatekeeper setup at $(date)"

echo "Updating system packages"
apt-get update -y

echo "Installing Python3 and pip"
apt-get install -y python3 python3-pip

echo "Installing Python packages"
pip3 install flask requests

echo "Creating gatekeeper application directory"
mkdir -p /opt/gatekeeper
cd /opt/gatekeeper

echo "Creating gatekeeper server application"
cat > /opt/gatekeeper/gatekeeper_server.py <<'GATEKEEPER_APP'
from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

PROXY_HOST = '__PROXY_HOST__'
PROXY_PORT = 5000
PROXY_URL = f'http://{PROXY_HOST}:{PROXY_PORT}/query'

def is_authenticated(request):
    api_key = request.headers.get('X-API-Key', '')
    
    if not api_key or len(api_key) == 0:
        return False
    
    return True

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'gatekeeper'}), 200

@app.route('/query', methods=['POST'])
def handle_request():
    try:
        if not is_authenticated(request):
            return jsonify({
                'success': False,
                'error': 'Authentication failed - API key required'
            }), 401
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Invalid request format'
            }), 400
        
        query = data.get('query', '')
        strategy = data.get('strategy', 'direct')
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'No query provided'
            }), 400
        
        try:
            proxy_response = requests.post(
                PROXY_URL,
                json={'query': query, 'strategy': strategy},
                timeout=30
            )
            
            return jsonify(proxy_response.json()), proxy_response.status_code
        
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': 'Failed to communicate with proxy',
                'details': str(e)
            }), 503
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
GATEKEEPER_APP

echo "Creating systemd service for gatekeeper"
cat > /etc/systemd/system/gatekeeper.service <<'SERVICE'
[Unit]
Description=MySQL Cluster Gatekeeper Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/gatekeeper
ExecStart=/usr/bin/python3 /opt/gatekeeper/gatekeeper_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

echo "Setting permissions"
chown -R ubuntu:ubuntu /opt/gatekeeper

echo "Starting gatekeeper service"
systemctl daemon-reload
systemctl enable gatekeeper.service
systemctl start gatekeeper.service

touch /tmp/gatekeeper_setup_complete
echo "Gatekeeper setup completed at $(date)"