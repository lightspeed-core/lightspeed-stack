# List of scenarios

## [`authorized_noop.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/authorized_noop.feature)

* Check if the authorized endpoint works fine when user_id and auth header are not provided
* Check if the authorized endpoint works when auth token is not provided
* Check if the authorized endpoint works when user_id is not provided
* Check if the authorized endpoint rejects empty user_id
* Check if the authorized endpoint works when providing proper user_id

## [`authorized_noop_token.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/authorized_noop_token.feature)

* Check if the authorized endpoint fails when user_id and auth header are not provided
* Check if the authorized endpoint works when user_id is not provided
* Check if the authorized endpoint rejects empty user_id
* Check if the authorized endpoint works when providing proper user_id
* Check if the authorized endpoint works with proper user_id but bearer token is not present
* Check if the authorized endpoint works when auth token is malformed

## [`authorized_rh_identity.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/authorized_rh_identity.feature)

* Request fails when x-rh-identity header is missing
* Request fails when identity field is missing
* Request succeeds with valid User identity and required entitlements
* Request succeeds with valid System identity and required entitlements
* Request fails when required entitlement is missing
* Request fails when entitlement exists but is_entitled is false
* Request fails when User identity is missing user_id
* Request fails when User identity is missing username
* Request fails when System identity is missing cn

## [`conversation_cache_v2.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/conversation_cache_v2.feature)

* V2 conversations endpoint WITHOUT no_tools (known bug - empty vector DB)
* V2 conversations endpoint finds the correct conversation when it exists
* V2 conversations endpoint fails when auth header is not present
* V2 conversations/{conversation_id} endpoint finds conversation with full metadata
* V2 conversations/{conversation_id} endpoint fails when auth header is not present
* V2 conversations/{conversation_id} GET endpoint fails when conversation_id is malformed
* V2 conversations/{conversation_id} GET endpoint fails when conversation does not exist
* Check conversations/{conversation_id} works when llama-stack is down
* Check conversations/{conversation_id} fails when cache not configured
* V2 conversations DELETE endpoint removes the correct conversation
* V2 conversations/{conversation_id} DELETE endpoint fails when auth header is not present
* V2 conversations/{conversation_id} DELETE endpoint fails when conversation_id is malformed
* V2 conversations DELETE endpoint fails when the conversation does not exist
* V2 conversations DELETE endpoint works even when llama-stack is down
* V2 conversations PUT endpoint successfully updates topic summary
* V2 conversations PUT endpoint fails when auth header is not present
* V2 conversations PUT endpoint fails when conversation_id is malformed
* V2 conversations PUT endpoint fails when conversation does not exist
* V2 conversations PUT endpoint fails with empty topic summary (422)

## [`conversations.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/conversations.feature)

* Check if conversations endpoint finds the correct conversation when it exists
* Check if conversations endpoint fails when the auth header is not present
* Check if conversations/{conversation_id} endpoint finds the correct conversation when it exists
* Check if conversations/{conversation_id} endpoint fails when the auth header is not present
* Check if conversations/{conversation_id} GET endpoint fails when conversation_id is malformed
* Check if conversations/{conversation_id} GET endpoint fails when llama-stack is unavailable
* Check if conversations DELETE endpoint removes the correct conversation
* Check if conversations/{conversation_id} DELETE endpoint fails when conversation_id is malformed
* Check if conversations DELETE endpoint fails when the conversation does not exist
* Check if conversations/{conversation_id} DELETE endpoint fails when llama-stack is unavailable

## [`faiss.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/faiss.feature)

* check if vector store is registered
* Check if rags endpoint fails when llama-stack is unavailable
* Check if rags endpoints responds with error when not authenticated
* Query vector db using the file_search tool

## [`feedback.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/feedback.feature)

