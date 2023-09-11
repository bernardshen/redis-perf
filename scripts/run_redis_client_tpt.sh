#!/bin/bash

. shell_settings.sh

if [ ! -d "./results" ]; then
    mkdir results
fi

st_client_id=$1
num_clients=$2
workload=$3
redis_ip=$4
run_time=$5

../build/redis_perf_tpt $st_client_id $num_clients $memcached_ip $workload $redis_ip $run_time
