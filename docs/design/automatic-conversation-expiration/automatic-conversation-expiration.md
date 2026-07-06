# Feature design for the Automatic conversation expiration

|               |                                                              |
|---------------|--------------------------------------------------------------|
| **Date**      | 2026-06-29                                                   |
| **Component** | Conversation history database, runners                       |
| **Authors**   | Pavel Tišnovský                                              |
| **Feature**   | [LCORE-1475](https://redhat.atlassian.net/browse/LCORE-1475) |
| **Spike**     | [LCORE-2661](https://redhat.atlassian.net/browse/LCORE-2661) |
| **Links**     | Spike doc: `docs/automatic-conversation-expiration`          |

<!-- vim-markdown-toc GFM -->

* [Overview](#overview)
    * [The problem](#the-problem)
    * [Use Cases](#use-cases)
        * [Configurable idle TTL enforcement](#configurable-idle-ttl-enforcement)
        * [Active session usability preserved](#active-session-usability-preserved)
        * [Predictable compliance behavior for high-security tenants](#predictable-compliance-behavior-for-high-security-tenants)
        * [Automated deletion across multiple persistence layers](#automated-deletion-across-multiple-persistence-layers)
        * [Stale conversation cleanup during low traffic](#stale-conversation-cleanup-during-low-traffic)
        * [Idempotent handling of concurrent activity](#idempotent-handling-of-concurrent-activity)
        * [Tenant-specific retention profiles](#tenant-specific-retention-profiles)
        * [Programmatic manual deletion still supported](#programmatic-manual-deletion-still-supported)
        * [Deletion when users stop mid-session](#deletion-when-users-stop-mid-session)
        * [Bulk/periodic expiration windows](#bulkperiodic-expiration-windows)
        * [Retention policy changes take effect predictably](#retention-policy-changes-take-effect-predictably)
        * [Audit/logging for compliance evidence*](#auditlogging-for-compliance-evidence)
    * [The recommendation](#the-recommendation)
    * [PoC validation](#poc-validation)
* [Proposed solution](#proposed-solution)
    * [Basic idea](#basic-idea)
    * [Conversation cleaner variants](#conversation-cleaner-variants)
    * [Solution S1](#solution-s1)
        * [Pros](#pros)
        * [Cons](#cons)
    * [Solution S2](#solution-s2)
        * [Pros](#pros-1)
        * [Cons](#cons-1)
    * [Solution S3](#solution-s3)
        * [Pros](#pros-2)
        * [Cons](#cons-2)
    * [Configuration options](#configuration-options)
        * [Conclusion](#conclusion)
    * [Audit log](#audit-log)
        * [Requirements for audit log](#requirements-for-audit-log)
        * [Security reviews](#security-reviews)
        * [Operational troubleshooting](#operational-troubleshooting)
        * [Accountability and governance](#accountability-and-governance)
        * [Correctness](#correctness)
    * [Performance impact](#performance-impact)
    * [Requirements](#requirements)
* [Architecture](#architecture)
    * [Trigger mechanism](#trigger-mechanism)
    * [Existing storage / data model](#existing-storage--data-model)
        * [Table `user_conversation`](#table-user_conversation)
        * [Table `user_turn`](#table-user_turn)
        * [Table `cache`](#table-cache)
        * [Table `conversation_summaries`](#table-conversation_summaries)
        * [Table `conversations`](#table-conversations)
    * [Storage / data model changes](#storage--data-model-changes)
    * [Audit log table](#audit-log-table)
    * [Alternative designs considered](#alternative-designs-considered)
* [Acceptance criteria](#acceptance-criteria)
    * [Configurable idle TTL enforcement (core)](#configurable-idle-ttl-enforcement-core)
    * [Active session usability preserved](#active-session-usability-preserved-1)
    * [Predictable compliance behavior for high-security tenants](#predictable-compliance-behavior-for-high-security-tenants-1)
    * [Automated deletion across multiple persistence layers](#automated-deletion-across-multiple-persistence-layers-1)
    * [Stale conversation cleanup during low traffic](#stale-conversation-cleanup-during-low-traffic-1)
    * [Idempotent handling of concurrent activity](#idempotent-handling-of-concurrent-activity-1)
    * [Tenant-specific retention profiles](#tenant-specific-retention-profiles-1)
    * [Programmatic manual deletion still supported](#programmatic-manual-deletion-still-supported-1)
    * [Deletion when users stop mid-session](#deletion-when-users-stop-mid-session-1)
    * [Bulk/periodic expiration windows](#bulkperiodic-expiration-windows-1)
    * [Retention policy changes take effect predictably](#retention-policy-changes-take-effect-predictably-1)
    * [Audit/logging for compliance evidence](#auditlogging-for-compliance-evidence-1)
* [Unknowns](#unknowns)
* [References](#references)
* [JIRA stories](#jira-stories)
    * [Epics created](#epics-created)
    * [Stories created](#stories-created)
* [Changelog](#changelog)

<!-- vim-markdown-toc -->

# Overview

This document is the formal deliverable for feature request
[LCORE-1475](https://issues.redhat.com/browse/LCORE-1475). In its final form it
presents a detailed design proposal for adding the new end-to-end support to
clean older conversations in a controlled and consistent manner. The proposal
covers the key mechanisms needed to identify which conversations are eligible
for cleaning, how the cleanup process should be recommended or initiated, and
how the system should ensure safe and predictable behavior across different
conversation states. In addition, it outlines a proof-of-concept validation
plan to confirm that the proposed approach works as intended, demonstrates the
expected outcomes, and provides early evidence for operational feasibility and
effectiveness of the recommendation and cleanup workflow.

## The problem

Conversation history can already be removed manually via REST API endpoints,
but customers in high-security environments need stronger, more predictable
controls over how long conversation data persists. Because conversations by
nature require some degree of persistence for usability (for example, to
maintain context across an active session), those customers have accepted that
conversation data will remain available for a limited time that is fully
configurable.

To meet their security expectations, they want this persistence to be governed
by a configurable idle timer or TTL mechanism: when a conversation has not been
used for a specified period, it should be automatically deleted from every
applicable persistence layer. This aligns the retention behavior with their
operational policies, reducing the chance that stale conversation data remains
accessible longer than intended.

The requirement for configurable, idle-based automatic cleanup was communicated
to us by our stakeholders in the RHOKP team.


## Use Cases

Several use cases have been identified:

### Configurable idle TTL enforcement

- An administrator sets an idle timeout (e.g., 30 minutes) for a tenant.
- When a conversation is inactive longer than the TTL, the system automatically deletes it from every configured persistence layer.

### Active session usability preserved

- A user keeps interacting within the idle window.
- The conversation remains available to maintain context, and is deleted only after the user stops for longer than the TTL.

### Predictable compliance behavior for high-security tenants

- A security team defines an operational policy: “No conversation data older than X idle time.”
- The platform maps that policy to the configurable TTL so deletion timing is deterministic and auditable.

### Automated deletion across multiple persistence layers

- Conversations are stored in more than one place (e.g., conversation store + indexing/cache layer).
- When idle TTL expires, the system ensures deletion propagates to all applicable layers so no stale copies remain.

### Stale conversation cleanup during low traffic

- TTL-based cleanup runs even when there are few or no API calls.
- Conversations that expire are deleted automatically without requiring users to trigger deletion.

### Idempotent handling of concurrent activity

- A conversation approaches TTL expiration while a user submits a new message.
- The system prevents premature deletion by resetting the “last used” timestamp on activity.

### Tenant-specific retention profiles

- Different customers (or environments like staging vs production) require different retention idle timers.
- The platform enforces TTL per tenant/config profile.

### Programmatic manual deletion still supported

- A customer calls a REST endpoint to delete a conversation immediately.
- The TTL mechanism remains intact for other conversations; the system handles “manual delete then TTL” safely (no errors, no resurrected data).

### Deletion when users stop mid-session

- A user starts a conversation, stops using it, and leaves.
- After the TTL expires, the conversation is automatically removed without requiring any explicit user action.

### Bulk/periodic expiration windows

- The system performs background sweeps (e.g., every N minutes).
- Any conversation whose idle time exceeds TTL by the sweep window is deleted, aligning retention with policy.

### Retention policy changes take effect predictably

- An admin updates TTL configuration (e.g., from 60 minutes to 15 minutes).
- Existing conversations follow the updated policy according to defined rules (e.g., next evaluation vs immediate recalculation).

### Audit/logging for compliance evidence*

- For each deleted conversation (triggered by idle TTL), the system records metadata useful for audits (e.g., conversation ID, deletion reason=idle TTL, timestamp).
- This supports demonstrating that stale data wasn’t retained longer than intended.

## The recommendation

This problem can be addressed by introducing a new background runner/service
responsible for identifying idle conversations and enforcing retention based on
a configured policy. The runner would periodically scan for conversations that
have been inactive for longer than the allowed idle window and, for each
candidate, compare its calculated remaining time-to-live (TTL) against the
maximum duration defined by configuration. If a conversation’s TTL exceeds the
allowed duration—meaning it has effectively remained in persistence longer than
the policy permits—the runner would automatically delete it.

To ensure consistent behavior and reduce duplication of logic, the deletion
action should reuse the exact implementation used by the existing “delete
conversation” REST API endpoints (please note that there are two such
endpoints: for conversation v1 and conversation v2). By leveraging the same
deletion code path, the solution maintains a single source of truth for cleanup
semantics (such as what records are removed, what related data is handled, and
how deletion is validated).

## PoC validation

The proof-of-concept (PoC) implementation is not included in this deliverable
because the document is focused on proposing and validating the overall design
and requirements (how idle conversations are identified, how TTL/retention
policy is enforced, and how deletion should be triggered). Providing a full PoC
implementation would require additional scope such as wiring the new runner
into the running services, selecting and configuring persistence-layer queries,
setting up test environments, and implementing end-to-end integration details
that are inherently dependent on the target architecture and operational setup.

Instead, this deliverable defines the approach and expected behavior so the PoC
can be implemented in a follow-up phase once the design is agreed upon. That
sequencing ensures the PoC effort validates the right thing—confirming that the
proposed design works—rather than committing to implementation choices before
the requirements, boundaries, and deletion semantics are finalized.

# Proposed solution

## Basic idea

Lightspeed Core is built around a mechanism called “runners.” Runners are
long-running background components responsible for handling auxiliary system
tasks (for example, scheduled work or continuous services). The implementation
of each runner lives under `src/runners`.

At the moment, Lightspeed Core includes two runner implementations:

1. `uvicorn` (serves the application/API workload)
1. `quota_scheduler` (executes quota-related scheduled logic, like prolonging quota etc.)

Both of these runners are started by the main entrypoint module,
`src/lightspeed_stack.py`, which acts as a very primitive orchestrator for
bringing up the background processes.

To address limitations of the existing conversation cleanup approach, we can
introduce a new runner named `conversation_cleaner`. This runner would run
continuously (in its own thread or worker context) and be responsible for
enforcing the updated conversation retention rules, such as automatically
removing stale conversation data once it exceeds the configured idle TTL.

The `conversation_cleaner` runner should be implemented under `src/runners` and
integrated into the startup sequence in `lightspeed_stack.py`. Because cleanup
behavior may vary by deployment and must be controllable for different
environments, the runner will be configurable—both in terms of whether it is
enabled and in terms of its cleanup configuration (e.g., TTL/idle thresholds,
cleanup frequency, and any batch/limit parameters).

## Conversation cleaner variants

The new proposed runner `conversation_cleaner` can be implemented using several
different methodologies, each representing an alternative solution pattern for
how the runner schedules work, selects candidates, and performs cleanup. These
options differ mainly in how they handle workload selection (batch sweeps vs
queue-driven processing), and concurrency/safety (single-instance simplicity vs
multi-instance coordination). The following sections describe these solutions
and how the runner could be structured for each approach.

## Solution S1

Runner performs operations in a regular loop (periodic runner)
The runner repeatedly executes a fixed set of operations inside an infinite loop (or until shutdown is requested).

1. select all conversations older than given duration from database tables, sorted by timestamp of last update
1. call the cleaning deletion code, one conversation by one

### Pros

1. No complicated transactions are needed
1. If only one conversation is deleted (instead of batch delete) this operation won't interfere with other DB operations
1. One (or more) deletion failures can be skipped

### Cons

1. More DB operations might cause (theoretical) problems with DB throughput

## Solution S2

Runner performs operations in a regular loop (periodic runner)
The runner repeatedly executes a fixed set of operations inside an infinite loop (or until shutdown is requested).

1. select and delete all conversations older than given duration from database tables

### Pros

1. One transaction is easier to develop

### Cons

1. DB will be slower for other operations in "cleanup" time

## Solution S3

Two runners are needed: one for identify older conversations, second to cleanup
such conversations. Runners will communicate via message queue. This queue won't
have to be persisted - it will be recreated after LCore restart.

### Pros

1. Cleanest implementation
1. Responsibilities are segregated

### Cons

1. A bit more complicated overall architecture

## Configuration options

| Field                       | Type    | Description                                                                                                                                                                  |
|-----------------------------|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| minimal_retention_time      | string  | minimal retention time for conversations, specified in human-readable form                                                                                                   |
| period                      | integer | old conversation cleanup scheduler period specified in seconds                                                                                                               |
| database_reconnection_count | integer | Database reconnection count on startup. When database with conversations is not available on startup, the service tries to reconnect N times with specified delay.           |
| database_reconnection_delay | integer | Database reconnection delay specified in seconds. When database with conversations is not available on startup, the service tries to reconnect N times with specified delay. |

The `minimal_retention_time` is written in a human readable format, for example:

```
2 days 5 hours
600 minutes
```

etc.

### Conclusion

In conclusion, the runner-based approach was selected because it is consistent
with the system’s current background job architecture, can be implemented using
the existing schema with limited or no disruptive changes, and provides
predictable, policy-aligned deletion behavior. This minimizes integration risk
and avoids shifting cleanup work into the critical request path, while still
allowing performance safeguards through indexing and controlled execution.

## Audit log

### Requirements for audit log

Audit logging is needed for conversation deletion because deleting
user-generated conversational data is a high-impact, policy-driven operation
that must be transparent, traceable, and verifiable.

### Security reviews

First, audit logs provide evidence for compliance and security reviews. When
deletion is triggered automatically (for example by an idle TTL/retention
policy), the audit entry records that the system enforced the configured
policy, including when the deletion happened, which conversation was affected,
and the reason code (e.g., “idle TTL expired” vs “manual deletion”). This
enables auditors to confirm that stale data is not retained longer than
intended.

### Operational troubleshooting

Second, audit logs support operational troubleshooting. Conversation deletion
may touch multiple persistence layers (primary storage, caches, indexes,
derived artifacts). If a later inconsistency occurs—such as a conversation
still appearing in a UI, search results, or a downstream index—audit records
help identify the exact cleanup run, the deletion path taken, and the decision
timing. This makes it far easier to diagnose whether the issue is due to missed
propagation, temporary failures, or a race condition.

### Accountability and governance

Third, audit logs improve accountability and governance. Manual REST deletions
should be attributable to a caller or request context, while automatic
deletions should be attributable to the lifecycle/cleanup subsystem and its
configuration state. Recording both types of events provides a complete
narrative of “what happened” and “what triggered it,” which is important for
incident response and for change control when retention settings are modified.

### Correctness

Fourth, audit logs help ensure correctness in edge cases. TTL-based cleanup can
be affected by near-boundary timing, concurrent activity, retries, and partial
failures. Having a durable audit trail makes it possible to confirm that the
system applied idle semantics correctly (e.g., did not delete a conversation
that received new activity just before TTL expiry) and that retries did not
accidentally reprocess or resurrect data.

Overall, audit logging turns deletion from a silent background action into an
observable, reviewable workflow—critical for both meeting retention
expectations and maintaining confidence in the system’s behavior over time.

## Performance impact

The older conversation cleanup mechanism introduced via this new feature
request may negatively impact overall system performance, because it likely
triggers a larger number of database operations (for example, scanning for
expired conversations and issuing deletes/updates more frequently or at
inopportune times). This can increase query load, contention, and I/O
utilization, which may reduce throughput or raise latency for regular request
traffic.

To minimize this performance impact, the persistence layer should be optimized
with proper indexes that support the cleanup queries end-to-end. In particular,
database indexes should be added to efficiently identify conversations that are
eligible for deletion (e.g., by tenant/account scope and by idle/last-activity
timestamp, and—where applicable—by status flags indicating “pending cleanup”).
With the right indexes in place, the cleanup workload can avoid full table
scans and reduce the number of rows the system needs to examine and touch.

Additionally, the new cleanup runner should run in a separated execution
context (a dedicated async I/O thread/worker) so it does not block or compete
with latency-sensitive operations such as request handling and interactive
conversation flows. This separation helps ensure that cleanup work is scheduled
and executed in a controlled manner, with appropriate batching and backoff,
rather than interfering with the main application’s event loop.

We expect the performance degradation introduced by enabling and running the
new cleanup mechanism to be limited to no more than a 1% drop under typical
production load.

Finally, performance testing is required to validate that the change meets the
expected impact target. We should run controlled load tests and/or canary
benchmarks with the cleanup runner enabled, compare key metrics (p95/p99
latency, error rates, throughput, DB CPU/IO, and lock wait times) against a
baseline without the new mechanism, and ensure the overall performance drop
does not exceed 1% under representative production-like workloads.

## Requirements

Different part of source code need to be updated:

1. New runner need to be added
1. Existing database schema need to be altered
1. New table for audit log need to be added

# Architecture

## Trigger mechanism

The runner will trigger the conversation deletion subroutines in a timely
manner, driven by a configurable `period` option. That period defines how often
the runner wakes up to evaluate which conversations are eligible for cleanup
(for example, based on idle time exceeding the configured TTL), and then
initiates the appropriate deletion workflow.

When the configured period elapses, the runner executes its selection logic,
processes eligible conversations (typically in controlled batches), and calls
the underlying deletion subroutines for each candidate. After completing the
current cycle, the runner waits until the next scheduled period before
repeating the process. This ensures deletion is performed predictably according
to configuration, while avoiding unnecessary database load from overly frequent
scans.

A very similar mechanism is already implemented in the quota handler. The quota
handler runs as a background component that periodically wakes up based on
configuration, evaluates what work is due (for example, quota items or
scheduled quota updates), and then executes the corresponding operations in a
loop. This includes controlled batching to limit load, and it relies on the
same overall runner lifecycle pattern used elsewhere in the system (start,
periodic execution, and graceful shutdown).

Because the quota handler already solves the problem of “run scheduled work
reliably without impacting request latency,” the conversation cleanup runner
can reuse the same implementation approach: a configurable schedule/period, a
loop-driven execution model, and consistent error handling and backoff
behavior.

## Existing storage / data model

The existing database schema affected by this feature request is described in
this section. It covers the tables and columns that are currently used to store
conversation records and track conversation metadata (such as tenant/account
ownership and timestamps).

This includes any existing structures that the new conversation deletion runner
will query against to determine which conversations have exceeded the
configured idle TTL, as well as the structures that will be updated during
cleanup (for example, status flags, deletion markers, or timestamp fields used
to control “last used” semantics). It also highlights how the current schema
supports (or limits) efficient cleanup operations, including which indexes
exist today and which access patterns may require additional indexing to avoid
performance regression.

### Table `user_conversation`

```sql
CREATE TABLE user_conversation (
            id VARCHAR NOT NULL, 
            user_id VARCHAR NOT NULL, 
            last_used_model VARCHAR NOT NULL, 
            last_used_provider VARCHAR NOT NULL, 
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
            last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
            last_response_id VARCHAR, 
            message_count INTEGER NOT NULL, 
            topic_summary VARCHAR NOT NULL, 
            PRIMARY KEY (id)
);
CREATE INDEX ix_user_conversation_user_id ON user_conversation (user_id);
```

This table contains timestamp stored in a column named `last_message_at` that can be used by cleaner.

### Table `user_turn`

```sql
CREATE TABLE user_turn (
            conversation_id VARCHAR NOT NULL, 
            turn_number INTEGER NOT NULL, 
            started_at DATETIME NOT NULL, 
            completed_at DATETIME NOT NULL, 
            provider VARCHAR NOT NULL, 
            model VARCHAR NOT NULL, 
            response_id VARCHAR, 
            PRIMARY KEY (conversation_id, turn_number), 
            FOREIGN KEY(conversation_id) REFERENCES user_conversation (id) ON DELETE CASCADE
);
CREATE INDEX ix_user_turn_response_id ON user_turn (response_id);
```

This table contains timestamp stored in a column named `completed_at` that can be used by cleaner.

### Table `cache`

```sql
CREATE TABLE cache (
            user_id              text NOT NULL,
            conversation_id      text NOT NULL,
            created_at           int NOT NULL,
            started_at           text,
            completed_at         text,
            query                text,
            response             text,
            provider             text,
            model                text,
            referenced_documents text,
            tool_calls           text,
            tool_results         text,
            PRIMARY KEY(user_id, conversation_id, created_at)
        );

CREATE INDEX timestamps
            ON cache (created_at)
        ;
```

This table contains timestamp stored in a column named `completed_at` that can be used by cleaner.
Additionally we can access this table via compound key `user_id`+`conversation_id`.

### Table `conversation_summaries`

```sql
CREATE TABLE conversation_summaries (
            user_id                 text NOT NULL,
            conversation_id         text NOT NULL,
            created_at              text NOT NULL,
            summarized_through_turn int  NOT NULL,
            token_count             int  NOT NULL,
            model_used              text NOT NULL,
            summary_text            text NOT NULL,
            PRIMARY KEY(user_id, conversation_id, created_at)
        );
```

This table contains timestamp stored in a column named `created_at` that can be used by cleaner.
Additionally we can access this table via compound key `user_id`+`conversation_id`.

### Table `conversations`

```sql
CREATE TABLE conversations (
            user_id                text NOT NULL,
            conversation_id        text NOT NULL,
            topic_summary          text,
            last_message_timestamp int NOT NULL,
            PRIMARY KEY(user_id, conversation_id)
        );
```

This table contains timestamp stored in a column named `last_message_timestamp` that can be used by cleaner.
We can access this table via compound key `user_id`+`conversation_id`.

## Storage / data model changes

The existing database schema is sufficient for implementing the requested
behavior. The current tables already contain the key fields needed to determine
conversation eligibility for deletion (such as tenant/account ownership and
conversation activity timestamps), and they already support the queries
required by the cleanup workflow without requiring disruptive structural
changes.

In addition, the schema provides a place to record or infer cleanup state
(e.g., whether a conversation is still active, pending cleanup, or already
removed). As a result, the runner can select expired conversations efficiently
and apply the deletion subroutines using the existing persistence structures.

Where needed for performance, the feature can rely on creating or adjusting
database indexes to optimize the cleanup access patterns. This allows the
system to avoid full scans and to keep the runtime cost predictable while
implementing TTL/idle-based deletion using the schema that already exists.


## Audit log table

The new table needs to be created (on the fly) for storing audit log information.
Schema of this table can be following:

```sql
CREATE TABLE audit_log_conversation_deletion (
            id                     serial NOT NULL,
            deletion_time          DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
            user_id                text NOT NULL,
            conversation_id        text NOT NULL,
            deletion_source        text NOT NULL,
            requested_by           text NOT NULL,
            status                 text NOT NULL,
            error_code             int,
            error_message          text,
            PRIMARY KEY(user_id, conversation_id)
        );
```

Deletion source can identify Who/what triggered the deletion:

1. automatic_cleaner
1. manual_rest_call
1. admin_action


## Alternative designs considered

No alternate design was considered because the proposed solution aligns with
the system’s existing architecture and operational model, and it directly meets
the stated retention requirement with minimal disruption.

In particular, the platform already uses the runner pattern for periodic
background work (e.g., the quota handler). Implementing conversation cleanup as
another runner follows the same control flow, configuration approach, and
lifecycle management, which reduces integration risk and avoids introducing a
new scheduling/execution paradigm.

Additionally, the existing database schema is sufficient to implement idle
TTL-based deletion without requiring major structural changes. This further
lowers the cost and complexity of the implementation and avoids risky data
migrations or re-modeling.

Finally, alternative designs (such as handling cleanup through request-path
logic, external batch jobs, or implementing a different scheduling mechanism)
would either increase runtime overhead on the critical request path or
introduce operational complexity and harder-to-prove retention guarantees. The
runner-based async execution model provides predictable timing, controllable
load (via batching/period configuration), and clear observability—meeting the
high-security customer expectations with the least change to the current
system.

# Acceptance criteria

## Configurable idle TTL enforcement (core)

- **Given** a tenant has an idle TTL configured for conversations
- **When** a conversation’s idle time (time since last activity) exceeds the configured TTL
- **Then** the system automatically deletes the conversation from every applicable persistence layer
- **And** the conversation is no longer retrievable via the public/API read paths.

## Active session usability preserved

- **Given** a conversation is within the configured idle TTL window
- **When** the user sends a message (or otherwise triggers defined “activity”)
- **Then** the system updates the conversation’s last activity timestamp
- **And** the conversation is not deleted while activity continues before TTL expiry.

## Predictable compliance behavior for high-security tenants

- **Given** a high-security tenant defines a retention policy as “no conversation data older than X idle time”
- **When** the tenant’s TTL configuration is set to match X
- **Then** the system deletes conversations using that TTL
- **And** deletion events include audit metadata that enables deterministic review of why and when deletion occurred.

## Automated deletion across multiple persistence layers

- **Given** a conversation is stored in multiple configured persistence layers
- **When** idle TTL expiration triggers deletion
- **Then** deletion propagates to all those layers
- **And** no layer continues to serve or return the conversation after the deletion completes (per API/read guarantees).

## Stale conversation cleanup during low traffic

- **Given** conversations exist that are past their idle TTL
- **When** the system’s background cleanup/sweep runs
- **Then** all expired conversations are deleted without requiring user-initiated API deletion.

## Idempotent handling of concurrent activity

- **Given** a conversation is at/near the TTL expiration threshold
- **When** a user sends new activity at roughly the same time as a scheduled deletion job executes
- **Then** the system must not delete a conversation that has received valid new activity within the intended TTL semantics
- **And** deletion is idempotent (repeated delete attempts do not corrupt state or re-create data).

## Tenant-specific retention profiles

- **Given** multiple tenants have different TTL configurations
- **When** conversations are evaluated for expiration
- **Then** each conversation expires according to its tenant’s TTL
- **And** deletion workflows cannot delete or affect data from other tenants.

## Programmatic manual deletion still supported

- **Given** a customer calls the REST delete conversation endpoint for a conversation
- **When** the delete request is processed
- **Then** the conversation is removed from all applicable persistence layers according to manual deletion semantics
- **And** any later idle TTL cleanup run does not fail due to already-deleted state
- **And** no subsequent job reintroduces the deleted conversation.

## Deletion when users stop mid-session

- **Given** a user stops interacting with a conversation and no manual deletion is performed
- **When** the conversation remains idle beyond TTL
- **Then** the system deletes the conversation automatically
- **And** subsequent attempts to continue the conversation according to the product contract do not return the expired conversation data.

## Bulk/periodic expiration windows

- **Given** TTL-based deletion is performed by periodic sweeps running every N minutes
- **When** a conversation exceeds TTL by more than the sweep window timing
- **Then** the conversation is deleted within the system’s defined bounded delay after TTL expiry
- **And** deletion occurs in a way that prevents partial cleanup from leaving readable remnants.

## Retention policy changes take effect predictably

- **Given** an admin updates the tenant’s idle TTL from one value to another
- **When** the system next evaluates conversations under the updated policy (according to the documented rule)
- **Then** existing conversations expire according to the defined “next evaluation” or “recompute deadlines” behavior
- **And** the system never extends retention beyond what the documented policy change semantics imply.

## Audit/logging for compliance evidence

- **Given** idle TTL deletion (and/or manual deletion) occurs for a conversation
- **When** the deletion event is recorded
- **Then** the audit record includes at minimum:
  - conversation identifier
  - tenant identifier
  - deletion timestamp
  - deletion reason (idle TTL expired vs manual)
  - the last-activity timestamp (or TTL basis) used for the decision
- **And** audit records are available for authorized audit/compliance retrieval per the system’s access rules.

# Unknowns

# References

# JIRA stories

## Epics created

| Epic       | Description                                             | Link                                           |
|------------|---------------------------------------------------------|------------------------------------------------|
| LCORE-2870 | Refactor runners code to be more modular                | https://redhat.atlassian.net/browse/LCORE-2870 |
| LCORE-2864 | Expose configured conversation expiration duration      | https://redhat.atlassian.net/browse/LCORE-2864 |
| LCORE-2865 | Update conversation activity tracking for expiration    | https://redhat.atlassian.net/browse/LCORE-2865 |
| LCORE-2866 | Expose remaining time until conversation expiration     | https://redhat.atlassian.net/browse/LCORE-2866 |
| LCORE-2867 | Add configurable conversation inactivity timeout        | https://redhat.atlassian.net/browse/LCORE-2867 |
| LCORE-2868 | Implement automatic deletion of expired conversations   | https://redhat.atlassian.net/browse/LCORE-2868 |
| LCORE-2869 | Add tests and documentation for conversation expiration | https://redhat.atlassian.net/browse/LCORE-2869 |

## Stories created

| Epic       | Story      | Description                                                                          | Link                                           |
|------------|------------|--------------------------------------------------------------------------------------|------------------------------------------------|
| LCORE-2870 | LCORE-2884 | Document current runners responsibilities and propose target module breakdown        | https://redhat.atlassian.net/browse/LCORE-2884 |
| LCORE-2870 | LCORE-2885 | Extract shared utilities and define internal interfaces                              | https://redhat.atlassian.net/browse/LCORE-2885 |
| LCORE-2870 | LCORE-2886 | Move core runner logic into separate modules (when the current module is not enough) | https://redhat.atlassian.net/browse/LCORE-2886 |
| LCORE-2870 | LCORE-2887 | Fix regressions, improve tests, and address refactor‑introduced tech debt.           | https://redhat.atlassian.net/browse/LCORE-2887 |
| LCORE-2870 | LCORE-2888 | Final review, documentation update, and sign‑off on acceptance criteria.             | https://redhat.atlassian.net/browse/LCORE-2888 |
| LCORE-2867 | LCORE-2889 | Update tests for configurable expiration behavior                                    | https://redhat.atlassian.net/browse/LCORE-2889 |
| LCORE-2867 | LCORE-2890 | Document the new conversation inactivity timeout configuration and behavior          | https://redhat.atlassian.net/browse/LCORE-2890 |
| LCORE-2867 | LCORE-2891 | Add instance-level conversation inactivity timeout configuration                     | https://redhat.atlassian.net/browse/LCORE-2891 |
| LCORE-2867 | LCORE-2892 | Expose the configured conversation expiration timeout via API                        | https://redhat.atlassian.net/browse/LCORE-2892 |
| LCORE-2867 | LCORE-2893 | Expose remaining conversation time via API                                           | https://redhat.atlassian.net/browse/LCORE-2893 |
| LCORE-2868 | LCORE-2894 | Document automatic conversation expiration behavior and user-facing semantics        | https://redhat.atlassian.net/browse/LCORE-2894 |
| LCORE-2868 | LCORE-2895 | Add tests for automatic conversation expiration behavior                             | https://redhat.atlassian.net/browse/LCORE-2895 |
| LCORE-2868 | LCORE-2896 | Ensure conversation deletion is propagated across all persistence layers             | https://redhat.atlassian.net/browse/LCORE-2896 |
| LCORE-2868 | LCORE-2897 | Implement automatic expiration detection and cleanup for idle conversations          | https://redhat.atlassian.net/browse/LCORE-2897 |


# Changelog

TODO: Record significant changes after initial creation.

| Date       | Change                      | Reason          |
|------------|-----------------------------|-----------------|
| 2026-06-29 | Initial version             | feature request |
| 2026-07-01 | Problem description         | initial spike   |
| 2026-07-06 | Database schema description | initial spike   |

