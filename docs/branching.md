# Branching

<!-- vim-markdown-toc GFM -->

* [Introduction](#introduction)
* [Basic rules](#basic-rules)
* [Release branch](#release-branch)
    * [Key points](#key-points)
* [Semantic versioning](#semantic-versioning)
    * [Rules (concise)](#rules-concise)
    * [Benefits](#benefits)
* [Branches naming](#branches-naming)
* [Branching visualization](#branching-visualization)
    * [Feature and fix branches that are merged into the main branch](#feature-and-fix-branches-that-are-merged-into-the-main-branch)
    * [Cherry-picking changes into release (stable) branch from the main branch](#cherry-picking-changes-into-release-stable-branch-from-the-main-branch)
    * [Multiple release branches, fixes made in fix branches](#multiple-release-branches-fixes-made-in-fix-branches)
* [Branching strategy](#branching-strategy)
    * [Steps (ordered)](#steps-ordered)
    * [Visualized flow](#visualized-flow)
    * [Cherry picking](#cherry-picking)
* [Git workflow](#git-workflow)
    * [New release branch](#new-release-branch)
    * [Update/fix existing release branch](#updatefix-existing-release-branch)

<!-- vim-markdown-toc -->

## Introduction

Lightspeed Core Stack adopts a Git workflow that creates and maintains
dedicated release branches for each published Lightspeed Core Stack version,
and pair that with strict semantic versioning to clearly communicate the nature
of each release.

## Basic rules

* For every formal release (major.minor.patch) a long-lived branch
  named is created to reflect the version (for example, release/0.6.0).

* Routine development occurs on main branch (as of today); only bug fixes,
  security patches, and approved backports are merged into the corresponding
  release branch or branches.

* Each change merged to a release branch must pass the same CI pipeline used
  for main branch, including unit, integration, and end-to-end tests, before
  being packaged.

* Semantic versioning is applied to all published artifacts:
    - Increment MAJOR for incompatible API changes.
    - Increment MINOR for backwards-compatible feature additions.
    - Increment PATCH for backwards-compatible bug fixes and security patches.

* Patch releases (e.g., 0.6.0 → 0.6.1) are cut from the release branch and
  tagged with the semantic version; release tags are reproducible and signed.

* Backport changes are cherry-picked or merged into the appropriate release
  branch and receive a patch-level version bump and changelog entry documenting
  the fix and any CVE identifiers.

* Merge and backport rules: require code review, automated tests, and QA
  approval; record the originating main commit(s) and rationale in the release
  branch.

* End-of-support or EOL for a release is recorded; no further patches are
  applied after EOL except by exception and with explicit approval.

This approach keeps ongoing development separate from maintenance work, ensures
clear, predictable version numbers for consumers, and provides a repeatable
process for issuing hotfixes and patch releases.



## Release branch

A release branch is a Git branch used to prepare a new production release. It
stabilizes the codebase for final testing, bug fixes, and release-specific
tasks without blocking ongoing feature development on main/develop. Those
branches will have the following naming schema:

```text
release/MAJOR.MINOR.PATCH
```



### Key points

* Purpose: Freeze features, perform QA, apply release-only fixes, update
  version numbers, and prepare release notes.

* Lifespan: Short-to-medium lived—exists from when you decide to cut a release
  until the release is shipped and merged back.

* Target branches: Typically created from a main integration branch (e.g.,
  develop or main) and merged back into both main (or master) and develop (or
  the integration branch) after release.

* Typical tasks on the branch: final bug fixes, documentation, version bump,
  packaging, and deployment scripts.

* Naming: Use clear names like release/1.4.0 or release-2026-03-30.

* Benefits: Isolates release stabilization work, lets feature development
  continue on develop/main, and provides a clear point for builds and QA.



## Semantic versioning

Semantic Versioning (SemVer) is a versioning scheme that conveys meaning about
changes in a release using a three-part number: MAJOR.MINOR.PATCH.



### Rules (concise)

* Format: MAJOR.MINOR.PATCH (e.g., 2.5.1).

* Increment MAJOR for incompatible API changes.

* Increment MINOR when you add backwards-compatible features.

* Increment PATCH for backwards-compatible bug fixes.

* Pre-release identifiers: append a hyphen and identifiers for unstable
  releases (e.g., 1.0.0-alpha.1).

* Build metadata: append a plus and metadata ignored for precedence (e.g.,
  1.0.0+20130313144700).

* Precedence: Compare MAJOR, then MINOR, then PATCH numerically; pre-release
  versions have lower precedence than the associated normal version.



### Benefits

* Communicates compatibility guarantees to users.

* Supports dependency resolution and predictable upgrades.



## Branches naming

| Branch        | Description                   |
|---------------|-------------------------------|
| main          | production-ready code         |
| release/x.y.z | release stabilization branch  |
| feature/*     | new features                  |
| hotfix/*      | urgent production fixes       |

NOTE: the actual proposal covers release branches only; feature and hotfix
branch naming conventions are not covered here.


## Branching visualization

### Feature and fix branches that are merged into the main branch

[branching_1](https://lightspeed-core.github.io/lightspeed-stack/branching_1.svg)

### Cherry-picking changes into release (stable) branch from the main branch

[branching_2](https://lightspeed-core.github.io/lightspeed-stack/branching_2.svg)

### Multiple release branches, fixes made in fix branches

[branching_3](https://lightspeed-core.github.io/lightspeed-stack/branching_3.svg)


## Branching strategy

### Steps (ordered)

1. Create release branch

2. Update metadata, such us version etc.

3. Run CI: full test suite, linters, build (this is to check that branching is
   ok)

4. Stabilize: apply bug fixes, adjust configurations, small polish commits on
   release branch

5. QA / UAT: Deploy release branch to staging environment (Konflux)

6. Fix issues: commit fixes directly on release branch; re-run CI

7. Prepare release: Finalize changelog, update docs, set release notes

8. Deploy: trigger production deployment (Konflux)

9. Hotfixes (if needed): create hotfix/x.y.z+1 from main, then follow same flow



### Visualized flow

```
                 +-----------------+
                 |   main branch   |
                 |                 |
                 +--------+--------+
                          | 
                          |  create release/x.y.z
                          v 
                 +-----------------+
                 |  release/x.y.z  |
                 |  (stabilize)    |
                 +----+---+---+----+
                      |   |   |
     update changelog |   |   | bug fixes & CI
                      |   |   |
                      v   v   v
                 +-----------------+
                 | Run CI / Tests  |
                 +--------+--------+
                          | 
                          v 
                 +-----------------+
                 |  Run e2e tests  |
                 |  in Konflux     |
                 |                 |
                 +--------+--------+
                          |
            issues found  |  validated
                 +--------+-----------+
                 |                    |
                 v                    v
       +----------------+     +----------------+
       | Fix on release |     | Ready for ship |
       +-------+--------+     +-------+--------+
               |                      |
               v                      v
          (re-run CI)          tag the release
               |                      |
               v                      v
       +----------------+     +----------------+
       |  return to QA  |     |    (tag vX)    |------------+
       +----------------+     +----------------+            |
                                      |                     |
                                      v                     v
                              +----------------+    +-----------------+
                              |  Build images  |    | Publish on PyPi |
                              +----------------+    +-----------------+
```



### Cherry picking

Cherry-picking is a Git operation that applies the changes introduced by a
specific commit from one branch onto another branch without merging the entire
branch history. Key points:

* Purpose: move a single fix, feature, or change (identified by its commit SHA)
  from one line of development (e.g., from main branch) into another (in our
  case into a release branch) when you don’t want to merge all other commits.

* How it works: Git copies the patch (diff) from the selected commit, attempts
  to apply it to the current branch, and creates a new commit with a new SHA on
  that branch.

* Typical workflow:
   - Checkout the target branch (e.g., release/0.6.0).
   - Run `git cherry-pick` (or multiple SHAs).
   - Resolve any merge conflicts, then `git add` and `git cherry-pick --continue`.
   Test, review, and push the resulting commit into the release branch.

NOTE: the cherry picking can be made in main -> release branch direction or
vice versa. We prefer the first method when possible.



## Git workflow

### New release branch

```bash
# 1. Create release branch from the main branch
git checkout -b release/1.2.0 main

# 2. Update version number in build files

# 3. Commit and push
git commit -am "Prepare for 1.2.0 release"
git push origin release/1.2.0

# 4. Tag the release
git tag -a v1.2.0 -m "Release 1.2.0"
git push origin v1.2.0

# 5. Merge into main (optional step)
git checkout main && git merge release/1.2.0
```



### Update/fix existing release branch

```bash
# 1. Create branch from the release branch
git checkout -b release/1.2.1 release/1.2.0

# 2. Update version number in build files

# 3. Commit and push
git commit -am "Prepare for 1.2.1 fix"
git push origin release/1.2.1

# 4. Tag the release
git tag -a v1.2.1 -m "Release 1.2.1"
git push origin v1.2.1
```

NOTE: 1.2.0 and 1.2.1 are just examples, of course.
