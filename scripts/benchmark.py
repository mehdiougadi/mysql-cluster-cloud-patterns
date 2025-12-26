import matplotlib.pyplot as plt
import requests
import subprocess
import time
import os
import re


"""
Strategies Benchmarking
"""
def send_http_request(url, headers, query, strategy, results):
    try:
        start = time.time()
        response = requests.post(
            url,
            headers=headers,
            json={'query': query, 'strategy': strategy},
            timeout=30
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            results['success'] += 1
            data = response.json()
            results['responses'].append({
                'host': data.get('host', 'unknown'),
                'time': elapsed
            })
        else:
            results['failed'] += 1
    except Exception as e:
        results['failed'] += 1
        print(f'- Error: {str(e)}')


def execute_strategy_requests(url, headers, query, strategy, request_type, count=1000):
    import sys
    
    print(f'- Sending {count} {request_type} requests')
    
    results = {'success': 0, 'failed': 0, 'total_time': 0, 'responses': []}
    start = time.time()
    
    for i in range(count):
        send_http_request(url, headers, query, strategy, results)
        

        sys.stdout.write(f'\r  Currently at {i + 1}/{count} requests (Success: {results["success"]}/{i + 1})')
        sys.stdout.flush()
    
    sys.stdout.write('\r' + ' ' * 80 + '\r')
    
    results['total_time'] = time.time() - start
    print(f"- {request_type} - Success: {results['success']}/{count}, Time: {results['total_time']:.2f}s")
    
    return results


def save_benchmark_report(results, strategies, gatekeeper_ip, ip_to_role):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results_dir = os.path.join(project_root, 'results')
    
    os.makedirs(results_dir, exist_ok=True)
    
    results_file = os.path.join(results_dir, 'benchmark_result.txt')
    
    with open(results_file, 'w') as f:
        f.write(f"Benchmark Results - Gatekeeper: {gatekeeper_ip}\n")
        f.write("-" * 50 + "\n")
        
        for strategy in strategies:
            data = results['strategies'][strategy]
            read_avg = data['read']['total_time'] / 1000
            write_avg = data['write']['total_time'] / 1000
            f.write(f"Strategy: {strategy.upper()}\n")
            f.write(f"  READ  - Success: {data['read']['success']}, Avg: {read_avg:.4f}s\n")
            f.write(f"  WRITE - Success: {data['write']['success']}, Avg: {write_avg:.4f}s\n\n")

        f.write("Host Distribution (READ):\n")
        for strategy in strategies:
            hosts = {}
            for resp in results['strategies'][strategy]['read']['responses']:
                ip = resp['host']
                role = ip_to_role.get(ip, ip)
                hosts[role] = hosts.get(role, 0) + 1
            f.write(f"  {strategy.upper()}: {hosts}\n")

    print('\n- All Cluster Benchmark results are available')


def run_cluster_benchmark(gatekeeper_ip, manager_ip, worker_ips, api_key="test-api-key"):
    ip_to_role = {manager_ip: 'manager'}
    for idx, ip in enumerate(worker_ips, 1):
        ip_to_role[ip] = f'worker-{idx}'
    
    url = f'http://{gatekeeper_ip}:8080/query'
    headers = {'Content-Type': 'application/json', 'X-API-Key': api_key}
    read_query = "SELECT * FROM actor LIMIT 10"
    write_query = "INSERT INTO actor (first_name, last_name, last_update) VALUES ('Benchmark', 'Test', NOW())"
    strategies = ['direct', 'random', 'customized']
    results = {'strategies': {}}

    for strategy in strategies:
        print(f'\n- Testing {strategy.upper()} strategy')
        
        read_results = execute_strategy_requests(url, headers, read_query, strategy, 'READ')
        write_results = execute_strategy_requests(url, headers, write_query, strategy, 'WRITE')
        
        results['strategies'][strategy] = {
            'read': read_results,
            'write': write_results
        }

    save_benchmark_report(results, strategies, gatekeeper_ip, ip_to_role)
    return results


def visualize_cluster_benchmark(results, strategies):
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
    os.makedirs(results_dir, exist_ok=True)
    
    read_times = [results['strategies'][s]['read']['total_time'] / 1000 for s in strategies]
    write_times = [results['strategies'][s]['write']['total_time'] / 1000 for s in strategies]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = range(len(strategies))
    width = 0.35
    
    ax.bar([i - width/2 for i in x], read_times, width, label='READ', color='blue')
    ax.bar([i + width/2 for i in x], write_times, width, label='WRITE', color='red')
    
    ax.set_xlabel('Strategy')
    ax.set_ylabel('Average Time (seconds)')
    ax.set_title('Benchmark: Response Time by Strategy')
    ax.set_xticks(x)
    ax.set_xticklabels([s.upper() for s in strategies])
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    for i, (r, w) in enumerate(zip(read_times, write_times)):
        ax.text(i - width/2, r, f'{r:.4f}s', ha='center', va='bottom')
        ax.text(i + width/2, w, f'{w:.4f}s', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, 'benchmark_chart.png'), dpi=150)
    print('\n- Chart saved: results/benchmark_chart.png')
    plt.close()


