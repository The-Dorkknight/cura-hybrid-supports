# Third-party notices

The [PolyForm Noncommercial licence](LICENSE.md) covers only Matthew Armstrong's own code in this repository. Everything below keeps its own licence; see the linked projects for their terms.

| Component | Used how | Licence |
|---|---|---|
| [UltiMaker Cura](https://github.com/Ultimaker/Cura) and [Uranium](https://github.com/Ultimaker/Uranium) | The plugin runs inside Cura and calls its public plugin APIs. No Cura or Uranium code is copied into this repository; scene-node creation follows the same pattern as Cura's own *Support Blocker* tool. | LGPL-3.0 or later |
| [CuraEngine](https://github.com/Ultimaker/CuraEngine) | Read (not copied) to confirm how support meshes and anti-overhang meshes are handled. | AGPL-3.0 |
| [NumPy](https://numpy.org) | Geometry maths; ships with Cura. | BSD-3-Clause |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) / Qt | Cura's UI toolkit, used through Cura. | GPL-3.0 / commercial (Cura's distribution) |
| [matplotlib](https://matplotlib.org), [pytest](https://pytest.org) | Development only (renders and tests), not shipped in the plugin. | PSF-based / MIT |

The PolyForm Noncommercial licence text is © PolyForm Project, used as published.

PrusaSlicer's paint-on supports were discussed as background during design; no PrusaSlicer code was used.

This project is not affiliated with, or endorsed by, UltiMaker or Prusa Research.
