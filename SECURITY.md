# Security Policy

## Supported Versions

Security updates are provided for the following maintained branches and
versions of this project:

| Branch or version | Supported | End of life |
| ----------------- | --------- | ----------- |
| main              | Yes       | N/A         |
| 0.5.1             | No        | 2026-07-30  |
| 0.5.2             | No        | 2026-08-30  |
| 0.6.0rc1          | No        | 2026-09-30  |
| 0.6.0rc2          | No        | 2026-10-30  |
| 0.6.0             | Yes       | 2026-11-30  |
| 0.7.0rc1          | Yes       | TBD         |
| 0.7.0rc2          | Yes       | TBD         |
| 0.7.0rc3          | Yes       | TBD         |
| 0.7.0             | Yes       | 2027-01-31  |

The supported versions table is summarized here for security reporting. The
maintenance documentation is the source of truth for current support status:
[Supported versions](docs/maintenance/versions_supported.md) and
[Unsupported versions](docs/maintenance/versions_unsupported.md).

## Reporting a Vulnerability

If you believe you have discovered a security vulnerability, please do not create a public issue.

Instead, report the vulnerability privately by contacting:

**secalert@redhat.com**

For more info please look at [Security Contacts and Procedures](https://access.redhat.com/security/team/contact)

Please include the following information, where possible:

- A description of the vulnerability
- Steps to reproduce the issue
- Affected versions, branches, or commits
- Any relevant logs, screenshots, or proof of concept code
- Your contact information, if you would like a response

We will acknowledge receipt of your report and investigate it as promptly as possible.

## Vulnerability Handling

Accepted vulnerabilities are triaged by the maintainers and handled according
to the affected supported branch or version. Fixes may be released on `main`,
backported to supported release branches, or published as patch releases when
appropriate.

When applicable, the resolution may include one or more of the following:

- A security fix merged through the normal review and CI process
- A backport to supported release branches
- A patch release or updated container image
- A CVE, advisory, or release note entry
- Public disclosure after a fix or mitigation is available

## Disclosure Policy

We ask that you allow a reasonable amount of time for us to investigate and address the issue before any public disclosure.

## Scope

This policy applies to code, configuration, container and deployment assets,
documentation, generated API schemas, and tests maintained in this repository.

This policy does not cover third-party services, third-party dependencies,
external infrastructure, or downstream deployments that are not maintained in
this repository. Reports about vulnerable dependencies are welcome when they
affect this project and should include the affected package, version, and known
CVE or advisory identifier when available.

## Responsible Disclosure

We appreciate responsible security research and will make reasonable efforts to work with reporters in good faith.
