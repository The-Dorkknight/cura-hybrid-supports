# Contributing

Thanks for helping. Bug reports with a model file (or a description of the shape) and the settings you used are the most useful thing right now, especially from people who have tried the plugin on a real print.

- **Issues:** use the bug report form. Include the plugin version (shown at the top of the tool panel), your Cura version and OS, and the relevant part of `cura.log` (*Help > Show Configuration Folder*).
- **Pull requests:** keep `hybrid_core.py` free of Cura imports so it stays testable, and add a test in `tests/test_core.py` for geometry changes. Run `python3 -m pytest tests -q` before submitting.
- **Hardware floor:** the plugin should stay usable on a 7th-gen Core i3. Run `python3 tools/bench.py` if you touch the hot paths.

## Licence of contributions

By contributing, you agree that your contribution is licensed under the same [PolyForm Noncommercial 1.0.0 licence](LICENSE.md) as the rest of the project.
