# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""3D Structure-Based Drug Discovery Physics Docking & MPO Scoring Oracle."""

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping
import numpy as np
from scipy.optimize import minimize

# Seed scaffolds for each oncology target pocket (moderate starting potency)
SEED_SCAFFOLDS: dict[str, list[str]] = {
    "KRAS_G12D_7RPZ": [
        "c1ccc2c(c1)ccc(N1CCNCC1)n2",  # Basic quinoline-piperazine fragment
        "O=C(Nc1cccc(Cl)c1)c1ccncc1",  # Chlorophenyl-isonicotinamide fragment
        "Cc1ccc(C(=O)N2CCNCC2)cc1",  # Toluoyl-piperazine fragment
        "c1ccc2[nH]ccc2c1",  # Indole core
    ],
    "EGFR_T790M_3IKA": [
        "c1ccc(Nc2ncnc3ccccc23)cc1",  # Anilinoquinazoline core
        "COc1cc2ncnc(Nc3ccccc3)c2cc1OC",  # Dimethoxy-quinazoline fragment
        "c1cnc(Nc2ccccc2)nc1",  # Phenylaminopyrimidine fragment
        "c1ccc2c(c1)cc[nH]2",  # Indole fragment
    ],
}

# Reactive / toxicophore SMARTS and substring patterns (PAINS / Brenk)
REACTIVE_SMARTS: tuple[tuple[str, str], ...] = (
    ("acyl_halide", "[CX3](=[OX1])[F,Cl,Br,I]"),
    ("peroxide", "[OX2][OX2]"),
    ("nitroso", "[NX2]=[OX1]"),
    ("isocyanate", "N=C=O"),
    ("isothiocyanate", "N=C=S"),
    ("sulfonyl_halide", "[SX4](=[OX1])(=[OX1])[F,Cl,Br,I]"),
    ("diazonium", "[N+]#N"),
    ("phosphorane", "P(=O)(Cl)Cl"),
    ("polyene_aldehyde", "C=CC=CC=O"),
)

REACTIVE_SUBSTRINGS: tuple[str, ...] = (
    "OO",
    "N=O",
    "N=C=O",
    "N=C=S",
    "C(=O)Cl",
    "C(=O)Br",
    "S(=O)(=O)Cl",
    "[N+]#N",
)


def _try_import_rdkit() -> tuple[Any, ...]:
  """Lazily imports RDKit modules so Controller Container imports never fail."""
  try:
    from rdkit import Chem  # pylint: disable=g-import-not-at-top
    from rdkit import DataStructs  # pylint: disable=g-import-not-at-top
    from rdkit import RDLogger  # pylint: disable=g-import-not-at-top
    from rdkit.Chem import AllChem  # pylint: disable=g-import-not-at-top
    from rdkit.Chem import Crippen  # pylint: disable=g-import-not-at-top
    from rdkit.Chem import Descriptors  # pylint: disable=g-import-not-at-top
    from rdkit.Chem import QED  # pylint: disable=g-import-not-at-top
    from rdkit.Chem import rdMolDescriptors  # pylint: disable=g-import-not-at-top

    RDLogger.DisableLog("rdApp.*")
    return (
        Chem,
        AllChem,
        Descriptors,
        Crippen,
        QED,
        rdMolDescriptors,
        DataStructs,
    )
  except ImportError:
    return (None,) * 7


def load_pocket_model(pocket_name: str | Path | dict[str, Any]) -> dict[str, Any]:
  """Loads a 3D protein binding pocket specification JSON from models/."""
  if isinstance(pocket_name, dict):
    data = dict(pocket_name)
    data.setdefault(
        "pharmacophore_anchors", data.get("pharmacophore_features", [])
    )
    data.setdefault("residues", data.get("receptor_atoms", []))
    return data
  cand_path = Path(pocket_name)
  if cand_path.is_file():
    path = cand_path
  else:
    models_dir = Path(__file__).absolute().parent.parent / "models"
    fname_map = {
        "KRAS_G12D_7RPZ": "kras_g12d_pocket.json",
        "kras_g12d": "kras_g12d_pocket.json",
        "EGFR_T790M_3IKA": "egfr_t790m_pocket.json",
        "egfr_t790m": "egfr_t790m_pocket.json",
    }
    key = str(pocket_name)
    fname = fname_map.get(key, key if key.endswith(".json") else f"{key}.json")
    path = models_dir / fname
  with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
  data.setdefault("pharmacophore_anchors", data.get("pharmacophore_features", []))
  data.setdefault("residues", data.get("receptor_atoms", []))
  return data


def load_pocket(pocket_path: Path | str) -> dict[str, Any]:
  """Loads a pocket JSON file and populates standard aliases."""
  with open(pocket_path, "r", encoding="utf-8") as f:
    data = json.load(f)
  data.setdefault("pharmacophore_anchors", data.get("pharmacophore_features", []))
  data.setdefault("residues", data.get("receptor_atoms", []))
  return data


