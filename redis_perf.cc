#include <iostream>
#include <sw/redis++/redis++.h>

#include <assert.h>
#include <stdlib.h>
#include <unistd.h>

#include "debug.h"
#include "memcached.h"
#include "redis_adapter.h"
#include "third_party/json.hpp"
#include "utils.h"
#include "workload.h"

#define TICK_US (500000)

using namespace sw::redis;
using json = nlohmann::json;

void *worker(void *_args) {
  ClientArgs *args = (ClientArgs *)_args;
  DMCMemcachedClient con_client(args->controller_ip);
  MyRedisAdapter *redis = get_redis(args);

  int ret = stick_this_thread_to_core(args->core);
  if (ret)
    printd(L_ERROR, "Failed to bind client %d to core %d", args->cid,
           args->core);
  else
    printd(L_INFO, "Running client %d on core %d", args->cid, args->core);

  Workload load_wl, trans_wl;
  load_workload_ycsb(args->wl_name, -1, args->cid, args->all_client_num,
                     &load_wl, &trans_wl);

  // ready to run workload
  // sync to load ycsb dataset
  char dumb_value_char[256] = {0};
  memset(dumb_value_char, 'a', 255);
  std::string dumb_value_str(dumb_value_char);
  printd(L_DEBUG, "Client %d waiting syncing", args->cid);
  con_client.memcached_sync_ready(args->cid);
  for (uint64_t i = 0; i < load_wl.num_ops; i++) {
    uint64_t key_addr, val_addr;
    uint32_t key_size, val_size;
    uint8_t op;
    get_workload_kv(&load_wl, i, &key_addr, &val_addr, &key_size, &val_size,
                    &op);
    std::string key((char *)key_addr);
    std::string val = dumb_value_str.substr(0, _KV_SIZE - key.size());
  set_retry:
    try {
      redis->set(key, val);
    } catch (const Error &e) {
      std::cout << e.what() << std::endl;
      printd(L_ERROR, "Failed to set key %s, retrying", key.c_str());
      goto set_retry;
    }
  }
  printd(L_DEBUG, "Client %d finished loading", args->cid);

  struct timeval st, et, tst;
  uint32_t seq = 0;
  uint32_t num_ticks = ((uint64_t)args->run_times_s * 1000000) / TICK_US;
  uint32_t cur_tick = 0;
  std::vector<uint32_t> *cont_tpt = args->cont_tpt;
  std::unordered_map<uint64_t, uint32_t> cur_lat_map;
  std::vector<std::unordered_map<uint64_t, uint32_t>> *cont_lat_map =
      args->cont_lat_map;
  cur_lat_map.clear();
  // sync to do trans
  printd(L_DEBUG, "Client %d waiting sync", args->cid);
  con_client.memcached_sync_ready(args->cid);
  printd(L_DEBUG, "Client %d start trans", args->cid);
  gettimeofday(&st, NULL);
  while (cur_tick < num_ticks) {
    uint32_t idx = seq % trans_wl.num_ops;
    uint64_t key_addr, val_addr;
    uint32_t key_size, val_size;
    uint8_t op;
    get_workload_kv(&trans_wl, idx, &key_addr, &val_addr, &key_size, &val_size,
                    &op);
    std::string key((char *)key_addr);
    std::string val = dumb_value_str.substr(0, _KV_SIZE - key.size());
    gettimeofday(&tst, NULL);
  trans_retry:
    try {
      if (op == GET) {
        auto val = redis->get(key);
      } else {
        redis->set(key, val);
      }
    } catch (const Error &e) {
      printd(L_ERROR, "Client %d failed %s, reconnect and retry", args->cid,
             key.c_str());
      goto trans_retry;
    }
    seq++;
    gettimeofday(&et, NULL);
    cur_lat_map[diff_ts_us(&et, &tst)]++;
    if (diff_ts_us(&et, &st) > cur_tick * TICK_US) {
      (*cont_tpt).push_back(seq);
      (*cont_lat_map).push_back(cur_lat_map);
      cur_lat_map.clear();
      cur_tick++;
    }
  }
  return NULL;
}

char save_fname[256];
char mode[256];
char experiment[256];

