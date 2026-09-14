# Realtime occupancy nowcast (website integration)

This document details how to turn **live GOES XRS-B 1-min soft X-rays**, and optionally **live OVRO-LWA 40 / 60 / 80 MHz flux**, into **GOES flare-class occupancy probabilities**.

The scientific notebook that trains and exports the models is `lwa_occupancy_ops.ipynb`. After a successful export it writes one NPZ per trained GOES lag:

```text
models/occupancy_ops_lag{1,2,3,4,5,6}min_v0.3.npz
```

The version string is stored inside each NPZ as `model_version` and must match the filename suffix. Current ship version is **`v0.3`**.

Website code should import [`realtime_nowcast_lookup.py`](realtime_nowcast_lookup.py). That module is **standalone**: it does **not** import `lwa_nowcast`. Dependencies are **NumPy** and **pygam** (for the pickled GAMs). Ship the `.py` file next to the six NPZs.

GOES is required. Radio is optional. If LWA flux is omitted or non-finite, the displayed probability is the **X-ray-only GAM**.

The older radio-only empirical table (`models/lwa_nowcast_probability_*.npz`) is **not** the website product anymore.

---

## What the product is

At issue time \(t\) (UTC), estimate the **occupancy** probability

\[
P\big(\text{GOES XRS-B is at class }\ge \mathrm{M1}/\mathrm{M5}/\mathrm{X1}
\text{ sometime in }(t,\, t+H]\ \big|\ \text{delayed SXR},\ \text{optional radio}\big)
\]

where \(H\) is `horizon_min` minutes (10 min in `v0.3`). Labels use the GOES 1-min XRS-B light curve (`sxr_exceed`), not NOAA catalog peak times.

Two GAM stacks are stored in each NPZ. What the website should display is always `probability`:

| Radio available? | `probability` | `probability_sxr_only` |
|------------------|---------------|------------------------|
| Yes (finite fluence) | Radio + X-ray **blend** | X-ray-only GAM |
| No | X-ray-only GAM | same as `probability` |

The blend uses the radio×SXR GAM when delayed SXR is below the radio gate and rising (`sxr_dlog3 ≥ 0.05`); otherwise it falls back to the X-ray-only GAM. Check `used_radio` to see which path ran.

This is **not** a lookup table. Each lag has a fitted GAM stack.

---

## Required live inputs

### GOES XRS-B (1 min, W m⁻²) — required

A causal 1-min soft X-ray history `(sxr_unix_s, sxr_flux)` ending at the **latest received GOES minute**, which will usually be **behind** \(t\). Keep at least `buffer_requirements(models)["sxr_s"]` seconds (~71 min in `v0.3`: 60 min background + 5 min rise window + longest lag).

Never interpolate GOES into the future. The model only reads SXR at or before \(t - \mathrm{lag}\).

### OVRO-LWA (1 s, SFU) — optional

If LWA is up, pass three parallel 1-second cadence light curves:

| Band | Key |
|------|-----|
| 40 MHz | `40` |
| 60 MHz | `60` |
| 80 MHz | `80` |

Keep a **trailing** buffer of at least `buffer_requirements(models)["radio_s"]` seconds (180 s in `v0.3`: 60 s peak window and 3 min fluence lookback). Samples at times \(> t\) must not be used. Missing / RFI samples: `NaN`.

If radio is down, omit `band_flux_sfu` (or pass `None`). Do **not** pad with zeros. The nowcast still runs on GOES alone.

---

## Lag selection (GOES latency)

Live GOES is delayed. Measure the actual delay

\[
\Delta = t - t_{\mathrm{latest\ GOES\ sample}\le t}
\]

then **ceil** to a trained lag (never use a shorter lag than \(\Delta\)):

| Actual delay | Lag used (`v0.3`) |
|--------------|-------------------|
| 0–60 s | 1 min |
| 61–120 s | 2 min |
| 121–180 s | 3 min |
| 181–240 s | 4 min |
| 241–300 s | 5 min |
| 301–360 s | 6 min |
| > 360 s | 6 min, and `delay_exceeds_train=True` |

`realtime_nowcast_lookup.nowcast` computes \(\Delta\) from the SXR timestamps unless you pass `actual_delay_s`. Radio presence does not change lag selection.

---

## Feature recipe (must match training)

Metadata in each NPZ (do not hard-code after the first ship except as fallbacks):

| Field | `v0.3` value | Role |
|-------|----------------|------|
| `frequencies_mhz` | `(40, 60, 80)` | LWA bands |
| `weights` | `0.5, 0.3, 0.2` | Per-second mix (renormalized if a band is missing) |
| `window_s` | `60` | Trailing radio **peak** window (s) |
| `stat` | `"peak"` | Window statistic |
| `radio_lookback_min` | `3` | Trailing radio **fluence** (min) |
| `lookback_s` | `300` | Delayed SXR rise window (s) |
| `dlog_recent_s` | `180` | Window for `sxr_dlog3` |
| `background_s` | `3600` | Quiet SXR background (s) |
| `horizon_min` | `10` | Occupancy horizon (min) |
| `dlog_min` | `0.05` | Blend rising-SXR gate |
| `delay_select` | `"ceil"` | Lag policy |