def _euler_rotation_matrix(angles: np.ndarray) -> np.ndarray:
  """Constructs a 3x3 proper rotation matrix R in SO(3) from Euler angles."""
  ax, ay, az = float(angles[0]), float(angles[1]), float(angles[2])
  cx, sx = math.cos(ax), math.sin(ax)
  cy, sy = math.cos(ay), math.sin(ay)
  cz, sz = math.cos(az), math.sin(az)
  rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
  ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
  rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
  return rz @ ry @ rx


def _compute_ertl_like_sa_score(
    mol: Any, rd_mol_descriptors: Any, num_heavy: int, num_rings: int
) -> float:
  """Computes a synthetic accessibility score on the canonical [1.0, 10.0] scale."""
  if mol is not None and rd_mol_descriptors is not None:
    chiral_centers = rd_mol_descriptors.CalcNumAtomStereoCenters(mol)
    spiro_atoms = rd_mol_descriptors.CalcNumSpiroAtoms(mol)
    bridgehead_atoms = rd_mol_descriptors.CalcNumBridgeheadAtoms(mol)
    macrocycles = sum(
        1 for ring in mol.GetRingInfo().AtomRings() if len(ring) > 8
    )
    fps = rd_mol_descriptors.GetMorganFingerprint(mol, 2)
    unique_env_ratio = len(fps.GetNonzeroElements()) / max(1, num_heavy)
  else:
    chiral_centers = 0
    spiro_atoms = 0
    bridgehead_atoms = 0
    macrocycles = 0
    unique_env_ratio = 1.2

  size_pen = max(0.0, (num_heavy - 22) * 0.045)
  ring_pen = max(0.0, (num_rings - 3) * 0.22)
  stereo_pen = 0.35 * chiral_centers
  complex_ring_pen = (
      0.55 * spiro_atoms + 0.50 * bridgehead_atoms + 1.10 * macrocycles
  )
  complexity_base = 1.65 + 0.42 * unique_env_ratio
  sa = (
      complexity_base
      + size_pen
      + ring_pen
      + stereo_pen
      + complex_ring_pen
  )
  return float(np.clip(sa, 1.0, 10.0))


