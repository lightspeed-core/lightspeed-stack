# Patches for bundled Python packages

Patches in this directory are applied to installed Python packages while
building the container image (see `deploy/lightspeed-stack/Containerfile`).
Use them only for urgent fixes that cannot wait for a new upstream release,
and remove them once the dependency is upgraded to a version with the fix.

Layout:

- One subdirectory per patched package, named after the package's import
  directory in `site-packages` (for example `llama_stack`).
- Patch files are named `NNN-short-description.patch` and are applied in
  numeric order.
- Paths in the patch are relative to the package directory and use `a/` and
  `b/` prefixes; they are applied with
  `patch -p1 -d site-packages/<package>`.
- Begin each patch with a description that links to the upstream change.
