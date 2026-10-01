# @skip-on-vllm: the vLLM matrices take the model id from an env var, and
# inference.context_windows keys are not env-substituted, so those runs
# cannot register the small window these scenarios need.
@cfg_compaction @skip-on-vllm
Feature: Conversation compaction

  Once the estimated input crosses the configured share of the model's
  context window, older turns are summarized before the request reaches
  the model. The compaction fixtures register a 2000-token window with a
  10% threshold and keep one recent turn verbatim, so a long third query
  is what crosses it first: turn one is summarized, turn two stays in the
  verbatim buffer, and the third query asks for a fact from each.

  From there every query summarizes the turn that has just fallen out of
  the buffer, so the fifth query runs against three summaries plus the
  verbatim fourth turn: the first holds the datacenter name, the second
  the team name (the turn the third query had kept verbatim), the third
  the long query itself, and the buffer holds the database name. The
  fifth query asks for those three names, which no later answer repeats,
  so it passes only if no summary replaced an earlier one and no
  buffered turn was dropped on the way (LCORE-4219).

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"


  Scenario: the third query crosses the threshold, later summaries keep the earlier ones, recall and history survive
    Given The service uses the lightspeed-stack-compaction.yaml configuration
      And the active model has a registered context window
      And The service is restarted
     When I use "query" to ask question
     """
     {"query": "My OpenShift cluster is named aurora-prod-7 and it runs in the datacenter called north-quarry. Remember both names and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "full"
      And I store conversation details
     When I use "query" to ask question with same conversation_id
     """
     {"query": "My application namespace is called blue-lagoon and the team that owns it is called lantern-ops. Remember both names too and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
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
     When I use "query" to ask question with same conversation_id
     """
     {"query": "My database is called green-harbor. Remember that name too and reply with OK only.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"
     When I use "query" to ask question with same conversation_id
     """
     {"query": "What is the name of my datacenter, what is the name of the team that owns my namespace, and what is the name of my database? Reply with the three names only, separated by commas.", "model": "{MODEL}", "provider": "{PROVIDER}"}
     """
     Then The status code of the response is 200
      And The response context_status is "summarized"
      And The response contains following fragments
          | Fragments in LLM response |
          | north-quarry              |
          | lantern-ops               |
          | green-harbor              |
     When I use REST API conversation endpoint with conversation_id from above using HTTP GET method
     Then The status code of the response is 200
      And The conversation history holds 5 turns and no compaction summary marker
      And The conversation history includes the following user queries
          | User query                                                                                                                                      |
          | My OpenShift cluster is named aurora-prod-7 and it runs in the datacenter called north-quarry. Remember both names and reply with OK only.      |
          | My application namespace is called blue-lagoon and the team that owns it is called lantern-ops. Remember both names too and reply with OK only. |


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
