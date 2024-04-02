#ifndef _REDIS_ADAPTER_H_
#define _REDIS_ADAPTER_H_

#include <sw/redis++/redis++.h>

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

#endif