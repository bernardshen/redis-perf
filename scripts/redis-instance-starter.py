import os
import time
import sys
import signal
import argparse

import redis_utils

server_port = 7000
core_id = 0
num_servers = 0


def SIGINT_handler(sig, frame):
    global num_servers
    print('Cleaning up before existing...')
    server_nodes = [server_port + i for i in range(num_servers)]
    redis_utils.cleanup_servers(server_nodes)
    exit(0)


signal.signal(signal.SIGINT, SIGINT_handler)


def create_multiple_instances(args):
    my_server_ip = args.ip
    for i in range(args.num_servers):
        port = server_port + i
        # clear old settings
        redis_utils.cleanup_servers([port], mkdir=True)
        # construct configurations
        redis_utils.create_config('redis-server.conf.templ', [port], my_server_ip)
        redis_utils.start_instances([port])


def create_single_instance(args):
    my_server_ip = args.ip
    # clear old settings
    redis_utils.cleanup_servers([server_port], mkdir=True)
    # construct configurations
    redis_utils.create_config('redis-server.conf.templ', [server_port], my_server_ip)
    redis_utils.start_instances([server_port])

def create_cluster(args):
    my_server_ip = args.ip
    server_ports = [server_port + i for i in range(args.num_servers)]
    server_ips = [f'{my_server_ip}:{p}' for p in server_ports]
    # clear old settings
    redis_utils.cleanup_servers(server_ports, mkdir=True)
    redis_utils.create_config('redis-large.conf.templ', server_ports, my_server_ip)
    redis_utils.start_instances(server_ports)
    print(f"Creating a Redis cluster with {len(server_ports)} nodes")
    redis_utils.create_cluster(server_ips)


parser = argparse.ArgumentParser(
    description="Start Redis server instances in cluster and single mode")
parser.add_argument('-m', '--mode', type=str, required=True,
                    help="start in cluster mode or single instance mode: <cluster | single>.", choices=['cluster', 'single', 'multi'])
parser.add_argument('-n', '--num-servers', type=int, required=False,
                    help="The number of Redis servers in cluster mode.", dest='num_servers')
parser.add_argument('-i', '--ip', type=str, required=True,
                    help="The IP of the server.")

args = parser.parse_args()

if args.mode == 'cluster' and args.num_servers == None:
    print(f"Usage: {sys.argv[0]} -m cluster -n <server_num> -i <Node IP>")
    assert (0)

if args.mode == 'cluster' or args.mode == 'multi':
    num_servers = args.num_servers
else:
    num_servers = 1

if args.mode == 'single':
    create_single_instance(args)
if args.mode == 'multi':
    create_multiple_instances(args)
if args.mode == 'cluster':
    # TODO: currently only support clusters with more than 3 nodes
    assert(num_servers >= 3)
    create_cluster(args)

# wait for SIGINT
while True:
    time.sleep(5)
