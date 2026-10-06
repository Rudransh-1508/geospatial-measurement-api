"""Compare area/length strategies against exact ellipsoid values.

Writes docs/accuracy.md and docs/accuracy.png. Run: uv run python -m scripts.benchmark_accuracy
"""

import math
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from pyproj import Geod, Transformer
from shapely.geometry.base import BaseGeometry

from app.processing.measure import measure

DOCS = Path(__file__).resolve().parent.parent / "docs"
GEOD = Geod(ellps="WGS84")

# WGS84 closed-form area of a meridian/parallel cell (independent of pyproj).
A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
E = math.sqrt(E2)


def _q(lat: float) -> float:
    s = math.sin(math.radians(lat))
    return (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * math.log((1 - E * s) / (1 + E * s)))


def exact_cell_area(lon: float, lat: float, size: float) -> float:
    return (A * A * math.radians(size) / 2) * (_q(lat + size) - _q(lat))


def cell(lon: float, lat: float, size: float) -> BaseGeometry:
    return shapely.segmentize(shapely.box(lon, lat, lon + size, lat + size), size / 200)


def planar(geom: BaseGeometry, crs: str) -> BaseGeometry:
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return shapely.transform(geom, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))


def utm_crs(lon: float, lat: float) -> str:
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def web_mercator(g: BaseGeometry) -> float:
    return float(planar(g, "EPSG:3857").area)


def utm(g: BaseGeometry) -> float:
    c = g.centroid
    return float(planar(g, utm_crs(c.x, c.y)).area)


def local_laea(g: BaseGeometry) -> float:
    m = measure(g).measurement
    assert m is not None
    return m.value


def geodesic(g: BaseGeometry) -> float:
    m = measure(g).measurement
    assert m is not None
    return m.geodesic_value


METHODS: dict[str, Callable[[BaseGeometry], float]] = {
    "Web Mercator (EPSG:3857)": web_mercator,
    "UTM zone of centroid": utm,
    "Local LAEA (this service)": local_laea,
    "Geodesic on WGS84": geodesic,
}
# Reference palette, categorical slots 1-4 in fixed order (light surface).
COLOURS = ["#eb6834", "#1baf7a", "#2a78d6", "#eda100"]
LON = 77.0  # mid-zone longitude: the best case for UTM; zone-edge features are worse
LATITUDES: list[float] = [0, 15, 30, 45, 60, 75, 85]
SIZES = [0.001, 0.01, 0.1, 1.0, 3.0]
FLOOR = 1e-13


def rel_error(value: float, truth: float) -> float:
    return max(abs(value - truth) / truth, FLOOR)


def length_rows() -> list[tuple[float, float, float, float]]:
    """10 km east-west line at each latitude: Mercator, UTM, AEQD relative errors vs geodesic."""
    rows: list[tuple[float, float, float, float]] = []
    for lat in LATITUDES:
        lon2, lat2, _ = GEOD.fwd(LON, lat, 90, 10_000.0)
        line = shapely.LineString([(LON, lat), (lon2, lat2)])
        truth = GEOD.geometry_length(line)
        merc = planar(line, "EPSG:3857").length
        utm_len = planar(line, utm_crs(LON, lat)).length
        m = measure(line).measurement
        assert m is not None
        rows.append((lat, rel_error(merc, truth), rel_error(utm_len, truth), rel_error(m.value, truth)))
    return rows


def fmt(x: float) -> str:
    return "< 1e-13" if x <= FLOOR else f"{x:.1e}"


