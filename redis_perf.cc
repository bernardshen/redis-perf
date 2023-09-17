// TODO: modify this, for elasticity test

#include <sw/redis++/redis++.h>
#include <iostream>

#include <assert.h>
#include <stdlib.h>
#include <unistd.h>

#include "memcached.h"
#include "third_party/json.hpp"
#include "utils.h"

#define NUM_ALL_CLIENTS 128
#define NUM_LOCAL_CLIENTS 128
#define NUM_CORES 32

using namespace sw::redis;
using json = nlohmann::json;

static int stick_this_thread_to_core(int core_id) {
  int num_cores = sysconf(_SC_NPROCESSORS_CONF);
  if (core_id < 0 || core_id >= num_cores) {
    return -1;
  }

  cpu_set_t cpuset;
  CPU_ZERO(&cpuset);
  CPU_SET(core_id, &cpuset);

  pthread_t current_thread = pthread_self();
  return pthread_setaffinity_np(current_thread, sizeof(cpu_set_t), &cpuset);
}

static int load_ycsb_single(char* wl_name,
                            int num_load_ops,
                            uint32_t server_id,
                            uint32_t all_client_num,
                            __OUT Workload* wl) {
  char wl_fname[128];
  sprintf(wl_fname, "../workloads/ycsb/%s", wl_name);
  FILE* f = fopen(wl_fname, "r");
  assert(f != NULL);
  printf("Client %d loading %s\n", server_id, wl_name);

  std::vector<std::string> wl_list;
  char buf[2048];
  uint32_t cnt = 0;
  while (fgets(buf, 2048, f) == buf) {
    if (buf[0] == '\n')
      continue;
    if ((cnt % all_client_num) + 1 == server_id)
      wl_list.emplace_back(buf);
    cnt++;
  }

  if (num_load_ops == -1)
    wl->num_ops = wl_list.size();
  else
    wl->num_ops = num_load_ops;
  wl->key_buf = malloc(128 * wl->num_ops);
  wl->val_buf = malloc(120 * wl->num_ops);
  wl->key_size_list = (uint32_t*)malloc(sizeof(uint32_t) * wl->num_ops);
  wl->val_size_list = (uint32_t*)malloc(sizeof(uint32_t) * wl->num_ops);
  wl->op_list = (uint8_t*)malloc(sizeof(uint8_t) * wl->num_ops);
  memset(wl->key_buf, 0, 128 * wl->num_ops);
  memset(wl->val_buf, 0, 120 * wl->num_ops);

  printf("Client %d loading %ld ops\n", server_id, wl_list.size());
  char ops_buf[64];
  char key_buf[64];
  for (int i = 0; i < wl->num_ops; i++) {
    sscanf(wl_list[i].c_str(), "%s %s", ops_buf, key_buf);
    memcpy((void*)((uint64_t)wl->key_buf + i * 128), key_buf, 128);
    memcpy((void*)((uint64_t)wl->val_buf + i * 120), &i, sizeof(int));
    wl->key_size_list[i] = strlen(key_buf);
    wl->val_size_list[i] = sizeof(int);
    if (strcmp("READ", ops_buf) == 0) {
      wl->op_list[i] = GET;
    } else {
      wl->op_list[i] = SET;
    }
  }
  return 0;
}

static void get_workload_kv(Workload* wl,
                            uint32_t idx,
                            __OUT uint64_t* key_addr,
                            __OUT uint64_t* val_addr,
                            __OUT uint32_t* key_size,
                            __OUT uint32_t* val_size,
                            __OUT uint8_t* op) {
  idx = idx % wl->num_ops;
  *key_addr = ((uint64_t)wl->key_buf + idx * 128);
  *val_addr = ((uint64_t)wl->val_buf + idx * 120);
  *key_size = wl->key_size_list[idx];
  *val_size = wl->val_size_list[idx];
  *op = wl->op_list[idx];
}

