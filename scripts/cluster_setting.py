cluster_ips = [f'node-{i}' for i in range(3)]
master_id = 0
mn_id = 1
client_ids = [0]

default_fc_size = 10*1024*1024

NUM_CLIENT_PER_NODE = 32

EXP_HOME = 'redis_test'
build_dir = f'{EXP_HOME}/build'
config_dir = f'{EXP_HOME}/experiments'