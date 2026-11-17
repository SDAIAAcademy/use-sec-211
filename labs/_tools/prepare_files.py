# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2", "scipy>=1.13", "rasterio>=1.3", "pyproj>=3.6"]
# ///
"""Writes the file pack of USE-SEC-211 into labs/files/ and the trainer's key into labs/solutions/.

  uv run labs/_tools/fetch_public.py   --raw <a folder outside the course> --bbox ... --point ... --tile ...
  uv run labs/_tools/prepare_files.py  --raw <the same folder>

Two kinds of files come out of it:

1. Extracts of public data (read from --raw, never committed):
   - Sentinel-2 L2A over the window that fetch_public.py read (its window.json; the course
     writes no coordinate of it anywhere) (Copernicus Sentinel data 2021, 2023 and 2024): the scene list with the clear share of the
     window, and the mean red and near-infrared reflectance of each plot on each date. Plot
     outlines are found here from the imagery; only an id and an area leave this script, never a
     coordinate.
   - ESA WorldCover 10 m 2021 v200 (CC BY 4.0) at 200 sampled points, with a reference class
     from the 2021 Sentinel-2 series at the same point.
   - ERA5 daily weather and past ET0 forecasts at one point (Open-Meteo, CC BY 4.0).
2. Synthetic files of Al-Suqya Water and Agriculture Authority (case_texts.py): the plot
   declarations, the farm, the zone meters, the leak alerts, the use cases. Seed 211.

The same raw files and the same seed give the same bytes on every run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import io
import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from rasterio.transform import Affine
from rasterio.windows import from_bounds
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_texts as T  # noqa: E402
import water as Wt  # noqa: E402

LABS = Path(__file__).resolve().parent.parent
FILES = LABS / "files"
SOL = LABS / "solutions"
SEED = 211
KEY: dict = {}

BBOX: tuple = ()          # read from <raw>/window.json in main()
TILE: Affine = Affine.identity()  # the 10 m grid of the Sentinel-2 tile, from the same file
UTM = ""                  # the tile's UTM zone as an EPSG code
CLEAR_SCL = (4, 5, 6, 7)       # vegetation, not vegetated, water, unclassified
CLOUD_SCL = (3, 8, 9, 10)      # cloud shadow, cloud medium and high, cirrus
CROPS = ["قمح", "برسيم", "علف صيفي", "بور"]


# ---------------------------------------------------------------- helpers

def write_csv(path: Path, header: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    path.write_bytes(("﻿" + buf.getvalue()).encode("utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def r3(x):
    return None if x is None else round(float(x), 3)


def ndvi(red, nir):
    return (nir - red) / (nir + red)


# ---------------------------------------------------------------- imagery

def utm_window():
    """The pixel window that fetch_public.py read, on the 10 m grid of its Sentinel-2 tile."""
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
    x0, y0 = t.transform(BBOX[0], BBOX[1])
    x1, y1 = t.transform(BBOX[2], BBOX[3])
    w = from_bounds(x0, y0, x1, y1, TILE).round_offsets().round_lengths()
    return w, t


def load_period(raw: Path, name: str):
    meta = json.loads((raw / name / "scenes.json").read_text())
    scenes, red, nir, ok, valid = [], [], [], [], []
    for m in meta:
        f = raw / name / f"{m['id']}.npz"
        if "skipped" in m or not f.exists():
            continue
        z = np.load(f)
        dn_r, dn_n = z["red"].astype(np.float32), z["nir"].astype(np.float32)
        # baseline 04.00 and later adds 1000 to every value; Earth Search removes it when
        # earthsearch:boa_offset_applied is true
        shift = 1000.0 if (str(m.get("baseline") or "00") >= "04" and not m.get("boa_offset_applied")) else 0.0
        v = z["red"] > 0
        red.append(np.clip((dn_r - shift) * 1e-4, 0.001, None))
        nir.append(np.clip((dn_n - shift) * 1e-4, 0.001, None))
        ok.append(np.isin(z["scl"], CLEAR_SCL) & v)
        valid.append(v)
        scenes.append(m)
    return scenes, np.array(red), np.array(nir), np.array(ok), np.array(valid)


def find_circles(mx: np.ndarray, threshold: float, min_px: int):
    lab, _ = ndi.label(mx > threshold)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab)):
        m = lab[sl] == i + 1
        a = int(m.sum())
        if a < min_px:
            continue
        h, w = m.shape
        if 0.65 < a / (h * w) < 0.85 and abs(h - w) / max(h, w) < 0.15:
            cy, cx = ndi.center_of_mass(lab == i + 1)
            out.append((float(cy), float(cx), math.sqrt(a / math.pi)))
    return out


def classify(series: list[tuple[str, float]]) -> dict:
    """The rules of crop_rules.txt on one plot's clear NDVI values (date, ndvi)."""
    def vals(months):
        return [v for d, v in series if d[5:7] in months]
    win = vals({"12", "01", "02", "03"})
    summ = vals({"06", "07", "08"})
    summ_max = vals({"06", "07", "08", "09"})
    f = {"winter_max": max(win), "summer_mean": st.mean(summ), "summer_max": max(summ_max),
         "season_max": max(v for _, v in series)}
    f = {k: round(v, 3) for k, v in f.items()}
    f["agrees"] = {
        "قمح": f["winter_max"] >= 0.50 and f["summer_mean"] < 0.30,
        "برسيم": f["winter_max"] >= 0.40 and f["summer_mean"] >= 0.40,
        "علف صيفي": f["winter_max"] < 0.35 and f["summer_max"] >= 0.50,
        "بور": f["season_max"] < 0.30,
    }
    return f


