"""
Li et al. generated-output adapter for em-iam-val.

Loads the numpy arrays saved by the Li et al. (Deep-IAM) generation notebooks
and reshapes them into the canonical format expected by the em-iam-val checks:

    test_data  : pd.DataFrame  — index columns [Model, Scenario, Region,
                                  Scenario_Category, Year]
    values     : np.ndarray    — shape (n_rows, n_targets), float64
    targets    : list[str]     — IAMC variable names, length n_targets

The generated outputs have shape (n_scenarios, n_timesteps, n_features).
Since generated scenarios have no Model/Scenario identifiers, synthetic ones
are created: Model = <model_name>, Scenario = gen_00001, gen_00002, ...

Category labels map as:
    0 → C1234  (strong mitigation, warming < 2°C)
    1 → C56    (moderate mitigation)
    2 → C78    (weak / no mitigation)

The 15 features in the generated output correspond to these IAMC variables
(in the order used by the CGAN/RCGAN; VAE uses the same set):
    0  Carbon Sequestration|CCS
    1  Final Energy|Liquids
    2  Primary Energy|Coal
    3  Primary Energy|Gas
    4  Primary Energy|Oil
    5  Secondary Energy|Electricity|Nuclear
    6  Secondary Energy|Electricity|Oil
    7  Secondary Energy|Electricity|Solar
    8  Secondary Energy|Electricity|Wind
    9  Secondary Energy|Electricity|Hydro
    10 Secondary Energy|Electricity|Geothermal
    11 Secondary Energy|Electricity|Gas
    12 Secondary Energy|Electricity|Coal
    13 Secondary Energy|Electricity|Biomass
    14 Secondary Energy|Electricity

The VAE outputs a slightly different shape: (n_scenarios, n_timesteps, n_features)
where n_features may be fewer if the Top-N variant was used. Feature order is
confirmed from the RCGAN/CGAN training data column ordering.

Timesteps cover 2020–2100 in 10-year intervals (9 steps).

Usage
-----
    from li_generated_adapter import load_generated_data

    # Load VAE outputs (saved by VAE-Secondary.ipynb save cell)
    test_data, values, targets = load_generated_data("vae")

    # Load CGAN outputs
    test_data, values, targets = load_generated_data("cgan")

    # Load RCGAN outputs
    test_data, values, targets = load_generated_data("rcgan")

    # Custom path
    test_data, values, targets = load_generated_data(
        "vae",
        data_path="/path/to/gen_data_vae.npy",
        labels_path="/path/to/gen_labels_vae.npy",
    )
"""

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_LI_ROOT = _HERE.parent.parent / "Li-emulation" / "Policy-Generative Model"

# Default file paths per model
_DEFAULT_PATHS: dict[str, tuple[str, str]] = {
    "vae":   ("gen_data_vae.npy",   "gen_labels_vae.npy"),
    "cgan":  ("gen_data_cgan.npy",  "gen_labels_cgan.npy"),
    "rcgan": ("gen_data_rcgan.npy", "gen_labels_rcgan.npy"),
}

# ---------------------------------------------------------------------------
# Feature order
# This matches the column order in the CGAN/RCGAN training CSVs and the VAE.
# Confirmed from notebook variable lists and CSV column headers.
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    # Feature order confirmed from Secondary-data-generate.ipynb,
    # cell 3bd21e93 (Variables list) + cell 96ef0b61 (Kyoto_Gases appended).
    # This is the order used to construct X, and therefore the channel order
    # in Gen_C1234 / Gen_C56 / Gen_C78.
    "Carbon Sequestration|CCS",                 # 0
    "Final Energy|Liquids",                     # 1
    "Primary Energy|Coal",                      # 2
    "Primary Energy|Gas",                       # 3
    "Primary Energy|Oil",                       # 4
    "Secondary Energy|Electricity|Nuclear",     # 5
    "Secondary Energy|Electricity|Oil",         # 6
    "Secondary Energy|Electricity|Solar",       # 7
    "Secondary Energy|Electricity|Wind",        # 8
    "Secondary Energy|Electricity|Hydro",       # 9
    "Secondary Energy|Electricity|Geothermal",  # 10
    "Secondary Energy|Electricity|Gas",         # 11
    "Secondary Energy|Electricity|Coal",        # 12
    "Secondary Energy|Electricity|Biomass",     # 13
    "Secondary Energy|Electricity",             # 14  parent (total)
    "Emissions|Kyoto Gases",                    # 15
]

# Timesteps: 2020–2100 in 10-year steps (9 steps, matching notebook output)
TIMESTEPS: list[int] = list(range(2020, 2110, 10))

