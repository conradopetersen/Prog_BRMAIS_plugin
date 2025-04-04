# -*- coding: utf-8 -*-
"""
/***************************************************************************
 PlanetPlugin
 Plugin QGIS para acesso a imagens da Planet Labs
***************************************************************************/
"""

def classFactory(iface):
    """Carrega a classe PlanetPlugin.
    
    :param iface: Interface QGIS
    :type iface: QgsInterface
    """
    from .planet_plugin import PlanetPlugin
    return PlanetPlugin(iface)