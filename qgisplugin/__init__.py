def classFactory(iface):
    from .plugin import ZoneCompositionPlugin

    return ZoneCompositionPlugin(iface)