def imagery(raw: Path):
    scenes, red, nir, ok, valid = load_period(raw, "s2_2324")
    dates = [m["date"] for m in scenes]
    nd = ndvi(red, nir)
    # 1.2: the scene list
    rows = []
    clear_share = []
    for m, o, v in zip(scenes, ok, valid):
        share = float(o[v].mean() * 100)
        clear_share.append(share)
        rows.append([m["date"], m["id"][:3], round(float(m["tile_cloud"]), 1), round(share, 1)])
    write_csv(FILES / "imagery" / "scenes.csv",
              ["date", "satellite", "tile_cloud_pct", "window_clear_pct"], rows)
    by_month = defaultdict(lambda: [0, 0])
    for d, s in zip(dates, clear_share):
        by_month[d[:7]][0] += 1
        by_month[d[:7]][1] += s >= 90
    misleading = sum(1 for r in rows if r[2] < 20 and r[3] < 90)
    clear_dates = [dt.date.fromisoformat(d) for d, s in zip(dates, clear_share) if s >= 90]
    winter = [d for d in clear_dates if dt.date(2023, 11, 1) <= d <= dt.date(2024, 2, 29)]
    gaps = [(b - a).days for a, b in zip(winter, winter[1:])]
    KEY["1.2"] = {"scenes": len(rows), "clear_scenes": len(clear_dates),
                  "clear_by_month": {k: v[1] for k, v in sorted(by_month.items())},
                  "scenes_by_month": {k: v[0] for k, v in sorted(by_month.items())},
                  "low_tile_cloud_but_not_clear": misleading,
                  "longest_winter_gap_days": max(gaps)}
    sizes = []
    for name, ha in T.PLOT_SIZES:
        side = math.sqrt(ha * 10000)
        row = [name, ha]
        for res in (10, 30, 250):
            row.append(round(ha * 10000 / res ** 2, 1))
        for res in (10, 30, 250):
            row.append(max(0, math.floor(side / res) - 2) ** 2)
        sizes.append(row)
    write_csv(FILES / "imagery" / "plot_sizes.csv", ["plot_type", "area_ha"], [r[:2] for r in sizes])
    KEY["1.2"]["pixels"] = {r[0]: {"all_10": r[2], "all_30": r[3], "all_250": r[4],
                                   "pure_10": r[5], "pure_30": r[6], "pure_250": r[7]} for r in sizes}

    # the plots: circles green in 2023-24, and circles green in 2021 that stayed bare (fallow)
    mx = np.where(ok, nd, -1).max(0)
    circles = find_circles(mx, 0.35, 150)
    s21, red21, nir21, ok21, valid21 = load_period(raw, "s2_2021")
    nd21 = ndvi(red21, nir21)
    mx21 = np.where(ok21, nd21, -1).max(0)
    for c in find_circles(mx21, 0.35, 800):
        if all(math.hypot(c[0] - o[0], c[1] - o[1]) > o[2] for o in circles):
            circles.append(c)
    yy, xx = np.mgrid[: mx.shape[0], : mx.shape[1]]
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(circles))
    plots = []
    for k, idx in enumerate(order):
        cy, cx, r = circles[idx]
        pm = ((yy - cy) ** 2 + (xx - cx) ** 2) <= (r - 1) ** 2
        area = round(float(pm.sum()) / 100, 1)
        ser, full = [], []
        for t, d in enumerate(dates):
            o = ok[t][pm]
            frac = float(o.mean())
            if frac == 0:
                full.append((d, frac, None, None))
                continue
            rr, nn = float(red[t][pm][o].mean()), float(nir[t][pm][o].mean())
            rr, nn = r3(rr), r3(nn)
            full.append((d, frac, rr, nn))
            if frac >= 0.9:
                ser.append((d, round(ndvi(rr, nn), 3)))
        plots.append({"id": f"P{k + 1:02d}", "area": area, "full": full, "series": ser,
                      "f": classify(ser)})
    observed = {}
    for p in plots:
        agrees = [c for c, a in p["f"]["agrees"].items() if a]
        observed[p["id"]] = agrees[0] if len(agrees) == 1 else ("غير واضح" if not agrees else "+".join(agrees))
    return plots, observed, dates, (s21, red21, nir21, ok21, valid21, nd21)


