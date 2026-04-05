#!/usr/bin/env python3

"""Generate documentation for all modules from Lightspeed Core Stack service."""

import ast
import os
from pathlib import Path

DIRECTORIES = ["src", "tests/unit", "tests/integration", "tests/e2e"]


def generate_docfile(directory):
    """
    Write or overwrite a README.md in the current working directory with module docstring summaries.

    The file will begin with a header indicating the provided `directory` path.
    For each `.py` file in the current working directory the function writes a
    second-level Markdown header linking to the file, then writes the first
    line of the module docstring if present, and finally writes the filename as
    a separate entry.
    """
    with open("README.md", "w", encoding="utf-8", newline="\n") as indexfile:
        print(
            f"# List of source files stored in `{directory}` directory",
            file=indexfile,
        )
        print(file=indexfile)
        files = sorted(os.listdir())

        for file in files:
            if file.endswith(".py"):
                print(f"## [{file}]({file})", file=indexfile)
                with open(file, encoding="utf-8") as fin:
                    source = fin.read()
                try:
                    mod = ast.parse(source)
                    doc = ast.get_docstring(mod)
                except SyntaxError:
                    doc = None
                if doc:
                    print(doc.splitlines()[0], file=indexfile)
                print(file=indexfile)


def generate_documentation_on_path(path):
    """Generate documentation for all the sources found in path.

    This function generate README.md for Python sources in the given directory.

    Parameters:
    ----------
        path (str or os.PathLike): Directory in which to generate the README.md file.
    """
    directory = path
    cwd = os.getcwd()
    os.chdir(directory)
    print(f"[gendoc] Generating README.md in: {directory}")

    try:
        generate_docfile(directory)
    finally:
        os.chdir(cwd)


def main():
    """Entry point to this script, regenerates documentation in all directories."""
    for directory in DIRECTORIES:
        generate_documentation_on_path(f"{directory}/")
        for path in Path(directory).rglob("*"):
            if path.is_dir():
                # LCORE-679: Script to generate documentation should create
                #            README.md files just for source modules
                if (
                    path.name == "lightspeed_stack.egg-info"
                    or path.name == "__pycache__"
                    or ".ruff_cache" in str(path)
                    or ".mypy_cache" in str(path)
                ):
                    continue
                generate_documentation_on_path(path)


if __name__ == "__main__":
    main()
