from itertools import product
import memcache
import time
import json

from cluster_setting import *
from cmd_manager import CMDManager

cmd_manager = CMDManager(cluster_ips)

num_instance_controllers = 1
memcached_ip = cluster_ips[master_id]
instance_ips = [cluster_ips[mn_id]]
client_ips = [cluster_ips[client_ids[0]]]

num_client_list = [1, 2]
workload_list = ['ycsbc', 'ycsba']

redis_work_dir = f'{EXP_HOME}/scripts'
ULIMIT_CMD = "ulimit -n unlimited"
for num_clients, wl in product(num_client_list, workload_list):
    # start redis-cluster
    mc = memcache.Client([memcached_ip])
    assert (mc != None)
    mc.flush_all()

    # start instances
    print(f"Start Redis instances")
    instance_prom = cmd_manager.execute_on_node(
        mn_id, f"{ULIMIT_CMD} && cd {redis_work_dir} && ./run_redis_single.sh {cluster_ips[mn_id]}")
    server_port = 7000
    initial_instance = f'{instance_ips[0]}:{server_port}'

    # start instance controller wait for instance controllers to reply
    print("Wait Redis instance ready")
    for i in range(num_instance_controllers):
        ready_msg = f'redis-{i}-ready'
        val = mc.get(ready_msg)
        while val == None:
            val = mc.get(ready_msg)
        print(ready_msg)

    # start clients
    time.sleep(5)
    c_prom = cmd_manager.execute_on_node(
        client_ids[0], 
        f'{ULIMIT_CMD} && cd {redis_work_dir} && ./run_redis_client_tpt.sh 1 {num_clients} {wl} tcp://{cluster_ips[mn_id]}:7000 20'
    )

    # sync ycsb load
    print("Wait all clients ready.")
    for i in range(1, num_clients + 1):
        ready_msg = f'client-{i}-ready-0'
        val = mc.get(ready_msg)
        while val == None:
            val = mc.get(ready_msg)
        print(ready_msg)
    print("Notify Clients to load.")
    mc.set('all-client-ready-0', 1)  # clients start loading

    # wait all clients load ready and sync their to execute trans
    for i in range(1, num_clients + 1):
        ready_msg = f'client-{i}-ready-1'
        val = mc.get(ready_msg)
        while val == None:
            val = mc.get(ready_msg)
        print(ready_msg)
    mc.set('all-client-ready-1', 1)  # clients start executing trans
    print("Notify all clients start trans")

    # wait for client finish
    res = {}
    for i in range(1, num_clients + 1):
        key = f'client-{i}-result-0'
        val = mc.get(key)
        while val == None:
            val = mc.get(key)
        res[i] = json.loads(str(val.decode('utf-8')))

    c_prom.join()

    # finishing experiment and exit!
    mc.set('test-finish', 1)
    instance_prom.join()

    # parse results
    combined_res = {}
    tpt = 0
    lat_map = {}
    for i in range(1, num_clients + 1):
        tpt += res[i]['ops_cont'][-1]
        for itm in res[i]['lat_map']:
            if itm[0] not in lat_map:
                lat_map[itm[0]] = 0
            lat_map[itm[0]] += itm[1]
    lat_list = []
    for item in lat_map.items():
        lat_list += [item[0]] * item[1]
    lat_list.sort()

    combined_res['tpt'] = tpt / 20
    combined_res['p99'] = lat_list[int(len(lat_list) * 0.99)]
    combined_res['p50'] = lat_list[int(len(lat_list) * 0.50)]