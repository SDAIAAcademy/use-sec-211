# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run the reference solution of every lab of USE-SEC-211 on the participants' files.

    uv run labs/solutions/check.py            # all labs
    uv run labs/solutions/check.py 1.4 2.3    # some labs

Every number is recomputed from labs/files/ (the files a participant opens), the way the lab page
tells a participant to compute it, and compared with key.json, which the file generator wrote.
The text labs (1.1, 2.7, 2.8) are checked against their keys and guides. No lab calls a language
model. Standard library only. Nothing is written to disk.
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE.parent / "files"
KEY = json.loads((HERE / "key.json").read_text(encoding="utf-8"))
RUN: dict = {}


def lab(lab_id):
    def wrap(fn):
        RUN[lab_id] = fn
        return fn
    return wrap


def rows(rel: str) -> list[dict]:
    with (FILES / rel).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def same(label, got, want, tol=0.0):
    if isinstance(want, (int, float)) and not isinstance(want, bool) and want is not None:
        ok = got is not None and abs(float(got) - float(want)) <= tol
    else:
        ok = got == want
    if not ok:
        raise AssertionError(f"{label}: computed {got!r}, key {want!r}")


# ---------------------------------------------------------------- Day 1

@lab("1.1")
def l11():
    qs = rows("monitoring_questions.csv")
    same("questions", len(qs), 8)
    card = (FILES / "sources_card.txt").read_text(encoding="utf-8")
    sources = [n for n in range(1, 9) if f"\n{n}. " in card]
    same("sources in the card", len(sources), 8)
    key = KEY["1.1"]
    same("every question has a source", sorted(key), [q["question_id"] for q in qs])
    print("  key:", ", ".join(f"{q}→{s}" for q, s in key.items()), "· pass mark 6 of 8")


@lab("1.2")
def l12():
    sc = rows("imagery/scenes.csv")
    k = KEY["1.2"]
    same("scenes", len(sc), k["scenes"])
    clear = [r for r in sc if float(r["window_clear_pct"]) >= 90]
    same("clear scenes", len(clear), k["clear_scenes"])
    by = defaultdict(int)
    for r in clear:
        by[r["date"][:7]] += 1
    for m, n in k["clear_by_month"].items():
        same(f"clear in {m}", by.get(m, 0), n)
    mis = sum(1 for r in sc if float(r["tile_cloud_pct"]) < 20 and float(r["window_clear_pct"]) < 90)
    same("misleading tile cloud", mis, k["low_tile_cloud_but_not_clear"])
    import datetime as dt
    win = [dt.date.fromisoformat(r["date"]) for r in clear if "2023-11-01" <= r["date"] <= "2024-02-29"]
    same("longest winter gap", max((b - a).days for a, b in zip(win, win[1:])), k["longest_winter_gap_days"])
    for r in rows("imagery/plot_sizes.csv"):
        ha = float(r["area_ha"])
        side = math.sqrt(ha * 10000)
        for res in (10, 30, 250):
            same(f"{r['plot_type']} pure {res}", max(0, math.floor(side / res) - 2) ** 2, k["pixels"][r["plot_type"]][f"pure_{res}"])
    print(f"  {len(sc)} scenes, {len(clear)} clear; clear per month {dict(by)}; misleading {mis}")


def ndvi_by_plot():
    out = defaultdict(list)
    for r in rows("imagery/plots_reflectance.csv"):
        if r["red"] and float(r["clear_fraction"]) >= 0.9:
            red, nir = float(r["red"]), float(r["nir"])
            out[r["plot_id"]].append((r["date"], r["month"], (nir - red) / (nir + red)))
    return out


def features(series):
    win = [v for _, m, v in series if m in ("12", "01", "02", "03")]
    summ = [v for _, m, v in series if m in ("06", "07", "08")]
    smax = [v for _, m, v in series if m in ("06", "07", "08", "09")]
    return {"winter_max": max(win), "summer_mean": st.mean(summ), "summer_max": max(smax),
            "season_max": max(v for *_, v in series)}


RULES = {
    "قمح": lambda f: f["winter_max"] >= 0.50 and f["summer_mean"] < 0.30,
    "برسيم": lambda f: f["winter_max"] >= 0.40 and f["summer_mean"] >= 0.40,
    "علف صيفي": lambda f: f["winter_max"] < 0.35 and f["summer_max"] >= 0.50,
    "بور": lambda f: f["season_max"] < 0.30,
}