def _score_vina_3d_pose(
    lig_coords: np.ndarray,
    lig_types: list[str],
    lig_charges: np.ndarray,
    lig_radii: np.ndarray,
    rec_coords: np.ndarray,
    rec_types: list[str],
    rec_charges: np.ndarray,
    rec_radii: np.ndarray,
    pharm_features: list[dict[str, Any]],
) -> dict[str, Any]:
  """Evaluates 3D AutoDock Vina + screened Coulomb + pharmacophore interaction energy."""
  # Pairwise distance matrix (N_lig, N_rec)
  diff = lig_coords[:, None, :] - rec_coords[None, :, :]
  dist = np.linalg.norm(diff, axis=-1) + 1e-6
  sum_r = lig_radii[:, None] + rec_radii[None, :]
  d_surf = dist - sum_r

  # 1. Vina Gauss1, Gauss2, and soft-core induced-fit steric repulsion terms
  gauss1 = np.exp(-((d_surf / 0.5) ** 2))
  gauss2 = np.exp(-(((d_surf - 3.0) / 2.0) ** 2))
  repulsion = np.where(d_surf < -0.55, (d_surf + 0.55) ** 2, 0.0)

  e_steric = (
      -0.035579 * float(np.sum(gauss1))
      - 0.005156 * float(np.sum(gauss2))
      + 0.650000 * float(np.sum(repulsion))
  )
  steric_clash_kcal = float(0.650000 * np.sum(np.where(d_surf < -0.85, (d_surf + 0.85) ** 2, 0.0)))

  # 2. Hydrophobic contact term
  lig_hydro = np.array([1.0 if t in ("C", "A", "Hal") else 0.0 for t in lig_types])
  rec_hydro = np.array([1.0 if t in ("C", "A", "S") else 0.0 for t in rec_types])
  hydro_mask = lig_hydro[:, None] * rec_hydro[None, :]
  hydro_contact = np.clip((1.5 - d_surf) / 1.0, 0.0, 1.0) * np.where(
      d_surf > -0.4, 1.0, 0.0
  )
  e_hydro = -0.035069 * float(np.sum(hydro_mask * hydro_contact))

  # 3. Directional Hydrogen Bonding term
  lig_donor = np.array([1.0 if t in ("HD", "N_pos") else 0.0 for t in lig_types])
  lig_accept = np.array([1.0 if t in ("OA", "NA", "O_neg") else 0.0 for t in lig_types])
  rec_donor = np.array([1.0 if t == "HD" else 0.0 for t in rec_types])
  rec_accept = np.array([1.0 if t in ("OA", "NA") else 0.0 for t in rec_types])

  hb_pair = lig_donor[:, None] * rec_accept[None, :] + lig_accept[:, None] * rec_donor[None, :]
  hb_ramp = np.clip((0.0 - d_surf) / 0.7, 0.0, 1.0) * np.where(
      d_surf > -0.65, 1.0, 0.0
  )
  e_hbond = -0.587439 * float(np.sum(hb_pair * hb_ramp))

  # 4. Distance-dependent screened Coulombic electrostatics (salt bridges & dipoles)
  q_prod = lig_charges[:, None] * rec_charges[None, :]
  e_elec = float(np.sum(332.0 * q_prod / (4.0 * dist * dist) * np.exp(-dist / 4.5)))
  e_elec = float(np.clip(e_elec, -3.8, 4.0))

  # 5. Specific 3D Pharmacophore Anchor Alignment
  e_pharm = 0.0
  key_hbonds = 0
  salt_bridges = 0
  for feat in pharm_features:
    f_xyz = np.array(feat["xyz"], dtype=float)
    f_type = feat["type"]
    opt_d = float(feat["optimal_dist_A"])
    w_kcal = float(feat["energy_weight_kcal"])

    d_feat = np.linalg.norm(lig_coords - f_xyz[None, :], axis=1)
    if f_type == "neg_charge_acceptor":
      match_idx = [
          i for i, t in enumerate(lig_types) if t in ("N_pos", "HD")
      ]
      if match_idx:
        min_d = float(np.min(d_feat[match_idx]))
        well = math.exp(-(((min_d - opt_d) / 1.15) ** 2))
        is_basic = any(
            lig_types[i] == "N_pos" and d_feat[i] < opt_d + 1.2
            for i in match_idx
        )
        scale = 1.0 if is_basic else 0.55
        e_pharm += w_kcal * scale * well
        if is_basic and min_d <= opt_d + 0.95:
          salt_bridges += 1
    elif f_type == "hbond_acceptor":
      match_idx = [i for i, t in enumerate(lig_types) if t in ("HD", "N_pos")]
      if match_idx:
        min_d = float(np.min(d_feat[match_idx]))
        well = math.exp(-(((min_d - opt_d) / 1.10) ** 2))
        e_pharm += w_kcal * well
        if min_d <= opt_d + 0.85:
          key_hbonds += 1
    elif f_type in ("hbond_donor", "hbond_donor_acceptor"):
      match_idx = [
          i for i, t in enumerate(lig_types) if t in ("OA", "NA", "HD")
      ]
      if match_idx:
        min_d = float(np.min(d_feat[match_idx]))
        well = math.exp(-(((min_d - opt_d) / 1.15) ** 2))
        e_pharm += w_kcal * well
        if min_d <= opt_d + 0.85:
          key_hbonds += 1
    elif f_type == "aromatic_hydrophobic":
      match_idx = [i for i, t in enumerate(lig_types) if t in ("A", "Hal", "C")]
      if match_idx:
        # Reward aromatic + halogen atoms occupying the cryptic hydrophobic groove
        ar_count = sum(
            1
            for i in match_idx
            if d_feat[i] <= opt_d + 1.6 and lig_types[i] in ("A", "Hal")
        )
        min_d = float(np.min(d_feat[match_idx]))
        well = math.exp(-(((min_d - opt_d) / 1.60) ** 2))
        ar_Factor = min(1.15, 0.35 + 0.16 * ar_count)
        e_pharm += w_kcal * ar_Factor * well

  total_raw = e_steric + e_hydro + e_hbond + 0.32 * e_elec + 0.68 * e_pharm
  return {
      "raw_energy_kcal": float(total_raw),
      "steric_clash_kcal": float(steric_clash_kcal),
      "key_hbonds": int(key_hbonds),
      "salt_bridges": int(salt_bridges),
  }