def main() -> None:
    by_lat = {
        name: [rel_error(fn(cell(LON, lat, 0.01)), exact_cell_area(LON, lat, 0.01)) for lat in LATITUDES]
        for name, fn in METHODS.items()
    }
    by_size = {
        name: [rel_error(fn(cell(LON - s / 2, 45, s)), exact_cell_area(LON - s / 2, 45, s)) for s in SIZES]
        for name, fn in METHODS.items()
    }
    lengths = length_rows()

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), facecolor="#fcfcfb")
    panels = [
        (axes[0], LATITUDES, by_lat, "Latitude (°)", "Area error vs latitude (≈1 km cell)"),
        (axes[1], SIZES, by_size, "Cell size (degrees, at 45°N)", "Area error vs feature size"),
    ]
    for ax, xs, data, xlabel, title in panels:
        ax.set_facecolor("#fcfcfb")
        for (name, ys), colour in zip(data.items(), COLOURS, strict=True):
            ax.plot(xs, ys, color=colour, linewidth=2, marker="o", markersize=5, label=name)
        ax.set_yscale("log")
        ax.set_ylim(FLOOR / 3, 1e3)
        if xs is SIZES:
            ax.set_xscale("log")
        ax.set_xlabel(xlabel, color="#52514e")
        ax.set_title(title, loc="left", fontsize=11, color="#0b0b0b", fontweight="bold")
        ax.grid(True, which="major", color="#e6e5e0", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c9c8c2")
        ax.tick_params(colors="#52514e")
    axes[0].set_ylabel("Relative error vs exact ellipsoid area (log)", color="#52514e")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(DOCS / "accuracy.png", dpi=160, facecolor=fig.get_facecolor())

    names = list(METHODS)
    lines = [
        "# Accuracy benchmark",
        "",
        "Generated by `scripts/benchmark_accuracy.py`; do not edit by hand.",
        "",
        "Every strategy measures the same shapes. The reference is the **exact** area of a",
        "meridian/parallel cell on the WGS84 ellipsoid, computed from a closed-form formula that",
        "does not use pyproj. Cells are densified so their edges follow the parallels.",
        f"Longitude {LON}° is near the middle of a UTM zone, the best case for UTM.",
        "",
        "![Accuracy chart](accuracy.png)",
        "",
        "## Area error by latitude (0.01° cell, about 1 km)",
        "",
        "| Latitude | " + " | ".join(names) + " |",
        "|---:|" + "---:|" * len(names),
    ]
    for i, lat in enumerate(LATITUDES):
        lines.append(f"| {lat}° | " + " | ".join(fmt(by_lat[n][i]) for n in names) + " |")
    lines += [
        "",
        "## Area error by feature size (at 45°N)",
        "",
        "| Cell size | " + " | ".join(names) + " |",
        "|---:|" + "---:|" * len(names),
    ]
    for i, size in enumerate(SIZES):
        lines.append(f"| {size}° | " + " | ".join(fmt(by_size[n][i]) for n in names) + " |")
    lines += [
        "",
        "## Length error by latitude (10 km east-west line, reference: geodesic)",
        "",
        "| Latitude | Web Mercator | UTM zone of centroid | Local AEQD (this service) |",
        "|---:|---:|---:|---:|",
    ]
    for lat, merc, utm_err, aeqd in lengths:
        lines.append(f"| {lat}° | {fmt(merc)} | {fmt(utm_err)} | {fmt(aeqd)} |")
    lines += [
        "",
        "## Reading the results",
        "",
        "- **Web Mercator** is wrong by a factor of `1/cos²(lat)` for area: about 2x at 45°",
        "  and over 100x at 85°. It is fine for drawing maps and wrong for measuring them.",
        "- **UTM** is good near its central meridian (error around 1e-4 to 1e-3 from its",
        "  0.9996 scale factor) but cannot reach the accuracy of an equal-area projection,",
        "  and degrades for features that span zones.",
        "- **Local LAEA** is equal-area by construction, so its area error is at",
        "  floating-point level for parcel-sized features at every latitude. Error only",
        "  appears for very large features, where straight edges in the projection and",
        "  geodesic edges describe slightly different shapes.",
        "- **Geodesic** values agree with the exact formula to about 1e-12 and with PostGIS",
        "  `ST_Area(geography)` (see `tests/test_postgis_crosscheck.py`), which is why the",
        "  API reports them next to every projected value.",
        "",
    ]
    (DOCS / "accuracy.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