def declarations(plots, observed):
    """Declared crop per plot: the observed pattern, except planted mismatches (seed 211)."""
    rng = np.random.default_rng(SEED + 1)
    large = [p for p in plots if p["area"] >= 6]
    small = [p for p in plots if p["area"] < 6]
    decl, truth = {}, {}
    by = defaultdict(list)
    for p in large:
        by[observed[p["id"]]].append(p["id"])
    plan = {"برسيم": ("قمح", 3), "بور": ("قمح", 2), "قمح": ("بور", 1), "علف صيفي": ("قمح", 1)}
    planted = {}
    for obs, (said, n) in plan.items():
        ids = sorted(by.get(obs, []))
        for pid in [ids[i] for i in sorted(rng.choice(len(ids), size=min(n, len(ids)), replace=False))] if ids else []:
            planted[pid] = said
    for p in plots:
        o = observed[p["id"]]
        if p["id"] in planted:
            decl[p["id"]] = planted[p["id"]]
            truth[p["id"]] = ("زُرع غير المصرّح به", o)
        elif o in CROPS:
            decl[p["id"]] = o
            truth[p["id"]] = ("التصريح صحيح", o)
        else:
            # no single rule fits: the farmer declared the main crop; the field visit tells
            f = p["f"]
            main = "برسيم" if f["summer_mean"] >= 0.30 else "قمح"
            decl[p["id"]] = main
            truth[p["id"]] = ("التصريح صحيح، والنمط غير معتاد", main)
    return decl, truth, planted


def write_plots(plots, observed, dates):
    decl, truth, planted = declarations(plots, observed)
    rows, nd_rows = [], []
    for p in plots:
        for d, frac, rr, nn in p["full"]:
            rows.append([p["id"], d, d[5:7], round(frac, 2), r3(rr), r3(nn)])
            v = "" if (rr is None or frac < 0.9) else round(ndvi(rr, nn), 3)
            nd_rows.append([p["id"], d, d[5:7], v])
    write_csv(FILES / "imagery" / "plots_reflectance.csv",
              ["plot_id", "date", "month", "clear_fraction", "red", "nir"], rows)
    write_csv(FILES / "start" / "plots_ndvi.csv", ["plot_id", "date", "month", "ndvi"], nd_rows)
    farmer = {p["id"]: f"F-{1000 + 37 * i:04d}" for i, p in enumerate(sorted(plots, key=lambda q: q["id"]))}
    write_csv(FILES / "declarations.csv", ["plot_id", "area_ha", "declared_crop", "farmer_code"],
              [[p["id"], p["area"], decl[p["id"]], farmer[p["id"]]] for p in sorted(plots, key=lambda q: q["id"])])
    flags = []
    for p in sorted(plots, key=lambda q: q["id"]):
        f = p["f"]
        if not f["agrees"][decl[p["id"]]]:
            flags.append(p["id"])
    KEY["1.4"] = {"plots": len(plots), "flagged": flags,
                  "features": {p["id"]: {k: v for k, v in p["f"].items() if k != "agrees"} for p in plots},
                  "declared": decl, "observed": observed}
    KEY["field_checks"] = {pid: {"finding": truth[pid][0], "crop_found": truth[pid][1]} for pid in flags}
    KEY["planted"] = planted
    pool = [p for p in sorted(plots, key=lambda q: q["id"]) if p["id"] not in flags and p["area"] >= 6]
    def clean(p):  # textbook examples of each pattern for lab 1.3
        early = [v for d, v in p["series"] if d[5:7] in ("10", "11")]
        peak = max(p["series"], key=lambda x: x[1])[0][5:7]
        o = observed[p["id"]]
        if o == "قمح":
            return st.mean(early) < 0.25 and peak in ("01", "02", "03")
        if o == "برسيم":
            return p["f"]["summer_mean"] >= 0.5 and min(v for _, v in p["series"]) > 0.2
        return True
    six = []
    for want in ("قمح", "برسيم", "علف صيفي", "بور", "قمح", "برسيم", "قمح", "برسيم"):
        cand = [p["id"] for p in pool if observed[p["id"]] == want and p["id"] not in six and clean(p)]
        if cand and len(six) < 6:
            six.append(cand[0])
    KEY["1.3"] = {"plots": sorted(six), "patterns": {pid: observed[pid] for pid in six}}
    small = [p["id"] for p in plots if p["area"] < 6]
    large = [p["id"] for p in plots if p["area"] >= 6]
    KEY["1.5"] = {"small": len(small), "large": len(large),
                  "small_flagged": sum(1 for x in flags if x in small),
                  "large_flagged": sum(1 for x in flags if x in large)}
    write_csv(FILES / "start" / "flags.csv", ["plot_id", "area_ha", "declared_crop", "winter_max",
                                              "summer_mean", "summer_max", "season_max"],
              [[pid, next(p["area"] for p in plots if p["id"] == pid), decl[pid],
                *[KEY["1.4"]["features"][pid][k] for k in ("winter_max", "summer_mean", "summer_max", "season_max")]]
               for pid in flags])
    return decl