**Radio peak** (same as the training table): last `window_s` one-second samples per band → per-second weighted flux → `peak` of valid seconds. Clip to `[1, 2×10³]` SFU. Need `≥ min_valid_frac` valid seconds.

**Radio fluence**: sum of that same weighted 1 s series over the last `radio_lookback_min` minutes (SFU·s). If fluence is non-finite, treat radio as unavailable.

**Delayed SXR** at lag \(L\): only GOES minutes in \([t-L-5\,\mathrm{min},\, t-L]\). From that window: last flux (`sxr_last`), max (`sxr_max_delay`), 5 min log-gradient (`sxr_g5`), last-3-min log rise (`sxr_dlog3`). Background is the median on the 60 min immediately before that rise window.

If delayed SXR features are non-finite, probabilities are NaN — skip the UI update.

---

## Probability output

For each class in `class_names` (`>M1`, `>M5`, `>X1`):

| Field | Meaning |
|-------|---------|
| `result[class]["probability"]` | **Display this.** Blend if `used_radio`, else X-ray-only |
| `result[class]["probability_sxr_only"]` | X-ray-only GAM (always) |
| `result["used_radio"]` | `True` only when radio fluence was finite and the blend path ran |

Display tip: show percent (`100 * probability`). The operating point used in the science notebook is **P = 40%**.

GOES flux thresholds (W m⁻²), aligned with `class_names`:

| Class | Threshold |
|-------|-----------|
| >M1 | \(10^{-5}\) |
| >M5 | \(5\times10^{-5}\) |
| >X1 | \(10^{-4}\) |

---

## NPZ layout (one file per lag)

Each `occupancy_ops_lag{N}min_v0.3.npz` holds pickled pygam models plus provenance:

```text
format                 str        "occupancy_ops_v1"
lag_s                  int        60, 120, …, 360
lookback_s, dlog_recent_s, background_s
predict_stride_s       int        10
horizon_min            float      10
train_start, train_end
dlog_col, dlog_min, require_rising, gate_col
window_s, stat, radio_lookback_min, radio_col
weights, frequencies_mhz
class_names, threshold_names, threshold_values
model_version, created_utc, delay_select
sxr_gam_>M1 / >M5 / >X1     uint8 pickle
radio_gam_>M1 / >M5 / >X1   uint8 pickle
```

Re-export all six files from `lwa_occupancy_ops.ipynb` whenever training knobs change, and bump `MODEL_VERSION`.

---

## Python usage

Ship [`realtime_nowcast_lookup.py`](realtime_nowcast_lookup.py) next to `models/occupancy_ops_lag*min_v0.3.npz`. Do not ship or import `lwa_nowcast.py`.

```python
from realtime_nowcast_lookup import load_models, nowcast, buffer_requirements

models = load_models("models", model_version="v0.3")
print(buffer_requirements(models))
# radio_s=180 (optional), sxr_s=4260 (required),
# lags_min=(1, 2, 3, 4, 5, 6), horizon_min=10

# Radio + X-ray
result = nowcast(
    t_issue,                 # unix seconds or datetime
    sxr_unix,                # GOES 1-min unix seconds
    sxr_flux,                # GOES XRS-B, W m^-2
    {40: flux40, 60: flux60, 80: flux80},   # last ≥180 s at 1 s, SFU
    models,
)

# X-ray only (radio omitted)
result = nowcast(t_issue, sxr_unix, sxr_flux, models=models)

# result["used_radio"]
# result["lag_used_min"], result["actual_delay_s"]
# result[">M1"]["probability"]            # show this
# result[">M1"]["probability_sxr_only"]
```

Quick smoke test (loads the shipped NPZs; synthetic quiet-Sun GOES, with and without radio):

```bash
python realtime_nowcast_lookup.py
```

---

## Operational notes

1. **Cadence.** Training issue cadence is 10 s. Updating the UI every 10 s is enough; faster is fine.
2. **Horizon.** Probabilities are occupancy in the next `horizon_min` minutes — state that on the page.
3. **Primary stream.** Always show `probability`. That is the blend when LWA is available, and the X-ray-only GAM when it is not. `used_radio` tells the page which.
4. **Radio outage.** Omit the band dict. Do not skip the update solely because LWA is missing, as long as GOES history is long enough.
5. **RFI.** Clip live LWA to the same SFU range as training (`[1, 2000]`). Single-band spikes must not enter the weighted mean.
6. **Calibration.** Live LWA and GOES must be on the same physical scales as the training archive (SFU and W m⁻²).
7. **Versioning.** Ship `model_version` (`v0.3`) and `created_utc` with the frontend build. Bump the version when science re-exports.
8. **Delay flag.** If `delay_exceeds_train` is true, GOES is later than 6 min; the 6 min model is used and the page should say so.
9. **Not enough GOES history.** If the GOES buffer is shorter than `buffer_requirements()["sxr_s"]`, skip the update rather than padding with zeros. If radio is present but shorter than `radio_s`, the nowcast falls back to X-ray-only (`used_radio=False`).