# Category label → Scenario_Category string
CATEGORY_MAP: dict[int, str] = {
    0: "C1234",
    1: "C56",
    2: "C78",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_generated_data(
    model: str,
    data_path: str | Path | None = None,
    labels_path: str | Path | None = None,
    verbose: bool = True,
) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """
    Load Li et al. generated scenario outputs into the em-iam-val canonical format.

    Parameters
    ----------
    model : str
        One of "vae", "cgan", "rcgan". Used to find default file paths and
        to set the synthetic Model identifier in the output.
    data_path : path-like, optional
        Path to the .npy file containing Gen_Data
        (shape: n_scenarios × n_timesteps × n_features).
        Defaults to ``Li-emulation/Policy-Generative Model/gen_data_<model>.npy``.
    labels_path : path-like, optional
        Path to the .npy file containing Gen_Labels (shape: n_scenarios,).
        Defaults to ``Li-emulation/Policy-Generative Model/gen_labels_<model>.npy``.
    verbose : bool
        Print load status.

    Returns
    -------
    test_data : pd.DataFrame
        One row per (Model, Scenario, Region, Scenario_Category, Year).
    values : np.ndarray
        Shape (n_rows, n_targets), dtype float64.
    targets : list[str]
        IAMC variable names corresponding to columns of ``values``.
    """
    model_key = model.lower()
    if model_key not in _DEFAULT_PATHS:
        raise ValueError(f"model must be one of {list(_DEFAULT_PATHS)}; got {model!r}")

    default_data, default_labels = _DEFAULT_PATHS[model_key]

    data_file   = Path(data_path)   if data_path   else _LI_ROOT / default_data
    labels_file = Path(labels_path) if labels_path else _LI_ROOT / default_labels

    _log = print if verbose else lambda *a, **k: None
    _log(f"\nLoading {model.upper()} generated outputs")
    _log(f"  data   : {data_file}")
    _log(f"  labels : {labels_file}")

    for p in (data_file, labels_file):
        if not p.exists():
            raise FileNotFoundError(
                f"File not found: {p}\n"
                f"Run the save cell in the {model.upper()} notebook first:\n"
                f"  Li-emulation/Policy-Generative Model/"
                f"{'VAE' if model_key == 'vae' else model.upper()}-Secondary"
                f"{'Ele' if model_key == 'cgan' else ''}.ipynb"
            )

    gen_data   = np.load(data_file,   allow_pickle=False)   # (n, timesteps, features)
    gen_labels = np.load(labels_file, allow_pickle=False)   # (n,)

    _log(f"  gen_data shape  : {gen_data.shape}")
    _log(f"  gen_labels shape: {gen_labels.shape}")

    n_scenarios, n_timesteps, n_features = gen_data.shape

    # Determine which features are present (VAE Top-N variants may have fewer)
    if n_features > len(FEATURE_NAMES):
        raise ValueError(
            f"Generated data has {n_features} features but only "
            f"{len(FEATURE_NAMES)} are mapped in FEATURE_NAMES. "
            f"Update FEATURE_NAMES in li_generated_adapter.py."
        )
    targets = FEATURE_NAMES[:n_features]

    if n_timesteps != len(TIMESTEPS):
        raise ValueError(
            f"Expected {len(TIMESTEPS)} timesteps (2020–2100); "
            f"got {n_timesteps}. Check notebook output."
        )

    # -----------------------------------------------------------------------
    # Build long-format index DataFrame
    # Generated scenarios have no Model/Scenario IDs — synthesise them.
    # -----------------------------------------------------------------------
    model_label = model.upper()   # e.g. "VAE", "CGAN", "RCGAN"
    scenario_ids = [f"gen_{i:05d}" for i in range(n_scenarios)]

    # Expand: one row per (scenario, timestep)
    records = []
    for i in range(n_scenarios):
        cat = CATEGORY_MAP.get(int(gen_labels[i]), f"C{int(gen_labels[i])}")
        for t, year in enumerate(TIMESTEPS):
            records.append({
                "Model":             model_label,
                "Scenario":          scenario_ids[i],
                "Region":            "World",
                "Scenario_Category": cat,
                "Year":              year,
                "_scenario_idx":     i,
                "_timestep_idx":     t,
            })

    index_df = pd.DataFrame(records)

    # Build values array aligned to index_df row order
    # gen_data[i, t, :] → row where scenario=i, timestep=t
    scenario_idx = index_df["_scenario_idx"].to_numpy()
    timestep_idx = index_df["_timestep_idx"].to_numpy()
    values = gen_data[scenario_idx, timestep_idx, :].astype(float)

    test_data = index_df.drop(columns=["_scenario_idx", "_timestep_idx"]).copy()

    _log(
        f"\n  {n_scenarios:,} scenarios  ×  {n_timesteps} timesteps  "
        f"→  {len(test_data):,} rows  |  {len(targets)} variables"
    )
    _log(f"  Categories: { {k: (gen_labels == k).sum() for k in sorted(set(gen_labels.astype(int)))} }")

    return test_data, values, targets


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Summarise Li et al. generated outputs")
    parser.add_argument("model", choices=["vae", "cgan", "rcgan"],
                        help="Which model's outputs to load")
    parser.add_argument("--data_path",   default=None)
    parser.add_argument("--labels_path", default=None)
    args = parser.parse_args()

    td, vals, tgts = load_generated_data(
        args.model,
        data_path=args.data_path,
        labels_path=args.labels_path,
    )
    print(f"\ntest_data shape : {td.shape}")
    print(f"values shape    : {vals.shape}")
    print(f"targets         : {tgts}")
    print(f"\nCategory counts:\n{td['Scenario_Category'].value_counts().to_string()}")
