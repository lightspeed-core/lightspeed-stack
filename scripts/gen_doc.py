#!/usr/bin/env python3

"""Generate documentation for all modules from Lightspeed Core Stack service."""

import os

import ast
from pathlib import Path

DIRECTORIES = ["src", "tests/unit", "tests/integration", "tests/e2e"]


def generate_docfile(directory):
    """Generate README.md in the CWD."""
    with open("README.md", "w", encoding="utf-8", newline="\n") as indexfile:
        print(
            f"# List of source files stored in `{directory}` directory",
            file=indexfile,
        )
        print("", file=indexfile)
        files = sorted(os.listdir())

        for file in files:
            if file.endswith(".py"):
                print(f"## [{file}]({file})", file=indexfile)
                with open(file, "r", encoding="utf-8") as fin:
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
    """Generate documentation for all the sources found in path."""
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
                if (
                    path.name == "lightspeed_stack.egg-info"
                    or path.name == "__pycache__"
                    or ".ruff_cache" in str(path)
                ):
                    continue
                generate_documentation_on_path(path)


if __name__ == "__main__":
    main()
