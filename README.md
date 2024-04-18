# Dependencies
- CMake
- Anaconda3
- Python packages:
    `pip install python-memcached fabric`
- Other dependencies:
    `sudo apt install libmemcached-dev memcached libboost-all-dev libhiredis-dev`
- Redis++:
    ```bash
    git clone https://github.com/sewenew/redis-plus-plus.git
    cd redis-plus-plus
    mkdir build
    cd build
    cmake ..
    make -j 8
    sudo make install
    ```
- Modify `/etc/memcached.conf`
  ```
  -l 0.0.0.0
  -I 128m
  -m 2048
  ```
# Usage
We provide a script for downloading Twitter workloads in `workloads/download_workloads.sh`. Execute `cd workloads && ./download_workloads.sh twitter` to download and setup the execution directories for the Twitter workloads. You may at leat 1TB disk space to download and decompress these workloads.

We support executing client threads on multiple nodes. Different nodes are synchronized through memcached with a controller. We currently support two modes of executions:
- Separate data loading and workload execution
    - Load data: 
        1. `python3 scripts/ycsb_load_or_trans.py <memcached-ip> <num-clients>`. The `<num-clients>` field should be the total number of client threads.
        2. On another client node: `cd build && ./redis_load_ycsb <node-id> <num-local-threads> <num-total-threads> <memcached-ip> load <redis-ip> <execution-time> <output-fname> <mode>`. The `load` and `<execution-time>` are a placeholders, taking no effect to the command. The `<mode>` field can either be `cluster`, `single`, or `dmc_cluster`. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.
    - Executing workload normally:
        1. `python3 scripts/ycsb_load_or_trans.py <memcached-ip> <num-clients>`
        2. On another client node: `cd build && ./redis_trans_ycsb <node-id> <num-local-threads> <num-total-threads> <memcached-ip> <workload> <redis-ip> <execution-time> <output-fname> <mode> normal`. The `<workload>` should be in `[ycsba, ycsbb, ycsbc, ycsbd, twitter-compute, twitter-storage, twitter-transient]` and The `<execution-time>` controls how long each thread iterates with the workload. The `<mode>` field can either be `cluster`, `single`, or `dmc_cluster`. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.
    - Executing workload for dmc cluster:
        0. Prepare experiment settings:
            - In `scripts/ycsb_dmc_cluster_elasticity.py` there are two variables to control the execution time of scale out and scale in nodes, which are `seconds_before_scale` and `seconds_before_shrink`.
            - In `dmc_cluster_config.json` set `num_initial_servers` and `num_scale_servers` to control the number of servers used before and after resource scaling.
        1. `python scripts/ycsb_dmc_cluster_elasticity.py <memcached-ip> <num-clients>`.
        2. On another client node: `cd build && ./redis_trans_ycsb <node-id> <num-local-threads> <num-total-threads> <memcached-ip> <workload> <redis-ip> <execution-time> <output-fname> <mode> elasticity`. The `<workload>` should be in `[ycsba, ycsbb, ycsbc, ycsbd, twitter-compute, twitter-storage, twitter-transient]` and The `<execution-time>` controls how long each thread iterates with the workload. The `<mode>` field can either be `cluster`, `single`, or `dmc_cluster`. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.
- End-to-end testing (load data and execute the workload):
    1. `python3 scripts/ycsb_load_and_trans.py <memcached-ip> <num-clients>`. The `<num-clients>` field should be the total number of client threads.
    2. On another client node: `cd build && ./redis_perf <node-id> <num-local-threads> <num-total-threads> <memcached-ip> <workload> <redis-ip> <execution-time> <output-fname> <mode>`. The `<workload>` should be in `[ycsba, ycsbb, ycsbc, ycsbd]` and The `<execution-time>` controls how long each thread iterates with the workload. The `<mode>` field can either be `cluster`, `single`, or `dmc_cluster`. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.

**Note 1: In all above commands, the `<redis-ip>` field should be a URI with a scheme, *e.g.*, `tcp://127.0.0.1:7000`.**  
**Note 2: Create a `results` directory under the `build` directory. Otherwise, results can be lost.**  
**Note 3: When executing Twitter workloads, we do not load data first.**  
**Note 4: For `dmc_cluster` mode, we use `dmc_cluster_config.json` to setup nodes in the cluster and the number of initial servers and the number of scale servers (for elasticity experiment).**  

# Output Format
```json
{
    "cont_tpt": [num_ops, num_ops, num_ops, ...], // record every 500ms
    "cont_lat_map": [[[lat_us, time], [lat_us, time], ...], 
                     [[lat_us, time], [lat_us, time], ...],
                     ...], //record every 500ms
}
```

# TODO
- [ ] Working on `redis-instance-starter.py` to start a single redis server instance or a redis cluster with multiple nodes  
    - [x] Single server mode
    - [ ] Cluster mode