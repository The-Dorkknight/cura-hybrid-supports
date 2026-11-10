# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.

from . import HybridSupportsExtension
from . import HybridSupportsTool


def getMetaData():
    return {
        "tool": {
            "name": "Hybrid Supports",
            "description": "Hollow tower supports with gussets and a trapezoid or conforming head (H)",
            "icon": "tool_icon.svg",
            "tool_panel": "HybridSupportsTool.qml",
            "weight": 5,
        }
    }


def register(app):
    return {
        "tool": HybridSupportsTool.HybridSupportsTool(),
        "extension": HybridSupportsExtension.HybridSupportsExtension(),
    }
