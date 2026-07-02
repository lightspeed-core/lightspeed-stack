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

- An admin sets an idle timeout (e.g., 30 minutes) for a tenant.
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

Lightspeed Core uses mechanism based on so called _runners_. Runners implementation are located under `src/runners`. Currently, two runners are implemented:

1. `uvicorn`
1. `quota_scheduler`

These runners are started from the main package: `lightspeed_stack.py`

In order to solve the old conversation cleanup mechanism We can implement a new runner called _conversation_cleaner_ that will run in it's own thread and that will need to be configured. This runner will perform the cleanup.

## Conversation cleaner variants

## Solution S1

Runner will regularly perform the following operations in a loop:

1. select all conversations older than given duration from database tables
1. call the cleaning deletion code, one conversation by one

### Pros
### Cons

## Solution S2

Runner will regularly perform the following operations in a loop:

1. select and delete all conversations older than given duration from database tables

### Pros
### Cons

## Configuration options

## Performance impact

## Requirements

# Architecture

## Trigger mechanism

## Existing storage / data model

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

```sql
CREATE TABLE conversations (
            user_id                text NOT NULL,
            conversation_id        text NOT NULL,
            topic_summary          text,
            last_message_timestamp int NOT NULL,
            PRIMARY KEY(user_id, conversation_id)
        );
```

## Storage / data model changes

## Alternative designs considered

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

| Epic       | Story      | Description                                                                        | Link                                           |
|------------|------------|------------------------------------------------------------------------------------|------------------------------------------------|
| LCORE-0000 | LCORE-0000 |                                                                                    | https://redhat.atlassian.net/browse/LCORE-0000 |


# Changelog

TODO: Record significant changes after initial creation.

| Date       | Change              | Reason          |
|------------|---------------------|-----------------|
| 2026-06-29 | Initial version     | feature request |
| 2026-07-01 | Problem description | initial spike   |

