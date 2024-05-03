import os
import sys
import time
import subprocess
import psutil
import memcache
import signal
import json

import redis_utils

my_server_ip = "10.10.1.2"
server_port_st = 7000
seconds_before_failover = 5
seconds_before_rereplicate = 5

NUM_CORES = psutil.cpu_count(logical=False)
redis_utils.set_cores(NUM_CORES)


def SIGINT_handler(sig, frame):
    global num_all_servers
    print('Cleaning up before existing...')
    server_ports = [server_port_st + i for i in range(num_all_servers)]
    redis_utils.cleanup_servers(server_ports)
    exit(0)


signal.signal(signal.SIGINT, SIGINT_handler)


if len(sys.argv) != 3:
    print("Usage {} <num_redis_clients> <memcached_ip>")

num_all_servers = 4
num_redis_clients = int(sys.argv[1].strip())
memcached_ip = sys.argv[2].strip()

mc = memcache.Client([memcached_ip])
assert (mc != None)
mc.flush_all()

server_ports = [server_port_st + i for i in range(num_all_servers)]
sentinel_port = server_ports[0]
primary_port = server_ports[1]
backup_old_port = server_ports[2]
backup_new_port = server_ports[3]

# clear old settings
redis_utils.cleanup_servers(server_ports, mkdir=True)

# construct configurations
redis_utils.create_config('redis-server.conf.templ', [primary_port], my_server_ip)
redis_utils.create_config('redis-sentinel.conf.templ', [sentinel_port], my_server_ip, my_server_ip, primary_port)
redis_utils.create_config('redis-slave.conf.templ', [backup_old_port, backup_new_port], my_server_ip, my_server_ip, primary_port)

# start redis instances
# 1. start primary and backups
redis_utils.start_instances([primary_port, backup_old_port], bind_cores=True)
time.sleep(2)
# 2. start sentinel
redis_utils.start_instances([sentinel_port], bind_cores=True, sentinel=True)

# sync ycsb load
print("Wait all clients ready.")
for i in range(1, num_redis_clients + 1):
    ready_msg = f'client-{i}-ready-0'
    val = mc.get(ready_msg)
    while val == None:
        val = mc.get(ready_msg)
    # print(ready_msg)
print("Notify Clients to load.")
mc.set('all-client-ready-0', 1)  # clients start loading

# wait all clients load ready and sync their to execute trans
for i in range(1, num_redis_clients + 1):
    ready_msg = f'client-{i}-ready-1'
    val = mc.get(ready_msg)
    while val == None:
        val = mc.get(ready_msg)
    # print(ready_msg)
mc.set('all-client-ready-1', 1)  # clients start executing trans
print("Notify all clients start trans")

# fail master
time.sleep(seconds_before_failover)
print("Failing over the master")
redis_utils.kill_servers([primary_port])

# rereplicate backup
time.sleep(seconds_before_rereplicate)
print("Creating a new backup")
redis_utils.start_instances([backup_new_port], bind_cores=True)

timer_dict = {
    'failover_st': seconds_before_failover,
    'rereplicate_st': seconds_before_failover + seconds_before_rereplicate
}

if not os.path.exists('./results'):
    os.mkdir('results')
with open('results/sentinel_timer.json', 'w') as f:
    json.dump(timer_dict, f)

# wait for SIGINT
while True:
    time.sleep(5)