"""
MySQL Sysbench
"""
def run_ssh_command(host, command, key_path, user='ubuntu', timeout=30):
    try:
        cmd = [
            'ssh', '-i', key_path,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', f'ConnectTimeout={timeout}',
            f'{user}@{host}', command
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except:
        return -1, '', 'Command failed'


def copy_file_via_scp(local_path, remote_host, remote_path, key_path, user='ubuntu'):
    try:
        cmd = [
            'scp', '-i', key_path,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            local_path, f'{user}@{remote_host}:{remote_path}'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False


def setup_ssh_key_on_gatekeeper(gatekeeper_ip, key_path):
    print('- Copying SSH key to gatekeeper')
    if not copy_file_via_scp(key_path, gatekeeper_ip, '~/mysql-cluster-key.pem', key_path):
        print('- ERROR: Failed to copy SSH key')
        return False
    
    returncode, _, stderr = run_ssh_command(gatekeeper_ip, 'chmod 400 ~/mysql-cluster-key.pem', key_path)
    if returncode != 0:
        print(f'- ERROR: Failed to set permissions: {stderr}')
        return False
    
    return True


def collect_node_sysbench(gatekeeper_ip, node_name, node_ip, key_path, results_dir):
    print(f'- Collecting from {node_name.upper()} ({node_ip})')
    
    cmd = f'ssh -i ~/mysql-cluster-key.pem -o StrictHostKeyChecking=no ubuntu@{node_ip} "cat /tmp/sysbench_results.txt"'
    returncode, stdout, _ = run_ssh_command(gatekeeper_ip, cmd, key_path, timeout=30)
    
    if returncode != 0 or not stdout.strip():
        print('- No results found, trying log...')
        cmd = f'ssh -i ~/mysql-cluster-key.pem -o StrictHostKeyChecking=no ubuntu@{node_ip} "grep -A 100 \\"Running sysbench benchmark\\" /var/log/user-data.log"'
        returncode, stdout, _ = run_ssh_command(gatekeeper_ip, cmd, key_path, timeout=30)
        if returncode != 0:
            print('- ERROR: Could not retrieve results')
            return False
    
    results_file = os.path.join(results_dir, f'{node_name}_sysbench_results.txt')
    with open(results_file, 'w') as f:
        f.write(stdout)
    return True


def collect_sysbench(gatekeeper_ip, manager_ip, worker_ips, key_path):
    print('\n- Collecting sysbench results')
    
    if not setup_ssh_key_on_gatekeeper(gatekeeper_ip, key_path):
        return False
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results_dir = os.path.join(project_root, 'results')
    
    os.makedirs(results_dir, exist_ok=True)
    
    all_nodes = {'manager': manager_ip, **{f'worker-{i+1}': ip for i, ip in enumerate(worker_ips)}}
    
    for node_name, node_ip in all_nodes.items():
        collect_node_sysbench(gatekeeper_ip, node_name, node_ip, key_path, results_dir)
    
    print('- All sysbench results are available')
    return True


def visualize_sysbench_results():
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
    
    nodes_data = {}
    for filename in os.listdir(results_dir):
        if filename.endswith('_sysbench_results.txt'):
            node_name = filename.replace('_sysbench_results.txt', '')
            
            with open(os.path.join(results_dir, filename), 'r') as f:
                content = f.read()
                match = re.search(r'transactions:\s+\d+\s+\(([\d.]+)\s+per sec', content)
                if match:
                    nodes_data[node_name] = float(match.group(1))
    
    if not nodes_data:
        print('- No sysbench results found')
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    nodes = sorted(nodes_data.keys())
    values = [nodes_data[n] for n in nodes]
    
    ax.bar(nodes, values, color='green')
    ax.set_xlabel('Node')
    ax.set_ylabel('Transactions Per Second')
    ax.set_title('Sysbench: Performance by Node')
    ax.grid(axis='y', alpha=0.3)
    
    for i, (node, val) in enumerate(zip(nodes, values)):
        ax.text(i, val, f'{val:.1f}', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, 'sysbench_chart.png'), dpi=150)
    print(f'\n- Chart saved: results/sysbench_chart.png')
    plt.close()