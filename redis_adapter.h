#ifndef _REDIS_ADAPTER_H_
#define _REDIS_ADAPTER_H_

#include <atomic>
#include <boost/crc.hpp>
#include <memory>
#include <random>
#include <stdint.h>
#include <string>
#include <sw/redis++/redis++.h>

#include "utils.h"

// #define DMC_CLUSTER_STATISTICS

using namespace sw::redis;

class MyRedisAdapter {
public:
  virtual OptionalString get(std::string) = 0;
  virtual bool set(std::string, std::string) = 0;
};

class RedisAdapter : public MyRedisAdapter {
  Redis redis;

public:
  RedisAdapter(const std::string &redis_ip) : redis(redis_ip) {}

  OptionalString get(std::string key) override { return redis.get(key); }

  bool set(std::string key, std::string val) override {
    return redis.set(key, val);
  }
};

class RedisClusterAdapter : public MyRedisAdapter {
  RedisCluster redis;

public:
  RedisClusterAdapter(const std::string &redis_ip) : redis(redis_ip) {}

  OptionalString get(std::string key) override { return redis.get(key); }

  bool set(std::string key, std::string val) override {
    return redis.set(key, val);
  }
};

class DMCClusterAdapter : public MyRedisAdapter {
  std::vector<Redis> dmc_cluster_;
  std::vector<std::string> dmc_cluster_ips_;
  boost::crc_32_type crc_processor_;
  std::random_device rd_;
  std::mt19937 gen_;
  std::uniform_int_distribution<> dist_;

  static std::atomic<uint32_t> num_alive_servers_;
#ifdef DMC_CLUSTER_STATISTICS
  static std::atomic<uint32_t> access_vector_[32];
#endif

public:
  DMCClusterAdapter(char dmc_cluster_ips[32][256], int num_total_servers)
      : gen_(rd_()), dist_(0, 999) {
    for (int i = 0; i < num_total_servers; i++) {
      std::string str_ip(dmc_cluster_ips[i]);
      dmc_cluster_.emplace_back(str_ip);
      dmc_cluster_ips_.push_back(str_ip);
    }
    // assert(num_alive_servers_.load() <= dmc_cluster_.size());
  }

  OptionalString get(std::string key) override {
    crc_processor_.process_bytes(key.data(), key.length());
    uint32_t target_server =
        dist_(gen_) % num_alive_servers_.load(std::memory_order_acquire);
    // uint32_t target_server = crc_processor_.checksum() %
    //                          num_alive_servers_.load(std::memory_order_acquire);
#ifdef DMC_CLUSTER_STATISTICS
    access_vector_[target_server].fetch_add(1);
#endif
    return dmc_cluster_[target_server].get(key);
  }

  bool set(std::string key, std::string val) override {
    crc_processor_.process_bytes(key.data(), key.length());
    uint32_t target_server = crc_processor_.checksum() %
                             num_alive_servers_.load(std::memory_order_acquire);
#ifdef DMC_CLUSTER_STATISTICS
    access_vector_[target_server].fetch_add(1);
#endif
    return dmc_cluster_[target_server].set(key, val);
  }

  static void update_num_servers(int new_num_servers) {
    printd(L_INFO, "scale to %d servers", new_num_servers);
    num_alive_servers_.store(new_num_servers, std::memory_order_release);
  }

  static void print_access_vector() {
#ifdef DMC_CLUSTER_STATISTICS
    for (int i = 0; i < 32; i++) {
      printf("%d ", access_vector_[i].load());
    }
    printf("\n");
#endif
  }
};
std::atomic<uint32_t> DMCClusterAdapter::num_alive_servers_ = 0;
#ifdef DMC_CLUSTER_STATISTICS
std::atomic<uint32_t> DMCClusterAdapter::access_vector_[32] = {0};
#endif

