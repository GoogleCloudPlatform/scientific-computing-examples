FROM gcr.io/deeplearning-platform-release/base-gpu.py310 

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /tmp
RUN curl -fsSL https://install.julialang.org > julia.sh && \
     sh julia.sh -y && \
     rm julia.sh
     
RUN /root/.juliaup/bin/juliaup add 1.9 && \
     /root/.juliaup/bin/juliaup default 1.9
     
# taking effect properly on the .local folder in the jovyan home dir.
RUN /root/.juliaup/bin/julia -e 'import Pkg; Pkg.update()' 
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("IJulia")'
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("Lux")' 
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("ModelingToolkit")'  
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("Optimization")' 
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("OptimizationOptimisers")'
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("NeuralPDE")' 
RUN /root/.juliaup/bin/julia -e 'using Pkg; Pkg.add("Plots")'

EXPOSE 8080
