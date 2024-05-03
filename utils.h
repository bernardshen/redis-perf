#ifndef _UTILS_H_
#define _UTILS_H_

#include <fstream>
#include <map>
#include <sstream>
#include <unordered_map>
#include <vector>

#include <pthread.h>
#include <stdint.h>

#include <boost/foreach.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <sw/redis++/redis++.h>

#define __OUT
#define _KV_SIZE (256)

enum KVOP { SET, GET };
enum REDIS_PERF_MODE {
  MOD_SINGLE,
  MOD_CLUSTER,
  MOD_DMC_CLUSTER,
  MOD_SENTINEL,
  MOD_DMC_SENTINEL
};
enum REDIS_PERF_EXP { EXP_NORMAL, EXP_ELASTICITY, EXP_RECOVERY };

typedef struct _ClientArgs {
  uint32_t cid;
  uint32_t all_client_num;

  uint32_t core;

  int mode;
  int exp;

  char controller_ip[256];
  char wl_name[256];
  char redis_ip[256];
  uint32_t run_times_s;
  char dmc_cluster_ips[32][256];
  uint32_t num_dmc_cluster_total_servers;
  uint32_t num_dmc_cluster_initial_servers;
  uint32_t num_dmc_cluster_scale_servers;

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

static int load_dmc_cluster_config(const char *fname, __OUT ClientArgs *args) {
  printd(L_DEBUG, "Loading config for DMC cluster.");
  std::fstream config_fs(fname);
  assert(config_fs.is_open());

  boost::property_tree::ptree pt;
  try {
    boost::property_tree::read_json(config_fs, pt);
  } catch (boost::property_tree::ptree_error &e) {
    perror("read_json failed\n");
    return -1;
  }

  int i = 0;
  BOOST_FOREACH (boost::property_tree::ptree::value_type &v,
                 pt.get_child("cluster_ips")) {
    std::string ip = v.second.get<std::string>("");
    assert(ip.length() > 0);
    strcpy(args->dmc_cluster_ips[i], ip.c_str());
    i++;
  }
  args->num_dmc_cluster_total_servers = i;

  args->num_dmc_cluster_initial_servers =
      pt.get<uint32_t>("num_initial_servers", i);
  args->num_dmc_cluster_scale_servers =
      pt.get<uint32_t>("num_scale_servers", i);

  return 0;
}

#endif