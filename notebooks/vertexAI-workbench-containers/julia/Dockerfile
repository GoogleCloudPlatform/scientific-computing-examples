FROM gcr.io/deeplearning-platform-release/base-gpu.py310 

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /tmp
#RUN curl -fsSL https://install.julialang.org > julia.sh && \
#     sh julia.sh -y && \
#     rm julia.sh

RUN mkdir /opt/julia && \
    cd /opt/julia && \
    wget https://julialang-s3.julialang.org/bin/linux/x64/1.9/julia-1.9.4-linux-x86_64.tar.gz && \
    tar zxvf julia-1.9.4-linux-x86_64.tar.gz && \
    ln -s /opt/julia/julia-1.9.4/bin/julia /usr/local/bin/julia

# See https://github.com/JuliaCI/julia-buildkite/blob/70bde73f6cb17d4381b62236fc2d96b1c7acbba7/utilities/build_envs.sh#L54
# for an explanation of these options
ENV JULIA_CPU_TARGET="generic;sandybridge,-xsaveopt,clone_all;haswell,-rdrnd,base(1)" 
     
#RUN /root/.juliaup/bin/juliaup add 1.9 && \
#     /root/.juliaup/bin/juliaup default 1.9
     
RUN julia -e 'import Pkg; Pkg.update()'  && \
    julia -e 'using Pkg; Pkg.add(["IJulia", "Lux", "ModelingToolkit", "Optimization", "OptimizationOptimisers", "NeuralPDE", "Plots"])' &&\
    julia -e 'using Pkg; Pkg.precompile'

EXPOSE 8080
