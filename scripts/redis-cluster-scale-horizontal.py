import os
import sys
import time
import subprocess
import psutil
import memcache
import signal
import json

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
print(f"Creating a Redis cluster with {num_initial_servers} nodes")
cmd = 'redis-cli --cluster create ' \
    + ' '.join(initial_nodes) + ' --cluster-yes'
print(cmd)
os.system(cmd)
time.sleep(5)

# add scale nodes as empty masters to the cluster
for instance in scale_nodes:
    os.system(f"redis-cli --cluster add-node {instance} {my_server_ip}:7000")
    time.sleep(5)

# get port_node map
port_slots = {}
for port in server_ports:
    proc = subprocess.Popen(
        f'redis-cli --cluster check {my_server_ip}:{port} | grep {my_server_ip}:{port}',
        stdout=subprocess.PIPE,
        shell=True)
    proc.wait()
    l = proc.stdout.readline().decode().strip()
    num_slots = int(l.split(' ')[6])
    port_slots[port] = num_slots
    print(f'{port} {num_slots}')

# get ip_node_id and node_id_ip map
port_node_id = {}
node_id_port = {}
for port in server_ports:
    proc = subprocess.Popen(f'redis-cli -h {my_server_ip} -p {port} \
                            cluster nodes | grep myself',
                            stdout=subprocess.PIPE, shell=True)
    proc.wait()
    output = proc.stdout.read().decode().strip()
    node_id = output.split(' ')[0]
    node_id_port[node_id] = port
    port_node_id[port] = node_id
    print(f'{port} {node_id}')
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

# scale
time.sleep(seconds_before_scale)
print("Start scaling out")
reshard_st = time.time()
for i, port in enumerate(initial_ports):
    os.system(f'redis-cli --cluster reshard 127.0.0.1:7000\
              --cluster-from {port_node_id[port]}\
              --cluster-to {port_node_id[scale_ports[i]]}\
              --cluster-slots {port_slots[port]//2}\
              --cluster-yes > /dev/null 2>&1')
    port_slots[scale_ports[i]] = port_slots[port]//2
reshard_et = time.time()
reshard_time = int(reshard_et - reshard_st)
print(f"Reshard takes {reshard_time} seconds")

# shrink
time.sleep(seconds_before_shrink)
print("Start scaling in")
shrink_st = time.time()
for i, port in enumerate(initial_ports):
    os.system(f'redis-cli --cluster reshard 127.0.0.1:7000\
              --cluster-from {port_node_id[scale_ports[i]]}\
              --cluster-to {port_node_id[port]}\
              --cluster-slots {port_slots[scale_ports[i]]}\
              --cluster-yes > /dev/null 2>&1')
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
