import geopandas as gpd
import pandas as pd

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingUtils,
    QgsVectorFileWriter,
    QgsWkbTypes,
)

from .zone_composition import ZoneComposition


class ZoneCompositionAlgorithm(QgsProcessingAlgorithm):
    INPUT_ELEMENTS = "INPUT_ELEMENTS"
    INPUT_ZONES = "INPUT_ZONES"
    ELEMENT_TYPE_FIELD = "ELEMENT_TYPE_FIELD"
    ELEMENT_WEIGHT_FIELD = "ELEMENT_WEIGHT_FIELD"
    ZONE_ID_FIELD = "ZONE_ID_FIELD"
    TARGET_CRS = "TARGET_CRS"
    DENSITY = "DENSITY"
    MIX_INDEX = "MIX_INDEX"
    MIX_INDEX_NORMALIZED = "MIX_INDEX_NORMALIZED"
    OUTPUT = "OUTPUT"

    def name(self):
        return "compute_zone_composition"

    def displayName(self):
        return "Compute Zone Composition"

    def group(self):
        return "Zone Composition"

    def groupId(self):
        return "zonecomposition"

    def shortHelpString(self):
        return (
            "Overlay element and zone layers, then compute zone-level composition "
            "statistics with optional density and entropy mix index."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ELEMENTS,
                "Element layer",
                [QgsProcessing.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_ZONES,
                "Zone layer (polygon)",
                [QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ELEMENT_TYPE_FIELD,
                "Element type field (optional)",
                parentLayerParameterName=self.INPUT_ELEMENTS,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ELEMENT_WEIGHT_FIELD,
                "Element weight field (optional)",
                parentLayerParameterName=self.INPUT_ELEMENTS,
                type=QgsProcessingParameterField.Numeric,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.ZONE_ID_FIELD,
                "Zone ID field (optional; defaults to index)",
                parentLayerParameterName=self.INPUT_ZONES,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                "Target projected CRS (optional)",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DENSITY,
                "Compute density (divide by zone area)",
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.MIX_INDEX,
                "Compute entropy mix index",
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.MIX_INDEX_NORMALIZED,
                "Normalize row values before mix index",
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Output table",
                type=QgsProcessing.TypeVector,
            )
        )

    def _export_layer_to_gdf(self, layer, context, stem):
        # Build a deterministic temp path that GDAL can open.
        safe_stem = "".join(ch if ch.isalnum() else "_" for ch in stem)
        gpkg_path = QgsProcessingUtils.generateTempFilename(f"{safe_stem}.gpkg")

        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "GPKG"
        save_options.fileEncoding = "UTF-8"
        save_options.layerName = safe_stem
        write_result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            gpkg_path,
            context.transformContext(),
            save_options,
        )
        if write_result[0] != QgsVectorFileWriter.NoError:
            raise QgsProcessingException(f"Failed to export layer '{stem}' to temporary file: {write_result[1]}")

        return gpd.read_file(gpkg_path)

    @staticmethod
    def _qvariant_for_dtype(dtype) -> QVariant.Type:
        if pd.api.types.is_bool_dtype(dtype):
            return QVariant.Bool
        if pd.api.types.is_integer_dtype(dtype):
            return QVariant.LongLong
        if pd.api.types.is_float_dtype(dtype):
            return QVariant.Double
        return QVariant.String

    @staticmethod
    def _python_value(value):
        if value is None:
            return None
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                return value
        return value

    def processAlgorithm(self, parameters, context, feedback):
        element_layer = self.parameterAsVectorLayer(parameters, self.INPUT_ELEMENTS, context)
        zone_layer = self.parameterAsVectorLayer(parameters, self.INPUT_ZONES, context)
        element_type_field = self.parameterAsString(parameters, self.ELEMENT_TYPE_FIELD, context) or None
        element_weight_field = self.parameterAsString(parameters, self.ELEMENT_WEIGHT_FIELD, context) or None
        zone_id_field = self.parameterAsString(parameters, self.ZONE_ID_FIELD, context) or None
        density = self.parameterAsBoolean(parameters, self.DENSITY, context)
        mix_index = self.parameterAsBoolean(parameters, self.MIX_INDEX, context)
        mix_index_normalized = self.parameterAsBoolean(parameters, self.MIX_INDEX_NORMALIZED, context)
        target_crs_obj = self.parameterAsCrs(parameters, self.TARGET_CRS, context)

        if element_layer is None:
            raise QgsProcessingException("Element layer is required.")
        if zone_layer is None:
            raise QgsProcessingException("Zone layer is required.")

        target_crs = None
        if target_crs_obj.isValid():
            target_crs = target_crs_obj.authid() or target_crs_obj.toWkt()

        feedback.pushInfo("Converting input layers to GeoDataFrames...")
        element_gdf = self._export_layer_to_gdf(element_layer, context, "elements")
        zone_gdf = self._export_layer_to_gdf(zone_layer, context, "zones")

        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Running zonal composition computation...")
        try:
            zc = ZoneComposition(
                element_gdf=element_gdf,
                zone_gdf=zone_gdf,
                element_type_col=element_type_field,
                element_weight_col=element_weight_field,
                zone_id_col=zone_id_field,
                target_crs=target_crs,
            )
            result_df = zc.compute_composition(
                density=density,
                mix_index=mix_index,
                mix_index_normalized=mix_index_normalized,
            )
        except Exception as exc:
            raise QgsProcessingException(str(exc)) from exc

        fields = QgsFields()
        for col in result_df.columns:
            fields.append(QgsField(str(col), self._qvariant_for_dtype(result_df[col].dtype)))

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.NoGeometry,
            QgsCoordinateReferenceSystem(),
        )
        if sink is None:
            raise QgsProcessingException("Failed to create output sink.")

        total = len(result_df.index)
        for idx, row in enumerate(result_df.itertuples(index=False, name=None)):
            if feedback.isCanceled():
                break
            feat = QgsFeature(fields)
            feat.setAttributes([self._python_value(v) for v in row])
            sink.addFeature(feat)
            if total > 0:
                feedback.setProgress(int((idx + 1) * 100.0 / total))

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return ZoneCompositionAlgorithm()
