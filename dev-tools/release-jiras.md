# Release JIRAs

Tickets to file for each major/minor release.

Placeholders:

- **{X}** — major version
- **{Y}** — minor version
- **{Z}** — patch version
- **{PRE}** — pre-release suffix (e.g. `rc1`, `rc2`), empty for GA

<!-- no-epic -->

## Proposed JIRAs

<!-- type: Task -->
### LCORE-???? Create release branch for lightspeed-stack

**Description**: Create the `release/{X}.{Y}` branch for lightspeed-stack to establish the new release stream.

**Scope**:

- Create `release/{X}.{Y}` branch from `main`
- Confirm `src/version.py` on `main` reflects the previous shipped version before branching
- Retarget the previous application's Konflux components to the new release branch

**Acceptance criteria**:

- Branch `release/{X}.{Y}` exists on `lightspeed-core/lightspeed-stack`
- CI pipelines pass on the new branch
- Konflux components for the previous minor are retargeted from `main` to the release branch

<!-- type: Task -->
### LCORE-???? Create release branch for rag-content

**Description**: Create the `release/{X}.{Y}` branch for rag-content to establish the new release stream.

**Scope**:

- Create `release/{X}.{Y}` branch from `main`
- Retarget Konflux `rag-content-*` components for the previous minor to the new release branch

**Acceptance criteria**:

- Branch `release/{X}.{Y}` exists on `lightspeed-core/rag-content`
- CI pipelines pass on the new branch
- Konflux rag-content components for the previous minor are retargeted from `main` to the release branch

<!-- type: Task -->
### LCORE-???? Update version string in src/version.py

**Description**: Bump `__version__` in `src/version.py` on `main` to the new release version and update all files that reference the version.

**Scope**:

- Set `__version__` to `{X}.{Y}.{Z}{PRE}` (or `{X}.{Y}.{Z}`) on `main`
- Update version references in tests and docs per the list in `docs/releasing.md`
- Confirm `pdm show --version` matches the new version string

**Acceptance criteria**:

- `src/version.py` contains the correct `__version__` value
- All version references across the codebase are consistent
- CI version validation passes

<!-- type: Task -->
### LCORE-???? Regenerate OpenAPI specification

**Description**: Regenerate `docs/openapi.json` after the version bump so the published spec reflects the new release version.

**Scope**:

- Run `make schema` to regenerate the OpenAPI spec
- Verify the version field in the generated spec matches `src/version.py`
- Commit the updated `docs/openapi.json`

**Acceptance criteria**:

- `docs/openapi.json` reflects the new version
- No unintended schema changes beyond the version bump

<!-- type: Task -->
### LCORE-???? Create release tag for lightspeed-stack

**Description**: Create a git tag on lightspeed-stack to trigger the release build pipeline and mark the release point.

**Scope**:

- Create tag `{X}.{Y}.{Z}{PRE}` (PEP 440 format, no separator) on the appropriate branch
- Draft a new GitHub release from the tag
- Verify the tag triggers `build_and_push_release.yaml`

**Acceptance criteria**:

- Git tag exists and points to the correct commit
- GitHub Release is published with auto-generated release notes

<!-- type: Task -->
### LCORE-???? Create release tag for rag-content

**Description**: Create a git tag on rag-content to trigger the release build pipeline and mark the release point.

**Scope**:

- Create tag `{X}.{Y}.{Z}{PRE}` (PEP 440 format, no separator) on the appropriate branch
- Draft a new GitHub release from the tag

**Acceptance criteria**:

- Git tag exists and points to the correct commit
- GitHub Release is published with auto-generated release notes

<!-- type: Task -->
### LCORE-???? Generate release notes for lightspeed-stack

**Description**: Generate and publish release notes for the lightspeed-stack release.

**Scope**:

- Use GitHub Releases "Generate release notes" to produce a changelog
- Review and edit the auto-generated notes for clarity
- Publish the release on GitHub

**Acceptance criteria**:

- Release notes are published on the GitHub Releases page
- Notes accurately summarize changes since the previous release

<!-- type: Task -->
### LCORE-???? Generate release notes for rag-content

**Description**: Generate and publish release notes for the rag-content release.

**Scope**:

- Use GitHub Releases "Generate release notes" to produce a changelog
- Review and edit the auto-generated notes for clarity
- Publish the release on GitHub

**Acceptance criteria**:

- Release notes are published on the GitHub Releases page
- Notes accurately summarize changes since the previous release

<!-- type: Task -->
### LCORE-???? Publish release images to Quay.io for lightspeed-stack

**Description**: Verify that release container images for lightspeed-stack are built and pushed to Quay.io.

**Scope**:

- Confirm the git tag push triggered `build_and_push_release.yaml`
- Verify images are available at `quay.io/lightspeed-core/lightspeed-stack` with the tag name and `latest`
- Smoke-test the published image

**Acceptance criteria**:

- Image is available on Quay.io with the release tag (e.g. `{X}.{Y}.{Z}{PRE}`)
- `latest` tag is updated
- Image starts and passes basic health check

<!-- type: Task -->
### LCORE-???? Publish release images to Quay.io for rag-content

**Description**: Verify that release container images for rag-content are built and pushed to Quay.io.

**Scope**:

- Confirm the git tag push triggered the rag-content build pipeline
- Verify images are available on Quay.io for all compute flavors (cpu, cuda-12.9, etc.)
- Smoke-test the published images

**Acceptance criteria**:

- Images are available on Quay.io with the release tag for each compute flavor
- Images start and pass basic health check

<!-- type: Task -->
### LCORE-???? Publish release images to registry.redhat.io

**Description**: Promote release images to `registry.redhat.io` via Konflux for both lightspeed-stack and rag-content.

**Scope**:

- Update RPA `componentTags` to include the new immutable tag (e.g. `{X}.{Y}.{Z}{PRE}`) for all shipping components
- Select the correct Snapshot in the Konflux Application
- Create a `Release` referencing the Snapshot and the application's `ReleasePlan`
- Verify tags on `registry.redhat.io` after the release pipeline completes

**Acceptance criteria**:

- Immutable tag (e.g. `{X}.{Y}.{Z}{PRE}`) is present on `registry.redhat.io` for lightspeed-stack and all rag-content flavors
- Floating tags (`{X}.{Y}-latest`, `latest` if applicable) are updated
- Images are pullable from `registry.redhat.io`

<!-- type: Task -->
### LCORE-???? Update docs/versions document

**Description**: Update the `docs/versions*` document to reflect the new release version and any version-specific notes.

**Scope**:

- Add the new version entry to the versions document
- Update supported-versions matrix if applicable
- Note any deprecations or breaking changes for this version

**Acceptance criteria**:

- Versions document includes the new release
- Version information is accurate and consistent with the shipped artifacts
