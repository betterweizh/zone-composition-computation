import pyproj
import numpy as np
import pandas as pd
import geopandas as gpd

from numpy.typing import NDArray
from typing import Mapping, Optional, List


def entropy_mix_index(
    arr: List[float] | NDArray[np.floating] |pd.Series,
    normalized: bool = True,
    zero_value: float = 0.0,
) -> float:
    """
    Compute a entropy-based mix index.

    This function calculates the normalized Shannon entropy of a 1-D array of
    category values. The result is clipped to the range [0.0, 1.0], where:

    - 0.0 indicates no mix (complete concentration)
    - 1.0 indicates maximum mix (uniform distribution)

    Parameters
    ----------
    arr
        A 1-D array-like object containing land-use values. Supported inputs
        include:
        - NumPy arrays
        - Python lists
        - pandas Series

        Values are expected to be non-negative.
    normalized
        If True, normalize the input so its elements sum to 1 before computing
        entropy. If False, `arr` is assumed to already represent proportions or
        probabilities.
    zero_value
        Value to return when the sum of the input is zero.

    Returns
    -------
    float
        The normalized entropy value, clipped to the range [0.0, 1.0].

    Raises
    ------
    ValueError
        If the input is not 1-D, contains negative values, or is empty.

    Notes
    -----
    The formula used is:

        H = -sum(p_i * log(p_i)) / log(k)

    where:
    - `p_i` are the positive entries of the normalized array
    - `k` is the number of categories

    For `k <= 1`, the function returns 0.0 because entropy is not meaningful
    with fewer than two categories.
    """
    # Convert supported inputs to a NumPy array of floats.
    values = np.asarray(arr, dtype=float)
    # Validate array
    if values.ndim != 1:
        raise ValueError(f"Input 'arr' must be a 1-D array, but got shape {values.shape}.")
    if values.size == 0:
        raise ValueError("Input 'arr' must not be empty.")
    if np.any(values < 0):
        raise ValueError("Input 'arr' must contain only non-negative values.")

    total = float(np.sum(values))
    if total == 0.0:
        return float(zero_value)

    # Normalize
    if normalized:
        values = values / total

    category_count = values.size
    if category_count <= 1:
        return 0.0

    # Ignore zero values to avoid log(0).
    positive_mask = values > 0
    entropy = -np.sum(values[positive_mask] * np.log(values[positive_mask]))
    entropy /= np.log(category_count)

    return float(np.clip(entropy, 0.0, 1.0))

# ----------------------------------------------------------------------------------
def compute_reference_entropy_mix_index_value(
    type_num: int = 2,
    start: int = 2,
    end: int = 15,
) -> dict[int, float]:
    """
    Compute reference entropy mix index values for different category counts.

    For each total number of categories from `start` to `end` (inclusive), this
    function creates an array where the first `type_num` categories are equally
    distributed and the remaining categories are zero. It then computes the
    entropy mix index for each case.
    """
    if type_num < 1:
        raise ValueError("'land_type' must be at least 1.")
    if start < 1:
        raise ValueError("'start' must be at least 1.")
    if end < start:
        raise ValueError("'end' must be greater than or equal to 'start'.")
    if type_num > start:
        raise ValueError("'land_type' must be less than or equal to 'start'.")

    lum_index: dict[int, float] = {}

    for category_count in range(start, end + 1):
        values = np.zeros(category_count, dtype=float)
        values[:type_num] = 1.0 / type_num
        lum_index[category_count] = entropy_mix_index(values, normalized=False)

    return lum_index

# =================================================================================================
# def _validate_gdf_crs(gdf1, gdf2, target_crs=None, projected_crs=True):
#     """
#     Validate CRS of two GeoDataFrames.
#     1. Both GeoDataFrames must have a CRS defined.
#     2. If `target_crs` is provided:
#        - Reproject both GeoDataFrames to the target CRS.
#        - Optionally enforce the target CRS is projected.
#     3. If `target_crs` is NOT provided:
#        - Ensure both CRS are identical.
#        - Optionally enforce CRS is projected.
#
#     Parameters
#     ----------
#     gdf1, gdf2 : GeoDataFrame
#         Input GeoDataFrames.
#     target_crs : optional
#         CRS to reproject both GeoDataFrames to.
#     projected_crs : bool, default True
#         Whether the output CRS must be projected.
#
#     Returns
#     -------
#     (gdf1, gdf2) : tuple of GeoDataFrames
#         CRS-aligned (and possibly reprojected) GeoDataFrames.
#     """
#
#     # Validate CRS existence
#     if gdf1.crs is None:
#         raise ValueError("gdf1 has no CRS.")
#     if gdf2.crs is None:
#         raise ValueError("gdf2 has no CRS.")
#
#     crs1 = pyproj.CRS.from_user_input(gdf1.crs)
#     crs2 = pyproj.CRS.from_user_input(gdf2.crs)
#
#     # Case 1: target CRS provided
#     if target_crs is not None:
#         target_crs = pyproj.CRS.from_user_input(target_crs)
#
#         # Ensure projected CRS if required
#         if projected_crs and not target_crs.is_projected:
#             raise ValueError(f"target_crs must be projected when `projected_crs=True`, got: {target_crs.to_string()}")
#
#         # Reproject only if necessary
#         if not crs1.equals(target_crs):
#             gdf1 = gdf1.to_crs(target_crs)
#         if not crs2.equals(target_crs):
#             gdf2 = gdf2.target_crs(target_crs)
#
#         return gdf1, gdf2
#
#     # Case 2: no target CRS
#     # Ensure both CRS are identical
#     if not crs1.equals(crs2):
#         raise ValueError(f"CRS mismatch: {crs1.to_string()} vs {crs2.to_string()}")
#
#     # Ensure CRS is projected if required
#     if projected_crs and not crs1.is_projected:
#         raise ValueError(f"CRS must be projected when `projected_crs=True`, got: {crs1.to_string()}" )
#
#     return gdf1, gdf2
# --------------------------------------------------------------------------


