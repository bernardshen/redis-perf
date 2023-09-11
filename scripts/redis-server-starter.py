import os
import memcache
import time
import sys

if len(sys.argv) != 3:
    print("Usage {} <memcached_ip> <my_server_ip>", sys.argv[0])

server_port = 7000
core_id = 0

instance_controller_id = 0
memcached_ip = sys.argv[1]
my_server_ip = sys.argv[2]

# clear old settings
if os.path.exists(f'./{server_port}'):
    if os.path.exists(f'./{server_port}/pid'):
        pid = int(open(f'./{server_port}/pid', 'r').read())
        os.system(f'sudo kill -9 {pid}')
    os.system(f'rm -rf ./{server_port}')

os.mkdir(f'./{server_port}')

# construct configurations
config_templ = open('redis-server.conf.templ', 'r').read()
with open(f'./{server_port}/redis.conf', 'w') as f:
    f.write(config_templ.format(server_port, server_port, my_server_ip))

# start redis instances
os.system(f'cd {server_port}; \
          taskset -c {core_id} redis-server ./redis.conf; cd ..')

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
if os.path.exists(f'./{server_port}/pid'):
    pid = int(open(f'./{server_port}/pid', 'r').read())
    os.system(f'sudo kill -9 {pid}')
os.system(f'rm -rf ./{server_port}')