def landcover(raw: Path, period21):
    s21, red21, nir21, ok21, valid21, nd21 = period21
    wc = np.load(raw / "worldcover_2021.npy")
    w, tr = utm_window()
    # WorldCover is on a 1/12000 degree grid; its window starts at the box's north-west corner
    res = 1 / 12000
    lon0 = math.floor(BBOX[0] / res) * res
    lat0 = math.ceil(BBOX[3] / res) * res
    names = {40: "مزروعة", 60: "جرداء", 50: "مبنية", 30: "عشبية", 10: "شجرية"}
    quota = {40: 60, 60: 60, 50: 30, 30: 30, 10: 20}
    rng = np.random.default_rng(SEED + 2)
    built = T_BUILT
    pts = []
    for cls, n in quota.items():
        ii, jj = np.nonzero(wc == cls)
        pick = rng.permutation(len(ii))
        got = 0
        for k in pick:
            i, j = int(ii[k]), int(jj[k])
            lon = lon0 + (j + 0.5) * res
            lat = lat0 - (i + 0.5) * res
            x, y = tr.transform(lon, lat)
            col = int((x - (TILE.c + w.col_off * 10)) // 10)
            row = int(((TILE.f - w.row_off * 10) - y) // 10)
            if not (0 <= row < nd21.shape[1] and 0 <= col < nd21.shape[2]):
                continue
            if any(abs(row - p[2]) < 5 and abs(col - p[3]) < 5 for p in pts):
                continue
            vals = nd21[:, row, col][ok21[:, row, col]]
            p10, p90 = float(np.percentile(vals, 10)), float(np.percentile(vals, 90))
            if p10 >= 0.20 and p90 < 0.65:
                ref = "شجرية"
            elif p90 >= 0.40:
                ref = "مزروعة"
            elif any(r0 <= row <= r1 and c0 <= col <= c1 for r0, c0, r1, c1 in built):
                ref = "مبنية"
            else:
                ref = "جرداء"
            pts.append((names[cls], ref, row, col))
            got += 1
            if got == n:
                break
    order = rng.permutation(len(pts))
    rows = [[f"N{k + 1:03d}", pts[i][0], pts[i][1]] for k, i in enumerate(order)]
    write_csv(FILES / "landcover" / "points.csv", ["point_id", "map_class", "reference_class"], rows)
    classes = ["مزروعة", "جرداء", "مبنية", "عشبية", "شجرية"]
    cm = {m: {r: 0 for r in classes} for m in classes}
    for _, m, r in rows:
        cm[m][r] += 1
    total = len(rows)
    correct = sum(cm[c][c] for c in classes)
    users = {c: round(cm[c][c] / sum(cm[c].values()), 3) for c in classes}
    prods = {c: (round(cm[c][c] / s, 3) if (s := sum(cm[m][c] for m in classes)) else None) for c in classes}
    KEY["1.6"] = {"points": total, "matrix": cm, "correct": correct}
    KEY["1.7"] = {"overall": round(correct / total, 3), "users": users, "producers": prods}
    write_csv(FILES / "start" / "confusion_matrix.csv", ["map_class \\ reference_class", *classes],
              [[m, *[cm[m][r] for r in classes]] for m in classes])
    # 1.7 permitted uses, decided by the stated accuracy need
    def meets(use):
        _, _, cls, need, _ = use
        u, p = users.get(cls), prods.get(cls)
        if "المستخدم والمنتج" in need:
            return u >= 0.85 and (p or 0) >= 0.85
        if "المستخدم" in need:
            return u >= 0.70
        if "المنتج" in need:
            return (p or 0) >= 0.80
        return False
    verdict = {}
    for use in T.PROPOSED_USES:
        if use[4] == "قرار فردي":
            verdict[use[0]] = "غير مسموح"
        else:
            verdict[use[0]] = "مسموح" if meets(use) else "غير مسموح"
    KEY["1.7"]["uses"] = verdict
    write_csv(FILES / "landcover" / "proposed_uses.csv", ["use_id", "use", "class", "accuracy_needed", "kind"],
              [list(u) for u in T.PROPOSED_USES])
    # 1.8 interval half-widths and points needed
    n_map = {c: sum(cm[c].values()) for c in classes}
    half = {c: round(1.96 * math.sqrt(users[c] * (1 - users[c]) / n_map[c]), 3) for c in classes}
    need = {c: math.ceil(1.96 ** 2 * users[c] * (1 - users[c]) / 0.10 ** 2) for c in classes}
    extra = {c: max(0, need[c] - n_map[c]) for c in classes}
    KEY["1.8"] = {"n": n_map, "half_width": half, "needed": need, "extra": extra}
    write_csv(FILES / "start" / "accuracy_table.csv", ["class", "points_in_class", "users_accuracy", "producers_accuracy"],
              [[c, n_map[c], users[c], prods[c] if prods[c] is not None else ""] for c in classes])


# hand-drawn settlement boxes on the 10 m window (row0, col0, row1, col1), from the 2021 red band
T_BUILT: list[tuple[int, int, int, int]] = [
    (0, 300, 45, 800), (10, 215, 55, 300), (140, 165, 180, 235), (200, 195, 225, 240), (205, 0, 240, 30)]


# ---------------------------------------------------------------- weather and the farm

def weather(raw: Path):
    e = json.loads((raw / "weather" / "era5_daily_2000_2024.json").read_text())["daily"]
    pr = json.loads((raw / "weather" / "previous_runs_2024.json").read_text())["hourly"]
    idx = {d: i for i, d in enumerate(e["time"])}
    fd = defaultdict(lambda: defaultdict(float))
    for i, t in enumerate(pr["time"]):
        for k in (1, 2, 3):
            fd[t[:10]][f"f{k}"] += pr[f"et0_fao_evapotranspiration_previous_day{k}"][i]
    clim = defaultdict(list)
    for i, d in enumerate(e["time"]):
        if d < "2024":
            clim[d[5:]].append(e["et0_fao_evapotranspiration"][i])

    def climd(d):
        base = dt.date(2000, int(d[5:7]), int(d[8:10]))  # a leap year, so 29 February exists
        vals = []
        for k in range(-7, 8):
            vals += clim[(base + dt.timedelta(days=k)).strftime("%m-%d")]
        return round(st.mean(vals), 2)

    days = [d for d in e["time"] if "2024-02-01" <= d <= "2024-10-31"]
    rows = []
    for d in days:
        rows.append([d, d[5:7], round(e["et0_fao_evapotranspiration"][idx[d]], 2),
                     round(fd[d]["f1"], 2), round(fd[d]["f2"], 2), round(fd[d]["f3"], 2), climd(d)])
    write_csv(FILES / "weather" / "et0_forecasts_2024.csv",
              ["date", "month", "era5_et0", "forecast_lead1", "forecast_lead2", "forecast_lead3", "climatology_et0"], rows)

    def mae(col, months=None):
        sel = [r for r in rows if months is None or r[1] in months]
        return round(st.mean(abs(r[col] - r[2]) for r in sel), 3)
    k = {"mae_lead1": mae(3), "mae_lead2": mae(4), "mae_lead3": mae(5), "mae_clim": mae(6),
         "bias_lead1": round(st.mean(r[3] - r[2] for r in rows), 3)}
    for lead in (1, 2, 3):
        k[f"skill_lead{lead}"] = round(1 - k[f"mae_lead{lead}"] / k["mae_clim"], 3)
    for name, months in (("spring", {"03", "04", "05"}), ("summer", {"06", "07", "08"})):
        k[f"skill_lead1_{name}"] = round(1 - mae(3, months) / mae(6, months), 3)
    KEY["2.1"] = k

    # the farm season
    season = [r for r in rows if "2024-03-01" <= r[0] <= "2024-10-31"]
    et0 = [r[2] for r in season]
    rain = [round(e["precipitation_sum"][idx[r[0]]], 1) for r in season]
    month_clim = defaultdict(list)
    for r in season:
        month_clim[r[1]].append(r[6])
    kc, taw = 0.70, 90.0
    raw_ = 0.65 * taw
    fixed = []
    for i, r in enumerate(season):
        depth = round(st.mean(month_clim[r[1]]) * kc * 3 * T.FIXED_MARGIN[r[1]] * 2) / 2
        fixed.append(depth if i % 3 == 0 else 0.0)
    res = Wt.balance(et0, rain, fixed, kc, taw, raw_)
    rng = np.random.default_rng(SEED + 3)
    drift_start = "2024-07-10"
    probe = []
    for i, r in enumerate(season):
        theta = 0.24 - res["dr"][i] * (0.0167 / 10)
        theta += rng.normal(0, 0.003)
        if r[0] >= drift_start:
            theta += 0.0006 * (dt.date.fromisoformat(r[0]) - dt.date.fromisoformat(drift_start)).days
        probe.append(round(theta, 3))
    write_csv(FILES / "farm" / "season_2024.csv",
              ["date", "month", "et0_mm", "rain_mm", "fixed_irrigation_mm", "probe_theta"],
              [[r[0], r[1], r[2], p, f, pb] for r, p, f, pb in zip(season, rain, fixed, probe)])
    fsum = Wt.summary(res, fixed)
    model_theta = [0.24 - d * (0.0167 / 10) for d in res["dr"]]
    diff = [pb - m for pb, m in zip(probe, model_theta)]
    first = None
    for i in range(len(diff) - 6):
        if all(abs(x) > 0.02 for x in diff[i:i + 7]):
            first = season[i][0]
            break
    KEY["2.2"] = {**fsum, "water_m3": round(fsum["water_mm"] * 400), "taw": taw, "raw": raw_,
                  "probe_gap_from": first, "drift_planted_from": drift_start,
                  "stress_dates": [season[i][0] for i, v in enumerate(res["ks"]) if v < 1][:5]}
    # forecast-driven, 30 mm per irrigation
    n = len(season)
    f1 = [r[3] for r in season]
    f2 = [r[4] for r in season]
    f3 = [r[5] for r in season]
    look = [round(f1[t] + (f2[t + 1] if t + 1 < n else f1[t]) + (f3[t + 2] if t + 2 < n else f1[t]), 2) for t in range(n)]
    write_csv(FILES / "start" / "season_fixed.csv",
              ["date", "et0_mm", "rain_mm", "fixed_irrigation_mm", "fixed_depletion_mm", "fixed_drainage_mm", "fixed_stress",
               "forecast_et0_next3"],
              [[season[t][0], et0[t], rain[t], fixed[t], round(res["dr"][t], 1), round(res["drain"][t], 1), int(res["ks"][t] < 1), look[t]]
               for t in range(n)])
    rf = Wt.forecast_schedule(et0, rain, f1, f2, f3, kc, taw, raw_, depth=30.0, look=look)
    s = Wt.summary(rf)
    KEY["2.3"] = {"fixed": fsum, "forecast": s, "depth": 30.0,
                  "fixed_drain_file": round(sum(round(v, 1) for v in res["drain"]), 1),
                  "saving_mm": round(fsum["water_mm"] - s["water_mm"], 1),
                  "saving_m3": round((fsum["water_mm"] - s["water_mm"]) * 400),
                  "saving_pct": round((1 - s["water_mm"] / fsum["water_mm"]) * 100, 1)}
    # 2.4 scenarios: three soils, three forecasts
    clim = [r[6] for r in season]
    sc_rows, sc = [], {}
    for soil, t_ in (("رملية", 60.0), ("رملية طميية", 90.0), ("طميية", 120.0)):
        r_ = 0.65 * t_
        fx = Wt.summary(Wt.balance(et0, rain, fixed, kc, t_, r_), fixed)
        for fname, (a, b, c) in (("التنبؤ الفعلي", (f1, f2, f3)), ("تنبؤ كامل", (et0, et0, et0)),
                                 ("المناخ المعتاد", (clim, clim, clim))):
            fc = Wt.summary(Wt.forecast_schedule(et0, rain, a, b, c, kc, t_, r_, depth=30.0))
            sc_rows.append([soil, t_, fname, fx["water_mm"], fx["stress_days"], fc["water_mm"], fc["stress_days"]])
            sc[f"{soil}|{fname}"] = {"saving_pct": round((1 - fc["water_mm"] / fx["water_mm"]) * 100, 1),
                                     "stress_fixed": fx["stress_days"], "stress_forecast": fc["stress_days"]}
    write_csv(FILES / "start" / "scenarios.csv",
              ["soil", "taw_mm", "forecast_used", "fixed_water_mm", "fixed_stress_days",
               "forecast_water_mm", "forecast_stress_days"], sc_rows)
    pct = [v["saving_pct"] for v in sc.values()]
    KEY["2.4"] = {"scenarios": sc, "saving_min": min(pct), "saving_max": max(pct)}


# ---------------------------------------------------------------- meters

def meters():
    rng = np.random.default_rng(SEED + 4)
    start = dt.date(2024, 8, 1)
    nights = 56
    profile = [0.35, 0.25, 0.2, 0.2, 0.25, 0.5, 0.9, 1.2, 1.3, 1.2, 1.1, 1.1,
               1.2, 1.3, 1.2, 1.1, 1.1, 1.2, 1.4, 1.5, 1.4, 1.2, 0.9, 0.6]
    rows = []
    base_leak = {}
    for zid, name, hh, farms in T.ZONES:
        base_leak[zid] = round(float(rng.uniform(1.5, 4.0)), 2)
        per_hh = 0.025
        for k in range(nights):
            day = start + dt.timedelta(days=k)
            for h in range(24):
                q = hh * per_hh * profile[h] + base_leak[zid] + farms * 0.05 + rng.normal(0, 0.25)
                ds = day.isoformat()
                if zid == "Z03" and ds >= "2024-08-22":
                    q += 4.0
                if zid == "Z07" and ds >= "2024-09-01":
                    q += 0.25 * (day - dt.date(2024, 9, 1)).days
                if zid == "Z05" and ds >= "2024-08-29" and h <= 5:
                    q += 5.0
                if zid == "Z02" and ds == "2024-08-15" and h <= 4:
                    q += 6.0
                if zid == "Z10" and "2024-09-15" <= ds <= "2024-09-17":
                    q += 25.0
                if zid == "Z09" and "2024-09-08" <= ds <= "2024-09-11":
                    q = 0.0
                rows.append([zid, ds, h, round(max(q, 0.0), 2)])
    write_csv(FILES / "meters" / "zone_hourly.csv", ["zone", "date", "hour", "flow_m3h"], rows)
    write_csv(FILES / "meters" / "zones.csv", ["zone", "name", "households", "farms"],
              [list(z) for z in T.ZONES])
    # key: minimum night flow (hours 1 to 4), baseline the median of the first 14 nights
    mnf = defaultdict(dict)
    for z, d, h, q in rows:
        if 1 <= h <= 4:
            mnf[z][d] = min(mnf[z].get(d, 1e9), q)
    out = {}
    for z, series in mnf.items():
        ds = sorted(series)
        base = st.median(series[d] for d in ds[:14])
        lim = base + max(2.0, 0.3 * base)
        flag = None
        for i in range(len(ds) - 2):
            if all(series[ds[i + j]] > lim for j in range(3)):
                flag = ds[i]
                break
        zero = [d for d in ds if series[d] == 0]
        out[z] = {"baseline": round(base, 2), "limit": round(lim, 2), "first_flag": flag,
                  "zero_nights": zero[:1] + zero[-1:] if zero else []}
    KEY["2.5"] = out

    # 2.6: a year of alerts at eight thresholds, 60 zones, against the repairs log
    leaks = []
    for i in range(48):
        z = f"R{int(rng.integers(1, 61)):02d}"
        day = int(rng.integers(0, 330))
        flow = round(float(rng.gamma(3.0, 1.0)), 1)
        leaks.append({"id": f"L{i + 1:02d}", "zone": z, "start_day": day, "flow": flow})
    write_csv(FILES / "meters" / "repairs.csv", ["leak_id", "zone", "start_day_of_year", "flow_m3h"],
              [[x["id"], x["zone"], x["start_day"], x["flow"]] for x in leaks])
    noise_scores = rng.gamma(1.6, 0.9, size=60 * 52)          # one weekly maximum per zone
    fault_scores = rng.uniform(3.0, 8.5, size=14)              # meter faults look like leaks
    leak_score = {x["id"]: 1.2 * x["flow"] + float(rng.normal(1.5, 1.0)) for x in leaks}
    table = []
    for th in range(1, 9):
        false = int((noise_scores >= th).sum())
        faults = int((fault_scores >= th).sum())
        found = [x for x in leaks if leak_score[x["id"]] >= th]
        delay = [max(1, round(3 + 2.5 * th - 0.8 * x["flow"])) for x in found]
        table.append([th, false + faults + len(found), len(found), faults, false,
                      round(st.median(delay), 1) if delay else ""])
    write_csv(FILES / "meters" / "alerts_by_threshold.csv",
              ["threshold", "alerts_per_year", "alerts_on_confirmed_leaks", "alerts_on_meter_faults",
               "alerts_with_nothing_found", "median_days_to_alert"], table)
    k = {}
    for th, alerts, found, faults, false, delay in table:
        k[th] = {"precision": round(found / alerts, 3), "recall": round(found / 48, 3),
                 "per_week": round(alerts / 52, 1), "faults": faults}
    ok = [th for th in k if k[th]["per_week"] <= 5]
    choice = min(ok)
    row = table[choice - 1]
    # the page's estimate: leaks found x 3 m3/h x 24 h x (40 days - median days to alert)
    saved = row[2] * 3 * 24 * (40 - row[5])
    k["choice"] = choice
    k["water_saved_m3"] = round(saved)
    KEY["2.6"] = k


# ---------------------------------------------------------------- the map

MAP_SCORES = {  # water, readiness, equity, accountability: the trainer's reference
    "U01": (2, 2, 2, 3), "U02": (1, 2, 0, 0), "U03": (3, 2, 3, 2), "U04": (1, 3, 3, 3),
    "U05": (0, 3, 1, 2), "U06": (1, 0, 1, 0), "U07": (0, 2, 3, 2), "U08": (0, 1, 3, 2),
    "U09": (1, 2, 3, 2), "U10": (1, 1, 1, 0), "U11": (1, 2, 3, 2), "U12": (1, 1, 1, 2),
}


def the_map():
    hdr = ["use_id", "name", "description", "owner", "claimed_saving_m3_per_year", "basis_of_claim",
           "data", "licence", "personal_data", "small_farms", "human_step"]
    cases = [list(u) for u in T.USE_CASES]
    # two claims come from the course's own runs: lab 2.3 scaled to the registered olive area, lab 2.6
    cases[2][4] = int(round(KEY["2.3"]["saving_m3"] / 40 * T.OLIVE_HA, -4))
    cases[3][4] = int(round(KEY["2.6"]["water_saved_m3"], -3))
    write_csv(FILES / "map" / "use_cases.csv", hdr, cases)
    write_csv(FILES / "map" / "register_template.csv",
              ["use_id", "data_exists", "licence_allows", "accuracy_measured_here", "personal_data",
               "national_reference", "readiness_0_3", "rights_note"],
              [[u[0], "", "", "", "", "", "", ""] for u in T.USE_CASES])
    write_csv(FILES / "start" / "register.csv", ["use_id", "name", "readiness_0_3", "personal_data"],
              [[u[0], u[1], MAP_SCORES[u[0]][1], u[8].split(":")[0]] for u in T.USE_CASES])
    write_csv(FILES / "map" / "map_template.csv",
              ["rank", "use_id", "water_0_3", "readiness_0_3", "equity_0_3", "accountability_0_3",
               "total", "decision", "one_line_reason"], [["", "", "", "", "", "", "", "", ""] for _ in range(12)])
    total = {u: sum(s) for u, s in MAP_SCORES.items()}
    hold = sorted(u for u, s in MAP_SCORES.items() if s[3] == 0)
    ranked = sorted((u for u in MAP_SCORES if u not in hold),
                    key=lambda u: (-total[u], -MAP_SCORES[u][1], u))
    KEY["2.7"] = {u: {"readiness": s[1], "personal": T.USE_CASES[int(u[1:]) - 1][8].startswith("نعم")}
                  for u, s in MAP_SCORES.items()}
    KEY["2.8"] = {"scores": {u: list(s) for u, s in MAP_SCORES.items()}, "total": total,
                  "ranked": ranked, "hold": hold}


# ---------------------------------------------------------------- texts

def texts():
    write_text(FILES / "authority_profile.txt", T.PROFILE)
    write_text(FILES / "sources_card.txt", T.SOURCES_CARD)
    write_csv(FILES / "monitoring_questions.csv", ["question_id", "question", "owner"], T.QUESTIONS)
    write_csv(FILES / "matching_table.csv", ["question_id", "source_number", "why_this_source", "what_it_cannot_tell"],
              [[q[0], "", "", ""] for q in T.QUESTIONS])
    KEY["1.1"] = {q: v[0] for q, v in T.QUESTIONS_KEY.items()}
    write_text(FILES / "imagery" / "crop_calendar.txt", T.CROP_CALENDAR)
    write_text(FILES / "crop_rules.txt", T.CROP_RULES)
    write_text(FILES / "field_team.txt", T.FIELD_TEAM)
    write_text(FILES / "landcover" / "class_legend.txt", T.CLASS_LEGEND)
    write_text(FILES / "landcover" / "campaign_costs.txt", T.CAMPAIGN_COSTS)
    write_text(FILES / "farm" / "farm_profile.txt", T.FARM_PROFILE)
    write_text(FILES / "meters" / "zone_events.txt", T.ZONE_EVENTS)
    write_text(FILES / "meters" / "crew_capacity.txt", T.CREW)
    write_text(FILES / "map" / "scoring_guide.txt", T.SCORING_GUIDE)
    write_text(FILES / "prework_guide.txt", T.PREWORK_GUIDE)
    write_text(FILES / "prework_fallback.txt", T.PREWORK_FALLBACK)
    write_csv(FILES / "prework_sheet.csv", ["decision", "who_decides", "how_often", "monitored_today_by",
                                            "costly_error", "who_could_be_wronged"], [["", "", "", "", "", ""]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    raw = Path(a.raw)
    global BBOX, TILE, UTM
    win = json.loads((raw / "window.json").read_text())
    BBOX, TILE = tuple(win["bbox"]), Affine(*win["tile_grid_10m"])
    UTM = f"EPSG:326{win['tile'][:2]}"
    texts()
    plots, observed, dates, p21 = imagery(raw)
    write_plots(plots, observed, dates)
    landcover(raw, p21)
    weather(raw)
    meters()
    the_map()
    SOL.mkdir(parents=True, exist_ok=True)
    (SOL / "key.json").write_bytes((json.dumps(KEY, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(json.dumps({k: v for k, v in KEY.items() if k not in ("1.4", "field_checks")}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