* Check if enabling the feedback is working
* Check if disabling the feedback is working
* Check if toggling the feedback with incorrect attribute name fails
* Check if getting feedback status returns true when feedback is enabled
* Check if getting feedback status returns false when feedback is disabled
* Check if feedback endpoint is not working when feedback is disabled
* Check if feedback endpoint fails when required fields are not specified
* Check if feedback endpoint is working when sentiment is negative
* Check if feedback endpoint is working when sentiment is positive
* Check if feedback submission fails when invalid sentiment is passed
* Check if feedback submission fails when nonexisting conversation ID is passed
* Check if feedback submission fails when conversation belongs to a different user
* Check if feedback endpoint is not working when not authorized
* Check if update feedback status endpoint is not working when not authorized
* Check if feedback submittion fails when invalid feedback storage path is configured
* Check if feedback endpoint fails when only empty string user_feedback is provided

## [`health.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/health.feature)

* Check if service report proper readiness state
* Check if service report proper liveness state
* Check if service report proper readiness state when llama stack is not available
* Check if service report proper liveness state even when llama stack is not available

## [`info.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/info.feature)

* Check if the OpenAPI endpoint works as expected
* Check if info endpoint is working
* Check if info endpoint reports error when llama-stack connection is not working
* Check if models endpoint is working
* Check if models endpoint reports error when llama-stack is unreachable
* Check if shields endpoint is working
* Check if shields endpoint reports error when llama-stack is unreachable
* Check if tools endpoint is working
* Check if tools endpoint reports error when llama-stack is unreachable
* Check if metrics endpoint is working
* Check if MCP client auth options endpoint is working

## [`query.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/query.feature)

* Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
* Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
* Check if LLM ignores new system prompt in same conversation
* Check if LLM responds to sent question with error when not authenticated
* Check if LLM responds to sent question with error when bearer token is missing
* Check if LLM responds to sent question with error when attempting to access conversation
* Check if LLM responds to sent question with error when attempting to access conversation with incorrect conversation ID format
* Check if LLM responds for query request with error for missing query
* Check if LLM responds for query request with error for missing query
* Check if LLM responds for query request for missing model and provider
* Check if LLM responds for query request with error for missing model
* Check if LLM responds for query request with error for missing provider
* Check if LLM responds for query request with error for unknown model
* Check if LLM responds for query request with error for unknown provider
* Check if LLM responds for query request with error for inability to connect to llama-stack
* Check if LLM responds properly when XML and JSON attachments are sent

## [`rbac.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/rbac.feature)

* Request without token returns 401
* Request with malformed Authorization header returns 401
* Admin can access query endpoint
* Admin can access models endpoint
* Admin can list conversations
* User can access query endpoint
* User can list conversations
* Viewer can list conversations
* Viewer can access info endpoint
* Viewer cannot query - returns 403
* Query-only user can query without specifying model
* Query-only user cannot override model - returns 403
* Query-only user cannot list conversations - returns 403
* No-role user can access info endpoint (everyone role)
* No-role user cannot query - returns 403
* No-role user cannot list conversations - returns 403

## [`rest_api.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/rest_api.feature)

* Check if the OpenAPI endpoint works as expected

## [`smoketests.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/smoketests.feature)

* Check if the main endpoint is reachable

## [`streaming_query.feature`](https://github.com/lightspeed-core/lightspeed-stack/blob/main/tests/e2e/features/streaming_query.feature)

* Check if streaming_query response in tokens matches the full response
* Check if LLM responds properly to restrictive system prompt to sent question with different system prompt
* Check if LLM responds properly to non-restrictive system prompt to sent question with different system prompt
* Check if LLM ignores new system prompt in same conversation
* Check if LLM responds for streaming_query request with error for missing query
* Check if LLM responds for streaming_query request for missing model and provider
* Check if LLM responds for streaming_query request with error for missing model
* Check if LLM responds for streaming_query request with error for missing provider
* Check if LLM responds for streaming_query request with error for unknown model
* Check if LLM responds for streaming_query request with error for unknown provider
* Check if LLM responds properly when XML and JSON attachments are sent
* Check if LLM responds to sent question with error when not authenticated

