cmake_minimum_required(VERSION 3.0)

project(DMCRedis LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)

add_executable(redis_perf redis_perf.cc memcached.cc)
add_executable(redis_perf_tpt redis_perf_tpt.cc memcached.cc)

target_link_libraries(
    redis_perf
    redis++
    hiredis
    pthread
    memcached
)

target_link_libraries(
    redis_perf_tpt
    redis++
    hiredis
    pthread
    memcached
)

target_compile_options(redis_perf PRIVATE -O0 -g)
target_compile_options(redis_perf_tpt PRIVATE -O2 -g)