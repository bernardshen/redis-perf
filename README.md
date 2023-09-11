# Dependencies
- CMake
- Anaconda3
- Python packages:
    `pip install python-memcached fabric`
- Other dependencies:
    `sudo apt install libmemcached-dev memcached libboost-all-dev libhiredis-dev`
- Redis++:
    ```bash
    git clone https://github.com/sewenew/redis-plus-plus.git
    cd redis-plus-plus
    mkdir build
    cd build
    cmake ..
    make -j 8
    sudo make install
    ```
- Modify `/etc/memcached.conf`
  ```
  -l 0.0.0.0
  -I 128m
  -m 2048
  ```
