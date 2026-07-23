@e2e_group_2
Feature: Agent skills tests

  Background:
    Given The service is started locally
      And The system is in default state
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  # --- Skill tools registration ---

  @SkillsConfig
  Scenario: Skill tools are registered when skills are configured
    Given The service uses the lightspeed-stack-skills.yaml configuration
      And MCP configuration is reset for a new scenario
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
            "provider_id": "file-search",
            "toolgroup_id": "builtin::file_search",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "file_search",
            "description": "Search files for relevant information",
            "parameters": [
              {
                "name": "query",
                "description": "The query to search for. Can be a natural language sentence or keywords.",
                "parameter_type": "string",
                "required": true,
                "default": null
              }
            ],
            "provider_id": "file-search",
            "toolgroup_id": "builtin::file_search",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "list_skills",
            "description": "Get an overview of all available skills and what they do.\n\nUse this when you need to discover what skills exist or refresh your knowledge\nof available capabilities. Skills provide domain-specific knowledge and instructions\nfor specialized tasks.",
            "parameters": [],
            "provider_id": "agent-skills",
            "toolgroup_id": "builtin::agent-skills",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "load_skill",
            "description": "Load complete instructions and capabilities for a specific skill.\n\nA skill contains detailed instructions, supplementary resources (like templates or\nreference docs), and executable scripts. Load a skill when you need to perform a\ntask within its domain.",
            "parameters": [
              {
                "name": "skill_name",
                "description": "Exact name from your available skills list.\nMust match exactly (e.g., \"data-analysis\" not \"data analysis\").",
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
            "description": "Access supplementary documentation, templates, or data from a skill.\n\nResources are additional files that support skill execution. They can be static\ncontent (markdown docs, templates, schemas) or dynamic callables (functions that\ngenerate content based on parameters).\n\nWhen to use this:\n- When a skill's instructions reference a specific resource\n- To access form templates, reference documentation, or data schemas\n- When you need supplementary information beyond the skill instructions",
            "parameters": [
              {
                "name": "skill_name",
                "description": "Name of the skill containing the resource.",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "resource_name",
                "description": "Exact name of the resource as listed in the skill.\nExamples: \"FORMS.md\", \"REFERENCE.md\", \"get_schema\"\nMust match exactly - do not infer or guess.",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "args",
                "description": "Arguments for callable resources (optional for static files).\nKeys must match the parameter names in the resource's schema.",
                "parameter_type": "object",
                "required": false,
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
            "description": "Execute a skill script that performs actions or computations.\n\nScripts are executable programs provided by skills that can perform actions\n(API calls, file operations), process data (transformations, analysis), or\ngenerate outputs (reports, visualizations).\n\nWhen to use this:\n- When a skill's instructions tell you to run a specific script\n- To perform automated tasks that the skill provides\n- For data processing, API interactions, or file operations",
            "parameters": [
              {
                "name": "skill_name",
                "description": "Name of the skill containing the script.",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "script_name",
                "description": "Exact name of the script as listed in the skill.\nExamples: \"analyze.py\", \"scripts/analyze.py\", \"scripts/deploy.sh\", \"scripts/runner\"\nMust match exactly - do not infer or guess.",
                "parameter_type": "string",
                "required": true,
                "default": null
              },
              {
                "name": "args",
                "description": "Arguments required by the script.\nKeys must match the parameter names in the script's schema.",
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
      And MCP configuration is reset for a new scenario
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
            "provider_id": "file-search",
            "toolgroup_id": "builtin::file_search",
            "server_source": "builtin",
            "type": "tool"
          },
          {
            "identifier": "file_search",
            "description": "Search files for relevant information",
            "parameters": [
              {
                "name": "query",
                "description": "The query to search for. Can be a natural language sentence or keywords.",
                "parameter_type": "string",
                "required": true,
                "default": null
              }
            ],
            "provider_id": "file-search",
            "toolgroup_id": "builtin::file_search",
            "server_source": "builtin",
            "type": "tool"
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

  @SkillsConfig @flaky
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

  @SkillsConfig @flaky
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