int load_workload_ycsb(char* wl_name,
                       int num_load_ops,
                       uint32_t server_id,
                       uint32_t all_client_num,
                       __OUT Workload* load_wl,
                       __OUT Workload* trans_wl) {
  char fname_buf[256];
  sprintf(fname_buf, "%s.load", wl_name);
  // server_id starts with 1
  load_ycsb_single(fname_buf, num_load_ops, server_id, all_client_num, load_wl);

  sprintf(fname_buf, "%s.trans", wl_name);
  load_ycsb_single(fname_buf, num_load_ops, server_id, all_client_num,
                   trans_wl);
  return 0;
}

void* worker(void* _args) {
  ClientArgs* args = (ClientArgs*)_args;
  auto redis_cluster = RedisCluster(args->redis_ip);
  DMCMemcachedClient con_client(args->controller_ip);

  int ret = stick_this_thread_to_core(args->core);
  if (ret)
    printf("Failed to bind client %d to core %d\n", args->cid, args->core);
  else
    printf("Running client %d on core %d\n", args->cid, args->core);

  Workload load_wl, trans_wl;
  ret = load_workload_ycsb(args->wl_name, -1, args->cid, args->all_client_num,
                           &load_wl, &trans_wl);
  assert(ret == 0);

  // ready to run workload
  // sync to load ycsb dataset
  char dumb_value_char[256] = {0};
  memset(dumb_value_char, 'a', 254);
  std::string dumb_value_str(dumb_value_char);
  printf("Client %d waiting syncing\n", args->cid);
  con_client.memcached_sync_ready(args->cid);
  for (int i = 0; i < load_wl.num_ops; i++) {
    uint64_t key_addr, val_addr;
    uint32_t key_size, val_size;
    uint8_t op;
    get_workload_kv(&load_wl, i, &key_addr, &val_addr, &key_size, &val_size,
                    &op);
    std::string key((char*)key_addr);
    std::string val = dumb_value_str.substr(0, 256 - key.size());
  set_retry:
    try {
      redis_cluster.set(key, val);
    } catch (const Error& e) {
      printf("Failed to set key %s\n", key.c_str());
      goto set_retry;
    }
  }
  printf("Client %d finished loading\n", args->cid);

  struct timeval st, et, tst;
  uint32_t seq = 0;
  uint32_t num_ticks = args->run_times_s * 2;
  uint64_t tick_us = 500000;
  uint64_t lat_tick_us = tick_us * 8;
  uint32_t cur_tick = 0;
  std::vector<uint32_t>* ops_list = args->ops_list;
  std::unordered_map<uint64_t, uint32_t> cur_lat_map;
  std::vector<std::unordered_map<uint64_t, uint32_t>>* lat_map =
      args->lat_map_cont;
  cur_lat_map.clear();
  // sync to do trans
  printf("Client %d waiting sync\n", args->cid);
  con_client.memcached_sync_ready(args->cid);
  gettimeofday(&st, NULL);
  while (true) {
    uint32_t idx = seq % trans_wl.num_ops;
    uint64_t key_addr, val_addr;
    uint32_t key_size, val_size;
    uint8_t op;
    get_workload_kv(&trans_wl, idx, &key_addr, &val_addr, &key_size, &val_size,
                    &op);
    std::string key((char*)key_addr);
    std::string val = dumb_value_str.substr(0, 256 - key.size());
    gettimeofday(&tst, NULL);
  trans_retry:
    try {
      if (op == GET) {
        auto val = redis_cluster.get(key);
      } else {
        redis_cluster.set(key, val);
      }
    } catch (const Error& e) {
      printf("Client %d failed %s, reconnect and retry\n", args->cid,
             key.c_str());
      redis_cluster = RedisCluster(args->redis_ip);
      goto trans_retry;
    }
    seq++;
    gettimeofday(&et, NULL);
    cur_lat_map[diff_ts_us(&et, &tst) / 10]++;
    if (diff_ts_us(&et, &st) > cur_tick * tick_us) {
      (*ops_list).push_back(seq);
      if (cur_tick % 8 == 0) {
        (*lat_map).push_back(cur_lat_map);
        cur_lat_map.clear();
      }
      cur_tick++;
    }
    if (cur_tick == num_ticks)
      break;
  }
  // json trans_res;
  // trans_res["ops_cont"] = json(*ops_list);
  // trans_res["lat_map_cont"] = json(*lat_map);
  // printf("itemsize: %ld\n", strlen(trans_res.dump().c_str()) / 1024);
  // con_client.memcached_put_result((void*)trans_res.dump().c_str(),
  //                                 strlen(trans_res.dump().c_str()),
  //                                 args->cid);
  // // save file to local
  // char fname_buf[256];
  // sprintf(fname_buf, "results/worker-%d.json", args->cid);
  // FILE* f = fopen(fname_buf, "w");
  // assert(f != NULL);
  // fprintf(f, "%s", trans_res.dump().c_str());
  return NULL;
}

