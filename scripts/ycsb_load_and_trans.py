from itertools import product
import memcache
import time
import json
import os
import sys

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

    for i in range(1, num_clients+1):
        ready_msg = f'client-{i}-ready-1'
        val = mc.get(ready_msg)
        while val == None:
            val = mc.get(ready_msg)
    mc.set('all-client-ready-1', 1)