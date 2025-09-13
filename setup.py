# setup.py - Build script to support dynamic version extraction in pyproject.toml
# This file ensures the local project path is added to sys.path during the build process,
# allowing import of the 'api_quotex' module for reading __version__.

import os
import sys

# Add the current directory to sys.path to enable local module imports during build
# This resolves the ModuleNotFoundError for 'api_quotex' in the isolated build environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import setuptools and run the setup function
# setuptools will automatically read and apply the configuration from pyproject.toml
from setuptools import setup

# No additional attributes needed here; pyproject.toml handles the rest
# This minimal setup ensures compatibility without overriding pyproject.toml
setup()
