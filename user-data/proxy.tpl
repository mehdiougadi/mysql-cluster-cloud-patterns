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
import re
import random
import subprocess

app = Flask(__name__)

DB_CONFIG = {
    'manager_host': '{MANAGER_HOST}',
    'worker_hosts': '{WORKER_HOSTS}'.split(','),
    'user': 'app_user',
    'password': 'App123!',
    'database': 'sakila'
}

def is_read_query(query):
    query_upper = query.strip().upper()
    read_keywords = ['SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN']
    write_keywords = ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'GRANT', 'REVOKE']
    
    for keyword in write_keywords:
        if query_upper.startswith(keyword):
            return False
    
    for keyword in read_keywords:
        if query_upper.startswith(keyword):
            return True
    
    return False

def execute_query(host, query):
    try:
        connection = pymysql.connect(
            host=host,
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            
            if is_read_query(query):
                result = cursor.fetchall()
                return {'success': True, 'data': result, 'host': host}
            else:
                connection.commit()
                return {'success': True, 'affected_rows': cursor.rowcount, 'host': host}
    
    except Exception as e:
        return {'success': False, 'error': str(e), 'host': host}
    
    finally:
        if 'connection' in locals():
            connection.close()

def get_ping_time(host):
    try:
        result = subprocess.run(
            ['ping', '-c', '3', host],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'avg' in line:
                    avg_time = float(line.split('/')[-3])
                    return avg_time
        return float('inf')
    except Exception:
        return float('inf')

def select_worker_direct():
    return DB_CONFIG['manager_host']

def select_worker_random():
    workers = [w for w in DB_CONFIG['worker_hosts'] if w]
    if not workers:
        return DB_CONFIG['manager_host']
    return random.choice(workers)

def select_worker_customized():
    workers = [w for w in DB_CONFIG['worker_hosts'] if w]
    if not workers:
        return DB_CONFIG['manager_host']
    
    ping_times = {worker: get_ping_time(worker) for worker in workers}
    best_worker = min(ping_times, key=ping_times.get)
    return best_worker

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'proxy'}), 200

@app.route('/query', methods=['POST'])
def handle_query():
    try:
        data = request.get_json()
        query = data.get('query', '')
        strategy = data.get('strategy', 'direct')
        
        if not query:
            return jsonify({'success': False, 'error': 'No query provided'}), 400
        
        is_read = is_read_query(query)
        
        if is_read:
            if strategy == 'direct':
                host = select_worker_direct()
            elif strategy == 'random':
                host = select_worker_random()
            elif strategy == 'customized':
                host = select_worker_customized()
            else:
                host = select_worker_random()
        else:
            host = DB_CONFIG['manager_host']
        
        result = execute_query(host, query)
        
        return jsonify({
            'success': result['success'],
            'query_type': 'READ' if is_read else 'WRITE',
            'strategy': strategy,
            'host_used': host,
            'result': result
        }), 200 if result['success'] else 500
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
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

chown -R ec2-user:ec2-user /opt/proxy

systemctl daemon-reload
systemctl enable proxy.service
systemctl start proxy.service

touch /tmp/proxy_setup_complete
echo "Proxy setup completed at $(date)"