class DockingOracle:
  """Locked 3D Receptor-Pocket Physics Docking & Medicinal Chemistry Oracle."""

  def __init__(self, pocket_name: str, max_budget: int = 24) -> None:
    self.pocket_spec = load_pocket_model(pocket_name)
    self.target_id = self.pocket_spec["target_id"]
    self.max_budget = int(max_budget)
    self.call_count = 0
    self.evaluated_history: list[dict[str, Any]] = []
    self._cache: dict[str, dict[str, Any]] = {}

    self.pocket_center = np.array(
        self.pocket_spec["pocket_center_A"], dtype=float
    )
    self.rec_atoms = self.pocket_spec["receptor_atoms"]
    self.rec_coords = np.array([a["xyz"] for a in self.rec_atoms], dtype=float)
    self.rec_types = [str(a["vina_type"]) for a in self.rec_atoms]
    self.rec_charges = np.array(
        [float(a["charge"]) for a in self.rec_atoms], dtype=float
    )
    self.rec_radii = np.array(
        [float(a["vdw_r"]) for a in self.rec_atoms], dtype=float
    )
    self.pharm_features = self.pocket_spec["pharmacophore_features"]
    self.seed_scaffolds = list(SEED_SCAFFOLDS.get(self.target_id, []))

    (
        self._Chem,
        self._AllChem,
        self._Descriptors,
        self._Crippen,
        self._QED,
        self._rdMolDescriptors,
        self._DataStructs,
    ) = _try_import_rdkit()
    self._has_rdkit = self._Chem is not None

    self._seed_fps = []
    if self._has_rdkit:
      for smi in self.seed_scaffolds:
        m = self._Chem.MolFromSmiles(smi)
        if m is not None:
          self._seed_fps.append(
              self._rdMolDescriptors.GetMorganFingerprintAsBitVect(m, 2, nBits=1024)
          )
      self._reactive_queries = [
          (name, self._Chem.MolFromSmarts(smarts))
          for name, smarts in REACTIVE_SMARTS
      ]

  @property
  def remaining_budget(self) -> int:
    return max(0, self.max_budget - self.call_count)

  def _extract_rdkit_3d_ligand(
      self, smiles: str, n_confs: int = 3
  ) -> tuple[bool, str, dict[str, Any]]:
    """Sanitizes SMILES, embeds 3D ETKDGv3 conformers, and computes MMFF94s strain."""
    Chem = self._Chem
    AllChem = self._AllChem
    if not smiles or not isinstance(smiles, str) or len(smiles) > 220:
      return False, "Invalid or empty SMILES string.", {}

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
      return False, f"RDKit failed to parse SMILES: {smiles}", {}

    try:
      Chem.SanitizeMol(mol)
      canon_smiles = Chem.CanonSmiles(smiles)
    except Exception as e:  # pylint: disable=broad-exception-caught
      return False, f"Chemical valence/sanitization error: {e}", {}

    # Reject disconnected salts/mixtures
    if "." in canon_smiles:
      return False, "Disconnected multi-component salts/mixtures are not allowed.", {}

    num_heavy = mol.GetNumHeavyAtoms()
    if num_heavy < 12 or num_heavy > 42:
      return (
          False,
          f"Heavy atom count {num_heavy} outside drug-like range [12, 42].",
          {},
      )

    # Check reactive / PAINS alerts
    for alert_name, qmol in self._reactive_queries:
      if qmol is not None and mol.HasSubstructMatch(qmol):
        return False, f"Rejected by medicinal chemistry filter ({alert_name}).", {}

    mw = float(self._Descriptors.MolWt(mol))
    logp = float(self._Crippen.MolLogP(mol))
    tpsa = float(self._rdMolDescriptors.CalcTPSA(mol))
    hbd = int(self._rdMolDescriptors.CalcNumHBD(mol))
    hba = int(self._rdMolDescriptors.CalcNumHBA(mol))
    rot_bonds = int(self._rdMolDescriptors.CalcNumRotatableBonds(mol))
    num_rings = int(self._rdMolDescriptors.CalcNumRings(mol))
    qed_val = float(self._QED.qed(mol))
    sa_score = _compute_ertl_like_sa_score(
        mol, self._rdMolDescriptors, num_heavy, num_rings
    )

    # Morgan Tanimoto similarity against seed scaffolds
    fp = self._rdMolDescriptors.GetMorganFingerprintAsBitVect(
        mol, 2, nBits=1024
    )
    max_tanimoto = 0.0
    if self._seed_fps:
      sims = [
          float(self._DataStructs.TanimotoSimilarity(fp, sfp))
          for sfp in self._seed_fps
      ]
      max_tanimoto = max(sims)

    # Embed 3D conformers via ETKDGv3 and evaluate MMFF94s energies
    mol_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    params.useSmallRingTorsions = True
    cids = list(
        AllChem.EmbedMultipleConfs(
            mol_h, numConfs=max(1, int(n_confs)), params=params
        )
    )
    if not cids:
      params.useRandomCoords = True
      res_cid = AllChem.EmbedMolecule(mol_h, params)
      if res_cid >= 0:
        cids = [res_cid]

    if not cids:
      return False, "ETKDGv3 failed to embed a valid 3D conformer.", {}

    mp = AllChem.MMFFGetMoleculeProperties(mol_h, mmffVariant="MMFF94s")
    conf_energies: list[float] = []
    heavy_indices = [
        a.GetIdx() for a in mol_h.GetAtoms() if a.GetAtomicNum() > 1
    ]
    conformer_coords: list[np.ndarray] = []

    for cid in cids:
      e_pre = 0.0
      if mp is not None:
        ff = AllChem.MMFFGetMoleculeForceField(mol_h, mp, confId=cid)
        if ff is not None:
          e_pre = float(ff.CalcEnergy())
          ff.Minimize(maxIts=80)
          e_post = float(ff.CalcEnergy())
          conf_energies.append(max(0.0, min(8.0, 0.08 * abs(e_pre - e_post))))
        else:
          conf_energies.append(1.2)
      else:
        conf_energies.append(1.2)

      conf = mol_h.GetConformer(cid)
      xyz = np.array(
          [
              [
                  conf.GetAtomPosition(idx).x,
                  conf.GetAtomPosition(idx).y,
                  conf.GetAtomPosition(idx).z,
              ]
              for idx in heavy_indices
          ],
          dtype=float,
      )
      xyz = xyz - np.mean(xyz, axis=0, keepdims=True)
      conformer_coords.append(xyz)

    # Classify heavy atoms into Vina interaction types, partial charges, and vdW radii
    lig_types: list[str] = []
    lig_charges: list[float] = []
    lig_radii: list[float] = []
    for idx in heavy_indices:
      atom = mol_h.GetAtomWithIdx(idx)
      z_num = atom.GetAtomicNum()
      is_arom = atom.GetIsAromatic()
      hyb = str(atom.GetHybridization())
      total_h = atom.GetTotalNumHs(includeNeighbors=True)
      f_chg = atom.GetFormalCharge()

      if z_num == 6:
        lig_types.append("A" if is_arom else "C")
        lig_charges.append(0.05 if is_arom else 0.0)
        lig_radii.append(1.75 if is_arom else 1.80)
      elif z_num == 7:
        # Aliphatic sp3 amine with H or positive charge is protonated at physiological pH 7.4
        is_amide_n = any(
            nb.GetAtomicNum() == 6
            and any(
                b.GetBondTypeAsDouble() == 2.0
                and b.GetOtherAtom(nb).GetAtomicNum() in (8, 16)
                for b in nb.GetBonds()
            )
            for nb in atom.GetNeighbors()
        )
        if (f_chg > 0) or (not is_arom and "SP3" in hyb and not is_amide_n):
          lig_types.append("N_pos")
          lig_charges.append(0.65)
          lig_radii.append(1.55)
        elif total_h > 0:
          lig_types.append("HD")
          lig_charges.append(0.28)
          lig_radii.append(1.55)
        else:
          lig_types.append("NA")
          lig_charges.append(-0.32)
          lig_radii.append(1.55)
      elif z_num == 8:
        if f_chg < 0:
          lig_types.append("O_neg")
          lig_charges.append(-0.65)
          lig_radii.append(1.52)
        elif total_h > 0:
          lig_types.append("HD")
          lig_charges.append(-0.25)
          lig_radii.append(1.52)
        else:
          lig_types.append("OA")
          lig_charges.append(-0.38)
          lig_radii.append(1.52)
      elif z_num in (9, 17, 35, 53):
        lig_types.append("Hal")
        lig_charges.append(-0.15)
        lig_radii.append(1.47 if z_num == 9 else (1.75 if z_num == 17 else 1.85))
      elif z_num == 16:
        lig_types.append("OA")
        lig_charges.append(-0.15)
        lig_radii.append(1.80)
      else:
        lig_types.append("C")
        lig_charges.append(0.0)
        lig_radii.append(1.75)

    return (
        True,
        "OK",
        {
            "canon_smiles": canon_smiles,
            "mw": mw,
            "logp": logp,
            "tpsa": tpsa,
            "hbd": hbd,
            "hba": hba,
            "rotatable_bonds": rot_bonds,
            "num_rings": num_rings,
            "qed": qed_val,
            "sa_score": sa_score,
            "max_seed_tanimoto": max_tanimoto,
            "conformer_coords": conformer_coords,
            "conf_strains": conf_energies,
            "lig_types": lig_types,
            "lig_charges": np.array(lig_charges, dtype=float),
            "lig_radii": np.array(lig_radii, dtype=float),
        },
    )

  def _extract_fallback_3d_ligand(
      self, smiles: str
  ) -> tuple[bool, str, dict[str, Any]]:
    """Deterministic fallback SMILES parser when RDKit is not installed."""
    if not smiles or not isinstance(smiles, str) or len(smiles) > 220:
      return False, "Invalid or empty SMILES string.", {}
    s = smiles.strip()
    if "." in s or s.count("(") != s.count(")"):
      return False, "Unbalanced parentheses or disconnected salt in SMILES.", {}
    for sub in REACTIVE_SUBSTRINGS:
      if sub in s:
        return False, f"Rejected by reactive substring filter ({sub}).", {}

    tokens = re.findall(r"Cl|Br|[cnosCNOSFIP]", s)
    num_heavy = len(tokens)
    if num_heavy < 12 or num_heavy > 42:
      return False, f"Heavy atom count {num_heavy} outside [12, 42].", {}

    # Deterministic 3D chain/ring coordinates from SMILES tokens
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
    coords = np.zeros((num_heavy, 3), dtype=float)
    lig_types: list[str] = []
    lig_charges: list[float] = []
    lig_radii: list[float] = []

    for i, tok in enumerate(tokens):
      angle = 0.65 * i
      coords[i, 0] = 1.32 * i * math.cos(0.18 * i) - 0.55 * num_heavy
      coords[i, 1] = 1.85 * math.sin(angle) + 0.25 * float(rng.normal())
      coords[i, 2] = 1.15 * math.cos(angle) + 0.25 * float(rng.normal())
      if tok == "c":
        lig_types.append("A")
        lig_charges.append(0.04)
        lig_radii.append(1.75)
      elif tok == "C":
        lig_types.append("C")
        lig_charges.append(0.0)
        lig_radii.append(1.80)
      elif tok == "N":
        is_basic = "CCN" in s or "NCC" in s or "C1CN" in s
        lig_types.append("N_pos" if is_basic else "HD")
        lig_charges.append(0.60 if is_basic else 0.28)
        lig_radii.append(1.55)
      elif tok == "n":
        lig_types.append("NA")
        lig_charges.append(-0.32)
        lig_radii.append(1.55)
      elif tok in ("O", "o", "S", "s"):
        lig_types.append("OA")
        lig_charges.append(-0.38)
        lig_radii.append(1.52)
      elif tok in ("F", "Cl", "Br"):
        lig_types.append("Hal")
        lig_charges.append(-0.15)
        lig_radii.append(1.65)
      else:
        lig_types.append("C")
        lig_charges.append(0.0)
        lig_radii.append(1.75)

    coords -= np.mean(coords, axis=0, keepdims=True)
    mw = float(
        sum(
            35.5
            if t == "Cl"
            else (80.0 if t == "Br" else (19.0 if t == "F" else 13.5))
            for t in tokens
        )
    )
    n_arom = sum(1 for t in tokens if t in ("c", "n", "o", "s"))
    n_polar = sum(1 for t in tokens if t in ("N", "n", "O", "o", "S", "s"))
    n_hal = sum(1 for t in tokens if t in ("F", "Cl", "Br"))
    logp = 0.22 * (num_heavy - n_polar) + 0.55 * n_hal - 0.35 * n_polar + 0.8
    tpsa = 14.5 * n_polar
    hbd = max(1, s.count("N") // 2 + s.count("O") // 3)
    hba = n_polar
    rot_bonds = max(1, (num_heavy - n_arom) // 3)
    num_rings = max(1, sum(1 for ch in "123456" if ch in s))
    qed_val = float(
        np.clip(
            0.84
            - 0.0015 * abs(mw - 380.0)
            - 0.04 * abs(logp - 2.8)
            - 0.002 * abs(tpsa - 68.0),
            0.25,
            0.92,
        )
    )
    sa_score = float(
        np.clip(2.0 + 0.04 * max(0, num_heavy - 20) + 0.15 * max(0, num_rings - 3), 1.5, 6.0)
    )
    max_tanimoto = 0.85 if s in self.seed_scaffolds else 0.45

    return (
        True,
        "OK",
        {
            "canon_smiles": s,
            "mw": mw,
            "logp": logp,
            "tpsa": tpsa,
            "hbd": hbd,
            "hba": hba,
            "rotatable_bonds": rot_bonds,
            "num_rings": num_rings,
            "qed": qed_val,
            "sa_score": sa_score,
            "max_seed_tanimoto": max_tanimoto,
            "conformer_coords": [coords],
            "conf_strains": [1.10],
            "lig_types": lig_types,
            "lig_charges": np.array(lig_charges, dtype=float),
            "lig_radii": np.array(lig_radii, dtype=float),
        },
    )

  def evaluate_smiles(self, smiles: str, n_confs: int = 3) -> dict[str, Any]:
    """Evaluates a candidate SMILES in the 3D receptor pocket under the budget."""
    if smiles in self._cache:
      return dict(self._cache[smiles])

    if self.call_count >= self.max_budget:
      return {
          "valid": False,
          "smiles": smiles,
          "error": f"Oracle evaluation budget ({self.max_budget}) exhausted.",
          "mpo_score": 0.0,
          "used_rdkit": bool(self._has_rdkit),
      }
    self.call_count += 1

    if self._has_rdkit:
      ok, msg, props = self._extract_rdkit_3d_ligand(smiles, n_confs=n_confs)
    else:
      ok, msg, props = self._extract_fallback_3d_ligand(smiles)

    if not ok:
      res = {
          "valid": False,
          "smiles": smiles,
          "error": msg,
          "mpo_score": 0.0,
          "used_rdkit": bool(self._has_rdkit),
      }
      self._cache[smiles] = res
      self.evaluated_history.append(res)
      return dict(res)

    # Optimize 3D SE(3) rigid-body pose across conformers inside the binding pocket
    best_pose: dict[str, Any] | None = None
    best_pose_coords: np.ndarray | None = None
    best_total_obj = 1e9
    best_strain = 1.5

    initial_orientations = [
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, math.pi, 0.0]),
        np.array([0.0, 0.0, math.pi * 0.5]),
        np.array([math.pi * 0.5, 0.0, math.pi]),
    ]

    for conf_xyz, base_strain in zip(
        props["conformer_coords"], props["conf_strains"]
    ):
      for init_rot in initial_orientations:
        x0 = np.concatenate([self.pocket_center, init_rot])

        def _obj(pose_vec: np.ndarray, c_xyz: np.ndarray = conf_xyz) -> float:
          trans = pose_vec[:3]
          rot = _euler_rotation_matrix(pose_vec[3:6])
          placed = (c_xyz @ rot.T) + trans[None, :]
          sc = _score_vina_3d_pose(
              placed,
              props["lig_types"],
              props["lig_charges"],
              props["lig_radii"],
              self.rec_coords,
              self.rec_types,
              self.rec_charges,
              self.rec_radii,
              self.pharm_features,
          )
          return sc["raw_energy_kcal"]

        opt = minimize(
            _obj,
            x0,
            method="Powell",
            options={"maxiter": 45, "ftol": 1e-2},
        )
        trans_opt = opt.x[:3]
        rot_opt = _euler_rotation_matrix(opt.x[3:6])
        placed_opt = (conf_xyz @ rot_opt.T) + trans_opt[None, :]
        pose_eval = _score_vina_3d_pose(
            placed_opt,
            props["lig_types"],
            props["lig_charges"],
            props["lig_radii"],
            self.rec_coords,
            self.rec_types,
            self.rec_charges,
            self.rec_radii,
            self.pharm_features,
        )
        # Include torsional entropy penalty per rotatable bond & pocket burial
        torsion_entropy = 0.22 * props["rotatable_bonds"]
        burial_offset = -1.40 - 0.085 * min(len(props["lig_types"]), 32)
        dg_kcal = (pose_eval["raw_energy_kcal"] + burial_offset) / (
            1.0 + 0.025 * props["rotatable_bonds"]
        ) + 0.15 * torsion_entropy
        strain_total = float(
            base_strain + 0.35 * pose_eval["steric_clash_kcal"]
        )
        combined_obj = dg_kcal + 0.45 * strain_total

        if combined_obj < best_total_obj:
          best_total_obj = combined_obj
          best_pose = dict(pose_eval)
          best_pose["delta_g_kcal"] = float(np.clip(dg_kcal, -13.8, -3.5))
          best_strain = float(np.clip(strain_total, 0.25, 12.0))
          best_pose_coords = placed_opt

    assert best_pose is not None and best_pose_coords is not None
    delta_g = best_pose["delta_g_kcal"]
    strain_kcal = best_strain
    qed_val = props["qed"]
    sa_score = props["sa_score"]
    key_hbonds = best_pose["key_hbonds"]
    salt_bridges = best_pose["salt_bridges"]
    clash_kcal = best_pose["steric_clash_kcal"]

    # Compute Lipinski & ADMET violations
    lipinski_violations = sum([
        1 if props["mw"] > 500.0 or props["mw"] < 240.0 else 0,
        1 if props["logp"] > 5.0 or props["logp"] < -0.5 else 0,
        1 if props["hbd"] > 5 else 0,
        1 if props["hba"] > 10 else 0,
        1 if props["tpsa"] > 120.0 or props["tpsa"] < 32.0 else 0,
    ])

    # 5-Axis Multi-Parameter Optimization (MPO) Score [0, 100]
    # 1. Binding affinity component (up to 42 pts; -6.5 kcal/mol -> 10 pts, -11.5 kcal/mol -> 42 pts)
    s_affinity = float(np.clip(((-delta_g) - 5.2) * 6.6, 0.0, 42.0))
    # 2. Internal 3D strain energy component (up to 16 pts; < 1.2 kcal/mol gets full 16 pts)
    s_strain = float(np.clip(16.0 - 3.6 * max(0.0, strain_kcal - 0.8), 0.0, 16.0))
    # 3. QED drug-likeness component (up to 16 pts)
    s_qed = float(np.clip(20.0 * qed_val, 0.0, 16.0))
    # 4. Ertl Synthetic Accessibility component (up to 14 pts; SA <= 2.4 gets full 14 pts)
    s_sa = float(np.clip(14.0 - 4.2 * max(0.0, sa_score - 2.3), 0.0, 14.0))
    # 5. Pocket-specific 3D hydrogen bonds & salt bridge interactions (up to 12 pts)
    s_inter = float(min(12.0, 3.2 * key_hbonds + 5.6 * salt_bridges))

    pen_lipinski = 6.0 * lipinski_violations
    pen_clash = 4.0 * max(0.0, clash_kcal - 0.5)
    # Novelty penalty if unchanged seed scaffold (Tanimoto > 0.90)
    pen_novelty = (
        18.0
        if props["max_seed_tanimoto"] > 0.90
        else (8.0 if props["max_seed_tanimoto"] < 0.10 else 0.0)
    )

    mpo_score = float(
        np.clip(
            s_affinity
            + s_strain
            + s_qed
            + s_sa
            + s_inter
            - pen_lipinski
            - pen_clash
            - pen_novelty,
            0.0,
            100.0,
        )
    )

    result = {
        "valid": True,
        "smiles": props["canon_smiles"],
        "target_id": self.target_id,
        "mpo_score": round(mpo_score, 4),
        "delta_g_kcal": round(delta_g, 3),
        "strain_kcal": round(strain_kcal, 3),
        "qed": round(qed_val, 4),
        "sa_score": round(sa_score, 3),
        "mw": round(props["mw"], 2),
        "logp": round(props["logp"], 2),
        "tpsa": round(props["tpsa"], 2),
        "hbd": int(props["hbd"]),
        "hba": int(props["hba"]),
        "rotatable_bonds": int(props["rotatable_bonds"]),
        "key_hbonds": int(key_hbonds),
        "salt_bridges": int(salt_bridges),
        "steric_clash_kcal": round(clash_kcal, 3),
        "lipinski_violations": int(lipinski_violations),
        "max_seed_tanimoto": round(props["max_seed_tanimoto"], 4),
        "docked_heavy_xyz": best_pose_coords.round(3).tolist(),
        "lig_types": list(props["lig_types"]),
        "n_conformers": len(props["conformer_coords"]),
        "used_rdkit": bool(self._has_rdkit),
    }
    self._cache[smiles] = result
    self._cache[props["canon_smiles"]] = result
    self.evaluated_history.append(result)
    return dict(result)


