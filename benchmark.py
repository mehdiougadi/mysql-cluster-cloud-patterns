import requests
import time


def send_request(url, headers, query, strategy, results_dict):
    try:
        request_start = time.time()
        response = requests.post(
            url,
            headers=headers,
            json={'query': query, 'strategy': strategy},
            timeout=30
        )
        request_time = time.time() - request_start
        
        if response.status_code == 200:
            results_dict['success'] += 1
            data = response.json()
            results_dict['responses'].append({
                'host': data.get('host', 'unknown'),
                'time': request_time
            })
        else:
            results_dict['failed'] += 1
    except Exception as e:
        results_dict['failed'] += 1
        print(f'  Error: {str(e)}')


def generate_report(results, strategies, gatekeeper_ip, ip_to_role):
    filename = "benchmark_result.txt"
    with open(filename, 'w') as f:
        f.write(f"Benchmark Results - Gatekeeper: {gatekeeper_ip}\n")
        f.write("-" * 50 + "\n")
        
        for strategy in strategies:
            s_data = results['strategies'][strategy]
            read_avg = s_data['read']['total_time'] / 1000
            write_avg = s_data['write']['total_time'] / 1000
            f.write(f"Strategy: {strategy.upper()}\n")
            f.write(f"  READ  - Success: {s_data['read']['success']}, Avg: {read_avg:.4f}s\n")
            f.write(f"  WRITE - Success: {s_data['write']['success']}, Avg: {write_avg:.4f}s\n\n")

        f.write("Host Distribution (READ):\n")
        for strategy in strategies:
            hosts = {}
            for resp in results['strategies'][strategy]['read']['responses']:
                ip = resp['host']
                role = ip_to_role.get(ip, ip)
                hosts[role] = hosts.get(role, 0) + 1
            f.write(f"  {strategy.upper()}: {hosts}\n")


def benchmark_cluster(gatekeeper_ip: str, manager_ip: str, worker_ips: list, api_key: str = "blah-blah"):
    ip_to_role = {manager_ip: 'manager'}
    for idx, worker_ip in enumerate(worker_ips, 1):
        ip_to_role[worker_ip] = f'worker-{idx}'
    
    gatekeeper_url = f'http://{gatekeeper_ip}:8080/query'
    headers = {'Content-Type': 'application/json', 'X-API-Key': api_key}
    
    read_query = "SELECT * FROM actor LIMIT 10"
    write_query = "INSERT INTO actor (first_name, last_name, last_update) VALUES ('Benchmark', 'Test', NOW())"
    strategies = ['direct', 'random', 'customized']
    
    results = {'strategies': {}}

    for strategy in strategies:
        print(f'- Testing strategy: {strategy.upper()}')
        
        strategy_results = {
            'read': {'success': 0, 'failed': 0, 'total_time': 0, 'responses': []},
            'write': {'success': 0, 'failed': 0, 'total_time': 0, 'responses': []}
        }
        
        print(f'- Sending 1000 READ requests with {strategy} strategy...')
        read_start_time = time.time()
        for i in range(1000):
            send_request(gatekeeper_url, headers, read_query, strategy, strategy_results['read'])
            if (i + 1) % 100 == 0:
                print(f'  Progress: {i + 1}/1000 READ requests completed')
        strategy_results['read']['total_time'] = time.time() - read_start_time

        print('\n-  READ Results:')
        print(f'    - Successful: {strategy_results["read"]["success"]}/1000')
        print(f'    - Failed: {strategy_results["read"]["failed"]}/1000')
        print(f'    - Total Time: {strategy_results["read"]["total_time"]:.2f}s')
        print(f'    - Average Time per Request: {strategy_results["read"]["total_time"]/1000:.4f}s')

        print(f'\n  Sending 1000 WRITE requests with {strategy} strategy...')
        write_start_time = time.time()
        for i in range(1000):
            send_request(gatekeeper_url, headers, write_query, strategy, strategy_results['write'])
            if (i + 1) % 100 == 0:
                print(f'  Progress: {i + 1}/1000 WRITE requests completed')
        strategy_results['write']['total_time'] = time.time() - write_start_time

        print('\n-  WRITE Results:')
        print(f'    - Successful: {strategy_results["write"]["success"]}/1000')
        print(f'    - Failed: {strategy_results["write"]["failed"]}/1000')
        print(f'    - Total Time: {strategy_results["write"]["total_time"]:.2f}s')
        print(f'    - Average Time per Request: {strategy_results["write"]["total_time"]/1000:.4f}s')
        
        results['strategies'][strategy] = strategy_results
        print(f'-  Strategy {strategy.upper()} completed!\n')

    generate_report(results, strategies, gatekeeper_ip, ip_to_role)
    print('\n- Benchmark results saved to benchmark_result.txt')

    return results