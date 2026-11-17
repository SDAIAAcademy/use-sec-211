"""The soil water balance of USE-SEC-211, labs 2.2 to 2.4, as the lab pages describe it.

One function, used by the generator and by labs/solutions/check.py, so that the key and the
check compute the same thing the participants compute in the spreadsheet:

  depletion at the end of day t:
    Dr[t] = clamp(Dr[t-1] - rain[t] - irrigation[t] + Ks[t] * Kc * ET0[t], 0, TAW)
  Ks[t] = 1 when Dr[t-1] <= RAW, otherwise (TAW - Dr[t-1]) / (TAW - RAW)
  a stress day is a day with Ks[t] < 1
  drainage[t] = water above field capacity, lost below the roots
FAO Irrigation and Drainage Paper 56, chapter 8 (Ks) and the daily root-zone balance.
"""
from __future__ import annotations


def balance(et0, rain, irrigation, kc, taw, raw, dr0=0.0):
    """Returns per-day lists: dr, ks, etc_adj, drainage."""
    dr_prev = dr0
    out = {"dr": [], "ks": [], "etc": [], "drain": []}
    for e, p, i in zip(et0, rain, irrigation):
        ks = 1.0 if dr_prev <= raw else (taw - dr_prev) / (taw - raw)
        etc = ks * kc * e
        d = dr_prev - p - i + etc
        drain = 0.0
        if d < 0:
            drain = -d
            d = 0.0
        d = min(d, taw)
        out["dr"].append(d)
        out["ks"].append(ks)
        out["etc"].append(etc)
        out["drain"].append(drain)
        dr_prev = d
    return out


def forecast_schedule(et0, rain, f1, f2, f3, kc, taw, raw, depth, dr0=0.0, look=None):
    """The forecast-driven rule of lab 2.3.

    Each morning, before irrigating: projected = Dr[t-1] + Kc * (f1[t] + f2[t+1] + f3[t+2]),
    where fk is the forecast issued the day before day t (lead k). Irrigate `depth` mm on day t
    when projected >= RAW. The last two days use the forecasts that exist (f2, f3 may be None).
    The balance itself runs on the observed ET0 and rain.
    """
    n = len(et0)
    dr_prev = dr0
    irr = []
    res = {"dr": [], "ks": [], "etc": [], "drain": [], "irr": [], "projected": []}
    for t in range(n):
        ahead = look[t] if look is not None else (
            f1[t] + (f2[t + 1] if t + 1 < n else f1[t]) + (f3[t + 2] if t + 2 < n else f1[t]))
        projected = dr_prev + kc * ahead
        i = depth if projected >= raw else 0.0
        ks = 1.0 if dr_prev <= raw else (taw - dr_prev) / (taw - raw)
        etc = ks * kc * et0[t]
        d = dr_prev - rain[t] - i + etc
        drain = 0.0
        if d < 0:
            drain = -d
            d = 0.0
        d = min(d, taw)
        for k, v in (("dr", d), ("ks", ks), ("etc", etc), ("drain", drain), ("irr", i),
                     ("projected", projected)):
            res[k].append(v)
        dr_prev = d
        irr.append(i)
    return res


def summary(res: dict, irrigation=None) -> dict:
    irr = res["irr"] if irrigation is None else irrigation
    return {"water_mm": round(sum(irr), 1),
            "irrigations": sum(1 for v in irr if v > 0),
            "stress_days": sum(1 for v in res["ks"] if v < 1),
            "drain_mm": round(sum(res["drain"]), 1)}
