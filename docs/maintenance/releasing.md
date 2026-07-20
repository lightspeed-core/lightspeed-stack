# Releasing

<!-- vim-markdown-toc GFM -->

* [Semantic versioning](#semantic-versioning)
    * [Rules (concise)](#rules-concise)
* [Prerequisites](#prerequisites)
* [Update version in sources](#update-version-in-sources)
* [Regenerate OpenAPI specification](#regenerate-openapi-specification)
* [Publishing the Python package on PyPi](#publishing-the-python-package-on-pypi)
    * [Cleanup the whole repository](#cleanup-the-whole-repository)
    * [Build the distribution archive](#build-the-distribution-archive)
    * [Upload distribution archives into Python registry](#upload-distribution-archives-into-python-registry)
    * [Check packages on PyPI and Test PyPI](#check-packages-on-pypi-and-test-pypi)
* [New tag and release on GitHub](#new-tag-and-release-on-github)
    * [Create a new tag](#create-a-new-tag)
    * [Update link in `README.md`](#update-link-in-readmemd)
* [Konflux release organization](#release-organization)
    * [Conventions](#conventions)
    * [Goals of the layout](#1-goals-of-the-layout)
    * [Konflux](#2-konflux)
        * [Applications and components](#21-applications-and-components)
        * [ReleasePlan per application and connection to RPA](#22-releaseplan-per-application-and-connection-to-rpa)
        * [ReleasePlanAdmission (RPA)](#23-releaseplanadmission-rpa)
    * [Comet (container catalog): what users pull](#3-comet-container-catalog-what-users-pull)
        * [Lightspeed Stack](#31-lightspeed-stack)
        * [Lightspeed RAG Tool (and compute flavors)](#32-lightspeed-rag-tool-and-compute-flavors)
    * [How releases work in practice](#4-how-releases-work-in-practice)
        * [Snapshot selection and creating a `Release` for an Application](#41-snapshot-selection-and-creating-a-release-for-an-application)
        * [Micro releases (patch and RC)](#42-micro-releases-patch-and-rc)
        * [Minor releases (new minor branch, e.g. 0.7)](#43-minor-releases-new-minor-branch-eg-07)
    * [Checklists for release engineers](#5-checklists-for-release-engineers)
        * [Micro release checklist (patch or RC)](#51-micro-release-checklist-patch-or-rc)
        * [Minor release checklist (new minor branch)](#52-minor-release-checklist-new-minor-branch)
        * [Invariants (check on every ship)](#53-invariants-check-on-every-ship)
    * [Parallel publishing paths](#6-parallel-publishing-paths)

<!-- vim-markdown-toc -->

## Semantic versioning

Each LCORE release is identified by semantic version.

Semantic Versioning (SemVer) is a versioning scheme that conveys meaning about
changes in a release using a three-part number: `MAJOR.MINOR.PATCH`. In LCORE it
is possible to append a *release candidate* number in a form `MAJOR.MINOR.PATCHrcNUMBER`.



### Rules (concise)

* Format: MAJOR.MINOR.PATCH (e.g., 2.5.1).

* Increment MAJOR when you make incompatible API changes.

* Increment MINOR when you add functionality in a backwards-compatible manner.

* Increment PATCH when you make backwards-compatible bug fixes.

* Release candidates, e.g. 0.6.0rc1 (there is no hyphen!)

* Build metadata: append a plus and metadata ignored for precedence (e.g.,
  1.0.0+20130313144700).

* Precedence: Compare MAJOR, then MINOR, then PATCH numerically; pre-release
  versions have lower precedence than the associated normal version.

## Prerequisites

* Access to https://github.com/lightspeed-core/lightspeed-stack as owner or maintainer
* Access token to https://pypi.org/ and/or to https://test.pypi.org/py
* `git`
* text editor
* basic file system manipulation tools (`cp`, `rm`)

## Update version in sources

First step is to update version in sources. The version is stored in the file `src/version.py`:
https://github.com/lightspeed-core/lightspeed-stack/blob/main/src/version.py

Then update the version in other files, especially in tests:

1. src/observability/README.md
1. tests/e2e/features/info.feature
1. tests/integration/endpoints/test_rlsapi_v1_integration.py
1. tests/unit/app/endpoints/conftest.py
1. tests/unit/observability/test_rlsapi.py

NOTE: there's a task to make this step easier by using the same `version.py` everywhere:
LCORE-2248: Use only one version value stored in version.py everywhere across the LCORE sources and tests
https://redhat.atlassian.net/browse/LCORE-2248

## Regenerate OpenAPI specification

It is needed to generate OpenAPI specification that is stored in `docs/openapi.json`. In order to do it, run the following command:

```bash
make schema
```

NOTE: there's a task to automate these steps:
LCORE-1647: Automate versioning and changelog generation
https://redhat.atlassian.net/browse/LCORE-1647

## Publishing the Python package on PyPi

To publish the service as an Python package on PyPI to be installable by anyone
(including Konflux hermetic builds), perform the following three steps:

### Cleanup the whole repository

Source and tests folders must contain just source files and README.mds, nothing else. Make sure that all `__pycache__` and `.mypy_cache` directories are deleted (the latest are hidden on Unit systems!)

### Build the distribution archive

```bash
make distribution-archives
```

This command should finish with message:

```text
Successfully built lightspeed_stack-{version}.tar.gz and lightspeed_stack-{version}-py3-none-any.whl
```

Please double check that the `{version}` really contains the correct version number.
Also please make sure that the archive was really built to avoid publishing older one.

### Upload distribution archives into Python registry

```bash
make upload-distribution-archives
```

The Python registry to where the package should be uploaded can be configured
by changing `PYTHON_REGISTRY`. It is possible to select `pypi` or `testpypi`.

You might have your API token stored in file `~/.pypirc`. That file should have
the following form:

```ini
[testpypi]
  username = __token__
  password = pypi-{your-API-token}

[pypi]
  username = __token__
  password = pypi-{your-API-token}
```

If this configuration file does not exist, you will be prompted to specify API token from keyboard every time you try to upload the archive.

### Check packages on PyPI and Test PyPI

* https://pypi.org/project/lightspeed-stack/
* https://test.pypi.org/project/lightspeed-stack/

## New tag and release on GitHub

### Create a new tag

1. Open https://github.com/lightspeed-core/lightspeed-stack in a web browser
1. Go to the *Releases* section and click on *"Draft a new release"*
1. Create a tag, for example `0.6.0rc1` and fill-in release name such as `Lightspeed Stack version 0.6.0rc1`
1. Press the button *"Create a release notes"*
1. Press the button *"Publish release"*

### Update link in `README.md`

At the beggining of `README.md` there's a line:

```text
[![Tag](https://img.shields.io/github/v/tag/lightspeed-core/lightspeed-stack)](https://github.com/lightspeed-core/lightspeed-stack/releases/tag/0.5.0)
```

Update the link on this line, i.e. replace, for example, `0.5.0` by `0.6.0rc1`

## Konflux Release organization

This section describes how Konflux **Applications**, **ReleasePlans**, **components**, **ReleasePlanAdmission (RPA)**, the Comet (catalog) container images, and release practice fit together, and how to perform **micro** and **minor** releases.


#### Conventions

- **Branch naming:** Release branches use the format `**release/<major>.<minor>`** (e.g. `release/0.5`, `release/0.6`). The `main` branch tracks the current development minor. A separate design doc (`docs/design/supporting-backport-changes-for-releases/`) uses `release/x.y.z` (patch-level branches); that convention is aspirational and is **not** currently used by Konflux components or CI pipelines.
- **RC tag format (PEP 440):** Release-candidate tags use `**x.y.zrcN`** with no separator (e.g. `0.6.0rc1`, `0.7.0rc2`). This matches the format in `src/version.py` and PEP 440.
- **Version source of truth:** `src/version.py` (`__version__`) is the single authoritative version string, validated by CI against `pdm show --version`.

---

### Goals of the layout

- **Independent release branches**: Each maintained Git release branch (e.g. `main` for the current minor, `release/0.5` for 0.5.x) can be built and released without blocking the other.
- **Predictable user-facing images**: Comet exposes a fixed set of image repositories and tag conventions so consumers always pull from known Red Hat registry paths.
- **Controlled promotion**: RPA maps Konflux **components** to the **repositories** and **tags** that land on `registry.redhat.io`, so only intended builds are published under `latest`, `x.y-latest`, full versions, and RCs.

---

### Konflux

Konflux groups Lightspeed Core work by **Application** (one per minor release branch), **component** builds inside that application, and **release** wiring: a `**ReleasePlan`** per application in the developer tenant, paired with **ReleasePlanAdmission (RPA)** in the managed tenant so promotions land on the right `registry.redhat.io` paths and tags.

> **Where do these resources live?**
>
> - `**ReleasePlan`** manifests live in the **developer workspace namespace** (`lightspeed-core-tenant`) on Konflux. They are managed via the Konflux UI or `kubectl`/`oc` in that namespace — they are **not** checked into this Git repository.
> - **ReleasePlanAdmission (RPA)** manifests live in the **managed tenant** namespace (controlled by release engineering). Updates require a change request or PR in the managed-tenant configuration repo.
> - **Application** and **Component** definitions live in the same developer workspace namespace. Inspect them with `kubectl get applications,components -n lightspeed-core-tenant`.
> - **Build pipelines** (`.tekton/*.yaml`) and **hermetic build inputs** (`.konflux/`) are checked into this repository.

#### Applications and components

There is **one Konflux application per Lightspeed Core minor release branch** (not one app per patch):


| Application           | Purpose                    | Git revisions                                         |
| --------------------- | -------------------------- | ----------------------------------------------------- |
| `lightspeed-core-0.6` | Current development branch | `lightspeed-stack` and `rag-content` track `**main`** |
| `lightspeed-core-0.5` | Maintained 0.5.x branch    | Same repos track `**release/0.5**`                    |


Each application owns a set of components. There is a single component for lightspeed-stack and for rag-content, there is a component **per compute flavor** for that branch. The tables below reflect the **current** Konflux state (source: `release-structures.txt` at repo root).

**Application `lightspeed-core-0.6`**


| Component                   | Repository                                            | Revision |
| --------------------------- | ----------------------------------------------------- | -------- |
| `lightspeed-stack-0.6`      | `https://github.com/lightspeed-core/lightspeed-stack` | `main`   |
| `rag-content-cpu-0.6`       | `https://github.com/lightspeed-core/rag-content`      | `main`   |
| `rag-content-cuda-12.9-0.6` | `https://github.com/lightspeed-core/rag-content`      | `main`   |


**Application `lightspeed-core-0.5`**


| Component                   | Repository                                            | Revision      |
| --------------------------- | ----------------------------------------------------- | ------------- |
| `lightspeed-stack-0.5`      | `https://github.com/lightspeed-core/lightspeed-stack` | `release/0.5` |
| `rag-content-cpu-0.5`       | `https://github.com/lightspeed-core/rag-content`      | `release/0.5` |
| `rag-content-cuda-12.9-0.5` | `https://github.com/lightspeed-core/rag-content`      | `release/0.5` |


> **Component naming pattern:** RAG components are named `**rag-content-<gpu-flavor>-<minor>`** (e.g. `rag-content-cpu-0.6`, `rag-content-cuda-12.9-0.5`). When a new GPU flavor ships (e.g. `rocm-6.4`, `cuda-13.0`), add a corresponding `rag-content-<flavor>-<minor>` component to each active application and a matching RPA entry.

> **Note:** Each `rag-content-*` component must use the `**rag-content`** repository URL — not the `lightspeed-stack` URL.

**Takeaway:** The **minor version in the application and component names** (`0.5`, `0.6`) ties the Konflux wiring to a **release branch**. Patch and RC versions are expressed in **image tags and RPA mapping**, not by creating a new application for every `0.6.1` or `0.6.0rc1`.

#### ReleasePlan per application and connection to RPA

Konflux ties **testing and releasing to the Application**, not to an individual component in isolation. A `**ReleasePlan`** therefore belongs to **exactly one Application**: it describes how **Snapshots** of *that* application are turned into a release (which pipeline runs, what data flows to the managed release service). You need **one `ReleasePlan` per Lightspeed Core application** — for example one for `lightspeed-core-0.5`, one for `lightspeed-core-0.6`, and another when you add `lightspeed-core-0.7`. A single `ReleasePlan` cannot span two applications.

**ReleasePlanAdmission (RPA)** is the **managed-tenant** object that pairs with the developer-side story: it authorizes **which component names** from the release may be published and **to which `registry.redhat.io` repositories** under **which tags**. Practically, each application's promotion path is "`**ReleasePlan`** (dev) <-> **RPA** (managed)" plus the **component mapping** blocks inside the RPA that list the Konflux component names for that release branch (`lightspeed-stack`, `lightspeed-stack-release-0-5`, `rag-content-cpu-*`, `rag-content-cuda-12.9-*`, ...) and their target URLs.

When the Release Engineer adds a **new** Konflux application for a new minor release branch, they must also add a **new `ReleasePlan`** for that application **and** extend or duplicate **RPA** so the new application's components are admitted without colliding with tags owned by other applications. Keep names, `origin`, and `applications` fields in the RPA aligned with the application you intend to ship so the release service matches the right admission record.

#### ReleasePlanAdmission (RPA)

RPA connects **Konflux components** to **destination repositories** and declares which **component tags** (or tag templates) are written on release.

**Current RPA mapping** (abridged from `release-structures.txt` at repo root; the full manifest lives in the managed tenant:

```yaml
data:
  mapping:
    components:
      # --- 0.6 (current development branch, tracks main) ---
      - name: lightspeed-stack
        repositories:
          - url: registry.redhat.io/lightspeed-core/lightspeed-stack-rhel9
        componentTags:
          - "latest"
          - "0.6-latest"
          - "0.6-{{ git_sha }}"

      - name: rag-content-cpu-0.6
        repositories:
          - url: registry.redhat.io/lightspeed-core/rag-tool-cpu-rhel9
        componentTags:
          - "latest"
          - "0.6-latest"
          - "0.6-{{ git_sha }}"

      - name: rag-content-cuda-12.9-0.6
        repositories:
          - url: registry.redhat.io/lightspeed-core/rag-tool-cuda-12.9-rhel9
        componentTags:
          - "latest"
          - "0.6-latest"
          - "0.6-{{ git_sha }}"

      # --- 0.5 (maintained branch, tracks release/0.5) ---
      - name: lightspeed-stack-release-0-5
        repositories:
          - url: registry.redhat.io/lightspeed-core/lightspeed-stack-rhel9
        componentTags:
          - "0.5.1"
          - "0.5-latest"
          - "0.5-{{ git_sha }}"

      - name: rag-content-cpu-0.5
        repositories:
          - url: registry.redhat.io/lightspeed-core/rag-tool-cpu-rhel9
        componentTags:
          - "0.5.1"
          - "0.5-latest"
          - "0.5-{{ git_sha }}"

      - name: rag-content-cuda-12.9-0.5
        repositories:
          - url: registry.redhat.io/lightspeed-core/rag-tool-cuda-12.9-rhel9
        componentTags:
          - "0.5.1"
          - "0.5-latest"
          - "0.5-{{ git_sha }}"
```

> **Naming divergence:** Konflux component names use `rag-content-<flavor>-<minor>`, while `registry.redhat.io` paths use `rag-tool-<flavor>-rhel9`. The `<flavor>` segment is shared (e.g. `cpu`, `cuda-12.9`).

**Multiple Konflux components** can promote into the **same** registry repository with **different tag sets**, keyed off which release branch produced the build. For example, both `lightspeed-stack` (0.6) and `lightspeed-stack-release-0-5` (0.5) push to `lightspeed-stack-rhel9` but with disjoint tags.

**Takeaway:** RPA is where the Release Engineer enforces "**this** component build from **this** branch gets **these** tags on **this** registry path." When you add a new minor release branch or change RC/GA tagging, RPA must be updated in lockstep with Comet expectations.

---

### Comet (container catalog): what users pull

Comet defines **which container images are productized** and **which tags** appear on `registry.redhat.io` for Lightspeed Core users.

#### Lightspeed Stack

- **Image repository:** `lightspeed-core/lightspeed-stack-rhel9`
- **Architectures:** all supported CPU architectures documented for the product.
- **Version tags:**

  | Tag pattern  | Meaning                                                                                        |
  | ------------ | ---------------------------------------------------------------------------------------------- |
  | `latest`     | Default "current" GA stream for the product (policy defines what commit/build this tracks).    |
  | `x.y-latest` | Floating tag for minor **x.y** (e.g. `0.6-latest`, `0.5-latest`).                              |
  | `x.y.z`      | Immutable **GA** patch release (e.g. `0.5.2`, `0.6.1`).                                        |
  | `x.y.zrcN`   | **Release candidate** (PEP 440, no separator) for a given patch (e.g. `0.6.0rc1`, `0.7.0rc2`). |


#### Lightspeed RAG Tool (and compute flavors)

Multiple repositories follow the same **tag rules** as above, for example:

- `lightspeed-core/rag-tool-cpu-rhel9`
- `lightspeed-core/rag-tool-cuda-12.9-rhel9`
- `lightspeed-core/rag-tool-<gpu-flavor>-rhel9`

**Compute flavor naming** mirrors RHAI base images, for example:

- `rhai/base-image-cuda-12.9-rhel9`, `cuda-13.0`, `rocm-6.4`, `rocm-7.0`, `tpu`, `neuron`, `spyre`, etc.

**Takeaway:** Comet is the **customer-facing contract** (image names + tags). Konflux and RPA exist to **populate** those repositories consistently.

---

### How releases work in practice

#### Snapshot selection and creating a `Release` for an Application

Konflux promotes images only after the Release Engineer explicitly ties a **known-good Application state** to a `**Release`**. That state is recorded in a `**Snapshot**` custom resource: for a given **Application** (for example `lightspeed-core-0.6`), the Snapshot lists **which components** are in scope and **which built image** (digest) each one contributes for this promotion. A micro or minor ship for that branch always goes through **pick Snapshot -> create `Release`** in that application's workspace.

**Where Snapshots come from**

- Snapshots are typically **produced by automation** when integration or release-prep pipelines for that **Application** succeed (all required components built and tests you configured have passed). The exact trigger is defined in your Konflux pipeline and integration setup.
- You can also **inspect existing Snapshots** in the namespace at any time; each Snapshot is a candidate "bill of materials" for one promotion.

**How to select the Snapshot**

1. Open the Konflux **Application** you are shipping (e.g. `**lightspeed-core-0.6`** for the 0.6 release branch).
2. Go to the **Snapshots** view for that application (Konflux UI) or list Snapshot objects in your **workspace namespace**: `kubectl get snapshots -n lightspeed-core-tenant`.
3. Choose the Snapshot whose **component entries** match the commits and image digests you intend to release (compare Git revision, pipeline run, or digests to your ticket / build record). Only Snapshots that belong to **this** Application should be used; do not point a `Release` at a Snapshot from another application.

**How to create the `Release`**

1. Confirm the `**ReleasePlan**` name for this Application (one plan per application) — for example the plan wired to `lightspeed-core-0.6`.
2. Create a `**Release**` resource in the **developer workspace namespace** where the Application and `ReleasePlan` live. The `Release` must reference **by name**:
  - the `**ReleasePlan`** to run (defines the release pipeline and handoff to the managed service), and
  - the `**Snapshot**` you selected above (the frozen set of images for this promotion).
3. Use either the Konflux **UI flow** ("create release" from the chosen Snapshot) or `**kubectl` / `oc apply`** with a manifest; field names and optional labels (author, automated vs manual) are spelled out in Red Hat's **[Creating a release](https://konflux.pages.redhat.com/docs/users/releasing/create-release.html)** (public mirror: [konflux-ci.dev](https://konflux-ci.dev/docs/releasing/create-release/)).

**After you create the `Release`**

The Konflux **release service** reconciles the `Release`, pairs it with **ReleasePlanAdmission** on the managed side, runs the release pipeline, and — on success — publishes images to `registry.redhat.io` with the tags your RPA allows.

> **Failure recovery:** If the release pipeline fails:
>
> 1. **Check RPA coverage first** — a missing `componentTag` is the most common cause of tag-write failures.
> 2. **Do not mutate the existing Snapshot** to "retry" a promotion. Fix the underlying issue, then either wait for a new Snapshot or trigger a rebuild.
> 3. **Create a new `Release`** referencing the new (or same, if the fix was RPA-only) Snapshot.
> 4. **Partially-published tags:** If some tags were written before the failure, the new `Release` will overwrite floating tags (e.g. `x.y-latest`) and add the missing immutable tags. Confirm all expected tags are present after the retry succeeds.

**New tags must appear in the RPA**

The admission record is tag-driven: each component block lists `**componentTags`** (and repositories) the release is **allowed** to write. When you ship a **new** tag value for the first time — typically a new **immutable** GA or RC tag (`0.6.1`, `0.6.0rc1`, ...), or a deliberate change to which **floating** tags are updated — the Release Engineer must **add or adjust those tag strings in the RPA** for every affected Konflux component **before** the managed pipeline can succeed (or in the same approved change train as the `Release`, per your process). If the tag is missing from the admission mapping, the release may **fail** or **skip** writing that tag even when the `**Snapshot`** and `**Release**` are otherwise correct. Comet must already allow that tag shape for the product image if policy requires it.

#### Micro releases (patch and RC)

**Patch GA** (e.g. `0.5.2`, `0.6.1`) and **RC** (e.g. `0.6.0rc1`) are **micro releases** on an **existing** minor release branch.

Typical flow:

1. **Version bump**: Update `src/version.py` to the target version (e.g. `__version__ = "0.6.1"` or `__version__ = "0.6.0rc1"`). Commit and push to the correct branch. CI validates the version string via `pdm show --version`.
2. **Git**: Follow your team's tag or release-branch policy on the correct branch (`release/0.5` for 0.5.x, `main` for 0.6.x).
3. **GitHub Actions (Quay)**: If you push a **git tag**, `.github/workflows/build_and_push_release.yaml` automatically builds and pushes the image to `quay.io/lightspeed-core/lightspeed-stack` with the tag name **and** `latest`. This is **independent** of the Konflux pipeline (which publishes to `registry.redhat.io`). Both paths should produce equivalent images.
4. **Konflux**: The **same** application/components for that branch (`lightspeed-core-0.5` / `lightspeed-stack-0.5`, etc.) pick up the new commit from the configured revision.
5. **Build & test**: Pipelines produce candidate images for each component; integration completes so a **Snapshot** exists for that Application.
6. **RPA tags**: The Release Engineer updates **ReleasePlanAdmission** so `**componentTags`** for each shipping component include every **new** tag the pipeline must write for this micro release (immutable patch/RC and any floating-tag changes).
7. **Select Snapshot and create `Release`**: Pick the correct Application (`lightspeed-core-0.5` or `lightspeed-core-0.6`) using the Snapshot that captures those builds.
8. **Verify registry tags**: When the release pipeline succeeds, confirm the new **immutable** tag (`0.5.2`, `0.6.0rc1`, ...) and **floating** tags (`0.5-latest`, `0.6-latest`, `latest` if appropriate) on `registry.redhat.io` match policy. If something is missing, check RPA coverage before retrying with a new Snapshot/`Release`.

You **do not** create a new Konflux application for each `0.6.0rc1` or `0.5.2`; you reuse the **0.6** or **0.5** application and drive promotion with **Snapshot -> `Release` -> `ReleasePlan` / RPA**.

#### Minor releases (new minor branch, e.g. 0.7)

A **minor** bump (e.g. **0.7**) means a **new maintained API/product stream** carried on a new **release branch** (Git and Konflux application for that minor). That implies:

1. **Version bump on `main`**
  Update `src/version.py` to the new minor's first pre-release (e.g. `__version__ = "0.7.0rc1"`) and commit. The old branch's `version.py` should already reflect its latest shipped version.
2. **Branch promotion for the previous "current" branch**
  When `main` becomes **0.7** development, the **0.6** work should be maintained on a branch named `**release/0.6`** (analogous to `release/0.5` today).
3. **New Konflux application for the new branch**
  Create `**lightspeed-core-0.7`** with components:
  - `lightspeed-stack-0.7` -> `lightspeed-stack` @ `**main**`
  - `rag-content-cpu-0.7` -> `rag-content` @ `**main**`
  - `rag-content-cuda-12.9-0.7` -> `rag-content` @ `**main**`
  - (plus any additional compute-flavor components that are active)
4. **Retarget the previous branch's application**
  Update `**lightspeed-core-0.6`** components so revisions point to `**release/0.6**` (instead of `main`) for all repos — mirroring how **0.5** is wired today.
5. **Comet**
  Ensure catalog entries and tag patterns cover `**0.7-*`** (`0.7-latest`, future `0.7.z`, `0.7.zrcN`) alongside existing release branches.
6. **RPA**
  - Add (or split) **component mappings** and `**componentTags`** so 0.7 builds may publish tags such as `0.7-latest`, `0.7-{{ git_sha }}`, and eventually `0.7.z` / `0.7.zrcN`, without clobbering `0.6-*` or `0.5-*`. Every tag the release pipeline should write for a new minor must be **listed in the RPA** for the corresponding Konflux component names.
  - Decide how `**latest`** moves: usually it tracks the **newest supported default release branch** (often the newest minor GA); the Release Manager documents that policy.
7. **Release plans / admissions**
  Duplicate or parameterize any per-branch `**ReleasePlan` / RPA** pair so each branch can ship on its own cadence.
8. **GitHub Actions**
  The `.github/workflows/build_and_push_release.yaml` workflow triggers on **any** git tag push and is branch-agnostic. No workflow changes are needed for a new minor, but verify the Quay tag policy is acceptable.
9. **First `Release` on the new application**
  When `**lightspeed-core-0.7`** has a passing integration Snapshot, select that Snapshot and create a `**Release`** referencing it and the **0.7** `ReleasePlan`. `**lightspeed-core-0.6`** continues to ship only from its own Snapshots and `ReleasePlan`; never mix applications in one `Release`.

**Summary table**


| Event              | Git                                                                 | Konflux application                                           | Components / revisions                                        | Comet / RPA / promotion                                                     |
| ------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 0.6.1 patch        | Bump `version.py` to `0.6.1`; commits on `release/0.6`              | Keep `lightspeed-core-0.6`                                    | Same component names; revision still **that release branch**  | **RPA:** add `0.6.1` tag -> **Snapshot** -> `**Release`**            |
| 0.6.0rc1           | Bump `version.py` to `0.6.0rc1`; RC commit on 0.6 branch            | Same                                                          | Same                                                          | **RPA:** allow `0.6.0rc1` tag -> **Snapshot** -> `**Release`**              |
| Open 0.7 on `main` | Create `**release/0.6**`; bump `version.py` on `main` to `0.7.0rc1` | Add `**lightspeed-core-0.7**`; keep `**lightspeed-core-0.6**` | 0.7 components -> `main`; 0.6 components -> `**release/0.6**` | New `**ReleasePlan` / RPA** for 0.7; Comet `0.7-*`; first 0.7 ship |


---

### Checklists for release engineers

#### Micro release checklist (patch or RC)

Use this for shipping a patch GA (e.g. `0.5.2`) or RC (e.g. `0.6.0rc1`) on an existing minor branch.

- **Release Manager** approves the ship and confirms which commits/digests are in scope.
- Update `src/version.py` to the target version string (e.g. `0.6.1` or `0.6.0rc1`); push to the correct branch.
- (Optional) Push a git tag if Quay publication via GitHub Actions is desired (`.github/workflows/build_and_push_release.yaml`).
- Confirm Konflux pipelines have built and integration tests have passed for the **Application** (e.g. `lightspeed-core-0.6`).
- **RPA:** Add the new immutable tag (e.g. `"0.6.1"` or `"0.6.0rc1"`) to `componentTags` for **every** shipping component in the managed-tenant RPA. Update floating tags if policy changes.
- **Comet:** Verify the tag shape is already allowed for the product image (no action if the pattern already exists).
- Select the correct **Snapshot** in the Konflux Application.
- Create the `**Release`** referencing that Snapshot and the Application's `ReleasePlan` (§4.1, [Creating a release](https://konflux.pages.redhat.com/docs/users/releasing/create-release.html)).
- Wait for the release pipeline to complete.
- **Verify** on `registry.redhat.io`: immutable tag present, floating tags (`x.y-latest`, `latest` if applicable) updated.
- If verification fails, check RPA coverage -> fix -> new Snapshot/`Release` (§4.1 failure recovery).

#### Minor release checklist (new minor branch)

Use this when opening a new minor (e.g. 0.7) from `main`.

- **Release Manager** approves the branch cut and `latest`-tag policy for the new minor.
- Create the Git branch `**release/<previous-minor>`** (e.g. `release/0.6`) from `main`.
- On `main`: bump `src/version.py` to the new minor's first version (e.g. `0.7.0rc1`).
- On `release/<previous-minor>`: confirm `version.py` reflects the last shipped version for that branch.
- Create the new Konflux **Application** (e.g. `lightspeed-core-0.7`) with components pointing at `main` — include all GPU flavors: `lightspeed-stack-0.7`, `rag-content-cpu-0.7`, `rag-content-cuda-12.9-0.7`, etc.
- **Retarget** the previous Application's components (e.g. `lightspeed-core-0.6`) so revisions point to `**release/0.6`** instead of `main`.
- Create a new `**ReleasePlan**` for the new Application.
- **RPA:** Add component mappings and `componentTags` for the new minor (`0.7-latest`, `0.7-{{ git_sha }}`, future `0.7.z`/`0.7.zrcN`) without clobbering existing branches (§2.3).
- **RPA:** Update `latest` tag ownership if the new minor becomes the default GA stream.
- **Comet:** Ensure catalog entries cover `0.7-*` tag patterns.
- Verify `.github/workflows/build_and_push_release.yaml` tag policy is acceptable (no changes needed if tag-agnostic).
- Wait for the first passing integration Snapshot on the new Application.
- Create the first `**Release`** on the new Application.
- **Verify** tags on `registry.redhat.io` for the new minor.

#### Invariants (check on every ship)

- Application name and component names include the **minor release branch** (`0.5`, `0.6`, `0.7`).
- Each component's **Git URL and revision** match the repo and **release branch** for that application.
- Each Application has its own `**ReleasePlan`** and matching **RPA**.
- RPA maps each promoting component to the correct `registry.redhat.io/...` path and tag set.
- Comet lists every user-facing repository and allowed tag shapes.
- `src/version.py` matches the intended release version.

---

### Parallel publishing paths

Two independent mechanisms publish container images. Both should produce equivalent images for the same commit, but they target different registries.


| Path                                                                 | Trigger                              | Target registry                            | Tags written                      |
| -------------------------------------------------------------------- | ------------------------------------ | ------------------------------------------ | --------------------------------- |
| **Konflux**                                                   | Release Engineer creates a `Release` | `registry.redhat.io`                       | Controlled by RPA `componentTags` |
| **GitHub Actions** (`.github/workflows/build_and_push_release.yaml`) | Any git tag push                     | `quay.io/lightspeed-core/lightspeed-stack` | Git tag name + `latest`           |


The GitHub Actions workflow also has a **dev image** variant (`.github/workflows/build_and_push_dev.yaml`) that pushes `dev-latest` and timestamped tags on every push to `main`.
