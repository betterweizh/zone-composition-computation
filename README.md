# zone-composition-computation

Compute zone-level composition statistics for geometry

- `Point`/`MultiPoint`: count
- `LineString`/`MultiLineString`: length
- `Polygon`/`MultiPolygon`: area

This repository provides:
- `entropy_mix_index`: normalized entropy-based mix index.
- `ZoneComposition`: overlay-based zonal composition pipeline for point/line/polygon elements.

This toolset consists of two components:

- A pure Python script, in [pyscript](pyscript)
- A QGIS plugin, in [qgis_plugin](qgis_plugin) (to be completed...)

## Requirements

`numpy`, `pandas`, `shapely`, `geopandas`, `pyproj`

## Usage examples

```python
import geopandas as gpd
from zone_composition import ZoneComposition

elements = gpd.read_file("elements.geojson")
zones = gpd.read_file("zones.geojson")

zc = ZoneComposition(
    element_gdf = elements,
    zone_gdf = zones,
    element_type_col = "land_use",
    element_weight_col = None,
    zone_id_col = "zone_id",
    target_crs = "EPSG:3414",
)

zone_comp = zc.zonal_composition()

result = zc.compute_composition(
    density = True,        # Divide composition by zone area
    mix_index = True,
    mix_index_normalized = True,
)

print(result.head())
```


```python
from zone_composition import entropy_mix_index

print(entropy_mix_index([1, 0, 0]))  # 0.0
print(entropy_mix_index([1, 1, 1]))  # 1.0
print(entropy_mix_index([2, 1, 1]))  # between 0 and 1
```

## API Documentation

##### class `ZoneComposition`

Compute zonal composition by intersecting `element_gdf` with `zone_gdf`.

- Composition value depends on geometry type in `element_gdf`:
  - `Point`/`MultiPoint`: count
  - `LineString`/`MultiLineString`: length
  - `Polygon`/`MultiPolygon`: area
- The units length and area depend on the projected CRS used.

##### `ZoneComposition.__init__(...)`

Parameters:

- `element_gdf` (`geopandas.GeoDataFrame`, required): 
  - spatial elements to summarize inside zones.
- `zone_gdf` (`geopandas.GeoDataFrame`, required): 
  - zone polygons used for aggregation.
- `element_type_col` (`str | None`, default `None`, optional): 
  - category/type column in `element_gdf`; required to compute `mix_index`.
- `element_weight_col` (`str | None`, default `None`, optional): 
  - optional weight column in `element_gdf`; composition is multiplied by this weight.
- `zone_id_col` (`str | None`, default `None`, optional):
  - zone identifier column in `zone_gdf`; if `None`, `__zone_id` is created from index.
- `target_crs` (`str | None`, default `None`, optional): 
  - optional projected CRS to reproject both inputs before overlay.

- `element_gdf` and `zone_gdf` must be non-empty.
- both inputs must have CRS defined.
  - CRS used for computation must be projected.
  - if `target_crs` is provided, both inputs are reprojected to it.
  - if `target_crs` is not provided, both CRS must already match.
- referenced columns (`element_type_col`, `element_weight_col`, `zone_id_col`) must exist when provided.

Input Assumptions and Units

- `zone_gdf` should contain polygon zones.
- `element_gdf` geometry family should be homogeneous for composition (point-only, line-only, or polygon-only).
- Both inputs must have CRS defined for computing geometry's length and area.
  - CRS used for computation must be projected.
  - if `target_crs` is provided, both inputs are reprojected to it.
  - if `target_crs` is not provided, both CRS must already match.
  - length and area units come from the projected CRS.
- With `density=True`, results are composition per zone-area unit (for example, per `m^2` if CRS uses meters).

##### `ZoneComposition.zonal_composition() -> geopandas.GeoDataFrame`

Intersect elements with zones and compute per-intersection composition value.

Output columns include:
- original columns from overlay result.
- `__comp_value`: geometry-based composition value.
- `__comp_value_weighted`: only when `element_weight_col` is provided.

Notes:
- Uses `gpd.overlay(..., how="intersection", keep_geom_type=True, make_valid=True)`.
- Sorts by zone ID and, if present, element type.

##### `ZoneComposition.compute_composition(density=True, mix_index=False, mix_index_normalized=False) -> pandas.DataFrame`

Aggregate zonal composition to a zone-level table.

Parameters:

- `density` (`bool`, default `True`): 
  - if `True`, divide composition values by zone area of `zone_gdf`
- `mix_index` (`bool`, default `False`):
  - if `True`, append entropy-based `mix_index` column; requires `element_type_col`.
- `mix_index_normalized` (`bool`, default `False`): 
  - passed to `entropy_mix_index` as `normalized`.

Returns:
- `pandas.DataFrame` with first column as zone ID.
- If `element_type_col` is provided: one column per element type.
- If `element_type_col` is `None`: one aggregated composition column.
- Optional `mix_index` column.

Raises:
- `ValueError` when `mix_index=True` but `element_type_col` is not provided.
- `ValueError` when zone IDs are not unique and `density=True` (zone area lookup).

##### `entropy_mix_index(arr, normalized=True, zero_value=0.0) -> float`

Compute normalized **Shannon entropy** from a 1-D non-negative array.

$$
H = -\frac{\sum_{i=1}^n p_i \log(p_i)}{\log(n)}
$$

- where $p_i\geq0$ is the proportion of the $i$-th category. Define $p_i \log(p_i) = 0$ if $p_i=0$.

- $H \in [0, 1]$, and $H=0$ indicates completely homogenous of one specific category, while $H=1$ when values are equally distributed across all categories.

Parameters:

- `arr` (`list[float] | numpy.ndarray | pandas.Series`, required): 
  - 1-D non-negative values (counts/proportions).
- `normalized` (`bool`, default `True`): 
  - if `True`, normalize input to sum to 1 before entropy calculation.
- `zero_value` (`float`, default `0.0`): 
  - returned when input sum is exactly zero.

Returns:
- `float` in `[0.0, 1.0]`.

Raises:
- `ValueError` if input is not 1-D, empty, or contains negative values.

##### `compute_reference_entropy_mix_index_value(type_num=2, start=2, end=15) -> dict[int, float]`

Generate reference mix-index values for category counts from `start` to `end`.

Parameters:

- `type_num` (`int`, default `2`): 
  - number of active categories with equal share.
- `start` (`int`, default `2`): 
  - minimum total category count (inclusive).
- `end` (`int`, default `15`):
  - maximum total category count (inclusive).

Returns:
- `dict[int, float]`: key is total category count, value is reference mix index.

Raises:
- `ValueError` if `type_num < 1`, `start < 1`, `end < start`, or `type_num > start`.

## License

Apache License 2.0, [LICENSE](LICENSE)