@lab("1.3")
def l13():
    s = ndvi_by_plot()
    for pid in KEY["1.3"]["plots"]:
        f = features(s[pid])
        for k, v in KEY["1.4"]["features"][pid].items():
            same(f"{pid} {k}", round(f[k], 3), v, 0.0015)
        peak = max(s[pid], key=lambda x: x[2])
        print(f"  {pid}: peak {peak[2]:.2f} on {peak[0]}, pattern {KEY['1.4']['observed'][pid]}")


@lab("1.4")
def l14():
    s = ndvi_by_plot()
    # the start file gives the same values
    start = defaultdict(list)
    for r in rows("start/plots_ndvi.csv"):
        if r["ndvi"]:
            start[r["plot_id"]].append((r["date"], r["month"], float(r["ndvi"])))
    decl = {r["plot_id"]: r["declared_crop"] for r in rows("declarations.csv")}
    flags = []
    for pid in sorted(decl):
        f = features(start[pid])
        f2 = features(s[pid])
        same(f"{pid} winter max from both files", round(f["winter_max"], 2), round(f2["winter_max"], 2), 0.011)
        if not RULES[decl[pid]](f):
            flags.append(pid)
    same("flagged plots", flags, KEY["1.4"]["flagged"])
    print(f"  {len(decl)} plots, {len(flags)} flagged: {', '.join(flags)}")


@lab("1.5")
def l15():
    decl = rows("declarations.csv")
    flagged = {r["plot_id"] for r in rows("start/flags.csv")}
    same("start file is the 1.4 list", sorted(flagged), KEY["1.4"]["flagged"])
    small = [r for r in decl if float(r["area_ha"]) < 6]
    large = [r for r in decl if float(r["area_ha"]) >= 6]
    sf = sum(1 for r in small if r["plot_id"] in flagged)
    lf = sum(1 for r in large if r["plot_id"] in flagged)
    k = KEY["1.5"]
    same("small", len(small), k["small"])
    same("small flagged", sf, k["small_flagged"])
    same("large flagged", lf, k["large_flagged"])
    print(f"  small plots {sf}/{len(small)} flagged ({sf / len(small):.0%}), large {lf}/{len(large)} ({lf / len(large):.0%})")


CLASSES = ["مزروعة", "جرداء", "مبنية", "عشبية", "شجرية"]


@lab("1.6")
def l16():
    pts = rows("landcover/points.csv")
    same("points", len(pts), 200)
    cm = {m: {r: 0 for r in CLASSES} for m in CLASSES}
    for p in pts:
        cm[p["map_class"]][p["reference_class"]] += 1
    same("matrix", cm, KEY["1.6"]["matrix"])
    print("  correct on the diagonal:", sum(cm[c][c] for c in CLASSES), "of 200")


@lab("1.7")
def l17():
    cm = {r["map_class \\ reference_class"]: {c: int(r[c]) for c in CLASSES} for r in rows("start/confusion_matrix.csv")}
    total = sum(sum(v.values()) for v in cm.values())
    overall = sum(cm[c][c] for c in CLASSES) / total
    k = KEY["1.7"]
    same("overall", round(overall, 3), k["overall"])
    for c in CLASSES:
        row = sum(cm[c].values())
        col = sum(cm[m][c] for m in CLASSES)
        same(f"users {c}", round(cm[c][c] / row, 3), k["users"][c])
        same(f"producers {c}", round(cm[c][c] / col, 3) if col else None, k["producers"][c])
    uses = {r["use_id"]: r for r in rows("landcover/proposed_uses.csv")}
    print(f"  overall {overall:.3f}; users {k['users']}; producers {k['producers']}")
    print("  uses:", k["uses"], "·", len(uses), "proposed")


@lab("1.8")
def l18():
    k = KEY["1.8"]
    for r in rows("start/accuracy_table.csv"):
        c, n, p = r["class"], int(r["points_in_class"]), float(r["users_accuracy"])
        same(f"half width {c}", round(1.96 * math.sqrt(p * (1 - p) / n), 3), k["half_width"][c])
        same(f"needed {c}", math.ceil(1.96 ** 2 * p * (1 - p) / 0.01), k["needed"][c])
    print("  half widths", k["half_width"], "extra points", k["extra"])


# ---------------------------------------------------------------- Day 2

