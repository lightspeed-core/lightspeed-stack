# Supporting backport changes for releases

|                          |                                                                       |
|--------------------------|-----------------------------------------------------------------------|
| **Date**                 | 2026-04-15                                                            |
| **Component**            | lightspeed-stack                                                      |
| **Authors**              | Pavel Tišnovský                                                       |
| **Feature / Initiative** | [LCORE-1284](https://issues.redhat.com/browse/LCORE-1284)             |
| **Spike**                | [LCORE-1592](https://issues.redhat.com/browse/LCORE-1592)             |
| **Links**                | Spike doc: `docs/low-overhead-deployment-for-server-mode`             |


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
    * [R8](#r8)
    * [R9](#r9)
    * [R10](#r10)
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
    * [U10](#u10)
    * [U11](#u11)
    * [U12](#u12)
* [Available solutions](#available-solutions)
    * [S1](#s1)
    * [S2](#s2)
    * [S3](#s3)
    * [S4](#s4)
    * [S5](#s5)
* [Chosen approach and configuration (target state)](#chosen-approach-and-configuration-target-state)
* [Implementation details](#implementation-details)
    * [D1](#d1)
    * [D2](#d2)
    * [D3](#d3)
    * [D4](#d4)
    * [D5](#d5)
* [Conclusion](#conclusion)
* [Epics created](#epics-created)
* [Stories created](#stories-created)
* [Unknowns](#unknowns)
* [References](#references)
* [Changelog](#changelog)

<!-- vim-markdown-toc -->



# What

Our goal for this new feature is to shield teams from the complexity of
underlying frameworks and technologies, creating a clear separation between
platform internals and the surface developers use. By abstracting away
low-level implementation details, we want Lightspeed teams to focus on business
logic and product outcomes rather than compatibility, versioning, or
platform-specific quirks. This approach will reduce onboarding time for new
developers, lower the cognitive load for administrators, and minimize the
number of error modes that arise from direct interaction with heterogeneous
systems.

To accomplish this, Lightspeed developers and administrators will interact
exclusively with a consistent, well-documented Core API and a centralized
configuration model. The feature will provide stable interfaces, sensible
defaults, and robust compatibility layers so that internal changes to
frameworks or technology stacks do not cascade into dependent teams’ work. Over
time this will improve maintainability, speed up feature delivery, and enable
safer, more predictable upgrades across the platform.




# Why

One of the current deployment options is to run Llama Stack as a separate
server, which places an extra operational burden on teams. Developers and
administrators must learn the deployment mechanics, manage an additional
service lifecycle, and troubleshoot issues specific to that server. This
complexity increases the number of manual steps required to get Lightspeed Core
running for local development or test environments, slowing onboarding and
raising the chance of configuration errors that can block progress.

Because the Llama Stack team prefers and recommends server mode, we should
simplify that experience for Lightspeed developers. Providing streamlined
deployment artifacts, clear documentation, and automated setup scripts or
tooling will reduce friction and prevent divergent local setups. By making the
server-based option easy and repeatable, we ensure teams can follow the
recommended configuration with minimal effort, improving development velocity
and reducing environment-related failures.



# Requirements



## R1  

Lightspeed Core includes an automated startup mechanism that launches both
LCORE and Llama Stack images with a single command, removing manual
orchestration steps. This unified command initializes the required containers
or services, applies sensible defaults, and wires together networking and
configuration so developers don't need to perform separate launches or
hand-edit integration points. As a result, local development and testing
environments can be brought up quickly and consistently, reducing setup time
and the risk of misconfiguration.



## R2

The single-command startup also supports repeatable workflows for CI and
onboarding, making it straightforward to reproduce a known-good environment
across machines and teams. Built-in checks and logs surface any boot-time
issues and provide clear next steps for resolution, while configuration
overrides allow experienced users to customize behavior without abandoning the
convenience of automation. Overall, this feature streamlines getting Lightspeed
Core and Llama Stack running together, improving developer velocity and
reliability.



## R3

Lightspeed developers must not be required to interact directly with the Llama
Stack server; the platform should hide that complexity behind stable Lightspeed
interfaces. Requiring teams to manage or troubleshoot the Llama Stack service
would increase cognitive load, introduce variability across developer
environments, and create additional failure modes unrelated to application
logic. Instead, Lightspeed should surface any necessary Llama Stack
capabilities through the core API and configuration layer so developers can
build and run features without learning server internals or adjusting low-level
deployment parameters.



## R4

Until the official Llama Stack distribution from RHOAI includes native
lightspeed-providers, we should provide an interim, supported distribution of
Llama Stack tailored for Lightspeed. This custom distribution would bundle the
providers, sensible defaults, and integration glue so teams can consume Llama
Stack functionality transparently. Delivering it as part of Lightspeed’s
tooling—via automated images, single-command startup, and documented
configuration overlays—ensures consistent behavior across local, CI, and
staging environments while we coordinate with RHOAI on upstream support.



## R5

We require only Lightspeed Core configuration to run and manage features,
keeping developer interaction focused on a single, consistent surface. By
limiting required inputs to core configuration files and settings, we remove
the need for teams to understand or modify underlying platform pieces,
third‑party providers, or deployment artifacts. This reduces cognitive
overhead, prevents divergent environment setups, and makes it straightforward
to reproduce environments across machines and CI pipelines.



## R6

Centralizing control in Lightspeed Core also enables safer defaults,
validation, and automated transforms before any external systems are touched.
Configuration-driven behavior lets Lightspeed apply compatibility layers,
feature flags, and rollout controls without exposing low‑level plumbing to
application teams. As a result, updates to frameworks or bundled providers can
be handled centrally — via configuration changes or upgraded Core releases —
rather than requiring per‑team operational work.



## R7

Optional

Implement this deployment automation for both OpenShift and non-OpenShift
environments to cover the full range of developer and small-scale deployment
needs. For OpenShift, deliver templates, Operators, or Helm charts that
integrate with cluster APIs, route and service objects, security context
constraints, and image stream conventions so the automated startup works with
OpenShift-native workflows. For non-OpenShift targets (local Docker, Docker
Compose, Kubernetes upstream, lightweight k3s/minikube), provide equivalent
manifests, Compose files, and CLI tooling that perform the same lifecycle
tasks: image provisioning, network wiring, volume mounts, config injection, and
health checks.



## R8

Ensure parity of experience across platforms by exposing the same Lightspeed
Core configuration surface and command semantics regardless of deployment
target. Include platform-specific defaults and the minimal overrides necessary
(e.g., security policies, ingress class, storage class) so teams rarely need to
change manifests manually. Provide automation that supports developer workflows
(fast local boot, hot-reload, simple teardown) and small-scale environments
(stable persistence, resource limits, observability hooks), with clear upgrade
paths and testing to verify feature parity between OpenShift and non-OpenShift
deployments.



## R9

Investigate whether adjacent repositories require changes to support the new
deployment and integration patterns, starting with projects like rag-content
(BYOK tool) and lightspeed-providers. For each repo, enumerate integration
touchpoints (APIs, configuration formats, image tags, startup hooks,
secrets/credentials handling) and verify compatibility with the Lightspeed Core
configuration and automated startup flows. Run local and CI-based smoke tests
to surface breakages (schema mismatches, missing providers, or runtime errors)
and document any required code, config, or packaging updates.



## R10

Where changes are necessary, make targeted updates and follow
repository-specific contribution workflows: branch, implement, test, and submit
pull requests with clear descriptions and migration notes. Prioritize minimal,
backward-compatible changes—configuration wiring, additional environment
variables, packaging changes, or small adapter modules—so downstream consumers
see no disruption. Coordinate release and rollout sequencing (including version
bumps, image pushes, and CI adjustments) so Lightspeed’s automated deployments
pick up the new artifacts reliably, and add regression tests to prevent future
incompatibilities.



# Use Cases



## U1

Developers run Lightspeed Core and Llama Stack together locally with a single
command.



## U2  

Teams avoid interacting directly with Llama Stack server; Lightspeed surfaces
functionality via core API/config.



## U3  

Provide an interim Lightspeed-tailored Llama Stack distribution (until upstream
includes lightspeed-providers - which is very unlikely).



## U4  

Automated deployments for OpenShift environments (Operators/Helm/templates) for
developer/small-scale use.



## U5

Automated deployments for non-OpenShift targets (Docker, Docker Compose,
upstream Kubernetes, k3s/minikube).



## U6

Start LCORE & Llama Stack images with one automated startup command for CI,
onboarding, and reproducible dev environments.



## U7

Hide underlying frameworks/technologies so teams only supply Lightspeed Core
configuration.



## U8

Ship streamlined deployment artifacts, documentation, and tooling to simplify
server-mode Llama Stack setup.



## U9

Surface built-in checks, logs, and configuration overrides for troubleshooting
and customization.



## U10

Audit and modify adjacent repos (e.g., rag-content BYOK, lightspeed-providers)
for compatibility; run smoke/CI tests and submit PRs.



## U11

Provide parity of experience across OpenShift and non-OpenShift with minimal
platform-specific overrides (ingress, storage, security).



## U12

Support developer workflows (fast boot, hot-reload, teardown) and small-scale
environments (persistence, resource limits, observability).



# Available solutions



## S1

Single-command local orchestration based on Docker Compose / Podman Compose:
define LCORE + Llama Stack services, networks, volumes, env overrides; good for
simple local/dev setups and CI. CLI wrapper: single command that calls compose,
applies config transforms, and runs health checks.



## S2

OpenShift-native solution. OpenShift Templates or Operators: map to SCCs,
imageStreams, Routes; operator preferred for full lifecycle management.



## S3

Configuration-driven integration. Centralized Lightspeed Core config + config
injection: provide a small schema and parser that transforms core config into
provider configs, secrets, and envs.



## S4


LCORE can launch Llama Stack directly as part of its own lifecycle, embedding
the model service startup into the core workflow so teams don't have to manage
a separate server. When invoked, LCORE will detect the available container
runtime (Podman or Docker) and instantiate the specified Llama Stack image with
the correct network, volumes, and environment configuration derived from
Lightspeed Core configuration. This ensures the Llama Stack process is created
with consistent defaults, exposed ports, and health checks, and that any
runtime options or provider plugins required by Lightspeed are injected
automatically.

During teardown, LCORE will also be responsible for a clean shutdown of the
Llama Stack instance, sequencing termination to avoid data loss or orphaned
resources. The shutdown routine will run graceful stop commands, wait for
configured timeouts, capture and surface container logs if failures occur, and
remove ephemeral artifacts created for the session (temporary volumes,
networks). This controlled lifecycle management guarantees reproducible
startup/teardown behavior across developer machines and small-scale
deployments, reducing manual cleanup and simplifying troubleshooting.



## S5

Similar to the container-based approach, LCORE can start a local Llama Stack
process directly by invoking the uv (or equivalent) command, embedding the
model runtime as a local binary rather than a container. LCORE would assemble
the required command-line arguments, environment variables, and configuration
files from the Lightspeed Core configuration, then spawn the process and
monitor its stdout/stderr for readiness signals and health diagnostics. This
allows for a lightweight, low-overhead developer workflow that avoids container
runtime dependencies and can be faster to start and iterate on during
development.

For teardown and resiliency, LCORE would manage the process lifecycle: sending
graceful termination signals, applying configurable shutdown timeouts,
collecting logs on failure, and cleaning up any temporary files or sockets the
runtime created. The local-run path should expose the same API surface and
configuration semantics as the containerized option so teams get a consistent
experience across deployment modes. Provide command-override hooks and simple
validation checks so advanced users can customize the local runtime invocation
while preserving reproducible defaults for typical developer setups.



# Chosen approach and configuration (target state)

We propose supporting both production and local deployments by implementing solutions
S4 and S5. Llama Stack startup mode (containerized or local binary) will be
selectable via future `lightspeed-stack.yaml` schema changes, allowing teams and
environments to choose the best runtime without code changes.



# Implementation details

## D1

`lightspeed-stack.yaml` schema: include a top-level runtime field with values
like `container` or `local`, plus runtime-specific sections:
- `container`: image, runtime (docker|podman), ports, volumes, env, imagePullPolicy, resource limits.
- `local`: command (e.g., uv), args, env, workingDir, socket/path settings, resource hints.



## D2

Defaults and overrides: sensible defaults for dev and prod profiles; support
per-environment overrides and CLI flags.



## D3

Distribution: publish a Lightspeed-tailored Llama Stack OCI image
(lightspeed-providers included) and make it the default container image in
configs.



## D4

Lifecycle management: LCORE reads `lightspeed-stack.yaml`, instantiates either
container or local process, performs readiness checks, and ensures graceful
teardown (log collection, cleanup).



## D5

Testing & CI: include CI jobs that validate both container and local modes
using Compose/Kind or local-process harnesses to ensure parity.



# Conclusion

This design gives teams one declarative place to control Llama Stack behavior
while supporting both lightweight local runs and production-ready containerized
deployments.



# Epics created

| Epic       | Description                                                       | Link                                           |
|------------|-------------------------------------------------------------------|------------------------------------------------|
| LCORE-1489 | Build custom LLS distribution for LCORE                           | https://redhat.atlassian.net/browse/LCORE-1489 |
| LCORE-1854 | Ability to start and teardown LLS from container image            | https://redhat.atlassian.net/browse/LCORE-1854 |
| LCORE-1855 | Ability to start and teardown LLS installed locally               | https://redhat.atlassian.net/browse/LCORE-1855 |
| LCORE-1856 | Ability for LCORE to run in degraded mode when LLS is not running | https://redhat.atlassian.net/browse/LCORE-1856 |



# Stories created

| Epic       | Story      | Description                                                                        | Link                                           |
|------------|------------|------------------------------------------------------------------------------------|------------------------------------------------|
| LCORE-1854 | LCORE-1869 | Implement graceful teardown and cleanup of LLS container                           | https://redhat.atlassian.net/browse/LCORE-1869 |
| LCORE-1854 | LCORE-1870 | Automate ephemeral resource management for LLS container sessions                  | https://redhat.atlassian.net/browse/LCORE-1870 |
| LCORE-1854 | LCORE-1873 | Add automated tests for LLS container lifecycle management                         | https://redhat.atlassian.net/browse/LCORE-1873 |
| LCORE-1854 | LCORE-1872 | Implement LLS container startup with dynamic configuration injection               | https://redhat.atlassian.net/browse/LCORE-1872 |
| LCORE-1854 | LCORE-1871 | Expose and manage LLS container ports and health checks                            | https://redhat.atlassian.net/browse/LCORE-1871 |
| LCORE-1854 | LCORE-1874 | Document LLS container startup, teardown, and customization options                | https://redhat.atlassian.net/browse/LCORE-1874 |
| LCORE-1854 | LCORE-1875 | Support both OpenShift and non-OpenShift environments for LLS container management | https://redhat.atlassian.net/browse/LCORE-1875 |
| LCORE-1854 | LCORE-1876 | Validate and surface container logs and errors during LLS lifecycle                | https://redhat.atlassian.net/browse/LCORE-1876 |
| LCORE-1855 | LCORE-1862 | Ensure API and configuration parity with containerized LLS deployment              | https://redhat.atlassian.net/browse/LCORE-1862 |
| LCORE-1855 | LCORE-1863 | Implement graceful teardown and cleanup for local LLS process                      | https://redhat.atlassian.net/browse/LCORE-1863 |
| LCORE-1855 | LCORE-1865 | Monitor and report LLS process health and readiness                                | https://redhat.atlassian.net/browse/LCORE-1865 |
| LCORE-1855 | LCORE-1864 | Implement local LLS process startup logic                                          | https://redhat.atlassian.net/browse/LCORE-1864 |
| LCORE-1855 | LCORE-1866 | Validate local LLS runtime environment and configuration                           | https://redhat.atlassian.net/browse/LCORE-1866 |
| LCORE-1855 | LCORE-1867 | Add automated tests for local LLS process lifecycle management                     | https://redhat.atlassian.net/browse/LCORE-1867 |
| LCORE-1855 | LCORE-1868 | Document local LLS startup, teardown, and customization options                    | https://redhat.atlassian.net/browse/LCORE-1868 |
| LCORE-1856 | LCORE-1857 | Emit metrics, logs, and events for degraded mode transitions                       | https://redhat.atlassian.net/browse/LCORE-1857 |
| LCORE-1856 | LCORE-1858 | Implement degraded mode startup logic for LCORE when LLS is unavailable            | https://redhat.atlassian.net/browse/LCORE-1858 |
| LCORE-1856 | LCORE-1859 | Enhance /health endpoint to report LLS status and degraded mode indicators         | https://redhat.atlassian.net/browse/LCORE-1859 |
| LCORE-1856 | LCORE-1860 | Test startup and runtime scenarios for LLS failure and recovery                    | https://redhat.atlassian.net/browse/LCORE-1860 |
| LCORE-1856 | LCORE-1861 | Add and document configuration toggles for degraded mode behavior                  | https://redhat.atlassian.net/browse/LCORE-1861 |



# Unknowns

* Which architectures must be supported?
* Performance/overhead impact of LCORE-managed lifecycle vs. current separate deployments
* Migration strategy for teams currently running standalone Llama Stack
* Backward compatibility guarantees for existing configurations
* Resource requirements and scaling characteristics for each runtime mode
* Testing strategy for ensuring parity between containerized and local modes



# References



# Changelog

TODO: Record significant changes after initial creation.

| Date       | Change          | Reason          |
|------------|-----------------|-----------------|
| 2026-04-15 | Initial version | feature request |
| 2026-04-16 | Solutions, arch | feature request |

