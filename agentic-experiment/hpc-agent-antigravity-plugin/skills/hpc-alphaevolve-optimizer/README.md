# HPC AlphaEvolve Optimizer (`hpc-alphaevolve-optimizer`)

Evolutionary code, heuristic algorithm, and parametric 3D CAD optimization skill for Google Cloud HPC.

## Quick Verification

```bash
python3 scripts/alphaevolve_helper_test.py
```

## Contents

- `SKILL.md`: Main agent instructions and Golden Rules.
- `scripts/alphaevolve_helper.py`: CLI and library for `# EVOLVE-BLOCK-START` splicing, AST/sandbox verification, watertight mesh checks, 4-island prompting, and Cluster Toolkit blueprint generation.
- `scripts/alphaevolve_helper_test.py`: Unit test suite.
- `references/evolutionary_harness_guide.md`: Detailed evolutionary architecture reference.
- `examples/alpha_evolve_experiment_template.yaml`: Cluster Toolkit experiment YAML blueprint.
