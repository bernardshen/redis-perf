import os
import time
import sys
import signal
import argparse

server_port = 7000
core_id = 0
num_servers = 0


def SIGINT_handler(sig, frame):
    global num_servers
    print('Cleaning up before existing...')
    for i in range(num_servers):
        if os.path.exists(f'./{server_port + i}/pid'):
            pid = int(open(f'./{server_port + i}/pid', 'r').read())
            os.system(f'sudo kill -9 {pid}')
        os.system(f'rm -rf ./{server_port + i}')


signal.signal(signal.SIGINT, SIGINT_handler)


def create_single_instance(args):
    my_server_ip = args.ip
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

    os.system(f'cd {server_port}; redis-server ./redis.conf; cd ..')


parser = argparse.ArgumentParser(
    description="Start Redis server instances in cluster and single mode")
parser.add_argument('-m', '--mode', type=str, required=True,
                    help="start in cluster mode or single instance mode: <cluster | single>.", choices=['cluster', 'single'])
parser.add_argument('-n', '--num-servers', type=int, required=False,
                    help="The number of Redis servers in cluster mode.", dest='num_servers')
parser.add_argument('-i', '--ip', type=str, required=True,
                    help="The IP of the server.")

args = parser.parse_args()

if args.mode == 'cluster' and args.num_servers == None:
    print(f"Usage: {sys.argv[0]} -m cluster -n <server_num> -i <Node IP>")
    assert (0)

if args.mode == 'cluster':
    num_servers = args.num_servers
else:
    num_servers = 1

# TODO: currently only support single instance
assert (args.mode == 'single')

if args.mode == 'single':
    create_single_instance(args)

# wait for SIGINT
while True:
    sleep(5)