@lab("2.1")
def l21():
    rs = rows("weather/et0_forecasts_2024.csv")
    k = KEY["2.1"]

    def mae(col, months=None):
        sel = [r for r in rs if months is None or r["month"] in months]
        return st.mean(abs(float(r[col]) - float(r["era5_et0"])) for r in sel)
    clim = mae("climatology_et0")
    same("mae clim", round(clim, 3), k["mae_clim"])
    for lead in (1, 2, 3):
        m = mae(f"forecast_lead{lead}")
        same(f"mae lead {lead}", round(m, 3), k[f"mae_lead{lead}"])
        same(f"skill lead {lead}", round(1 - round(m, 3) / round(clim, 3), 3), k[f"skill_lead{lead}"], 0.002)
    bias = st.mean(float(r["forecast_lead1"]) - float(r["era5_et0"]) for r in rs)
    same("bias", round(bias, 3), k["bias_lead1"])
    print(f"  MAE clim {clim:.3f}, lead1 {k['mae_lead1']}, skill {k['skill_lead1']}/{k['skill_lead2']}/{k['skill_lead3']}, bias {bias:.2f}, spring {k['skill_lead1_spring']}, summer {k['skill_lead1_summer']}")


def run_balance(et0, rain, irr, kc=0.70, taw=90.0, raw=58.5):
    d, out = 0.0, []
    for e, p, i in zip(et0, rain, irr):
        ks = 1.0 if d <= raw else (taw - d) / (taw - raw)
        nd = d - p - i + ks * kc * e
        drain = -nd if nd < 0 else 0.0
        d = min(max(nd, 0.0), taw)
        out.append((d, ks, drain))
    return out


@lab("2.2")
def l22():
    rs = rows("farm/season_2024.csv")
    et0 = [float(r["et0_mm"]) for r in rs]
    rain = [float(r["rain_mm"]) for r in rs]
    irr = [float(r["fixed_irrigation_mm"]) for r in rs]
    b = run_balance(et0, rain, irr)
    k = KEY["2.2"]
    same("water", round(sum(irr), 1), k["water_mm"])
    same("stress days", sum(1 for _, ks, _ in b if ks < 1), k["stress_days"])
    same("drainage", round(sum(x[2] for x in b), 1), k["drain_mm"], 0.15)
    gap = [float(r["probe_theta"]) - (0.24 - d * 0.00167) for r, (d, _, _) in zip(rs, b)]
    first = next(rs[i]["date"] for i in range(len(gap) - 6) if all(abs(x) > 0.02 for x in gap[i:i + 7]))
    same("probe gap from", first, k["probe_gap_from"])
    print(f"  fixed: {sum(irr):.0f} mm = {sum(irr) * 400:,.0f} m³, stress days {k['stress_days']}, drainage {k['drain_mm']} mm; probe off from {first}")


@lab("2.3")
def l23():
    rs = rows("start/season_fixed.csv")
    et0 = [float(r["et0_mm"]) for r in rs]
    rain = [float(r["rain_mm"]) for r in rs]
    look = [float(r["forecast_et0_next3"]) for r in rs]
    d, irr, stress, drain = 0.0, [], 0, 0.0
    for e, p, lk in zip(et0, rain, look):
        i = 30.0 if d + 0.70 * lk >= 58.5 else 0.0
        ks = 1.0 if d <= 58.5 else (90 - d) / (90 - 58.5)
        stress += ks < 1
        nd = d - p - i + ks * 0.70 * e
        drain += -nd if nd < 0 else 0.0
        d = min(max(nd, 0.0), 90.0)
        irr.append(i)
    k = KEY["2.3"]
    same("forecast water", round(sum(irr), 1), k["forecast"]["water_mm"])
    same("forecast stress", stress, k["forecast"]["stress_days"])
    fixed = sum(float(r["fixed_irrigation_mm"]) for r in rs)
    same("fixed water", round(fixed, 1), k["fixed"]["water_mm"])
    same("fixed stress", sum(int(r["fixed_stress"]) for r in rs), k["fixed"]["stress_days"])
    same("saving pct", round((1 - sum(irr) / fixed) * 100, 1), k["saving_pct"])
    print(f"  fixed {fixed:.0f} mm, stress {k['fixed']['stress_days']}; forecast {sum(irr):.0f} mm, stress {stress}, drainage {drain:.1f}; saving {k['saving_pct']}% = {k['saving_m3']:,} m³")


