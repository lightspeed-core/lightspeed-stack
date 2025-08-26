"""Service version that is read by project manager tools."""

# this should be the only version value used in all source codes
# please don't use any other "magic value" defined elsewhere
#
# See: pyproject.toml and these settings:
# dynamic = ["version"]
#
# [tool.pdm.version]
# source = "file"
# path = "src/version.py"
__version__ = "0.2.0"
