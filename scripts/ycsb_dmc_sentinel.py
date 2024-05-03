import memcache
import time
import sys
import redis_utils

seconds_before_fail = 5
seconds_before_rereplicate = 5

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <memcached-ip> <num-clients>")
        exit()
    memcached_ip = sys.argv[1]
    num_clients = int(sys.argv[2])
    mc = memcache.Client([memcached_ip])
    mc.flush_all()

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

    # scale out
    print("Kill primary")
    redis_utils.kill_servers([7000])
    time.sleep(seconds_before_fail)
    mc.set('dmc-primary-failed', 1)

    # scale in
    time.sleep(seconds_before_rereplicate)
    mc.set('dmc-backup-created', 1)
