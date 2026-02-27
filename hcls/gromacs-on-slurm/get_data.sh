#!/bin/bash

# Dowload benchmark configuration data from UIUC website

wget https://zenodo.org/record/3893789/files/GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP.tar.gz 
tar xf GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP.tar.gz 
cd GROMACS_heterogeneous_parallelization_benchmark_info_and_systems_JCP/stmv