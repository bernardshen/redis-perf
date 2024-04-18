#ifndef _REDIS_ADAPTER_H_
#define _REDIS_ADAPTER_H_

#include <atomic>
#include <boost/crc.hpp>
#include <sw/redis++/redis++.h>

#define DMC_CLUSTER_STATISTICS

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

  static std::atomic<uint32_t> num_alive_servers_;
#ifdef DMC_CLUSTER_STATISTICS
  static std::atomic<uint32_t> access_vector_[32];
#endif

public:
  DMCClusterAdapter(char dmc_cluster_ips[32][256], int num_total_servers) {
    for (int i = 0; i < num_total_servers; i++) {
      std::string str_ip(dmc_cluster_ips[i]);
      dmc_cluster_.emplace_back(str_ip);
      dmc_cluster_ips_.push_back(str_ip);
    }
    // assert(num_alive_servers_.load() <= dmc_cluster_.size());
  }

  OptionalString get(std::string key) override {
    crc_processor_.process_bytes(key.data(), key.length());
    uint32_t target_server = crc_processor_.checksum() %
                             num_alive_servers_.load(std::memory_order_acquire);
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

#endif