import psutil
import time
from datetime import datetime

# Replace 'background_process_name', 'discord_bot_name', and 'mongodb_name' with actual names of your processes
PROCESS_NAMES = ["mongod"]
LOG_FILE = "log_file.log"

def get_process_stats(process_name):
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info', 'create_time']):
        print(proc.info['name'])
        if proc.info['name'] == process_name:
            uptime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
            return {
                'cpu_percent': proc.info['cpu_percent'],
                'memory_usage_mb': proc.info['memory_info'].rss / (1024 * 1024),
                'uptime': uptime.total_seconds() / 3600  # in hours
            }
    return None  # if process not found

def log_stats():
    with open(LOG_FILE, "a") as file:
        print(f"Logging at {datetime.now()}")
        file.write(f"\n--- Logging at {datetime.now()} ---\n")
        for process_name in PROCESS_NAMES:
            stats = get_process_stats(process_name)
            if stats:
                file.write(
                    f"{process_name}: CPU: {stats['cpu_percent']}%, "
                    f"Memory: {stats['memory_usage_mb']} MB, Uptime: {stats['uptime']} hours\n"
                )
            else:
                file.write(f"{process_name}: Process not found.\n")

if __name__ == "__main__":
    while True:
        log_stats()
        time.sleep(60)  # wait for 1 minute
