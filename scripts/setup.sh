#!/bin/bash

sudo apt update -y

# install anaconda
if [ ! -d "./install" ]; then
  mkdir install
fi
mkdir install

cd install
if [ ! -f "./anaconda-install.sh" ]; then
  wget https://repo.anaconda.com/archive/Anaconda3-2022.05-Linux-x86_64.sh -O anaconda-install.sh
fi
if [ ! -d "$HOME/anaconda3" ]; then
  chmod +x anaconda-install.sh
  ./anaconda-install.sh -b
  export PATH=$PATH:$HOME/anaconda3/bin
  # add conda to path
  # activate base
fi
echo PATH=$PATH:$HOME/anaconda3/bin >> $HOME/.bashrc
source ~/.bashrc
conda init bash
source ~/.bashrc
conda activate base
cd ..

pip install gdown python-memcached fabric
sudo apt install libmemcached-dev memcached libboost-all-dev -y

# install cmake
cd install
if [ ! -f cmake-3.16.8.tar.gz ]; then
  wget https://cmake.org/files/v3.16/cmake-3.16.8.tar.gz
fi
if [ ! -d "./cmake-3.16.8" ]; then
  tar zxf cmake-3.16.8.tar.gz
  cd cmake-3.16.8 && ./configure && make -j 4 && sudo make install
fi
cd ..

# install redis
sudo apt update -y
sudo apt install lsb-release -y
curl -fsSL https://packages.redis.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/redis.list
sudo apt-get update -y
sudo apt-get install redis -y

# install hiredis
sudo apt install libhiredis-dev -y

# install redis++
if [ ! -d "third_party" ]; then
  mkdir third_party
fi
cd third_party
git clone https://github.com/sewenew/redis-plus-plus.git
cd redis-plus-plus
if [ ! -d "build" ]; then
  mkdir build
fi
cd build
cmake ..
make -j 8
sudo make install
cd .. # -> redis-plus-plus
cd .. # -> third_party
cd .. # -> install

# install oh-my-zsh
#if [ ! -d '~/.oh-my-zsh' ]; then
#  sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
#fi
#echo "export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/usr/local/lib" >> ~/.zshrc
#echo "ulimit -n unlimited" >> ~/.zshrc
#conda init zsh
