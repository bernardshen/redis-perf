#ifndef _UTILS_H_
#define _UTILS_H_

#include <map>
#include <unordered_map>
#include <vector>

#include <pthread.h>
#include <stdint.h>

#include <sw/redis++/redis++.h>

#define __OUT
#define _KV_SIZE (256)

enum KVOP { SET, GET };

typedef struct _ClientArgs {
  uint32_t cid;
  uint32_t all_client_num;

  uint32_t core;

  bool is_cluster;

  char controller_ip[256];
  char wl_name[256];
  char redis_ip[256];
  uint32_t run_times_s;

  // used for direct test
  std::vector<uint32_t> *cont_tpt;
  std::vector<std::unordered_map<uint64_t, uint32_t>> *cont_lat_map;
} ClientArgs;

static inline uint64_t diff_ts_us(const struct timeval *et,
                                  const struct timeval *st) {
  return (et->tv_sec - st->tv_sec) * 1000000 + (et->tv_usec - st->tv_usec);
}

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

#endif