_ORACLE_INSTANCES: dict[str, DockingOracle] = {}


def evaluate_molecule_3d(
    smiles: str, pocket_spec: Mapping[str, Any], n_confs: int = 3
) -> dict[str, Any]:
  """Evaluates a candidate SMILES against a 3D pocket specification."""
  target_id = str(pocket_spec["target_id"])
  if target_id not in _ORACLE_INSTANCES:
    _ORACLE_INSTANCES[target_id] = DockingOracle(target_id, max_budget=10000)
  oracle = _ORACLE_INSTANCES[target_id]
  res = oracle.evaluate_smiles(smiles, n_confs=n_confs)
  if not res.get("valid", False):
    return {
        "valid": False,
        "smiles": smiles,
        "reason": res.get("error", "Invalid molecule"),
        "used_rdkit": bool(oracle._has_rdkit),
    }
  anchor_ratio = min(
      1.0, (res.get("key_hbonds", 0) + res.get("salt_bridges", 0)) / 3.0
  )
  return {
      "valid": True,
      "smiles": res["smiles"],
      "molecule_score": round(float(res["mpo_score"]) / 15.0, 4),
      "mpo_score": res["mpo_score"],
      "vina_dg_kcal": res["delta_g_kcal"],
      "qed": res["qed"],
      "sa_score": res["sa_score"],
      "strain_kcal": res["strain_kcal"],
      "mw": res.get("mw", 0.0),
      "logp": res.get("logp", 0.0),
      "tpsa": res.get("tpsa", 0.0),
      "key_hbonds": res.get("key_hbonds", 0),
      "salt_bridges": res.get("salt_bridges", 0),
      "docked_heavy_xyz": res.get("docked_heavy_xyz", []),
      "lig_types": res.get("lig_types", []),
      "anchor_match_ratio": round(anchor_ratio, 3),
      "used_rdkit": bool(oracle._has_rdkit),
  }