class RedisSentinelAdapter : public MyRedisAdapter {
  SentinelOptions sentinel_opts_;
  std::shared_ptr<Sentinel> sentinel_;
  std::vector<Redis> redis_nodes_;

public:
  RedisSentinelAdapter(const std::string &redis_ip) {
    std::string stripped = redis_ip.substr(6);
    std::size_t delimiter = stripped.find(':');
    std::string ip = stripped.substr(0, delimiter);
    std::string port = stripped.substr(delimiter + 1);
    sentinel_opts_.nodes = {{ip, std::stoi(port.c_str())}};
    sentinel_ = std::make_shared<Sentinel>(sentinel_opts_);

    ConnectionOptions connection_opts;
    connection_opts.connect_timeout = std::chrono::milliseconds(100);
    connection_opts.socket_timeout = std::chrono::milliseconds(100);

    ConnectionPoolOptions pool_opts;
    redis_nodes_.emplace_back(sentinel_, "master", Role::MASTER,
                              connection_opts, pool_opts);
    redis_nodes_.emplace_back(sentinel_, "slave", Role::SLAVE, connection_opts,
                              pool_opts);
  }

  OptionalString get(std::string key) override {
    struct timeval cur;
    gettimeofday(&cur, NULL);
    try {
      return redis_nodes_[cur.tv_usec % 2].get(key);
    } catch (const Error &e) {
      return redis_nodes_[0].get(key);
    }
  }

  bool set(std::string key, std::string val) override {
    return redis_nodes_[0].set(key, val);
  }
};

class DMCSentinelAdapter : public MyRedisAdapter {
  std::vector<Redis> dmc_nodes_;
  std::vector<std::string> dmc_node_ips_;
  static std::atomic<uint32_t> primary_idx_;

public:
  DMCSentinelAdapter(char dmc_sentinel_ips[32][256], int num_initial_servers) {
    for (int i = 0; i < num_initial_servers; i++) {
      std::string str_ip(dmc_sentinel_ips[i]);
      dmc_nodes_.emplace_back(str_ip);
      dmc_node_ips_.emplace_back(str_ip);
    }
    // assert(num_alive_servers_.load() <= dmc_cluster_.size());
  }
  OptionalString get(std::string key) override {
    struct timeval cur;
    gettimeofday(&cur, NULL);
    uint32_t cur_primary = primary_idx_.load(std::memory_order_acquire);
    uint32_t num_alive = dmc_nodes_.size() - cur_primary;
    uint32_t target_node = cur_primary + (cur.tv_usec % num_alive);

    try {
      return dmc_nodes_[target_node].get(key);
    } catch (const Error &e) {
      return dmc_nodes_[1].get(key);
    }
  }

  bool set(std::string key, std::string val) override {
    try {
      uint32_t cur_primary = primary_idx_.load(std::memory_order_acquire);
      return dmc_nodes_[cur_primary].set(key, val);
    } catch (const Error &e) {
      return dmc_nodes_[1].set(key, val);
    }
  }

  void connect_new_backup(const std::string ip) {
    dmc_nodes_.emplace_back(ip);
    dmc_node_ips_.emplace_back(ip);
  }

  static void set_primary(int primary_idx) {
    printd(L_INFO, "switch priamry to %d", primary_idx);
    primary_idx_.store(primary_idx, std::memory_order_release);
  }
};
std::atomic<uint32_t> DMCSentinelAdapter::primary_idx_ = 0;

static inline MyRedisAdapter *get_redis(ClientArgs *args) {
  if (args->mode == MOD_CLUSTER) {
    return new RedisClusterAdapter(args->redis_ip);
  } else if (args->mode == MOD_SINGLE) {
    return new RedisAdapter(args->redis_ip);
  } else if (args->mode == MOD_SENTINEL) {
    return new RedisSentinelAdapter(args->redis_ip);
  } else if (args->mode == MOD_DMC_SENTINEL) {
    return new DMCSentinelAdapter(args->dmc_cluster_ips,
                                  args->num_dmc_cluster_total_servers);
  } else {
    assert(args->mode == MOD_DMC_CLUSTER);
    return new DMCClusterAdapter(args->dmc_cluster_ips,
                                 args->num_dmc_cluster_total_servers);
  }
}

#endif