ClientArgs initial_args = {
    .cid = 1,
    .all_client_num = NUM_ALL_CLIENTS,
    .core = 0,
};

int main(int argc, char** argv) {
  if (argc != 5) {
    printf("Usage: %s <memcached_ip> <workload> <redis_ip> <run_time>\n",
           argv[0]);
    exit(1);
  }
  int sid = 1;
  strcpy(initial_args.controller_ip, argv[1]);
  strcpy(initial_args.wl_name, argv[2]);
  strcpy(initial_args.redis_ip, argv[3]);
  initial_args.run_times_s = atoi(argv[4]);
  printf("memcached_ip: %s\n", initial_args.controller_ip);
  printf("workload: %s\n", initial_args.wl_name);
  printf("redis_ip: %s\n", initial_args.redis_ip);
  printf("running %d seconds\n", initial_args.run_times_s);

  ClientArgs args[NUM_LOCAL_CLIENTS];
  pthread_t tids[NUM_LOCAL_CLIENTS];
  for (int i = 0; i < NUM_LOCAL_CLIENTS; i++) {
    memcpy(&args[i], &initial_args, sizeof(ClientArgs));
    args[i].cid = i + sid;
    args[i].core = i % NUM_CORES;
    args[i].ops_list = new std::vector<uint32_t>();
    args[i].lat_map_cont =
        new std::vector<std::unordered_map<uint64_t, uint32_t>>();

    pthread_create(&tids[i], NULL, worker, &args[i]);
  }

  for (int i = 0; i < NUM_LOCAL_CLIENTS; i++) {
    pthread_join(tids[i], NULL);
  }

  // merge results
  assert(args[0].ops_list->size() == args[0].lat_map_cont->size());
  std::vector<uin32_t> merged_ops_list(args[0].ops_list->size());
  std::vector<std::unordered_map<uint32_t, uint32_t>> merged_lat_map_cont(
      args[0].lat_map_cont->size());
  for (int i = 0; i < NUM_LOCAL_CLIENTS; i++) {
    for (int j = 0; j < args[i].ops_list->size(); j++) {
      merged_ops_list[j] += (*args[i].ops_list)[j];

      std::unordered_map<uint32_t, uint32_t>* cur_lat_map =
          &args[i].lat_map_cont[j];
      for (auto it = cur_lat_map->begin(); it != cur_lat_map->end(); it++) {
        merged_lat_map_cont[it->first] += it->second;
      }
    }
  }

  json merged_res;
  merged_res["ops_cont"] = json(merged_ops_list);
  merged_res["lat_map_cont"] = json(merged_lat_map_cont);

  char fname_buf[256];
  sprintf(fname_buf, "results/cont-merged-128.json");
  FILE* f = fopen(fname_buf, "w");
  assert(f != NULL);
  fprintf(f, "%s", merged_res.dump().c_str());
}
