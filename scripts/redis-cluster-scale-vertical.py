import memcache
import time
import json
import os
import sys
import subprocess
import signal
import psutil

import redis_utils

my_server_ip = "10.10.1.2"
server_port_st = 7000
seconds_before_scale = 5
seconds_before_shrink = 5

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

num_redis_clients = int(sys.argv[1].strip())
memcached_ip = sys.argv[2].strip()

mc = memcache.Client([memcached_ip])
assert (mc != None)
mc.flush_all()

num_all_servers = 5
server_ports = [7000, 7001, 7002, 7003, 7004]
initial_ports = [7000, 7001, 7002]
scale_port = 7003
shrink_port = 7004

servers = [f'{my_server_ip}:{p}' for p in server_ports]
initial_nodes = [f'{my_server_ip}:{p}' for p in initial_ports]
scale_node = f'{my_server_ip}:{scale_port}'
shrink_node = f'{my_server_ip}:{shrink_port}'

# clear old settings
redis_utils.cleanup_servers(server_ports, mkdir=True)

# construct configurations
redis_utils.create_config('redis-large.conf.templ', server_ports, my_server_ip)

# start redis instances
redis_utils.start_instances(server_ports, bind_cores=True)

time.sleep(2)
# create a redis cluster with all initial nodes
print(f"Creating a Redis cluster with {len(initial_ports)} nodes")
redis_utils.create_cluster(initial_nodes)

# reshard slots to 1 node
print("Reshard the cluster to 1 node")
port_node_id, node_id_port = redis_utils.get_node_id_port_map(
    initial_ports, my_server_ip)

port_slots = redis_utils.get_port_slot_map(initial_ports, my_server_ip)


redis_utils.cluster_reshard(
    f'{my_server_ip}:7000', port_node_id[7001], port_node_id[7000], port_slots[7001])
time.sleep(2)
redis_utils.cluster_reshard(
    f'{my_server_ip}:7000', port_node_id[7002], port_node_id[7000], port_slots[7002])

time.sleep(10)
redis_utils.cluster_del_node(f'{my_server_ip}:7000', port_node_id[7001])
redis_utils.cluster_del_node(f'{my_server_ip}:7000', port_node_id[7002])

# add two empty masters to the cluster
for p in [scale_port, shrink_port]:
    redis_utils.cluster_add_node(f'{my_server_ip}:7000', f'{my_server_ip}:{p}')
    node_id = redis_utils.get_node_id(p, my_server_ip)
    node_id_port[node_id] = p
    port_node_id[p] = node_id
    print(f'{p} {node_id}')
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

# scale up
time.sleep(seconds_before_scale)
print("Start scaling")
reshard_st = time.time()
redis_utils.cluster_reshard(
    f'{my_server_ip}:7000', port_node_id[7000], port_node_id[scale_port], 16384)
reshard_et = time.time()
reshard_time = int(reshard_et - reshard_st)
print(f"Reshard takes {reshard_time} seconds")

# scale down
time.sleep(seconds_before_shrink)
print("Start shrinking")
shrink_st = time.time()
redis_utils.cluster_reshard(
    f'{my_server_ip}:{scale_port}', port_node_id[scale_port], port_node_id[shrink_port], 16384)
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
with open('results/vertical_timer.json', 'w') as f:
    json.dump(timer_dict, f)

# wait for SIGINT
while True:
    time.sleep(5)
