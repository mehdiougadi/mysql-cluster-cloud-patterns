#!/bin/bash
set -e

exec > >(tee -a /var/log/user-data.log)
exec 2>&1

echo "Starting Proxy setup at $(date)"

yum update -y
yum install -y python3 python3-pip mariadb105 iputils
pip3 install flask pymysql requests

mkdir -p /opt/proxy
cd /opt/proxy

cat > /opt/proxy/proxy_server.py <<'PROXY_APP'
from flask import Flask, request, jsonify
import pymysql
import random
import subprocess
import time
import threading

app = Flask(__name__)

DB_CONFIG = {
    'manager_host': '{MANAGER_HOST}',
    'worker_hosts': '{WORKER_HOSTS}'.split(','),
    'user': 'app_user',
    'password': 'Mehdi1603!',
    'database': 'sakila'
}

worker_health = {}
health_lock = threading.Lock()

def is_read_query(query):
    query_upper = query.strip().upper()
    read_keywords = ['SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN']
    write_keywords = ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'GRANT', 'REVOKE']
    for keyword in write_keywords:
        if query_upper.startswith(keyword): return False
    for keyword in read_keywords:
        if query_upper.startswith(keyword): return True
    return False

def execute_query(host, query):
    try:
        connection = pymysql.connect(
            host=host, user=DB_CONFIG['user'], password=DB_CONFIG['password'],
            database=DB_CONFIG['database'], cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            cursor.execute(query)
            if is_read_query(query):
                return {'success': True, 'data': cursor.fetchall(), 'host': host}
            else:
                connection.commit()
                return {'success': True, 'affected_rows': cursor.rowcount, 'host': host}
    except Exception as e:
        return {'success': False, 'error': str(e), 'host': host}
    finally:
        if 'connection' in locals(): connection.close()

def get_ping_time(host):
    try:
        result = subprocess.run(['ping', '-c', '3', host], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'avg' in line: return float(line.split('/')[-3])
        return float('inf')
    except: return float('inf')

def background_health_monitor():
    while True:
        new_health = {w: get_ping_time(w) for w in DB_CONFIG['worker_hosts'] if w}
        with health_lock:
            worker_health.clear()
            worker_health.update(new_health)
        time.sleep(10)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'proxy'}), 200

@app.route('/query', methods=['POST'])
def handle_query():
    data = request.get_json()
    query = data.get('query', '')
    strategy = data.get('strategy', 'random')
    
    if is_read_query(query):
        if strategy == 'direct': host = DB_CONFIG['manager_host']
        elif strategy == 'customized':
            with health_lock:
                host = min(worker_health, key=worker_health.get) if worker_health else DB_CONFIG['manager_host']
        else: host = random.choice(DB_CONFIG['worker_hosts'])
    else:
        host = DB_CONFIG['manager_host']

    result = execute_query(host, query)
    return jsonify(result), 200 if result['success'] else 500

if __name__ == '__main__':
    threading.Thread(target=background_health_monitor, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
PROXY_APP

cat > /etc/systemd/system/proxy.service <<'SERVICE'
[Unit]
Description=MySQL Cluster Proxy Service
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/proxy
ExecStart=/usr/bin/python3 /opt/proxy/proxy_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable proxy.service
systemctl start proxy.service
echo "Proxy setup completed"