class ZoneComposition:
    """
    Compute zonal composition statistics for spatial elements within zones.

    This class overlays an element GeoDataFrame with a zone GeoDataFrame and
    summarizes the composition of element types within each zone. The composition
    value depends on geometry type:

    - Point / MultiPoint -> count of features
    - LineString / MultiLineString -> total length
    - Polygon / MultiPolygon -> total area

    Optionally, the composition can be converted to density by dividing by zone
    area, and a normalized entropy-based mix index can be added.

    Parameters
    ----------
    element_gdf
        GeoDataFrame containing the spatial elements to summarize.
    zone_gdf
        GeoDataFrame containing the zone polygons.
    element_type_col
        Column in `element_gdf` that defines the category/type of each element.
    element_weight_col
        Column in `element_gdf` that indicates the each element weight
    zone_id_col
        Column in `zone_gdf` used as the zone identifier. If None, the zone
        index is copied into a generated column named ``'__zone_id'``.
    target_crs
        Optional CRS to which both GeoDataFrames should be projected before
        spatial operations.

    Notes
    -----
    This class assumes `_validate_gdf_crs(...)` exists and returns aligned,
    projected GeoDataFrames suitable for area/length calculations.
    """
    def __init__(
        self,
        element_gdf: gpd.GeoDataFrame,
        zone_gdf: gpd.GeoDataFrame,
        element_type_col: Optional[str] = None,
        element_weight_col: Optional[str] = None,
        zone_id_col: Optional[str] = None,
        target_crs: Optional[str] = None,
    ) -> None:

        self.element_gdf = element_gdf.copy()
        self.zone_gdf = zone_gdf.copy()
        self.element_type_col = element_type_col
        self.element_weight_col = element_weight_col
        self.zone_id_col = zone_id_col
        self.target_crs = target_crs

        self._validate_inputs()
        self._validate_zone_id()
        self._validate_and_align_crs()

    @staticmethod
    def _geometry_element_value(gdf: gpd.GeoDataFrame) -> pd.Series:
        """
        Compute the composition value for each geometry in a GeoDataFrame.

        The metric depends on geometry type:
        - points -> 1 per feature
        - lines -> geometry length
        - polygons -> geometry area
        """
        geom_types = gdf.geom_type

        if geom_types.isin(["Point", "MultiPoint"]).all():
            return pd.Series(1.0, index=gdf.index, dtype=float)
        elif geom_types.isin(["LineString", "MultiLineString"]).all():
            return gdf.length.astype(float)
        elif geom_types.isin(["Polygon", "MultiPolygon"]).all():
            return gdf.area.astype(float)
        else:
            raise ValueError(f"Unsupported or mixed geometry types for composition value calculation: {geom_types.unique().tolist()}")


    def _validate_inputs(self) -> None:
        """
        Validate required columns and basic GeoDataFrame assumptions.
        """
        if self.element_type_col is not None:
            if self.element_type_col not in self.element_gdf.columns:
                raise ValueError(f"`element_type_col` '{self.element_type_col}' not found in `element_gdf`.")
        if self.element_weight_col is not None:
            if self.element_weight_col not in self.element_gdf.columns:
                raise ValueError(f"`element_weight_col` '{self.element_weight_col}' not found in `element_gdf`.")
        if self.zone_gdf.empty:
            raise ValueError("`zone_gdf` must not be empty.")
        if self.element_gdf.empty:
            raise ValueError("`element_gdf` must not be empty.")

    def _validate_zone_id(self) -> None:
        """
        Ensure that a valid zone ID column exists in `zone_gdf`.

        If `zone_id_col` is None, a new column named ``'__zone_id'`` is created
        from the index. If a column name is provided, it must already exist.
        """
        if self.zone_id_col is None:
            self.zone_id_col = "__zone_id"
            self.zone_gdf[self.zone_id_col] = self.zone_gdf.index
        elif self.zone_id_col not in self.zone_gdf.columns:
            raise ValueError(f"`zone_id_col` '{self.zone_id_col}' not found in `zone_gdf` columns.")

    def _validate_and_align_crs(self):
        """
        Validate CRS information and align both GeoDataFrames.

        If ``self.target_crs`` is provided, both GeoDataFrames are reprojected to
        that CRS when needed. Otherwise, both GeoDataFrames must already share the
        same CRS.

        This method also requires the working CRS to be projected, because later
        area and length calculations are performed in planar units.
        """
        # Validate CRS existence
        if self.element_gdf.crs is None:
            raise ValueError("`element_gdf` has no CRS.")
        if self.zone_gdf.crs is None:
            raise ValueError("`zone_gdf` has no CRS.")

        element_crs = pyproj.CRS.from_user_input(self.element_gdf.crs)
        zone_crs = pyproj.CRS.from_user_input(self.zone_gdf.crs)

        # Case 1: target CRS provided
        if self.target_crs is not None:
            target_crs = pyproj.CRS.from_user_input(self.target_crs)

            if not target_crs.is_projected:
                raise ValueError(
                    "`target_crs` must be projected because area and length "
                    f"calculations require a projected CRS, got: {target_crs.to_string()}"
                )

            if not element_crs.equals(target_crs):
                self.element_gdf = self.element_gdf.to_crs(target_crs)
            if not zone_crs.equals(target_crs):
                self.zone_gdf = self.zone_gdf.to_crs(target_crs)
            self.target_crs = target_crs

        # Case 2: no target CRS
        # Ensure both CRS are identical
        else:
            if not element_crs.equals(zone_crs):
                raise ValueError(f"CRS mismatch between `element_gdf` and `zone_gdf`: {element_crs.to_string()} vs {zone_crs.to_string()}")
            if not element_crs.is_projected:
                raise ValueError(f"CRS must be projected because area and length calculations require planar units, got: {element_crs.to_string()}")

    def _compute_zone_area(self) -> pd.Series:
        """
        Compute zone area indexed by zone ID.
        """
        zone_area = self.zone_gdf[[self.zone_id_col]].copy()
        zone_area["zone_area"] = self.zone_gdf.area.astype(float)

        if zone_area[self.zone_id_col].duplicated().any():
            raise ValueError("Zone IDs must be unique in `zone_gdf`.")
        return zone_area.set_index(self.zone_id_col)["zone_area"]

    def zonal_composition(self) -> gpd.GeoDataFrame:
        """
        Intersect elements with zones and compute the composition value.
        """
        # Geometry overlay
        zone_comp = gpd.overlay(
            self.element_gdf,
            self.zone_gdf,
            how = "intersection",
            keep_geom_type = True,
            make_valid = True,
        )
        zone_comp["__comp_value"] = self._geometry_element_value(zone_comp)

        if self.element_weight_col is not None:
            zone_comp["__comp_value_weighted"] = zone_comp["__comp_value"].mul(zone_comp[self.element_weight_col])

        # Sort results
        sort_by_cols = ([self.zone_id_col]
            if self.element_type_col is None
            else [self.zone_id_col, self.element_type_col]
        )
        zone_comp = zone_comp.sort_values(by = sort_by_cols, ignore_index = True)

        return zone_comp

    def compute_composition(
        self,
        density: bool = True,
        mix_index: bool = False,
        mix_index_normalized: bool = False,
    ) -> pd.DataFrame:
        """
        Compute zonal composition by element type.

        Parameters
        ----------
        density
            If True, divide each composition value by the corresponding zone area.
        mix_index
            If True, append a `mix_index` column using `entropy_mix_index`.
        mix_index_normalized
            Whether to normalize row values before computing the entropy mix index.

        Returns
        -------
        pandas.DataFrame
            A table with one column per element type.
            Optionally includes a `mix_index` column.
        """
        #
        zone_comp = self.zonal_composition()

        # Whether consider element weights
        comp_val_col = ("__comp_value"
            if self.element_weight_col is None
            else "__comp_value_weighted"
        )

        # Whether consider element types
        if self.element_type_col is None:
            compo_df = (
                zone_comp
                .groupby(by = self.zone_id_col, as_index = True)
                .agg({comp_val_col : 'sum'})
            )
        else:
            # Pivot table
            compo_df = (
                zone_comp
                .pivot_table(
                    index = self.zone_id_col,
                    columns = self.element_type_col,
                    values = comp_val_col,
                    aggfunc = "sum",
                    fill_value = 0.0,
                )
                .sort_index()
            )

        # Ensure plain column index instead of a named index if desired.
        compo_df.columns.name = None

        # Compute density, element value / zone area
        if density:
            zone_area = self._compute_zone_area()
            compo_df = compo_df.div(zone_area, axis=0)

        # Compute entropy mix index
        if mix_index:
            if self.element_type_col is None:
                raise ValueError("Entropy mix index can not be computed if `element_type_col` is not given.")

            compo_df["mix_index"] = compo_df.apply(
                lambda row: entropy_mix_index(
                    row,
                    normalized = mix_index_normalized,
                ),
                axis = 1,
            )

        # Index name
        compo_df.index.name = self.zone_id_col
        compo_df = compo_df.sort_index().reset_index(drop=False)

        return compo_df
# ======================================================================================================================