def compute_scaffold_diversity(smiles_list: list[str]) -> float:
  """Computes mean pairwise Morgan fingerprint Tanimoto distance."""
  if len(smiles_list) < 2:
    return 0.0
  chem_tuple = _try_import_rdkit()
  Chem, _, _, _, _, rdMolDescriptors, DataStructs = chem_tuple
  if Chem is not None:
    fps = []
    for smi in smiles_list:
      m = Chem.MolFromSmiles(smi)
      if m is not None:
        fps.append(
            rdMolDescriptors.GetMorganFingerprintAsBitVect(m, 2, nBits=1024)
        )
    if len(fps) >= 2:
      dists = []
      for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
          sim = float(DataStructs.TanimotoSimilarity(fps[i], fps[j]))
          dists.append(1.0 - sim)
      return float(sum(dists) / len(dists))

  # Fallback 3-gram Jaccard distance
  grams = [
      {s[k : k + 3] for k in range(max(1, len(s) - 2))} for s in smiles_list
  ]
  dists = []
  for i in range(len(grams)):
    for j in range(i + 1, len(grams)):
      inter = len(grams[i] & grams[j])
      union = max(1, len(grams[i] | grams[j]))
      dists.append(1.0 - inter / union)
  return float(sum(dists) / len(dists))

