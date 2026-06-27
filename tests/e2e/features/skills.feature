@e2e_group_2
Feature: Agent skills tests

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  # --- Skill tools registration ---

  @SkillsConfig @skip
  Scenario: Skill tools are registered when skills are configured
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And MCP toolgroups are reset for a new MCP configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
     And The body of the response is the following
      """
      {
        "tools": [
          {
            "identifier": "insert_into_memory",
            "description": "Insert documents into memory",
            "parameters": [],
            "provider_id": "rag-runtime",
            "toolgroup_id": "builtin::rag",
            "server_source": "builtin",
            "type": "tool_group"
          },
          {
            "identifier": "knowledge_search",
            "description": "Search for information in a database.",
            "parameters": [
              {
                "name": "query",
                "description": "The query to search for. Can be a natural language sentence or keywords.",
                "parameter_type": "string",
                "required": true,
                "default": null
              }
            ],
            "provider_id": "rag-runtime",
            "toolgroup_id": "builtin::rag",
            "server_source": "builtin",
            "type": "tool_group"
          },
          {
            "identifier": "list_skills",
            "description": "List available skills with their names and descriptions. Call this to discover what skills are available.",
            "parameters": [],
            "provider_id": "agent-skills",
            "toolgroup_id": "builtin::agent-skills",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "load_skill",
            "description": "Load full instructions for a skill. Call this when a task matches a skill's description.",
            "parameters": [
              {
                "name": "name",
                "description": "The name of the skill to load",
                "parameter_type": "string",
                "required": true,
                "default": null
              }
            ],
            "provider_id": "agent-skills",
            "toolgroup_id": "builtin::agent-skills",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "read_skill_resource",
            "description": "Load a file from a skill's references/ directory. Use this when skill instructions reference additional documentation.",
            "parameters": [
              {
                "name": "skill_name",
                "description": "The name of the skill containing the resource",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "path",
                "description": "Relative path to the resource file (e.g., 'references/guide.md')",
                "parameter_type": "string",
                "required": true,
                "default": null
              }
            ],
            "provider_id": "agent-skills",
            "toolgroup_id": "builtin::agent-skills",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "run_skill_script",
            "description": "Execute a skill script that performs actions or computations.",
            "parameters": [
              {
                "name": "skill_name",
                "description": "Name of the skill containing the script",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "script_name",
                "description": "Exact name of the script as listed in the skill",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "args",
                "description": "Arguments required by the script",
                "parameter_type": "object",
                "required": false,
                "default": null
              }
            ],
            "provider_id": "agent-skills",
            "toolgroup_id": "builtin::agent-skills",
            "server_source": "builtin",
            "type": "tool"
          }
        ]
      }
      """

  Scenario: Skill tools are not registered when no skills are configured
    Given The service uses the lightspeed-stack.yaml configuration
      And MCP toolgroups are reset for a new MCP configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
     And The body of the response is the following
      """
      {
        "tools": [
          {
            "identifier": "insert_into_memory",
            "description": "Insert documents into memory",
            "parameters": [],
            "provider_id": "rag-runtime",
            "toolgroup_id": "builtin::rag",
            "server_source": "builtin",
            "type": "tool_group"
          },
          {
            "identifier": "knowledge_search",
            "description": "Search for information in a database.",
            "parameters": [
              {
                "name": "query",
                "description": "The query to search for. Can be a natural language sentence or keywords.",
                "parameter_type": "string",
                "required": true,
                "default": null
              }
            ],
            "provider_id": "rag-runtime",
            "toolgroup_id": "builtin::rag",
            "server_source": "builtin",
            "type": "tool_group"
          }
        ]
      }
      """

  # --- Skill discovery ---

  @SkillsConfig
  Scenario: LLM can discover skills via list_skills tool using query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question 
    """
    {"query": "What skills are available? Use the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "list_skills",
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "{\"echo\":\"Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.\"}",
          "type": "function_call_output"
        }
      ]
      """
      And The token metrics have increased

  @SkillsConfig
  Scenario: LLM can discover skills via list_skills tool using streaming_query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question 
    """
    {"query": "What skills are available? Use the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The response is the last streamed fragment
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "list_skills",
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "{\"echo\":\"Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.\"}",
          "type": "function_call_output"
        }
      ]
      """
      And The token metrics have increased

  # --- Skill activation ---

  @SkillsConfig
  Scenario: LLM can Load a skill and use its instructions via query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question 
    """
    {"query": "Echo 'Hello World'. Use the load_skill tool to load the 'echo' skill.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "load_skill",
          "args": {
            "skill_name": "echo"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "<skill>\n<name>echo</name>\n<description>Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.</description>\n<uri>/app-root/skills/echo</uri>\n\n<resources>\n<resource name=\"references/guide.md\" />\n</resources>\n\n<scripts>\n<!-- No scripts -->\n</scripts>\n\n<instructions>\n# Echo Skill\n\n## When to use this skill\n\nUse this skill when:\n- A user asks to echo or repeat text\n- A user wants to verify that the agent can return their input verbatim\n\n## Instructions\n\n1. Read the user's input text\n2. Return the exact text back to the user without modification\n\nFor formatting guidelines, see [references/guide.md](references/guide.md).\n</instructions>\n</skill>\n",
          "type": "function_call_output"
        }
      ]
      """
      And The token metrics have increased

  @SkillsConfig
  Scenario: LLM can load a skill and use its instructions via streaming_query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question 
    """
    {"query": "Echo 'Hello World'. Use the load_skill tool to load the 'echo' skill.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The response is the last streamed fragment
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "load_skill",
          "args": {
            "skill_name": "echo"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "<skill>\n<name>echo</name>\n<description>Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.</description>\n<uri>/app-root/skills/echo</uri>\n\n<resources>\n<resource name=\"references/guide.md\" />\n</resources>\n\n<scripts>\n<!-- No scripts -->\n</scripts>\n\n<instructions>\n# Echo Skill\n\n## When to use this skill\n\nUse this skill when:\n- A user asks to echo or repeat text\n- A user wants to verify that the agent can return their input verbatim\n\n## Instructions\n\n1. Read the user's input text\n2. Return the exact text back to the user without modification\n\nFor formatting guidelines, see [references/guide.md](references/guide.md).\n</instructions>\n</skill>\n",
          "type": "function_call_output"
        }
      ]
      """
      And The token metrics have increased


  # --- Skill resource loading ---

  @SkillsConfig
  Scenario: LLM can load a skill reference file via read_skill_resource tool using query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question 
    """
    {"query": "Load the reference file references/guide.md from the 'echo' skill. Use the read_skill_resource tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "read_skill_resource",
          "args": {
            "skill_name": "echo",
            "resource_name": "references/guide.md"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "# Echo Formatting Guide\n\n## Output format\n\nWhen echoing text back to the user, follow these rules:\n\n- Preserve the exact input text without any modification\n- Do not add quotation marks around the echoed text\n- Do not add any prefix like \"Echo:\" or \"Output:\"\n- Return only the echoed text as the response\n- Preserve whitespace and line breaks exactly as provided\n\n## Examples\n\n**Input**: `Hello World!`\n**Output**: `Hello World!`\n\n**Input**: `multiple words with spaces`\n**Output**: `multiple words with spaces`\n",
          "type": "function_call_output"
        }
      ]
      """
      And The token metrics have increased

  @SkillsConfig
  Scenario: LLM can load a skill reference file via read_skill_resource tool using streaming_query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question 
    """
    {"query": "Load the reference file references/guide.md from the 'echo' skill. Use the read_skill_resource tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The response is the last streamed fragment
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "read_skill_resource",
          "args": {
            "skill_name": "echo",
            "resource_name": "references/guide.md"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "# Echo Formatting Guide\n\n## Output format\n\nWhen echoing text back to the user, follow these rules:\n\n- Preserve the exact input text without any modification\n- Do not add quotation marks around the echoed text\n- Do not add any prefix like \"Echo:\" or \"Output:\"\n- Return only the echoed text as the response\n- Preserve whitespace and line breaks exactly as provided\n\n## Examples\n\n**Input**: `Hello World!`\n**Output**: `Hello World!`\n\n**Input**: `multiple words with spaces`\n**Output**: `multiple words with spaces`\n",
          "type": "function_call_output"
        }
      ]
      """
      And The token metrics have increased

  # --- Error handling: unknown skill ---

  @SkillsConfig @skip
  Scenario: load_skill returns error for unknown skill name via query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I use "query" to ask question 
    """
    {"query": "load a skill called nonexistent-skill using the load_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "load_skill",
          "args": {
            "skill_name": "nonexistent-skill"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "failure",
          "type": "function_call_output"
        }
      ]
      """


  @SkillsConfig @skip
  Scenario: load_skill returns error for unknown skill name via streaming_query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question 
    """
    {"query": "Load a skill called nonexistent-skill using the load_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The response is the last streamed fragment
     And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "load_skill",
          "args": {
            "skill_name": "nonexistent-skill"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "failure",
          "type": "function_call_output"
        }
      ]
      """
  # --- Error handling: missing resource ---

  @SkillsConfig @skip
  Scenario: read_skill_resource returns error for nonexistent resource file via query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I use "query" to ask question 
    """
    {"query": "Load 'references/nonexistent.md' from the 'echo' skill. Use the read_skill_resource tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "read_skill_resource",
          "args": {
            "skill_name": "echo",
            "resource_name": "references/nonexistent.md"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "failure",
          "type": "function_call_output"
        }
      ]
      """

  @SkillsConfig @skip
  Scenario: read_skill_resource returns error for nonexistent resource file via streaming_query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question 
    """
    {"query": "Load 'references/nonexistent.md' from the 'echo' skill. Use the read_skill_resource tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The response is the last streamed fragment
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "read_skill_resource",
          "args": {
            "skill_name": "echo",
            "resource_name": "references/nonexistent.md"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "failure",
          "type": "function_call_output"
        }
      ]
      """


  # --- Context management: deduplication ---

  @SkillsConfig @skip
  Scenario: Duplicate skill activation in same conversation returns already-loaded note via query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I use "query" to ask question 
    """
    {"query": "Load the 'echo' skill using the load_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
     And I store conversation details
    And The body of the "tool_calls" field of the response is the following    
    """
    [
      {
        "name": "load_skill",
        "args": {
          "skill_name": "echo"
        },
        "type": "function_call"
      }
    ]
    """
    And The body of the "tool_results" field of the response is the following    
    """
    [
      {
        "status": "success",
        "content": "<skill>\n<name>echo</name>\n<description>Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.</description>\n<uri>/app-root/skills/echo</uri>\n\n<resources>\n<resource name=\"references/guide.md\" />\n</resources>\n\n<scripts>\n<!-- No scripts -->\n</scripts>\n\n<instructions>\n# Echo Skill\n\n## When to use this skill\n\nUse this skill when:\n- A user asks to echo or repeat text\n- A user wants to verify that the agent can return their input verbatim\n\n## Instructions\n\n1. Read the user's input text\n2. Return the exact text back to the user without modification\n\nFor formatting guidelines, see [references/guide.md](references/guide.md).\n</instructions>\n</skill>\n",
        "type": "function_call_output"
      }
    ]
    """

    When I use "query" to ask question with same conversation_id
    """
    {"query": "Load the 'echo' skill again using the load_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
    And The body of the "tool_calls" field of the response is the following    
    """
    [
      {
        "name": "load_skill",
        "args": {
          "skill_name": "echo"
        },
        "type": "function_call"
      }
    ]
    """
    And The body of the "tool_results" field of the response is the following    
    """
    [
      {
        "status": "failure",
        "type": "function_call_output"
      }
    ]
    """


  # --- Multiple skills ---

  @SkillsMultiConfig
  Scenario: Skills directory path discovers all skills in subdirectories via query endpoint
    Given The service uses the lightspeed-stack-skills-directory.yaml configuration
      And The service is restarted
    When I use "query" to ask question 
    """
    {"query": "List all available skills using the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "list_skills",
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "{\"echo\":\"Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.\",\"summarize\":\"Summarize text into a concise single-sentence overview. Use when a user asks to summarize, condense, or shorten text.\"}",
          "type": "function_call_output"
        }
      ]
      """

  @SkillsMultiConfig
  Scenario: Skills directory path discovers all skills in subdirectories via streaming_query endpoint
    Given The service uses the lightspeed-stack-skills-directory.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question 
    """
    {"query": "List all available skills using the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The response is the last streamed fragment
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "list_skills",
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "{\"echo\":\"Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.\",\"summarize\":\"Summarize text into a concise single-sentence overview. Use when a user asks to summarize, condense, or shorten text.\"}",
          "type": "function_call_output"
        }
      ]
      """

  # --- Full progressive disclosure flow ---

  @SkillsConfig @skip # TODO: This test is too flaky (should be run on demand)
  Scenario: LLM completes list_skills then load_skill then read_skill_resource via query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question
    """
    {"query": "Use Skills and follow progressive disclosure. Say 'Hello World'", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "list_skills",
          "type": "function_call"
        },
        {
          "name": "load_skill",
          "args": {
            "skill_name": "echo"
          },
          "type": "function_call"
        },
        {
          "name": "read_skill_resource",
          "args": {
            "skill_name": "echo",
            "resource_name": "references/guide.md"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "{\"echo\":\"Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.\"}",
          "type": "function_call_output",
          "round": 1
        },
        {
          "status": "success",
          "content": "<skill>\n<name>echo</name>\n<description>Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.</description>\n<uri>/app-root/skills/echo</uri>\n\n<resources>\n<resource name=\"references/guide.md\" />\n</resources>\n\n<scripts>\n<!-- No scripts -->\n</scripts>\n\n<instructions>\n# Echo Skill\n\n## When to use this skill\n\nUse this skill when:\n- A user asks to echo or repeat text\n- A user wants to verify that the agent can return their input verbatim\n\n## Instructions\n\n1. Read the user's input text\n2. Return the exact text back to the user without modification\n\nFor formatting guidelines, see [references/guide.md](references/guide.md).\n</instructions>\n</skill>\n",
          "type": "function_call_output",
          "round": 2
        },
        {
          "status": "success",
          "content": "# Echo Formatting Guide\n\n## Output format\n\nWhen echoing text back to the user, follow these rules:\n\n- Preserve the exact input text without any modification\n- Do not add quotation marks around the echoed text\n- Do not add any prefix like \"Echo:\" or \"Output:\"\n- Return only the echoed text as the response\n- Preserve whitespace and line breaks exactly as provided\n\n## Examples\n\n**Input**: `Hello World!`\n**Output**: `Hello World!`\n\n**Input**: `multiple words with spaces`\n**Output**: `multiple words with spaces`\n",
          "type": "function_call_output",
          "round": 3
        }
      ]
      """


  @SkillsConfig @skip # TODO: This test is too flaky (should be run on demand)
  Scenario: LLM completes list_skills then load_skill then read_skill_resource via streaming_query endpoint
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question
    """
    {"query": "Use Skills and follow progressive disclosure. Say 'Hello World'", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
     And The response is the last streamed fragment
      And The body of the "tool_calls" field of the response is the following    
      """
      [
        {
          "name": "list_skills",
          "type": "function_call"
        },
        {
          "name": "load_skill",
          "args": {
            "skill_name": "echo"
          },
          "type": "function_call"
        },
        {
          "name": "read_skill_resource",
          "args": {
            "skill_name": "echo",
            "resource_name": "references/guide.md"
          },
          "type": "function_call"
        }
      ]
      """
      And The body of the "tool_results" field of the response is the following    
      """
      [
        {
          "status": "success",
          "content": "{\"echo\":\"Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.\"}",
          "type": "function_call_output",
          "round": 1
        },
        {
          "status": "success",
          "content": "<skill>\n<name>echo</name>\n<description>Echo back the user's input exactly as provided. Use when a user asks to echo, repeat, or mirror text.</description>\n<uri>/app-root/skills/echo</uri>\n\n<resources>\n<resource name=\"references/guide.md\" />\n</resources>\n\n<scripts>\n<!-- No scripts -->\n</scripts>\n\n<instructions>\n# Echo Skill\n\n## When to use this skill\n\nUse this skill when:\n- A user asks to echo or repeat text\n- A user wants to verify that the agent can return their input verbatim\n\n## Instructions\n\n1. Read the user's input text\n2. Return the exact text back to the user without modification\n\nFor formatting guidelines, see [references/guide.md](references/guide.md).\n</instructions>\n</skill>\n",
          "type": "function_call_output",
          "round": 2
        },
        {
          "status": "success",
          "content": "# Echo Formatting Guide\n\n## Output format\n\nWhen echoing text back to the user, follow these rules:\n\n- Preserve the exact input text without any modification\n- Do not add quotation marks around the echoed text\n- Do not add any prefix like \"Echo:\" or \"Output:\"\n- Return only the echoed text as the response\n- Preserve whitespace and line breaks exactly as provided\n\n## Examples\n\n**Input**: `Hello World!`\n**Output**: `Hello World!`\n\n**Input**: `multiple words with spaces`\n**Output**: `multiple words with spaces`\n",
          "type": "function_call_output",
          "round": 3
        }
      ]
      """
