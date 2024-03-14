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
We support executing client threads on multiple nodes. Different nodes are synchronized through memcached with a controller. We currently support two modes of executions:
- Separate data loading and workload execution
    - Load data: 
        1. `python3 scripts/ycsb_load_or_trans.py <memcached-ip> <num-clients>`. The `<num-clients>` field should be the total number of client threads.
        2. On another client node: `cd build && ./redis_load_ycsb <node-id> <num-local-threads> <num-total-threads> <memcached-ip> load <redis-ip> <execution-time> <output-fname> <mode>`. The `load` and `<execution-time>` are a placeholders, taking no effect to the command. The `<mode>` field can either be `cluster` or `single`, representing Redis cluster and single instance. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.
    - Executing workload:
        1. `python3 scripts/ycsb_load_or_trans.py <memcached-ip> <num-clients>`
        2. On another client node: `cd build && ./redis_trans_ycsb <node-id> <num-local-threads> <num-total-threads> <memcached-ip> <workload> <redis-ip> <execution-time> <output-fname> <mode>`. The `<workload>` should be in `[ycsba, ycsbb, ycsbc, ycsbd]` and The `<execution-time>` controls how long each thread iterates with the workload. The `<mode>` field can either be `cluster` or `single`, representing Redis cluster and single instance. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.
- End-to-end testing (load data and execute the workload):
    1. `python3 scripts/ycsb_load_and_trans.py <memcached-ip> <num-clients>`. The `<num-clients>` field should be the total number of client threads.
    2. On another client node: `cd build && ./redis_perf <node-id> <num-local-threads> <num-total-threads> <memcached-ip> <workload> <redis-ip> <execution-time> <output-fname> <mode>`. The `<workload>` should be in `[ycsba, ycsbb, ycsbc, ycsbd]` and The `<execution-time>` controls how long each thread iterates with the workload. The `<mode>` field can either be `cluster` or `single`, representing Redis cluster and single instance. Note that this program will automatically read the workload file in `../workloads/ycsb`, hence must be executed in the `build` directory. An output will be written to `build/results` as a json file.

**Note 1: In all above commands, the `<redis-ip>` field should be a URI with a scheme, *e.g.*, `tcp://127.0.0.1:7000`.**  
**Note 2: Create a `results` directory under the `build` directory. Otherwise, results can be lost.**  

# Output Format
```json
{
    "cont_tpt": [num_ops, num_ops, num_ops, ...], // record every 500ms
    "cont_lat_map": [[[lat_us, time], [lat_us, time], ...], 
                     [[lat_us, time], [lat_us, time], ...],
                     ...], //record every 500ms
}
```