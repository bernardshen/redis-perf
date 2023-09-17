#!/bin/bash
. shell_settings.sh

num_cores=$1
my_server_ip=$2

python redis-cluster-node-starter.py $num_cores $memcached_ip $my_server_ip