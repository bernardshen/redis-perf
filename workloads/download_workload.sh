#!/bin/bash
wl=$1

if [ "$wl" == "ycsb" ]; then
    fid="1E-hyuwWGugDidX12ZgkRBNzAvLEeoNjv"
    python3 download_gdrive.py $fid "$1.tgz"
    if [ ! -d ycsb ]; then
        mkdir ycsb
    fi
    mv $1.tgz ycsb
    cd ycsb && tar xf $1.tgz && cd ..
fi

if [ "$wl" == "twitter" ]; then
    if [ ! -d twitter ]; then
        mkdir twitter
    fi
    wget https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/open_source/cluster3.sort.zst
    wget https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/open_source/cluster1.sort.zst
    wget https://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/open_source/cluster5.sort.zst

    # decompress cluster3 (storage)
    zstd -d ./cluster3.sort.zst
    head ./cluster3.sort -n 50000000 > twitter/twitter-storage
    mv ./cluster3.sort.zst twitter
    rm ./cluster3.sort

    # decompress cluster1 (compute)
    zstd -d ./cluster1.sort.zst
    head ./cluster1.sort -n 50000000 > twitter/twitter-compute
    mv ./cluster1.sort.zst twitter
    rm ./cluster1.sort

    # decompress cluster5 (transient)
    zstd -d ./cluster5.sort.zst
    head ./cluster5.sort -n 50000000 > twitter/twitter-transient
    mv ./cluster5.sort.zst twitter
    rm ./cluster5.sort
fi