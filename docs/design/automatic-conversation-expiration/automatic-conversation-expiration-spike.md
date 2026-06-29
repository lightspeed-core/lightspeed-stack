# Spike for the Automatic conversation expiration

## Overview

**The problem**: Conversation history can already be manually deleted, but
customers who operate high-security environments would like some strong
controls over conversation persistence. Since conversations require some level
of persistence, they have accepted the idea of conversations having a
configurable idle timer. If a conversation is idle for a certain amount of
time, the conversation becomes automatically deleted from any/all persistence
layers. This requirement was communicated to us (the RHOKP team) by our
stakeholders.

**The recommendation**: Implement a new runner that identify idle conversations
and if their time to live (TTL) is longer than defined duration, the
conversation will be deleted using the same code that is implemented in "delete
conversation" REST API endpoint.
