from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .zone_composition_algorithm import ZoneCompositionAlgorithm


class ZoneCompositionProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(ZoneCompositionAlgorithm())

    def id(self):
        return "zonecomposition"

    def name(self):
        return "Zone Composition"

    def icon(self):
        return QIcon()

    def longName(self):
        return self.name()
