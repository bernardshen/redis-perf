import memcache
import time
import json
import os
import subprocess

from cluster_setting import *
from cmd_manager import CMDManager

FIRST_EXECUTE_TIME = 800
SECOND_EXECUTE_TIME = 2000
TOTAL_EXECUTE_TIME = 4800

cmd_manager = CMDManager(cluster_ips)

num_instance_controllers = 1
memcached_ip = cluster_ips[master_id]
instance_ips = [cluster_ips[cn_id]]
client_ips = [cluster_ips[client_ids[0]]]

num_clients = 128
workload = 'ycsbc_small'

redis_work_dir = f'{EXP_HOME}/scripts'
ULIMIT_CMD = "ulimit -n unlimited"

mc = memcache.Client([memcached_ip])
assert (mc != None)
mc.flush_all()

instance_ip = cluster_ips[cn_id]
initial_ports = [7000, 7001, 7002]
server_ports = [7000, 7001, 7002]
initial_nodes = [f'{instance_ip}:{i}' for i in initial_ports]
scale_port = 7003
print(f"Start a Redis Cluter with 2 instances")

# start a cluster with 3 nodes
cmd = f"{ULIMIT_CMD} && cd {redis_work_dir} && ./run_redis_cluster_nodes.sh 4 {cluster_ips[cn_id]}"
print(cmd)
instance_prom = cmd_manager.execute_on_node(cn_id, cmd)

print('Wait Redis instance ready')
for i in range(num_instance_controllers):
    ready_msg = f'redis-{i}-ready'
    val = mc.get(ready_msg)
    while val == None:
        val = mc.get(ready_msg)
    print(ready_msg)

# create a redis cluster with the three nodes
time.sleep(2)
print("Creating Redis cluster")
cmd = 'redis-cli --cluster create ' \
        + ' '.join(initial_nodes) + ' --cluster-yes'
print(cmd)
os.system(cmd)

# reshard slots to 1 node
port_node_id = {}
node_id_port = {}
for i in server_ports:
    proc = subprocess.Popen(f'redis-cli -h {cluster_ips[cn_id]} -p {i} \
                            cluster nodes | grep myself',
                            stdout=subprocess.PIPE, shell=True)
    proc.wait()
    output = proc.stdout.read().decode().strip()
    node_id = output.split(' ')[0]
    node_id_port[node_id] = i
    port_node_id[i] = node_id
    print(f'{i} {node_id}')

ip_slots = {}
for p in server_ports:
    proc = subprocess.Popen(
        f'redis-cli --cluster check {cluster_ips[cn_id]}:{p}\
        | grep {cluster_ips[cn_id]}:{p}', stdout=subprocess.PIPE,
        shell=True)
    proc.wait()
    l = proc.stdout.readline().decode().strip()
    num_slots = int(l.split(' ')[6])
    ip_slots[p] = num_slots
    print(f'{p} {num_slots}')
os.system(f'redis-cli --cluster reshard {cluster_ips[cn_id]}:7001\
          --cluster-from {port_node_id[7001]}\
          --cluster-to {port_node_id[7000]}\
          --cluster-slots {ip_slots[7001]} --cluster-yes > /dev/null 2>&1')
time.sleep(2)
os.system(f'redis-cli --cluster reshard {cluster_ips[cn_id]}:7002\
          --cluster-from {port_node_id[7002]}\
          --cluster-to {port_node_id[7000]}\
          --cluster-slots {ip_slots[7002]} --cluster-yes > /dev/null 2>&1')
time.sleep(10)
os.system(
    f'redis-cli --cluster del-node {cluster_ips[cn_id]}:7000 {port_node_id[7001]}')
time.sleep(10)
os.system(
    f'redis-cli --cluster del-node {cluster_ips[cn_id]}:7000 {port_node_id[7002]}')

# add a empty master to the cluster
os.system(f"redis-cli --cluster add-node {instance_ip}:{scale_port} {instance_ip}:7000")
time.sleep(5)
proc = subprocess.Popen(f'redis-cli -h {instance_ip} -p {scale_port} \
                        cluster nodes | grep myself',
                        stdout=subprocess.PIPE, shell=True)
proc.wait()
output = proc.stdout.read().decode().strip()
node_id = output.split(' ')[0]
node_id_port[node_id] = scale_port
port_node_id[scale_port] = node_id
print(f'{scale_port} {node_id}')

# execute
# start clients
time.sleep(10)
print("Starting clients")
c_prom = cmd_manager.execute_on_node(
    client_ids[0], 
    f'{ULIMIT_CMD} && cd {redis_work_dir} && ../build/redis_perf 10.10.1.2 {workload} tcp://10.10.1.1:7000 {TOTAL_EXECUTE_TIME} scale-horizontal.json'
)

# sync ycsb load
print("Wait all clients ready.")
for i in range(1, num_clients + 1):
    ready_msg = f'client-{i}-ready-0'
    val = mc.get(ready_msg)
    while val == None:
        val = mc.get(ready_msg)
    # print(ready_msg)
print("Notify Clients to load.")
mc.set('all-client-ready-0', 1)  # clients start loading

# wait all clients load ready and sync their to execute trans
for i in range(1, num_clients + 1):
    ready_msg = f'client-{i}-ready-1'
    val = mc.get(ready_msg)
    while val == None:
        val = mc.get(ready_msg)
    # print(ready_msg)
mc.set('all-client-ready-1', 1)  # clients start executing trans
print("Notify all clients start trans")

# reshard half of slots to another node
time.sleep(FIRST_EXECUTE_TIME)
print("Start scaling")
reshard_st = time.time()
os.system(f'redis-cli --cluster reshard {cluster_ips[cn_id]}:7000\
          --cluster-from {port_node_id[7000]}\
          --cluster-to {port_node_id[scale_port]}\
          --cluster-slots {16384//2} --cluster-yes > /dev/null 2>&1')
reshard_et = time.time()
reshard_time = int(reshard_et - reshard_st)
print(f"Reshard takes {reshard_time} seconds")

# reshard half of slots back to one node
time.sleep(SECOND_EXECUTE_TIME - reshard_time)
print("Start shrinking")
shrink_st = time.time()
os.system(f'redis-cli --cluster reshard {cluster_ips[cn_id]}:7000\
          --cluster-from {port_node_id[scale_port]}\
          --cluster-to {port_node_id[7000]}\
          --cluster-slots {16384//2} --cluster-yes > /dev/null 2>&1')
shrink_et = time.time()
shrink_time = shrink_et - shrink_st
print(f"Shrink takes {shrink_time} seconds")

# wait client finish
c_prom.join()
mc.set('test-finish', 1)

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