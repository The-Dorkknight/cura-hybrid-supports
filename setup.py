# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Shim for tools that still call setup.py; all metadata lives in pyproject.toml.

The Cura plugin itself is installed with the .curapackage, not with pip.
"""
from setuptools import setup

setup()
