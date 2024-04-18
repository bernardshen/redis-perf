import memcache
import time
import sys

seconds_before_scale = 5
seconds_before_shrink = 5

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <memcached-ip> <num-clients>")
        exit()
    memcached_ip = sys.argv[1]
    num_clients = int(sys.argv[2])
    mc = memcache.Client([memcached_ip])
    mc.flush_all()

    for i in range(1, num_clients+1):
        ready_msg = f'client-{i}-ready-0'
        val = mc.get(ready_msg)
        while val == None:
            val = mc.get(ready_msg)
    mc.set('all-client-ready-0', 1)

    # scale out
    time.sleep(seconds_before_scale)
    mc.set('dmc-scale-0', 1)

    # scale in
    time.sleep(seconds_before_shrink)
    mc.set('dmc-scale-1', 1)
