FROM gcr.io/deeplearning-platform-release/base-gpu.py310 

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /tmp
RUN curl -fsSL https://install.julialang.org > julia.sh && \
     sh julia.sh -y && \
     rm julia.sh
     
RUN /root/.juliaup/bin/juliaup add 1.9 && \
     /root/.juliaup/bin/juliaup default 1.9
     
 RUN /root/.juliaup/bin/julia -e 'import Pkg; Pkg.update()'  && \
 /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("IJulia")' && \
/root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("Lux")'  && \
/root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("ModelingToolkit")'   && \
/root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("Optimization")'  && \
/root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("OptimizationOptimisers")' && \
/root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("NeuralPDE")'  && \
/root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("Plots")'

EXPOSE 8080
