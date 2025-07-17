# Lightspeed Core Stack installation on Linux

## Prerequisites

- git
- Python 3.12 or 3.13
- pip

## Installation steps

1. `pip install --user uv`
1. `uv --version` -- should return no error
1. Clone the repo to the current dir:
`git clone https://github.com/lightspeed-core/lightspeed-stack`
1. `cd service`
1. `uv info` -- should return no error
1. `uv install`

Note: `pip` installs the `uv` binary into ~/.local/bin, which is often missing from `$PATH` on fresh distributions. If the `uv` command is not found, please check if `$PATH` environment variable is set correctly.
