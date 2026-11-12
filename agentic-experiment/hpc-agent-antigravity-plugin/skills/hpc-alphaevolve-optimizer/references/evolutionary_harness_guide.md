# AlphaEvolve Evolutionary Harness & Multi-Fidelity Physics Guide

## 1. `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` Contract

AlphaEvolve isolates mutable algorithm or parametric CAD code inside explicit delimiter markers so surrounding solver setup, boundary conditions, and safety checks cannot be tampered with by LLM mutations:

```python
# EVOLVE-BLOCK-START
def evolve_params() -> dict[str, float]:
    """Mutable parametric design or heuristic scheduling policy."""
    return {
        "front_wing_aoa_deg": 13.8,
        "underbody_throat_mm": 19.5,
        "diffuser_expansion_deg": 11.4,
    }
# EVOLVE-BLOCK-END
```

### Diff Splicing & AST Validation
1. **Primary Mode (`diff_search_replace`)**: The LLM emits `RATIONALE: <one-sentence physics explanation>` followed by `<<<< SEARCH ... ==== ... >>>> REPLACE` blocks.
2. **Fallback Mode (`full_block_fallback`)**: If a search block fails to match whitespace, the parser extracts a fenced Python block, strips any outer markers, and validates the AST before splicing.
3. **AST Gate**: Every candidate must parse cleanly via `ast.parse()`, define exactly one top-level target function (`def evolve_params(...)`), contain at least one non-empty `return` statement, and refrain from importing network or subprocess modules.

---

## 2. Isolated Candidate Sandbox (`python3 -I`)

Untrusted LLM-generated candidates are executed inside an ephemeral directory with `python3 -I` (isolated mode):
- **Resource Limits**: `RLIMIT_AS = 2 GiB` virtual memory cap, `RLIMIT_CPU = 6s` CPU time limit, and a 5-second wall-clock timeout.
- **Import Hook Guard**: `builtins.__import__` blocks `socket`, `ssl`, `http`, `urllib`, `requests`, `subprocess`, `multiprocessing`, and `ctypes`.
- **Manifold & Finite Checks**: Returned dictionaries are checked for `math.isfinite(v)` on every numeric value, clamped against domain bounds, and any procedurally generated 3D STL mesh is audited for 2-manifold watertightness (`boundary_edges == 0`, `non_manifold_edges == 0`, `degenerate_triangles == 0`) prior to meshing in `snappyHexMesh` or `OpenRadioss`.

---

## 3. Multi-Island MAP-Elites & Specialist Prompting

| Island ID | Temperature | Specialist Focus | Model Tier Routing |
| :--- | :--- | :--- | :--- |
| **Island 0** | `0.75` | Primary physics balance & Pareto frontier exploitation | `GEMINI_V3P5_FLASH` (80%) / `GEMINI_V3P1_PRO_PREVIEW` (20%) |
| **Island 1** | `0.80` | Boundary-layer / DRC / constraint margin tightening | `GEMINI_V3P5_FLASH` |
| **Island 2** | `0.85` | Cross-parameter coupled trade-offs & nonlinear interactions | `GEMINI_V3P5_FLASH` / `GEMINI_V3P1_PRO_PREVIEW` |
| **Island 3** | `1.00` | Architectural & topological exploration to escape local optima | `GEMINI_V3P1_PRO_PREVIEW` |
