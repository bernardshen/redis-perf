cmake_minimum_required(VERSION 3.0)

project(DMCRedis LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)

add_executable(redis_perf redis_perf.cc memcached.cc)
add_executable(redis_load_ycsb redis_load_ycsb.cc memcached.cc)
add_executable(redis_trans_ycsb redis_trans_ycsb.cc memcached.cc)

target_link_libraries(
    redis_perf
    redis++
    hiredis
    pthread
    memcached
)

target_link_libraries(
    redis_load_ycsb
    redis++
    hiredis
    pthread
    memcached
)

target_link_libraries(
    redis_trans_ycsb
    redis++
    hiredis
    pthread
    memcached
)

target_compile_options(redis_perf PRIVATE -O0 -g)
target_compile_options(redis_load_ycsb PRIVATE -O0 -g)
target_compile_options(redis_trans_ycsb PRIVATE -O0 -g)