@lab("2.4")
def l24():
    rs = rows("start/scenarios.csv")
    pct = []
    for r in rs:
        p = round((1 - float(r["forecast_water_mm"]) / float(r["fixed_water_mm"])) * 100, 1)
        same(f"{r['soil']} {r['forecast_used']}", p, KEY["2.4"]["scenarios"][f"{r['soil']}|{r['forecast_used']}"]["saving_pct"])
        pct.append(p)
    same("min", min(pct), KEY["2.4"]["saving_min"])
    same("max", max(pct), KEY["2.4"]["saving_max"])
    print(f"  saving from {min(pct)}% to {max(pct)}% over nine scenarios")
    for r in rs:
        print(f"    {r['soil']:<12} {r['forecast_used']:<14} saving {(1 - float(r['forecast_water_mm']) / float(r['fixed_water_mm'])) * 100:5.1f}%  stress fixed {r['fixed_stress_days']} forecast {r['forecast_stress_days']}")


@lab("2.5")
def l25():
    mnf = defaultdict(dict)
    for r in rows("meters/zone_hourly.csv"):
        if 1 <= int(r["hour"]) <= 4:
            q = float(r["flow_m3h"])
            z, d = r["zone"], r["date"]
            mnf[z][d] = min(mnf[z].get(d, 1e9), q)
    for z, s in sorted(mnf.items()):
        ds = sorted(s)
        base = st.median(s[d] for d in ds[:14])
        lim = base + max(2.0, 0.3 * base)
        flag = next((ds[i] for i in range(len(ds) - 2) if all(s[ds[i + j]] > lim for j in range(3))), None)
        k = KEY["2.5"][z]
        same(f"{z} baseline", round(base, 2), k["baseline"])
        same(f"{z} first flag", flag, k["first_flag"])
        zero = [d for d in ds if s[d] == 0]
        print(f"  {z}: baseline {base:.2f}, limit {lim:.2f}, first flag {flag}{', zero nights ' + zero[0] + ' to ' + zero[-1] if zero else ''}")


@lab("2.6")
def l26():
    t = rows("meters/alerts_by_threshold.csv")
    leaks = rows("meters/repairs.csv")
    same("leaks", len(leaks), 48)
    k = KEY["2.6"]
    ok = []
    for r in t:
        th = r["threshold"]
        a, f = int(r["alerts_per_year"]), int(r["alerts_on_confirmed_leaks"])
        same(f"precision {th}", round(f / a, 3), k[th]["precision"])
        same(f"recall {th}", round(f / 48, 3), k[th]["recall"])
        if a / 52 <= 5:
            ok.append(int(th))
        print(f"  threshold {th}: precision {f / a:.2f}, recall {f / 48:.2f}, {a / 52:.1f} a week, faults {r['alerts_on_meter_faults']}")
    same("choice", min(ok), k["choice"])
    print(f"  choice {k['choice']}; water saved about {k['water_saved_m3']:,} m³ a year")


@lab("2.7")
def l27():
    uc = rows("map/use_cases.csv")
    same("use cases", len(uc), 12)
    for u in uc:
        same(f"{u['use_id']} personal", u["personal_data"].startswith("نعم"), KEY["2.7"][u["use_id"]]["personal"])
    print("  readiness:", {u: v["readiness"] for u, v in KEY["2.7"].items()})


@lab("2.8")
def l28():
    k = KEY["2.8"]
    hold = sorted(u for u, s in k["scores"].items() if s[3] == 0)
    same("hold", hold, k["hold"])
    rest = sorted((u for u in k["scores"] if u not in hold), key=lambda u: (-sum(k["scores"][u]), -k["scores"][u][1], u))
    same("ranking", rest, k["ranked"])
    reg = {r["use_id"]: int(r["readiness_0_3"]) for r in rows("start/register.csv")}
    for u, s in k["scores"].items():
        same(f"{u} readiness in start file", reg[u], s[1])
    print("  ranked:", " > ".join(f"{u} ({sum(k['scores'][u])})" for u in rest), "· hold:", ", ".join(hold))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    wanted = sys.argv[1:] or list(RUN)
    bad = 0
    for lid in wanted:
        print(f"Lab {lid}")
        try:
            RUN[lid]()
            print("  PASS")
        except Exception as e:  # report and continue
            bad += 1
            print("  FAIL:", e)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
