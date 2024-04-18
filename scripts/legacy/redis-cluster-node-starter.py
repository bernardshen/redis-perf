import os
import memcache
import time
import sys
import subprocess

if len(sys.argv) != 4:
    print("Usage {} <num_cores> <memcached_ip> <my_server_ip>", sys.argv[0])

num_required_instances = int(sys.argv[1].strip())
num_servers = num_required_instances if num_required_instances > 3 else 3

instance_controller_id = 0
memcached_ip = sys.argv[2]
my_server_ip = sys.argv[3]
server_port_st = 7000
num_cores = 10

server_ports = [server_port_st + i for i in range(num_servers)]
all_server_ports = [server_port_st + i for i in range(64)]

# clear old settings
for p in all_server_ports:
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
              taskset -c {i % num_cores} redis-server ./redis.conf; cd ..')

mc = memcache.Client([memcached_ip], debug=False)
assert (mc != None)
mc.set(f'redis-{instance_controller_id}-ready', instance_controller_id)
print("Finished creating instances, wait clean-up")

# wait for finishing workload
val = mc.get('test-finish')
while val == None:
    time.sleep(1)
    val = mc.get('test-finish')

# clean-up redis instances
for p in all_server_ports:
    if not os.path.exists(f'./{p}'):
        continue
    if os.path.exists(f'./{p}/pid'):
        pid = int(open(f'./{p}/pid', 'r').read())
        os.system(f'sudo kill -9 {pid}')
    os.system(f'rm -rf ./{p}')