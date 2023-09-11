#!/bin/bash

. shell_settings.sh

my_server_ip=$1

python redis-server-starter.py $memcached_ip $my_server_ip