int main(int argc, char **argv) {
  if (argc != 11) {
    printd(L_ERROR,
           "Usage: %s <node_id> <num_threads> <all_thread_num> <memcached_ip> "
           "<workload> <redis_ip> <run_time> <fname> <mode> <experiment>",
           argv[0]);
    exit(1);
  }
  ClientArgs initial_args;
  memset(&initial_args, 0, sizeof(initial_args));

  int sid = atoi(argv[1]);
  int num_threads = atoi(argv[2]);
  int all_thread_num = atoi(argv[3]);
  strcpy(initial_args.controller_ip, argv[4]);
  strcpy(initial_args.wl_name, argv[5]);
  strcpy(initial_args.redis_ip, argv[6]);
  initial_args.run_times_s = atoi(argv[7]);
  strcpy(save_fname, argv[8]);
  strcpy(mode, argv[9]);
  if (strcmp("cluster", mode) != 0 && strcmp("single", mode) != 0 &&
      strcmp("dmc_cluster", mode) != 0 && strcmp("sentinel", mode) != 0 &&
      strcmp("dmc_sentinel", mode) != 0) {
    printd(L_ERROR, "mode can be either [cluster] or [single] or [dmc_cluster] "
                    "or [sentinel] or [dmc_sentinel]");
    return 1;
  }
  strcpy(experiment, argv[10]);
  if (strcmp("normal", experiment) != 0 &&
      strcmp("elasticity", experiment) != 0 &&
      strcmp("recovery", experiment) != 0) {
    printd(L_ERROR, "experiment can be either [normal] or [elasticity] or "
                    "[recovery]");
    return 1;
  }

  if (strcmp("dmc_cluster", mode) == 0) {
    load_dmc_cluster_config("../dmc_cluster_config.json", &initial_args);
    DMCClusterAdapter::update_num_servers(
        initial_args.num_dmc_cluster_initial_servers);
    initial_args.mode = MOD_DMC_CLUSTER;
  } else if (strcmp("cluster", mode) == 0) {
    initial_args.mode = MOD_CLUSTER;
  } else if (strcmp("sentinel", mode) == 0) {
    initial_args.mode = MOD_SENTINEL;
  } else if (strcmp("dmc_sentinel", mode) == 0) {
    load_dmc_cluster_config("../dmc_cluster_config.json", &initial_args);
    DMCClusterAdapter::update_num_servers(
        initial_args.num_dmc_cluster_initial_servers);
    initial_args.mode = MOD_DMC_SENTINEL;
  } else {
    assert(strcmp("single", mode) == 0);
    initial_args.mode = MOD_SINGLE;
  }

  if (strcmp("normal", experiment) == 0) {
    initial_args.exp = EXP_NORMAL;
  } else if (strcmp("recovery", experiment) == 0) {
    initial_args.exp = EXP_RECOVERY;
  } else {
    assert(strcmp("elasticity", experiment) == 0);
    initial_args.exp = EXP_ELASTICITY;
  }

  long num_cores = sysconf(_SC_NPROCESSORS_ONLN);

  printd(L_INFO, "============== Redis-Cluster Settings ===================");
  printd(L_INFO, "node: %d", sid);
  printd(L_INFO, "num_threads: %d", num_threads);
  printd(L_INFO, "memcached_ip: %s", initial_args.controller_ip);
  printd(L_INFO, "workload: %s", initial_args.wl_name);
  printd(L_INFO, "redis_ip: %s", initial_args.redis_ip);
  printd(L_INFO, "running %d seconds", initial_args.run_times_s);
  printd(L_INFO, "save to file: %s", save_fname);
  printd(L_INFO, "num_cores: %ld", num_cores);
  printd(L_INFO, "mode: %s", mode);
  printd(L_INFO, "=========================================================");

  ClientArgs args[num_threads];
  pthread_t tids[num_threads];
  for (int i = 0; i < num_threads; i++) {
    memcpy(&args[i], &initial_args, sizeof(ClientArgs));
    args[i].cid = sid * num_threads + i + 1;
    args[i].core = i % num_cores;
    args[i].all_client_num = all_thread_num;
    args[i].cont_tpt = new std::vector<uint32_t>();
    args[i].cont_lat_map =
        new std::vector<std::unordered_map<uint64_t, uint32_t>>();

    pthread_create(&tids[i], NULL, worker, &args[i]);
  }

  // wait for load barrier
  if (initial_args.mode == MOD_DMC_SENTINEL &&
      initial_args.exp == EXP_RECOVERY) {
    DMCMemcachedClient con_client(args->controller_ip);
    con_client.memcached_wait("dmc-primary-failed");
    DMCSentinelAdapter::set_primary(1);
    con_client.memcached_wait("dmc-backup-created");
    DMCSentinelAdapter::connect_backup();
  }

  for (int i = 0; i < num_threads; i++) {
    pthread_join(tids[i], NULL);
  }

  // merge results
  std::vector<uint32_t> merged_cont_tpt(args[0].cont_tpt->size());
  for (int i = 0; i < num_threads; i++) {
    for (int j = 0; j < args[i].cont_tpt->size(); j++) {
      merged_cont_tpt[j] += (*args[i].cont_tpt)[j];
    }
  }

  std::vector<std::unordered_map<uint64_t, uint32_t>> merged_cont_lat_map;
  for (int j = 0; j < args[0].cont_lat_map->size(); j++) {
    std::unordered_map<uint64_t, uint32_t> cur_merged_lat_map;
    for (int i = 0; i < num_threads; i++) {
      std::unordered_map<uint64_t, uint32_t> *cur_lat_map =
          &((*args[i].cont_lat_map)[j]);
      for (auto it = cur_lat_map->begin(); it != cur_lat_map->end(); it++) {
        cur_merged_lat_map[it->first] += it->second;
      }
    }
    merged_cont_lat_map.push_back(cur_merged_lat_map);
  }

  if (initial_args.mode == MOD_DMC_CLUSTER) {
    printf("Access vector: ");
    DMCClusterAdapter::print_access_vector();
  }
  if (initial_args.mode == MOD_DMC_SENTINEL) {
    printf("Access vector: ");
    DMCSentinelAdapter::print_access_vector();
  }

  json merged_res;
  merged_res["cont_tpt"] = json(merged_cont_tpt);
  merged_res["cont_lat_map"] = json(merged_cont_lat_map);

  char fname_buf[512];
  sprintf(fname_buf, "results/%s.json", save_fname);
  FILE *f = fopen(fname_buf, "w");
  assert(f != NULL);
  printd(L_INFO, "Output file size: %ldMB",
         merged_res.dump().size() / 1024 / 1024);
  fprintf(f, "%s", merged_res.dump().c_str());
}