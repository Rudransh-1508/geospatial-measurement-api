"""Generate the sample files in samples/. Run: uv run python -m scripts.make_samples"""

import shutil
import tempfile
from pathlib import Path

import shapely
from pyproj import Transformer

from tests.factories import folder, placemark, shapefile_zip, write_kml, write_kmz, write_shapefile, zip_files

OUT = Path(__file__).resolve().parent.parent / "samples"

# Hand-drawn agricultural plots on the western edge of Pune, India.
PLOTS = {
    "S-101": [(73.7801, 18.5352), (73.7822, 18.5355), (73.7826, 18.5338), (73.7804, 18.5334)],
    "S-102": [(73.7822, 18.5355), (73.7845, 18.5357), (73.7849, 18.5341), (73.7826, 18.5338)],
    "S-103": [
        (73.7804, 18.5334),
        (73.7826, 18.5338),
        (73.7829, 18.5321),
        (73.7808, 18.5316),
        (73.7801, 18.5325),
    ],
    "S-104": [(73.7826, 18.5338), (73.7849, 18.5341), (73.7853, 18.5322), (73.7829, 18.5321)],
}
ROADS = {
    "Village road": [(73.7795, 18.5360), (73.7824, 18.5357), (73.7851, 18.5360), (73.7880, 18.5364)],
    "Farm track": [(73.7826, 18.5338), (73.7829, 18.5321), (73.7832, 18.5300)],
}
WELLS = {"Well 1": (73.7815, 18.5345), "Well 2": (73.7838, 18.5330)}


def india_survey_kml(path: Path) -> None:
    plots = [
        placemark(f"Plot {k}", shapely.Polygon(v), {"survey_no": k, "village": "Bavdhan"})
        for k, v in PLOTS.items()
    ]
    roads = [placemark(k, shapely.LineString(v)) for k, v in ROADS.items()]
    wells = [placemark(k, shapely.Point(v)) for k, v in WELLS.items()]
    write_kml(path, folder("Plots", *plots), folder("Infrastructure", folder("Roads", *roads), *wells))


def edge_cases_kml(path: Path) -> None:
    holed = shapely.Polygon(
        shapely.box(73.80, 18.50, 73.82, 18.52).exterior.coords,
        [shapely.box(73.805, 18.505, 73.81, 18.51).exterior.coords],
    )
    write_kml(
        path,
        placemark(
            "Fiji, crosses the antimeridian",
            shapely.Polygon([(179.9, -16.6), (-179.9, -16.6), (-179.9, -16.4), (179.9, -16.4)]),
        ),
        placemark("Svalbard, 78 N", shapely.box(15.5, 78.2, 15.7, 78.25)),
        placemark("Plot with a pond (hole)", holed),
        placemark(
            "Self-intersecting (bow-tie)",
            shapely.Polygon([(77.20, 28.60), (77.21, 28.61), (77.21, 28.60), (77.20, 28.61)]),
        ),
        placemark("Mumbai to Pune", shapely.LineString([(72.8777, 19.0760), (73.8567, 18.5204)])),
        placemark(
            "Two islands",
            shapely.MultiPolygon(
                [shapely.box(72.80, 18.90, 72.81, 18.91), shapely.box(72.83, 18.92, 72.84, 18.93)]
            ),
        ),
    )


def utm_parcels_zip(tmp: Path) -> Path:
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    geoms = []
    props = []
    for k, v in PLOTS.items():
        geoms.append(shapely.Polygon([to_utm.transform(x, y) for x, y in v]))
        props.append({"survey_no": k, "owner": f"Owner {k[-1]}", "crop": "sugarcane"})
    return shapefile_zip(tmp, geoms, properties=props, crs="EPSG:32643", name="parcels_utm43n")


def multi_layer_zip(tmp: Path) -> Path:
    src = tmp / "multi"
    plots = write_shapefile(
        src,
        "plots",
        [shapely.Polygon(v) for v in PLOTS.values()],
        properties=[{"survey_no": k} for k in PLOTS],
    )
    roads = write_shapefile(
        src / "network",
        "roads",
        [shapely.LineString(v) for v in ROADS.values()],
        properties=[{"name": k} for k in ROADS],
    )
    wells = write_shapefile(
        src / "network",
        "wells",
        [shapely.Point(v) for v in WELLS.values()],
        properties=[{"name": k} for k in WELLS],
    )
    return zip_files(tmp / "village_layers.zip", [*plots, *roads, *wells], src)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    india_survey_kml(OUT / "pune_survey.kml")
    edge_cases_kml(OUT / "edge_cases.kml")
    write_kmz(OUT / "pune_plots.kmz", *(placemark(f"Plot {k}", shapely.Polygon(v)) for k, v in PLOTS.items()))
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        shutil.copy(utm_parcels_zip(tmp), OUT / "parcels_utm43n.zip")
        shutil.copy(multi_layer_zip(tmp), OUT / "village_layers.zip")
        no_prj = shapefile_zip(
            tmp, [shapely.Polygon(v) for v in PLOTS.values()], name="plots_no_prj", drop=(".prj",)
        )
        shutil.copy(no_prj, OUT / "plots_no_prj.zip")
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:24} {p.stat().st_size:>7} bytes")


if __name__ == "__main__":
    main()
