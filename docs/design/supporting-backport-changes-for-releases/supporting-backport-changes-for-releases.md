# Supporting backport changes for releases

|                          |                                                                       |
|--------------------------|-----------------------------------------------------------------------|
| **Date**                 | 2026-03-30                                                            |
| **Component**            | lightspeed-stack                                                      |
| **Authors**              | Pavel Tišnovský                                                       |
| **Feature / Initiative** | [LCORE-1349](https://issues.redhat.com/browse/LCORE-1349)             |
| **Spike**                | [LCORE-1596](https://issues.redhat.com/browse/LCORE-1596)             |
| **Links**                | Spike doc: `docs/design/supporting-backport-changes-for-releases/`    |


<!-- vim-markdown-toc GFM -->

* [What](#what)
* [Why](#why)
* [Requirements](#requirements)
    * [R1](#r1)
    * [R2](#r2)
    * [R3](#r3)
    * [R4](#r4)
    * [R5](#r5)
    * [R6](#r6)
    * [R7](#r7)
* [Use Cases](#use-cases)
    * [U1](#u1)
    * [U2](#u2)
    * [U3](#u3)
    * [U4](#u4)
    * [U5](#u5)
    * [U6](#u6)
    * [U7](#u7)
    * [U8](#u8)
    * [U9](#u9)
* [Solution](#solution)
    * [Release branch](#release-branch)
        * [Key points](#key-points)
    * [Semantic versioning](#semantic-versioning)
        * [Rules (concise)](#rules-concise)
        * [Benefits](#benefits)
    * [Branches naming](#branches-naming)
    * [Release branches visualization](#release-branches-visualization)
        * [One release branch](#one-release-branch)
        * [Two release branches](#two-release-branches)
    * [Proposed workflow](#proposed-workflow)
        * [Steps (ordered)](#steps-ordered)
        * [Visualized flow](#visualized-flow)
        * [Cherry picking](#cherry-picking)
    * [Git workflow](#git-workflow)
        * [New release branch](#new-release-branch)
        * [Update/fix existing release branch](#updatefix-existing-release-branch)
        * [Branching visualization on CLI](#branching-visualization-on-cli)
* [Epics created](#epics-created)
* [Stories created](#stories-created)
* [Unknowns](#unknowns)
* [References](#references)
* [Changelog](#changelog)

<!-- vim-markdown-toc -->



# What

Supporting backport changes for releases means having processes and technical
support to take bug fixes, security patches, or small feature adjustments made
in the current (or main) codebase and apply them to older released versions so
those releases can be updated without merging forward-only development.
Concretely this includes:

* Maintaining long-lived release branches for each supported released version.

* Identifying which fixes should be backported (severity, compatibility, risk).

* Adapting code changes so they compile and run against the older codebase
  (resolving API/architecture differences).

* Running the same or appropriate test suites (unit, integration, regression)
  on the backported branch.

* Following defined review and approval workflows for backports (e.g., code
  review, QA sign-off).

* Documenting the backport (what changed, rationale, release notes, version
  tags).

* Creating and publishing a patch release (hotfix) from the backported branch,
  with rollback/rollback-tested procedures.

* Automating parts of the process where possible (CI jobs for branch creation,
  tests, and packaging).

In short: ensure you can reliably and safely apply, test, review, document, and
release fixes to past released versions without disrupting mainline
development.



# Why

We need the ability to create and maintain separate branches of the Lightspeed
Core Stack (LCS) codebase after each formal release so that, if any Lightspeed
team requests an urgent or on-demand patch, we can apply fixes to the released
version without disrupting ongoing development on the mainline. This branching
workflow should include versioned branch names, clear merge/backport/cherrypick
procedures, automated testing for patch branches, and a defined process for
releasing and documenting any hotfixes.

Here are key advantages that will allow the LCORE team to support its
customers:

* Parallel development: continued feature development while finalizing a
  release separately.

* Stability Before Deployment: isolating releases gives the team space for
  final QA testing, bug fixes, version number updates, and release-specific
  documentation

* Hotfix Support



# Requirements

## R1  

Long-term support for specific LCORE releases with the ability to fix bugs and
CVE in all supported versions.  Provide a formal Long-Term Support (LTS)
program for designated LCORE release versions that ensures ongoing maintenance,
security, and stability for those supported releases.

## R2

Supported-release policy. Defined support window: Publish explicit start and
end dates for support of each LCORE release (e.g., 18–24 months), and document
criteria for extending or ending support.

## R3

Supported versions list: Maintain an authoritative list of currently supported
LCORE releases and the type of support (security-only, critical-bug + security,
full support).

## R4

Timely fixes: Commit to SLAs for addressing defects and security
vulnerabilities (e.g., triage within 24 hours, patch within X days depending on
severity).

## R5

CVE handling: Track, triage, and remediate CVEs affecting any supported
release; coordinate CVE assignment, disclosure, and patch publication according
to industry best practices.

## R6

Release branches: Maintain long-lived release branches for each supported
version to apply fixes without impacting mainline development.

## R7

Backport process: Provide a documented, repeatable process to backport fixes
(including code adaptation, conflict resolution, and compatibility
verification).



# Use Cases

## U1

As a Lightspeed Core Stack developer I was notified about CVE in version x.y. I
need to fix the CVE in that particular version without altering older (stable)
versions.

## U2  

As a Lightspeed Core Stack developer I was notified about bug in version x.y. I
need to fix the bug in that particular version w/o altering older (stable)
versions.

## U3  

As a Lightspeed Core Stack developer I need to implement new feature planned in
version x+1, but maintain compatibility in version x.

## U4  

As a Lightspeed Core Stack developer I have to change the API, but the older
Lightspeed Core Stack versions should not be affected by this change.

## U5

As a Lightspeed Core Stack developer I need to backport the CVE from main
branch to given version x.y.

## U6

As a Lightspeed Core Stack developer I need to backport the bug from main
branch to given version x.y.

## U7

As a Lightspeed Core Stack developer I need to backport the CVE from version X
branch to version Y without altering other versions.

## U8

As a Lightspeed Core Stack developer I need to backport the bug from version X
branch to version Y without altering other versions.

## U9

As Lightspeed Core Stack user I need to have a list of supported versions,
support windows, status of versions etc. Similar to
https://devguide.python.org/versions/



# Solution

We will adopt a Git workflow that creates and maintains dedicated release
branches for each published Lightspeed Core Stack version, and pair that with
strict semantic versioning to clearly communicate the nature of each release.

Concretely:

* For every formal release (major.minor.patch) we create a long-lived branch
  named to reflect the version (for example, release/0.6.0).

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



## Release branches visualization

### One release branch

```
|  * tag: v0.6.0
|  * release/0.6.0  (release branch)
|  * commit C6
|  * commit C5
*  | commit C4
*  | commit C3
| /
|/
* commit C2
* commit C1  (main)
```

### Two release branches

```
|  *  tag: v2.0.0
|  *  release/2.0
|  *  commit R2-2
|  *  commit R2-1
|  | 
|  |  * tag: v1.2.1
|  |  * release/1.2
|  |  * commit R1-3
|  |  * commit R1-2
|  |  * commit R1-1
|  | /
|  |/
|  * commit C6
*  | commit C5
*  | commit C4
| /
|/
* commit C3
* commit C2
* commit C1  (main)
```



## Proposed workflow

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



### Branching visualization on CLI

Using `git-graph` tool:

```
   ●                              59c674c (HEAD -> release/1.2.3) Fix for 1.2.3
   │   ●                          dbc9619 (lcore-1602-update-lcore-version, origin/lcore-1602-update-lcore-version) LCORE-1602: Update LCORE version
   │   │ ●                        5d14721 (origin/lcore-1562-fixed-link) Update docs/design/conversation-compaction/conversation-compaction.md
 ┌─┴───┘ ●                        ad639c1 LCORE-1562: Fixed lin in FA
 ○<────┬─┘                        1b68d36 (main, origin/main, upstream/main) Merge pull request #1434 from tisnik/lcore-1319-more-jira-projects
 │     ●                          1395ad8 (origin/lcore-1319-more-jira-projects) LCORE-1319: More JIRA projects
 ├─────┘                          
 ○<──────┐                        9c9410c Merge pull request #1432 from asimurka/clear_reasoning_and_max_out_tokens
 ○<──────┼─────┐                  6c2ae1e Merge pull request #1399 from max-svistunov/lcore-1576-feature-design-process
 │       │     ●                  66d3557 Update JIRA ticket template
 ○<────┐ │     │                  d206a03 Merge pull request #1433 from tisnik/lcore-1319-updated-pr-title-checker
 │     ● │     │                  36ca0e4 (origin/lcore-1319-updated-pr-title-checker) LCORE-1319: Updated PR title checker
 │     │ ●     │                  fb50736 Clear reasoning and max_output_tokens in responses
 ├─────┴─┘ ●   │                  3e6c633 (origin/test-xyzzy) Test XYZZY
 ├─────────┘   │                  
 ○<────┐       │                  ee0bcf9 Merge pull request #1429 from tisnik/lcore-1319-pr-title-checker
 │     ●       │                  d0c8c97 (origin/lcore-1319-pr-title-checker) PR title checker GH action
 │     ●       │                  feae91c PR title checker config
 ├─────┘       │                  
```



# Epics created

| Epic       | Description                                                                 | Link                                           |
|------------|-----------------------------------------------------------------------------|------------------------------------------------|
| LCORE-1619 | Documentation containing long term support informations                     | https://redhat.atlassian.net/browse/LCORE-1619 |
| LCORE-1620 | Up to date page with supported and unsupported LCS versions                 | https://redhat.atlassian.net/browse/LCORE-1620 |
| LCORE-1621 | Implementation of official branching strategy                               | https://redhat.atlassian.net/browse/LCORE-1621 |
| LCORE-1622 | Accommodation phase: make 0.5.0 release branch with all required attributes | https://redhat.atlassian.net/browse/LCORE-1622 |
| LCORE-1623 | Production phase: make 0.6.0 release branch with all required attributes    | https://redhat.atlassian.net/browse/LCORE-1623 |



# Stories created

| Epic       | Story      | Description                                                                      | Link                                           |
|------------|------------|----------------------------------------------------------------------------------|------------------------------------------------|
| LCORE-1619 | LCORE-1635 | Specification: Finish documentation containing Long Term Support (LTS) agreement | https://redhat.atlassian.net/browse/LCORE-1635 |
| LCORE-1619 | LCORE-1649 | Document internal LTS process flow                                               | https://redhat.atlassian.net/browse/LCORE-1649 |
| LCORE-1620 | LCORE-1636 | Create and fill in section: Status of LCORE versions                             | https://redhat.atlassian.net/browse/LCORE-1636 |
| LCORE-1620 | LCORE-1637 | Create table with list of all supported versions                                 | https://redhat.atlassian.net/browse/LCORE-1637 |
| LCORE-1620 | LCORE-1638 | Create table with list of all unsupported versions                               | https://redhat.atlassian.net/browse/LCORE-1638 |
| LCORE-1620 | LCORE-1650 | Document support tiers and escalation contacts per version                       | https://redhat.atlassian.net/browse/LCORE-1650 |
| LCORE-1620 | LCORE-1652 | Add release and EOL dates for each LCORE version                                 | https://redhat.atlassian.net/browse/LCORE-1652 |
| LCORE-1620 | LCORE-1651 | Link to upgrade guidance and migration paths for each version                    | https://redhat.atlassian.net/browse/LCORE-1651 |
| LCORE-1621 | LCORE-1642 | Define and document branching model                                              | https://redhat.atlassian.net/browse/LCORE-1642 |
| LCORE-1621 | LCORE-1643 | Add CI/CD workflows for release creation and hotfixes                            | https://redhat.atlassian.net/browse/LCORE-1643 |
| LCORE-1621 | LCORE-1644 | Create and integrate PR, issue, and release note templates                       | https://redhat.atlassian.net/browse/LCORE-1644 |
| LCORE-1621 | LCORE-1645 | Write contribution and branching documentation                                   | https://redhat.atlassian.net/browse/LCORE-1645 |
| LCORE-1621 | LCORE-1646 | Implement branch protections and required PR checks in CI                        | https://redhat.atlassian.net/browse/LCORE-1646 |
| LCORE-1621 | LCORE-1647 | Automate versioning and changelog generation                                     | https://redhat.atlassian.net/browse/LCORE-1647 |
| LCORE-1621 | LCORE-1648 | Train teams on new branching strategy and workflows                              | https://redhat.atlassian.net/browse/LCORE-1648 |
| LCORE-1622 | LCORE-1640 | Create release branch for version 0.5.0                                          | https://redhat.atlassian.net/browse/LCORE-1640 |
| LCORE-1622 | LCORE-1653 | Add release metadata: tags, manifest, checksums, and signing information         | https://redhat.atlassian.net/browse/LCORE-1653 |
| LCORE-1622 | LCORE-1654 | Prepare customer-facing release notes for 0.5.0                                  | https://redhat.atlassian.net/browse/LCORE-1654 |
| LCORE-1623 | LCORE-1631 | Production — Create 0.6.0 Release Branch and note all problematic points         | https://redhat.atlassian.net/browse/LCORE-1641 |
| LCORE-1623 | LCORE-1655 | Compile and finalize changelog and release notes for 0.6.0                       | https://redhat.atlassian.net/browse/LCORE-1655 |
| LCORE-1623 | LCORE-1656 | Generate and publish release artifacts for 0.6.0                                 | https://redhat.atlassian.net/browse/LCORE-1656 |
| LCORE-1623 | LCORE-1657 | Tag release/0.6.0 branch and update release manifest                             | https://redhat.atlassian.net/browse/LCORE-1657 |



# Unknowns

* How to automate Konflux builds and integration tests


# References

* [A successful Git branching model](https://nvie.com/posts/a-successful-git-branching-model/)



# Changelog

TODO: Record significant changes after initial creation.

| Date       | Change          | Reason          |
|------------|-----------------|-----------------|
| 2026-03-30 | Initial version | feature request |
| 2026-03-31 | Created epics   | refinement      |
| 2026-04-16 | Link to stories | sync with Jira  |

