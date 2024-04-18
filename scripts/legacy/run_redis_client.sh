#!/bin/bash

. shell_settings.sh

if [ ! -d "./results" ]; then
    mkdir results
fi

st_client_id=$1
workload=$2
redis_ip=$3
run_time=$4

../build/redis_perf $st_client_id $memcached_ip $workload $redis_ip $run_time