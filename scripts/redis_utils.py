import os
import time
import subprocess

_NUM_CORES = 0


def set_cores(num_cores):
    global _NUM_CORES
    _NUM_CORES = num_cores


def cleanup_servers(server_ports, mkdir=False):
    for p in server_ports:
        if os.path.exists(f'./{p}/pid'):
            pid = int(open(f'./{p}/pid', 'r').read())
            os.system(f'sudo kill -9 {pid}')
        os.system(f'rm -rf ./{p}')
        if mkdir:
            os.mkdir(f'./{p}')


def create_config(template_fname, server_ports, my_server_ip):
    config_templ = open(template_fname, 'r').read()
    for p in server_ports:
        with open(f'./{p}/redis.conf', 'w') as f:
            f.write(config_templ.format(p, p, my_server_ip))


def start_instances(server_ports, bind_cores=False):
    for i, p in enumerate(server_ports):
        bind_core_cmd = ''
        if bind_cores:
            bind_core_cmd = f'taskset -c {i % _NUM_CORES}'
        os.system(f'cd {p}; \
                  {bind_core_cmd} redis-server ./redis.conf; cd ..')


def create_cluster(nodes_ip):
    cmd = 'redis-cli --cluster create ' + ' '.join(nodes_ip) + ' --cluster-yes'
    print(cmd)
    os.system(cmd)
    time.sleep(5)


def get_node_id(port, my_server_ip):
    proc = subprocess.Popen(f'redis-cli -h {my_server_ip} -p {port} \
                            cluster nodes | grep myself',
                            stdout=subprocess.PIPE, shell=True)
    proc.wait()
    output = proc.stdout.read().decode().strip()
    node_id = output.split(' ')[0]
    return node_id


def get_node_id_port_map(ports, my_server_ip):
    port_node_id = {}
    node_id_port = {}
    for i in ports:
        node_id = get_node_id(i, my_server_ip)
        node_id_port[node_id] = i
        port_node_id[i] = node_id
        print(f'{i} {node_id}')
    return port_node_id, node_id_port


def get_port_slot(port, my_server_ip):
    proc = subprocess.Popen(
        f'redis-cli --cluster check {my_server_ip}:{port} | grep {my_server_ip}:{port}',
        stdout=subprocess.PIPE,
        shell=True)
    proc.wait()
    l = proc.stdout.readline().decode().strip()
    num_slots = int(l.split(' ')[6])
    return num_slots


def get_port_slot_map(ports, my_server_ip):
    port_slots = {}
    for p in ports:
        num_slots = get_port_slot(p, my_server_ip)
        port_slots[p] = num_slots
        print(f'{p} {num_slots}')
    return port_slots


def cluster_reshard(master_ip, from_node_id, to_node_id, num_slots):
    os.system(f'redis-cli --cluster reshard {master_ip}\
              --cluster-from {from_node_id}\
              --cluster-to {to_node_id}\
              --cluster-slots {num_slots}\
              --cluster-yes > /dev/null 2 >&1')
    #   --cluster-yes')


def cluster_del_node(master_ip, node_id):
    os.system(
        f'redis-cli --cluster del-node {master_ip} {node_id}')
    time.sleep(10)


def cluster_add_node(master_ip, new_node_ip):
    os.system(f"redis-cli --cluster add-node {new_node_ip} {master_ip}")
    time.sleep(5)
