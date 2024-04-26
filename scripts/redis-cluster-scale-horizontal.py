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
seconds_before_scale = 5
seconds_before_shrink = 5

NUM_CORES = psutil.cpu_count(logical=False)
redis_utils.set_cores(NUM_CORES)

mc = memcache.Client([memcached_ip])
assert (mc != None)
mc.flush_all()


def SIGINT_handler(sig, frame):
    global num_all_servers
    print('Cleaning up before existing...')
    server_ports = [server_port_st + i for i in range(num_all_servers)]
    redis_utils.cleanup_servers(server_ports)
    exit(0)


signal.signal(signal.SIGINT, SIGINT_handler)


if len(sys.argv) != 4:
    print("Usage {} <num_initial_servers> <num_redis_clients> <memcached_ip>")

num_initial_servers = int(sys.argv[1].strip())
num_all_servers = 2 * num_initial_servers
num_redis_clients = int(sys.argv[2].strip())
memcached_ip = sys.argv[3].strip()
if num_initial_servers < 3:
    print("We only support creating an initial cluster with more than three nodes")
    exit(1)


server_ports = [server_port_st + i for i in range(num_all_servers)]
initial_ports = [server_port_st + i for i in range(num_initial_servers)]
scale_ports = [server_port_st +
               i for i in range(num_initial_servers, num_all_servers)]

servers = [f'{my_server_ip}:{p}' for p in server_ports]
initial_nodes = [f'{my_server_ip}:{p}' for p in initial_ports]
scale_nodes = [f'{my_server_ip}:{p}' for p in scale_ports]

# clear old settings
redis_utils.cleanup_servers(server_ports, mkdir=True)

# construct configurations
redis_utils.create_config('redis-large.conf.templ', server_ports, my_server_ip)

# start redis instances
redis_utils.start_instances(server_ports, bind_cores=True)

time.sleep(2)
# create a redis cluster with all initial nodes
print(f"Creating a Redis cluster with {num_initial_servers} nodes")
redis_utils.create_cluster(initial_nodes)

# add scale nodes as empty masters to the cluster
for instance in scale_nodes:
    redis_utils.cluster_add_node(f'{my_server_ip}:7000', instance)

# get port_slot map
port_slots = redis_utils.get_port_slot_map(server_ports, my_server_ip)

# get ip_node_id and node_id_ip map
port_node_id, node_id_port = redis_utils.get_node_id_port_map(
    server_ports, my_server_ip)
print("Finished cluster creation!")

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

# scale
time.sleep(seconds_before_scale)
print("Start scaling out")
reshard_st = time.time()
for i, port in enumerate(initial_ports):
    redis_utils.cluster_reshard(
        f'{my_server_ip}:7000', port_node_id[port], port_node_id[scale_ports[i]], port_slots[port]//2)
    port_slots[scale_ports[i]] = port_slots[port]//2
    port_slots[port] = port_slots[port] - port_slots[port]//2
reshard_et = time.time()
reshard_time = int(reshard_et - reshard_st)
print(f"Reshard takes {reshard_time} seconds")

# shrink
time.sleep(seconds_before_shrink)
print("Start scaling in")
shrink_st = time.time()
for i, port in enumerate(initial_ports):
    redis_utils.cluster_reshard(
        f'{my_server_ip}:7000', port_node_id[scale_ports[i]], port_node_id[port], port_slots[scale_ports[i]])
shrink_et = time.time()
shrink_time = shrink_et - shrink_st
print(f"Shrink takes {shrink_time} seconds")


print(f"Reshard Time: {reshard_time}")
print(f"Shrink Time: {shrink_time}")

timer_dict = {
    "reshard_time": reshard_time,
    "shrink_time": shrink_time
}

if not os.path.exists('./results'):
    os.mkdir('results')
with open('results/horizontal_timer.json', 'w') as f:
    json.dump(timer_dict, f)

# wait for SIGINT
while True:
    time.sleep(5)
