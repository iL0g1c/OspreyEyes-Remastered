import psutil
import time
from datetime import datetime

def get_top_processes(limit=5):
    # Get all processes and sort by CPU usage, then memory usage
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    # Sort processes by CPU and memory usage and get the top 'limit' processes
    processes = sorted(processes, key=lambda p: (p['cpu_percent'], p['memory_percent']), reverse=True)[:limit]
    return processes

def log_resource_usage():
    while True:
        print(f"Logging resource usage at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        with open("resource_usage_log.txt", "a") as log_file:
            log_file.write(f"--- Resource Usage at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            
            top_processes = get_top_processes()
            print(top_processes)
            for proc in top_processes:
                log_file.write(
                    f"PID: {proc['pid']}, "
                    f"Name: {proc['name']}, "
                    f"CPU: {proc['cpu_percent']}%, "
                    f"Memory: {proc['memory_percent']}%\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
            log_file.write("\n")
        
        time.sleep(60)  # Wait for one minute

if __name__ == "__main__":
    log_resource_usage()
