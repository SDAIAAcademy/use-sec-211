# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio>=1.3", "numpy>=2", "pyproj>=3.6"]
# ///
"""Downloads the public raw data of USE-SEC-211 into a folder outside the course.

  uv run labs/_tools/fetch_public.py --raw <a folder outside the course>       --bbox <west> <south> <east> <north> --point <lat> <lon> --tile <Sentinel-2 tile id>

The window is not written in the course: the plots, declarations and field findings of the labs are
invented, and no file may tie them to a real farm. The author keeps the values outside the repository.

1. Sentinel-2 Level-2A (Copernicus Sentinel data, free and open), read as cloud-optimised GeoTIFFs
   from the public Earth Search catalogue (Element 84, AWS Open Data). Only the window is read:
   the red (B04) and near-infrared (B08) bands at 10 m and the scene classification (SCL) at 20 m.
   Two periods: October 2023 to September 2024 (the plots), and the year 2021 (the land-cover
   reference points).
2. ESA WorldCover 10 m 2021 v200 (CC BY 4.0), the same window.
3. Daily ERA5 weather and past forecasts for one point in the window, from Open-Meteo
   (CC BY 4.0): the archive API with models=era5, and the previous-runs API.

Nothing here is committed. window.json in the raw folder records the window for prepare_files.py,
which turns it all into the small files of labs/files/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

BBOX: tuple = ()   # west, south, east, north: set from --bbox
POINT: tuple = ()  # lat, lon of the weather point: set from --point
TILE_ID = ""       # Sentinel-2 grid square: set from --tile
PERIODS = {"s2_2324": "2023-10-01T00:00:00Z/2024-09-30T23:59:59Z",
           "s2_2021": "2021-01-01T00:00:00Z/2021-12-31T23:59:59Z"}
STAC = "https://earth-search.aws.element84.com/v1/search"
WORLDCOVER = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
ARCHIVE = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
           "&start_date={a}&end_date={b}&models=era5&timezone=Asia%2FRiyadh"
           "&daily=et0_fao_evapotranspiration,precipitation_sum,temperature_2m_max,temperature_2m_min")
PREVIOUS = ("https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&start_date={a}&end_date={b}&timezone=Asia%2FRiyadh&hourly={vars}")


def get(url: str, data: bytes | None = None) -> bytes:
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                                  "User-Agent": "course-data-fetch"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # network hiccups: wait and retry
            print("retry", attempt, e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(url)


def items(period: str) -> list[dict]:
    body = {"collections": ["sentinel-2-l2a"], "bbox": list(BBOX), "datetime": period, "limit": 100,
            "query": {"grid:code": {"eq": f"MGRS-{TILE_ID}"}}}
    feats = []
    while True:
        j = json.loads(get(STAC, json.dumps(body).encode()))
        feats += j["features"]
        nxt = [link for link in j.get("links", []) if link.get("rel") == "next"]
        if not nxt or not j["features"]:
            break
        body = nxt[0].get("body", body)
    # a scene reprocessed later has a second item (_1); keep the latest processing of each scene
    latest = {}
    for f in sorted(feats, key=lambda f: f["id"]):
        latest[f["id"].rsplit("_", 2)[0]] = f
    return sorted(latest.values(), key=lambda f: f["properties"]["datetime"])


def worldcover_tile() -> str:
    """The 3 by 3 degree WorldCover file that holds the south-west corner of the window."""
    lat, lon = math.floor(BBOX[1] / 3) * 3, math.floor(BBOX[0] / 3) * 3
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


def tile_grid(href: str) -> list:
    with rasterio.open(href) as src:
        return list(src.transform)[:6]


def window_read(href: str, out_shape=None):
    with rasterio.open(href) as src:
        t = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x0, y0 = t.transform(BBOX[0], BBOX[1])
        x1, y1 = t.transform(BBOX[2], BBOX[3])
        w = from_bounds(x0, y0, x1, y1, src.transform).round_offsets().round_lengths()
        if out_shape is None:
            return src.read(1, window=w, boundless=True, fill_value=0)
        return src.read(1, window=w, out_shape=out_shape, boundless=True, fill_value=0,
                        resampling=rasterio.enums.Resampling.nearest)


def fetch_s2(raw: Path):
    for name, period in PERIODS.items():
        d = raw / name
        d.mkdir(parents=True, exist_ok=True)
        feats = items(period)
        if feats and not (raw / "window.json").exists():
            (raw / "window.json").write_text(json.dumps(
                {"bbox": list(BBOX), "point": list(POINT), "tile": TILE_ID,
                 "tile_grid_10m": tile_grid(feats[0]["assets"]["red"]["href"])}, indent=1))
        meta = []
        for f in feats:
            fid = f["id"]
            p = f["properties"]
            band = f["assets"]["red"]["raster:bands"][0]
            row = {"id": fid, "date": p["datetime"][:10], "tile_cloud": p.get("eo:cloud_cover"),
                   "boa_offset_applied": p.get("earthsearch:boa_offset_applied", False),
                   "baseline": p.get("s2:processing_baseline")}
            target = d / f"{fid}.npz"
            if not target.exists():
                try:
                    red = window_read(f["assets"]["red"]["href"])
                    if (red == 0).mean() > 0.05:
                        row["skipped"] = "outside the swath"
                        meta.append(row)
                        print(fid, "skipped")
                        continue
                    nir = window_read(f["assets"]["nir"]["href"])
                    scl = window_read(f["assets"]["scl"]["href"], out_shape=red.shape)
                    np.savez_compressed(target, red=red, nir=nir, scl=scl)
                    print(fid, red.shape)
                except Exception as e:
                    row["skipped"] = f"read error: {e}"
                    print(fid, "error", e)
            meta.append(row)
        (d / "scenes.json").write_text(json.dumps(meta, indent=1))


def fetch_worldcover(raw: Path):
    target = raw / "worldcover_2021.npy"
    if not target.exists():
        np.save(target, window_read(WORLDCOVER.format(tile=worldcover_tile())))


def fetch_weather(raw: Path):
    w = raw / "weather"
    w.mkdir(parents=True, exist_ok=True)
    lat, lon = POINT
    t = w / "era5_daily_2000_2024.json"
    if not t.exists():
        t.write_bytes(get(ARCHIVE.format(lat=lat, lon=lon, a="2000-01-01", b="2024-12-31")))
    vars_ = ",".join(["et0_fao_evapotranspiration", "precipitation"] +
                     [f"et0_fao_evapotranspiration_previous_day{k}" for k in range(1, 4)] +
                     [f"precipitation_previous_day{k}" for k in range(1, 4)])
    t = w / "previous_runs_2024.json"
    if not t.exists():
        t.write_bytes(get(PREVIOUS.format(lat=lat, lon=lon, a="2024-02-01", b="2024-10-31", vars=vars_)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    ap.add_argument("--point", nargs=2, type=float, required=True, metavar=("LAT", "LON"))
    ap.add_argument("--tile", required=True, help="Sentinel-2 grid square that holds the window")
    ap.add_argument("--only", choices=["s2", "worldcover", "weather"])
    a = ap.parse_args()
    global BBOX, POINT, TILE_ID
    BBOX, POINT, TILE_ID = tuple(a.bbox), tuple(a.point), a.tile
    raw = Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    if a.only in (None, "weather"):
        fetch_weather(raw)
    if a.only in (None, "worldcover"):
        fetch_worldcover(raw)
    if a.only in (None, "s2"):
        fetch_s2(raw)


if __name__ == "__main__":
    main()
