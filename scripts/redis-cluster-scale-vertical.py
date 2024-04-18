import memcache
import time
import json
import os
import sys
import subprocess
import signal
import psutil

my_server_ip = "10.10.1.2"
server_port_st = 7000
seconds_before_scale = 5
seconds_before_shrink = 5

NUM_CORES = psutil.cpu_count(logical=False)


def cleanup(num_servers):
    for i in range(num_servers):
        if os.path.exists(f'./{server_port_st + i}/pid'):
            pid = int(open(f'./{server_port_st + i}/pid', 'r').read())
            os.system(f'sudo kill -9 {pid}')
        os.system(f'rm -rf ./{server_port_st + i}')


def SIGINT_handler(sig, frame):
    global num_all_servers
    print('Cleaning up before existing...')
    cleanup(num_all_servers)
    exit(0)


signal.signal(signal.SIGINT, SIGINT_handler)

if len(sys.argv) != 3:
    print("Usage {} <num_redis_clients> <memcached_ip>")

num_redis_clients = int(sys.argv[1].strip())
memcached_ip = sys.argv[2].strip()

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
cleanup(num_all_servers)
for p in server_ports:
    if os.path.exists(f'./{p}'):
        if os.path.exists(f'./{p}/pid'):
            pid = int(open(f'./{p}/pid', 'r').read())
            os.system(f'sudo kill -9 {pid}')
        os.system(f'rm -rf ./{p}')
    os.mkdir(f'./{p}')

# construct configurations
config_templ = open('redis-large.conf.templ', 'r').read()
for p in server_ports:
    with open(f'./{p}/redis.conf', 'w') as f:
        f.write(config_templ.format(p, p, my_server_ip))

# start redis instances
for i, p in enumerate(server_ports):
    os.system(f'cd {p}; \
              taskset -c {i % NUM_CORES} redis-server ./redis.conf; cd ..')

time.sleep(2)
# create a redis cluster with all initial nodes
print(f"Creating a Redis cluster with {len(initial_ports)} nodes")
cmd = 'redis-cli --cluster create ' \
    + ' '.join(initial_nodes) + ' --cluster-yes'
print(cmd)
os.system(cmd)
time.sleep(5)

# reshard slots to 1 node
print("Reshard the cluster to 1 node")
port_node_id = {}
node_id_port = {}
for i in initial_ports:
    proc = subprocess.Popen(f'redis-cli -h {my_server_ip} -p {i} \
                            cluster nodes | grep myself',
                            stdout=subprocess.PIPE, shell=True)
    proc.wait()
    output = proc.stdout.read().decode().strip()
    node_id = output.split(' ')[0]
    node_id_port[node_id] = i
    port_node_id[i] = node_id
    print(f'{i} {node_id}')

port_slots = {}
for p in initial_ports:
    proc = subprocess.Popen(
        f'redis-cli --cluster check {my_server_ip}:{p}\
        | grep {my_server_ip}:{p}', stdout=subprocess.PIPE,
        shell=True)
    proc.wait()
    l = proc.stdout.readline().decode().strip()
    num_slots = int(l.split(' ')[6])
    port_slots[p] = num_slots
    print(f'{p} {num_slots}')
os.system(f'redis-cli --cluster reshard {my_server_ip}:7001\
          --cluster-from {port_node_id[7001]}\
          --cluster-to {port_node_id[7000]}\
          --cluster-slots {port_slots[7001]}\
              --cluster-yes')
#   --cluster-yes > /dev/null 2 >&1')
time.sleep(2)
os.system(f'redis-cli --cluster reshard {my_server_ip}:7002\
          --cluster-from {port_node_id[7002]}\
          --cluster-to {port_node_id[7000]}\
          --cluster-slots {port_slots[7002]}\
            --cluster-yes')
# --cluster-yes > /dev/null 2>&1')
time.sleep(10)
os.system(
    f'redis-cli --cluster del-node {my_server_ip}:7000 {port_node_id[7001]}')
time.sleep(10)
os.system(
    f'redis-cli --cluster del-node {my_server_ip}:7000 {port_node_id[7002]}')

# add two empty masters to the cluster
for p in [scale_port, shrink_port]:
    os.system(
        f"redis-cli --cluster add-node {my_server_ip}:{p} {my_server_ip}:7000")
    time.sleep(5)
    proc = subprocess.Popen(f'redis-cli -h {my_server_ip} -p {p} \
                            cluster nodes | grep myself',
                            stdout=subprocess.PIPE, shell=True)
    proc.wait()
    output = proc.stdout.read().decode().strip()
    node_id = output.split(' ')[0]
    node_id_port[node_id] = p
    port_node_id[p] = node_id
    print(f'{p} {node_id}')
print("Finished cluster creation!")

# sync ycsb load
mc = memcache.Client([memcached_ip])
assert (mc != None)
mc.flush_all()
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
os.system(f'redis-cli --cluster reshard {my_server_ip}:7000\
          --cluster-from {port_node_id[7000]}\
          --cluster-to {port_node_id[scale_port]}\
          --cluster-slots {16384} --cluster-yes > /dev/null 2>&1')
reshard_et = time.time()
reshard_time = int(reshard_et - reshard_st)
print(f"Reshard takes {reshard_time} seconds")

# scale down
time.sleep(seconds_before_shrink)
print("Start shrinking")
shrink_st = time.time()
os.system(f'redis-cli --cluster reshard {my_server_ip}:7000\
          --cluster-from {port_node_id[scale_port]}\
          --cluster-to {port_node_id[shrink_port]}\
          --cluster-slots {16384} --cluster-yes > /dev/null 2>&1')
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
