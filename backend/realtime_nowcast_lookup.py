"""Realtime occupancy nowcast from live GOES XRS and optional OVRO-LWA.

Standalone website entry point for the occupancy ops GAM stack trained in
``lwa_occupancy_ops.ipynb``. Loads ``models/occupancy_ops_lag{1-6}min_v0.3.npz``.

GOES XRS-B is required. OVRO-LWA radio is optional: if omitted (or features
are non-finite), the X-ray-only GAM is used for ``probability``.

Dependencies: NumPy and pygam (for the pickled GAMs). Not ``lwa_nowcast``.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

DEFAULT_MODEL_VERSION = "v0.3"
DEFAULT_LAGS_MIN = (1, 2, 3, 4, 5, 6)
MODEL_DIR = Path("models")

DEFAULT_THRESHOLDS = {">M1": 1e-5, ">M5": 5e-5, ">X1": 1e-4}
DEFAULT_FLUX_CLIP_MIN_SFU = 1.0
DEFAULT_FLUX_CLIP_MAX_SFU = 2.0e3
DEFAULT_MIN_VALID_FRAC = 0.5
DEFAULT_SXR_MIN_VALID = 3
DEFAULT_SXR_MIN_VALID_BACKGROUND = 10
DEFAULT_DELAY_SELECT = "ceil"


def occupancy_ops_model_filename(lag_s: int, model_version: str = DEFAULT_MODEL_VERSION) -> str:
    lag_min = int(round(int(lag_s) / 60.0))
    return f"occupancy_ops_lag{lag_min}min_{model_version}.npz"


def lags_s_from_min(lags_min=DEFAULT_LAGS_MIN) -> tuple[int, ...]:
    return tuple(int(m * 60) for m in lags_min)


def _to_unix(t_issue) -> int:
    if isinstance(t_issue, (int, np.integer)):
        return int(t_issue)
    if isinstance(t_issue, (float, np.floating)):
        return int(t_issue)
    if hasattr(t_issue, "timestamp"):
        return int(t_issue.timestamp())
    raise TypeError(f"t_issue must be unix seconds or a datetime; got {type(t_issue)!r}")


def _iso_utc(unix_s: int) -> str:
    return datetime.fromtimestamp(int(unix_s), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scalar(data, key: str, default=None):
    if key not in data.files:
        return default
    val = data[key]
    return val.item() if getattr(val, "shape", None) == () else val


def load_model(path: Path | str) -> dict:
    """Load one occupancy ops NPZ (SXR GAM + radio GAM + metadata)."""
    path = Path(path)
    with np.load(path, allow_pickle=True) as data:
        fmt = str(data["format"].item()) if "format" in data.files else ""
        if fmt and fmt != "occupancy_ops_v1":
            raise ValueError(f"unsupported occupancy ops format {fmt!r} in {path}")
        class_names = [str(x) for x in data["class_names"].tolist()]
        sxr_gam: dict = {}
        radio_gam: dict = {}
        for name in class_names:
            sxr_gam[name] = pickle.loads(bytes(data[f"sxr_gam_{name}"]))
            radio_gam[name] = pickle.loads(bytes(data[f"radio_gam_{name}"]))
        thresh_names = [str(x) for x in data["threshold_names"].tolist()]
        thresh_vals = np.asarray(data["threshold_values"], dtype=np.float64)
        thresholds = {n: float(v) for n, v in zip(thresh_names, thresh_vals)}
        freqs = [int(x) for x in np.asarray(data["frequencies_mhz"]).tolist()]
        w = np.asarray(data["weights"], dtype=np.float64)
        weights = {f: float(wi) for f, wi in zip(freqs, w)}
        gate = str(_scalar(data, "gate_col", "") or "")
        meta = {
            "lag_s": int(_scalar(data, "lag_s")),
            "lookback_s": int(_scalar(data, "lookback_s", 300)),
            "dlog_recent_s": int(_scalar(data, "dlog_recent_s", 180)),
            "background_s": int(_scalar(data, "background_s", 3600)),
            "horizon_min": float(_scalar(data, "horizon_min", 10.0)),
            "thresholds": thresholds,
            "dlog_col": str(_scalar(data, "dlog_col", "sxr_dlog3")),
            "dlog_min": float(_scalar(data, "dlog_min", 0.05)),
            "require_rising": bool(_scalar(data, "require_rising", True)),
            "gate_col": gate or None,
            "window_s": int(_scalar(data, "window_s", 60)),
            "stat": str(_scalar(data, "stat", "peak")),
            "weights": weights,
            "frequencies_mhz": tuple(freqs),
            "radio_lookback_min": float(_scalar(data, "radio_lookback_min", 3.0)),
            "radio_col": str(_scalar(data, "radio_col", "radio_lookback_fluence")),
            "model_version": str(_scalar(data, "model_version", DEFAULT_MODEL_VERSION)),
            "created_utc": str(_scalar(data, "created_utc", "")),
            "delay_select": str(_scalar(data, "delay_select", DEFAULT_DELAY_SELECT)),
            "class_names": class_names,
            "path": str(path),
        }
    return {"sxr_gam": sxr_gam, "radio_gam": radio_gam, "meta": meta}


def load_models(
    model_dir: Path | str = MODEL_DIR,
    model_version: str = DEFAULT_MODEL_VERSION,
    lags_min=DEFAULT_LAGS_MIN,
) -> dict[int, dict]:
    """Load one occupancy ops NPZ per trained lag. Keys are ``lag_s``."""
    model_dir = Path(model_dir)
    out: dict[int, dict] = {}
    for lag in lags_s_from_min(lags_min):
        path = model_dir / occupancy_ops_model_filename(int(lag), model_version)
        if not path.exists():
            raise FileNotFoundError(path)
        out[int(lag)] = load_model(path)
    return out


def buffer_requirements(models: dict[int, dict]) -> dict[str, float | int]:
    """Trailing history the live feed must keep (seconds)."""
    if not models:
        raise ValueError("models is empty")
    metas = [bundle["meta"] for bundle in models.values()]
    window_s = max(int(m.get("window_s", 60)) for m in metas)
    radio_lookback_s = max(
        int(round(float(m.get("radio_lookback_min", 3.0)) * 60.0)) for m in metas
    )
    lookback_s = max(int(m.get("lookback_s", 300)) for m in metas)
    background_s = max(int(m.get("background_s", 3600)) for m in metas)
    max_lag_s = max(int(m["lag_s"]) for m in metas)
    return {
        "radio_s": int(max(window_s, radio_lookback_s)),
        "radio_window_s": int(window_s),
        "radio_fluence_s": int(radio_lookback_s),
        "sxr_s": int(background_s + lookback_s + max_lag_s),
        "sxr_background_s": int(background_s),
        "sxr_lookback_s": int(lookback_s),
        "max_lag_s": int(max_lag_s),
        "horizon_min": float(metas[0].get("horizon_min", 10.0)),
        "model_version": str(metas[0].get("model_version", DEFAULT_MODEL_VERSION)),
        "created_utc": str(metas[0].get("created_utc", "")),
        "lags_min": tuple(sorted(int(s / 60) for s in models)),
    }


def select_lag(
    actual_delay_s: float,
    trained_lags_s: tuple[int, ...] | list[int],
    *,
    policy: str = DEFAULT_DELAY_SELECT,
) -> dict[str, float | int | bool]:
    """Ceil actual GOES delay to a trained lag (never shorter than the delay)."""
    lags = sorted(int(x) for x in trained_lags_s)
    if not lags:
        raise ValueError("trained_lags_s must be non-empty")
    if not np.isfinite(actual_delay_s) or float(actual_delay_s) < 0:
        raise ValueError(f"actual_delay_s must be finite and >= 0; got {actual_delay_s!r}")
    if str(policy).strip().lower() != "ceil":
        raise ValueError(f"unsupported delay policy {policy!r}; only 'ceil' is implemented")
    delay = float(actual_delay_s)
    delay_exceeds = delay > float(lags[-1])
    chosen = lags[-1]
    for lag in lags:
        if delay <= float(lag):
            chosen = lag
            break
    return {
        "lag_s": int(chosen),
        "actual_delay_s": delay,
        "delay_exceeds_train": bool(delay_exceeds),
    }


def goes_delay_s(t_issue, sxr_unix_s: np.ndarray) -> float:
    """Seconds between issue time and the latest GOES sample at or before it."""
    t = _to_unix(t_issue)
    unix = np.asarray(sxr_unix_s, dtype=np.int64)
    if unix.size == 0:
        return float("nan")
    i = int(np.searchsorted(unix, t, side="right") - 1)
    if i < 0:
        return float("nan")
    return float(t - int(unix[i]))


def _window_vals(
    sxr_unix: np.ndarray,
    sxr_flux: np.ndarray,
    lo: int,
    hi: int,
) -> np.ndarray:
    """Finite positive GOES samples with ``lo <= unix <= hi``."""
    left = int(np.searchsorted(sxr_unix, lo, side="left"))
    right = int(np.searchsorted(sxr_unix, hi, side="right"))
    if right <= left:
        return np.array([], dtype=np.float64)
    chunk = sxr_flux[left:right]
    return chunk[np.isfinite(chunk) & (chunk > 0)]


def delayed_sxr_features(
    t_unix: int,
    sxr_unix_s: np.ndarray,
    sxr_flux: np.ndarray,
    *,
    lag_s: int,
    lookback_s: int,
    dlog_recent_s: int,
    background_s: int,
    min_valid: int = DEFAULT_SXR_MIN_VALID,
    min_valid_background: int = DEFAULT_SXR_MIN_VALID_BACKGROUND,
) -> dict[str, float]:
    """Causal delayed-GOES features at one issue time. Never reads unix > t − lag."""
    unix = np.asarray(sxr_unix_s, dtype=np.int64)
    flux = np.asarray(sxr_flux, dtype=np.float64)
    t = int(t_unix)
    lag = int(lag_s)
    win_lo = t - lag - int(lookback_s)
    win_hi = t - lag
    left = int(np.searchsorted(unix, win_lo, side="left"))
    right = int(np.searchsorted(unix, win_hi, side="right"))
    out = {
        "sxr_last": float("nan"),
        "sxr_max_delay": float("nan"),
        "sxr_g5": float("nan"),
        "sxr_dlog3": float("nan"),
        "sxr_background": float("nan"),
        "n_valid_sxr": float("nan"),
        "n_valid_sxr_background": float("nan"),
    }
    if right <= left:
        return out
    times = unix[left:right]
    vals = flux[left:right]
    good = np.isfinite(vals) & (vals > 0)
    times = times[good]
    vals = vals[good]
    if vals.size < int(min_valid):
        return out
    sxr_last = float(vals[-1])
    sxr_first = float(vals[0])
    out["sxr_last"] = sxr_last
    out["sxr_max_delay"] = float(np.max(vals))
    out["n_valid_sxr"] = float(vals.size)
    if sxr_first > 0:
        out["sxr_g5"] = float(np.log10(sxr_last) - np.log10(sxr_first))
    recent_lo = t - lag - int(dlog_recent_s)
    in_recent = times >= recent_lo
    if np.any(in_recent):
        first3 = float(vals[in_recent][0])
        if first3 > 0:
            out["sxr_dlog3"] = float(np.log10(sxr_last) - np.log10(first3))

    bg_vals = _window_vals(unix, flux, t - lag - int(background_s), t - lag - int(lookback_s))
    if bg_vals.size >= int(min_valid_background):
        out["sxr_background"] = float(np.median(bg_vals))
        out["n_valid_sxr_background"] = float(bg_vals.size)
    return out


def radio_gate_from_background(
    background: float,
    thresholds: dict[str, float] | None = None,
) -> float:
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS
    if not np.isfinite(background):
        return float("nan")
    m1 = float(thresholds[">M1"])
    m5 = float(thresholds[">M5"])
    x1 = float(thresholds[">X1"])
    if background < m1:
        return m1
    if background < m5:
        return m5
    return x1


def _combine_then_window_stat(
    band_windows: list[np.ndarray],
    weights: np.ndarray,
    *,
    stat: str,
    flux_clip_min_sfu: float,
    flux_clip_max_sfu: float,
    min_valid_frac: float,
) -> float:
    if not band_windows:
        return float("nan")
    stack = np.stack(band_windows, axis=0)
    w_exp = np.asarray(weights, dtype=np.float64)[:, None]
    valid = (
        np.isfinite(stack)
        & (stack > 0)
        & (stack >= flux_clip_min_sfu)
        & (stack <= flux_clip_max_sfu)
    )
    masked = np.where(valid, stack, np.nan)
    num = np.nansum(masked * w_exp, axis=0)
    den = np.nansum(np.where(valid, w_exp, 0.0), axis=0)
    combined = np.divide(
        num,
        den,
        out=np.full(stack.shape[1], np.nan, dtype=np.float64),
        where=den > 0,
    )
    any_valid = np.any(valid, axis=0)
    combined = np.where(any_valid & np.isfinite(combined), combined, np.nan)
    roll_valid = (
        any_valid
        & np.isfinite(combined)
        & (combined > 0)
        & (combined >= flux_clip_min_sfu)
        & (combined <= flux_clip_max_sfu)
    )
    if roll_valid.sum() < min_valid_frac * stack.shape[1]:
        return float("nan")
    masked_combined = np.where(roll_valid, combined, np.nan)
    if stat == "peak":
        with np.errstate(all="ignore"):
            feat = float(np.nanmax(masked_combined))
    elif stat == "median":
        with np.errstate(all="ignore"):
            feat = float(np.nanmedian(masked_combined))
    else:
        raise ValueError(f"stat must be 'peak' or 'median', got {stat!r}")
    return feat if np.isfinite(feat) else float("nan")


def _radio_band_windows(
    band_flux_sfu: dict[int, np.ndarray],
    *,
    frequencies_mhz: tuple[int, ...] | list[int],
    weights: dict[int, float] | None,
    n_need: int,
) -> tuple[list[np.ndarray], np.ndarray]:
    freqs = tuple(int(f) for f in frequencies_mhz)
    if weights is None:
        w = np.ones(len(freqs), dtype=np.float64)
    else:
        w = np.array([float(weights.get(f, 0.0)) for f in freqs], dtype=np.float64)
    windows: list[np.ndarray] = []
    active_w: list[float] = []
    for f, wi in zip(freqs, w):
        if wi <= 0 or int(f) not in band_flux_sfu:
            continue
        arr = np.asarray(band_flux_sfu[int(f)], dtype=np.float64)
        if arr.size < n_need:
            continue
        windows.append(arr[-n_need:])
        active_w.append(float(wi))
    return windows, np.asarray(active_w, dtype=np.float64)


def radio_peak_from_bands(
    band_flux_sfu: dict[int, np.ndarray],
    *,
    frequencies_mhz: tuple[int, ...] | list[int],
    weights: dict[int, float] | None,
    window_s: int,
    stat: str = "peak",
    flux_clip_min_sfu: float = DEFAULT_FLUX_CLIP_MIN_SFU,
    flux_clip_max_sfu: float = DEFAULT_FLUX_CLIP_MAX_SFU,
    min_valid_frac: float = DEFAULT_MIN_VALID_FRAC,
) -> float:
    windows, w = _radio_band_windows(
        band_flux_sfu,
        frequencies_mhz=frequencies_mhz,
        weights=weights,
        n_need=int(window_s),
    )
    if not windows:
        return float("nan")
    return _combine_then_window_stat(
        windows,
        w,
        stat=stat,
        flux_clip_min_sfu=flux_clip_min_sfu,
        flux_clip_max_sfu=flux_clip_max_sfu,
        min_valid_frac=min_valid_frac,
    )


def feature_from_bands(band_flux_sfu: dict[int, np.ndarray], model: dict) -> float:
    """Weighted radio peak from trailing 1 s bands (training-matched)."""
    freqs = tuple(int(x) for x in np.asarray(model["frequencies_mhz"]).tolist())
    w = np.asarray(model["weights"], dtype=np.float64)
    weights = {int(f): float(wi) for f, wi in zip(freqs, w)}
    return radio_peak_from_bands(
        band_flux_sfu,
        frequencies_mhz=freqs,
        weights=weights,
        window_s=int(model["window_s"]),
        stat=str(model.get("stat", "peak")),
        flux_clip_min_sfu=float(model.get("flux_clip_min_sfu", DEFAULT_FLUX_CLIP_MIN_SFU)),
        flux_clip_max_sfu=float(model.get("flux_clip_max_sfu", DEFAULT_FLUX_CLIP_MAX_SFU)),
        min_valid_frac=float(model.get("min_valid_frac", DEFAULT_MIN_VALID_FRAC)),
    )


def radio_fluence_from_bands(
    band_flux_sfu: dict[int, np.ndarray],
    *,
    frequencies_mhz: tuple[int, ...] | list[int],
    weights: dict[int, float] | None,
    lookback_s: int,
    flux_clip_min_sfu: float = DEFAULT_FLUX_CLIP_MIN_SFU,
    flux_clip_max_sfu: float = DEFAULT_FLUX_CLIP_MAX_SFU,
    min_valid_frac: float = DEFAULT_MIN_VALID_FRAC,
) -> float:
    windows, w = _radio_band_windows(
        band_flux_sfu,
        frequencies_mhz=frequencies_mhz,
        weights=weights,
        n_need=int(lookback_s),
    )
    if not windows:
        return float("nan")
    stack = np.stack(windows, axis=0)
    ww = w[:, None]
    valid = (
        np.isfinite(stack)
        & (stack >= float(flux_clip_min_sfu))
        & (stack <= float(flux_clip_max_sfu))
    )
    masked = np.where(valid, stack, np.nan)
    with np.errstate(all="ignore"):
        num = np.nansum(masked * ww, axis=0)
        den = np.nansum(np.where(valid, ww, 0.0), axis=0)
        combined = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)
    ok = np.isfinite(combined)
    if ok.sum() < float(min_valid_frac) * int(lookback_s):
        return float("nan")
    return float(np.nansum(combined))


def _has_radio(band_flux_sfu) -> bool:
    if band_flux_sfu is None:
        return False
    if not isinstance(band_flux_sfu, dict) or not band_flux_sfu:
        return False
    return any(np.asarray(v).size > 0 for v in band_flux_sfu.values())


def _predict_sxr_gam(sxr_gam: dict, feat: dict[str, float], class_names: list[str]) -> dict[str, float]:
    fmax = float(feat["sxr_max_delay"])
    g5 = float(feat["sxr_g5"])
    bg = float(feat["sxr_background"])
    ok = np.isfinite(fmax) and fmax > 0 and np.isfinite(g5) and np.isfinite(bg) and bg > 0
    out = {name: float("nan") for name in class_names}
    if not ok:
        return out
    x = np.array([[np.log10(fmax), g5, np.log10(bg)]], dtype=np.float64)
    for name in class_names:
        out[name] = float(sxr_gam[name].predict_proba(x)[0])
    return out


def _predict_radio_gam(
    radio_gam: dict,
    feat: dict[str, float],
    fluence: float,
    class_names: list[str],
) -> dict[str, float]:
    fmax = float(feat["sxr_max_delay"])
    g5 = float(feat["sxr_g5"])
    bg = float(feat["sxr_background"])
    ok = (
        np.isfinite(fmax)
        and fmax > 0
        and np.isfinite(g5)
        and np.isfinite(bg)
        and bg > 0
        and np.isfinite(fluence)
        and fluence > 0
    )
    out = {name: float("nan") for name in class_names}
    if not ok:
        return out
    x = np.array([[np.log10(fmax), g5, np.log10(bg), np.log10(fluence)]], dtype=np.float64)
    for name in class_names:
        out[name] = float(radio_gam[name].predict_proba(x)[0])
    return out


def _blend_one(
    p_sxr: float,
    p_joint: float,
    *,
    sxr_last: float,
    gate: float,
    dlog3: float,
    dlog_min: float,
    require_rising: bool,
) -> float:
    if not np.isfinite(p_sxr):
        return float("nan")
    use_joint = (
        np.isfinite(sxr_last)
        and np.isfinite(gate)
        and sxr_last < gate
        and np.isfinite(p_joint)
    )
    if require_rising:
        use_joint = use_joint and np.isfinite(dlog3) and dlog3 >= float(dlog_min)
    return float(p_joint) if use_joint else float(p_sxr)


def nowcast(
    t_issue,
    sxr_unix_s: np.ndarray,
    sxr_flux: np.ndarray,
    band_flux_sfu: dict[int, np.ndarray] | None = None,
    models: dict[int, dict] | None = None,
    *,
    actual_delay_s: float | None = None,
) -> dict:
    """Score occupancy probabilities at ``t_issue``.

    Parameters
    ----------
    t_issue
        Issue time (unix seconds or ``datetime`` / pandas Timestamp).
    sxr_unix_s, sxr_flux
        GOES XRS-B 1-min history (unix seconds, W m⁻²), strictly causal.
    band_flux_sfu
        Optional trailing 1 s OVRO-LWA flux in SFU, keys ``40``, ``60``, ``80``.
        If omitted or non-finite, ``probability`` is the X-ray-only GAM.
    models
        Output of ``load_models``. Loaded from ``MODEL_DIR`` if omitted.
    actual_delay_s
        Measured GOES latency. If omitted, inferred from the latest SXR
        sample at or before ``t_issue``.
    """
    if models is None:
        models = load_models()
    if not models:
        raise ValueError("models is empty")

    t_unix = _to_unix(t_issue)
    if actual_delay_s is None:
        actual_delay_s = goes_delay_s(t_unix, sxr_unix_s)
    if not np.isfinite(actual_delay_s):
        raise ValueError("could not determine actual GOES delay")

    trained = sorted(int(k) for k in models)
    sel = select_lag(float(actual_delay_s), trained)
    lag_s = int(sel["lag_s"])
    bundle = models[lag_s]
    meta = bundle["meta"]
    class_names = list(meta.get("class_names") or (">M1", ">M5", ">X1"))
    thresholds = meta.get("thresholds") or DEFAULT_THRESHOLDS

    feat = delayed_sxr_features(
        t_unix,
        sxr_unix_s,
        sxr_flux,
        lag_s=lag_s,
        lookback_s=int(meta.get("lookback_s", 300)),
        dlog_recent_s=int(meta.get("dlog_recent_s", 180)),
        background_s=int(meta.get("background_s", 3600)),
    )
    p_sxr = _predict_sxr_gam(bundle["sxr_gam"], feat, class_names)

    feature_sfu = float("nan")
    fluence = float("nan")
    use_radio = _has_radio(band_flux_sfu)
    if use_radio:
        freqs = tuple(int(f) for f in meta.get("frequencies_mhz", (40, 60, 80)))
        weights = meta.get("weights")
        window_s = int(meta.get("window_s", 60))
        radio_lookback_s = int(round(float(meta.get("radio_lookback_min", 3.0)) * 60))
        feature_sfu = radio_peak_from_bands(
            band_flux_sfu,
            frequencies_mhz=freqs,
            weights=weights,
            window_s=window_s,
            stat=str(meta.get("stat", "peak")),
        )
        fluence = radio_fluence_from_bands(
            band_flux_sfu,
            frequencies_mhz=freqs,
            weights=weights,
            lookback_s=radio_lookback_s,
        )
        use_radio = np.isfinite(fluence) and fluence > 0

    p_blend = dict(p_sxr)
    radio_available = bool(use_radio)
    used_radio_blend = False
    if use_radio:
        p_joint = _predict_radio_gam(bundle["radio_gam"], feat, fluence, class_names)
        gate = radio_gate_from_background(feat["sxr_background"], thresholds)
        dlog_min = float(meta.get("dlog_min", 0.05))
        require_rising = bool(meta.get("require_rising", True))
        used_radio_blend = bool(
            np.isfinite(feat["sxr_last"]) and np.isfinite(gate)
            and feat["sxr_last"] < gate
            and (not require_rising or (
                np.isfinite(feat["sxr_dlog3"]) and feat["sxr_dlog3"] >= dlog_min
            ))
            and all(np.isfinite(p_joint[name]) for name in class_names)
        )
        for name in class_names:
            p_blend[name] = _blend_one(
                p_sxr[name],
                p_joint[name],
                sxr_last=feat["sxr_last"],
                gate=gate,
                dlog3=feat["sxr_dlog3"],
                dlog_min=dlog_min,
                require_rising=require_rising,
            )

    out = {
        "time_utc": _iso_utc(t_unix),
        "unix_s": t_unix,
        "horizon_min": float(meta.get("horizon_min", 10.0)),
        "model_version": str(meta.get("model_version", DEFAULT_MODEL_VERSION)),
        "actual_delay_s": float(sel["actual_delay_s"]),
        "lag_used_s": lag_s,
        "lag_used_min": lag_s / 60.0,
        "delay_exceeds_train": bool(sel["delay_exceeds_train"]),
        "radio_available": radio_available,
        "used_radio": used_radio_blend,
        "feature_sfu": float(feature_sfu),
        "radio_lookback_fluence": float(fluence),
        "sxr_last": float(feat["sxr_last"]),
        "probability": dict(p_blend),
        "probability_sxr_only": dict(p_sxr),
    }
    for name in class_names:
        out[name] = {
            "probability": float(p_blend[name]),
            "probability_sxr_only": float(p_sxr[name]),
        }
    return out


if __name__ == "__main__":
    models = load_models()
    req = buffer_requirements(models)
    print(
        f"version={req['model_version']}  created={req['created_utc']}  "
        f"lags={req['lags_min']} min  horizon={req['horizon_min']:g} min"
    )
    print(f"need ≥{req['radio_s']} s of 1-s LWA (optional)  and  ≥{req['sxr_s']} s of 1-min GOES")

    rng = np.random.default_rng(0)
    n_radio = int(req["radio_s"])
    demo_bands = {
        40: rng.uniform(2, 30, size=n_radio),
        60: rng.uniform(2, 40, size=n_radio),
        80: rng.uniform(2, 20, size=n_radio),
    }
    n_sxr = int(req["sxr_s"] // 60) + 2
    t_unix = int(datetime(2026, 4, 23, 17, 0, 0, tzinfo=timezone.utc).timestamp())
    sxr_unix = (t_unix - np.arange(n_sxr, 0, -1) * 60).astype(np.int64)
    sxr_flux = np.full(n_sxr, 3e-6, dtype=np.float64)
    sxr_unix[-1] = t_unix - 180

    for label, bands in (("radio+X-ray", demo_bands), ("X-ray only", None)):
        result = nowcast(t_unix, sxr_unix, sxr_flux, bands, models)
        print(
            f"{label}: delay={result['actual_delay_s']:.0f}s  "
            f"lag={result['lag_used_min']:g} min  used_radio={result['used_radio']}  "
            f"SXR_last={result['sxr_last']:.2e}"
        )
        for name in (">M1", ">M5", ">X1"):
            r = result[name]
            print(
                f"  {name}: P={100 * r['probability']:.2f}%  "
                f"X-ray-only={100 * r['probability_sxr_only']:.2f}%"
            )
