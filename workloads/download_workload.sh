#!/bin/bash

fid="1E-hyuwWGugDidX12ZgkRBNzAvLEeoNjv"
python3 download_gdrive.py $fid "$1.tgz"
if [ ! -d ycsb ]; then
    mkdir ycsb
fi
mv $1.tgz ycsb
cd ycsb && tar xf $1.tgz && cd ..
