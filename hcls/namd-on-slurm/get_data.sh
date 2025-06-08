#!/bin/bash

# Dowload benchmark configuration data from UIUC website

wget -qO- https://www.ks.uiuc.edu/Research/namd/benchmarks/systems/apoa1_gpu.tar.gz | tar xvz
wget -qO- https://www.ks.uiuc.edu/Research/namd/benchmarks/systems/stmv_gpu.tar.gz | tar xvz

cp apoa1_gpures_npt.namd apoa1_gpu