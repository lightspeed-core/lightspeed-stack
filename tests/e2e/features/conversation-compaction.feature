@cfg_compaction
Feature: Conversation compaction

  Once the estimated input crosses the configured share of the model's
  context window, older turns are summarized before the request reaches
  the model. The compaction fixtures register a 2000-token window with a
  10% threshold and keep one recent turn verbatim, so a long third query
  is what crosses it: turn one ends up in the summary, turn two stays in
  the verbatim buffer, and the third query asks for a fact from each.

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  Scenario: the third query crosses the threshold, older turns are summarized, recall and history survive
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And the active model has a registered context window
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "full"
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "My application namespace is called blue-lagoon. Remember that name too and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "full"
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Some background on my environment first, no need to comment on it. The cluster runs on bare metal in two racks with three control plane nodes and nine worker nodes, all on the same subnet behind a pair of hardware load balancers. Storage is provided by an external Ceph cluster exposed through the CSI driver, with three storage classes for block, file and object access. Ingress is handled by the default router with two replicas pinned to the infra nodes, and TLS certificates are issued by an internal certificate authority and rotated every ninety days. Monitoring uses the built-in Prometheus stack with a remote write to a central Thanos instance, and alerts are routed to an on-call rotation through a webhook receiver. The image registry is the internal one, backed by an object storage bucket, and images are mirrored from an upstream registry once a day by a scheduled job. Upgrades follow the stable channel, one minor version at a time, and are rehearsed on a staging cluster of the same shape a week before production. Backups of etcd are taken hourly and copied off-site nightly. Now the question: what is the name of my cluster and what is the name of my application namespace? Reply with the two names only, separated by a comma.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"
      And The response contains following fragments
          | Fragments in LLM response |
          | aurora-prod-7             |
          | blue-lagoon               |
     When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
     Then The status code of the response is 200
      And The conversation history includes the following user queries
          | User query                                                                                    |
          | My OpenShift cluster is named aurora-prod-7. Remember that name and reply with OK only.       |
          | My application namespace is called blue-lagoon. Remember that name too and reply with OK only. |


  Scenario: the native stream announces compaction on the query that crosses the threshold
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And the active model has a registered context window
      And The service is restarted
     When I use "streaming_query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I wait for the response to be completed
      And The streamed response end event has context_status "full"
      And I store conversation details
     When I use "streaming_query" to ask question with same conversation_id
     """
     {"query": "My application namespace is called blue-lagoon. Remember that name too and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I wait for the response to be completed
      And The streamed response end event has context_status "full"
     When I use "streaming_query" to ask question with same conversation_id
     """
     {"query": "Some background on my environment first, no need to comment on it. The cluster runs on bare metal in two racks with three control plane nodes and nine worker nodes, all on the same subnet behind a pair of hardware load balancers. Storage is provided by an external Ceph cluster exposed through the CSI driver, with three storage classes for block, file and object access. Ingress is handled by the default router with two replicas pinned to the infra nodes, and TLS certificates are issued by an internal certificate authority and rotated every ninety days. Monitoring uses the built-in Prometheus stack with a remote write to a central Thanos instance, and alerts are routed to an on-call rotation through a webhook receiver. The image registry is the internal one, backed by an object storage bucket, and images are mirrored from an upstream registry once a day by a scheduled job. Upgrades follow the stable channel, one minor version at a time, and are rehearsed on a staging cluster of the same shape a week before production. Backups of etcd are taken hourly and copied off-site nightly. Now the question: what is the name of my cluster and what is the name of my application namespace? Reply with the two names only, separated by a comma.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I wait for the response to be completed
      And The streamed response contains a compaction event before the first token
      And The streamed response end event has context_status "summarized"


  Scenario: compaction stays off when disabled, even past the threshold
    Given The service uses the lightspeed-stack-compaction-disabled.yaml configuration
      And the active model has a registered context window
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7. Remember that name and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "My application namespace is called blue-lagoon. Remember that name too and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
     When I use "query" to ask question with same conversation_id
     """
     {"query": "Some background on my environment first, no need to comment on it. The cluster runs on bare metal in two racks with three control plane nodes and nine worker nodes, all on the same subnet behind a pair of hardware load balancers. Storage is provided by an external Ceph cluster exposed through the CSI driver, with three storage classes for block, file and object access. Ingress is handled by the default router with two replicas pinned to the infra nodes, and TLS certificates are issued by an internal certificate authority and rotated every ninety days. Monitoring uses the built-in Prometheus stack with a remote write to a central Thanos instance, and alerts are routed to an on-call rotation through a webhook receiver. The image registry is the internal one, backed by an object storage bucket, and images are mirrored from an upstream registry once a day by a scheduled job. Upgrades follow the stable channel, one minor version at a time, and are rehearsed on a staging cluster of the same shape a week before production. Backups of etcd are taken hourly and copied off-site nightly. Now the question: what is the name of my cluster and what is the name of my application namespace? Reply with the two names only, separated by a comma.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "full"
