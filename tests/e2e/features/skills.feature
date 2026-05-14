@e2e_group_2
Feature: Agent skills tests

  Background:
    Given The service is started locally
      And The system is in default state
      And I set the Authorization header to Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva
      And REST API service prefix is /v1
      And the Lightspeed stack configuration directory is "tests/e2e/configuration"

  # --- Configuration & startup ---

  @SkillsConfig
  Scenario: Service starts successfully with skills configured
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains true

  @SkillsConfig
  Scenario: Service fails to start when skill path does not exist
    Given The service uses the lightspeed-stack-skills-invalid-path.yaml configuration
      And The service is restarted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is not 200

  @SkillsConfig
  Scenario: Service fails to start when SKILL.md is missing from skill directory
    Given The e2e-missing-skillmd-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-missing-skillmd.yaml configuration
      And The service is restarted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is not 200

  @SkillsConfig
  Scenario: Service fails to start when SKILL.md has invalid frontmatter
    Given The service uses the lightspeed-stack-skills-invalid-frontmatter.yaml configuration
      And The service is restarted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is not 200

  @SkillsConfig
  Scenario: Service fails to start when duplicate skill names are configured
    Given The service uses the lightspeed-stack-skills-duplicate-names.yaml configuration
      And The service is restarted
    When I access endpoint "readiness" using HTTP GET method
    Then The status code of the response is not 200


  # --- Skill tools registration ---

  @SkillsConfig
  Scenario: Skill tools are registered when skills are configured
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills.yaml configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response contains list_skills
      And The body of the response contains activate_skill
      And The body of the response contains load_skill_resource

  Scenario: Skill tools are not registered when no skills are configured
    Given The service uses the lightspeed-stack.yaml configuration
      And The service is restarted
    When I access REST API endpoint "tools" using HTTP GET method
    Then The status code of the response is 200
      And The body of the response does not contain list_skills
      And The body of the response does not contain activate_skill
      And The body of the response does not contain load_skill_resource


  # --- Skill discovery ---

  @SkillsConfig @Authorized @flaky
  Scenario: LLM can discover skills via list_skills tool using query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "What skills are available? Use the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains e2e-test-skill
      And The token metrics have increased

  @SkillsConfig @Authorized @flaky
  Scenario: LLM can discover skills via list_skills tool using streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "What skills are available? Use the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | e2e-test-skill            |
      And The token metrics have increased


  # --- Skill activation ---

  @SkillsConfig @Authorized @flaky
  Scenario: LLM can activate a skill and use its instructions via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "I need help with e2e testing. Use the activate_skill tool to load the e2e-test-skill.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains skill_content
      And The token metrics have increased

  @SkillsConfig @Authorized @flaky
  Scenario: LLM can activate a skill and use its instructions via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "I need help with e2e testing. Use the activate_skill tool to load the e2e-test-skill.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | skill_content             |
      And The token metrics have increased


  # --- Skill resource loading ---

  @SkillsConfig @Authorized @flaky
  Scenario: LLM can load a skill reference file via load_skill_resource tool using query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "query" to ask question with authorization header
    """
    {"query": "Load the reference file references/guide.md from the e2e-test-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains skill_resource
      And The token metrics have increased

  @SkillsConfig @Authorized @flaky
  Scenario: LLM can load a skill reference file via load_skill_resource tool using streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
      And I capture the current token metrics
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Load the reference file references/guide.md from the e2e-test-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | skill_resource            |
      And The token metrics have increased


  # --- Security: path traversal ---

  @SkillsConfig @Authorized @flaky
  Scenario: load_skill_resource rejects path traversal attempts via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Load the resource ../../etc/passwd from the e2e-test-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains outside skill directory

  @SkillsConfig @Authorized @flaky
  Scenario: load_skill_resource rejects path traversal attempts via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Load the resource ../../etc/passwd from the e2e-test-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | outside skill directory   |


  # --- Error handling: unknown skill ---

  @SkillsConfig @Authorized @flaky
  Scenario: activate_skill returns error for unknown skill name via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Activate a skill called nonexistent-skill using the activate_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains Unknown skill

  @SkillsConfig @Authorized @flaky
  Scenario: activate_skill returns error for unknown skill name via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Activate a skill called nonexistent-skill using the activate_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | Unknown skill             |

  @SkillsConfig @Authorized @flaky
  Scenario: load_skill_resource returns error for unknown skill name via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Load references/guide.md from a skill called nonexistent-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains Unknown skill

  @SkillsConfig @Authorized @flaky
  Scenario: load_skill_resource returns error for unknown skill name via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Load references/guide.md from a skill called nonexistent-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | Unknown skill             |


  # --- Error handling: missing resource ---

  @SkillsConfig @Authorized @flaky
  Scenario: load_skill_resource returns error for nonexistent resource file via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Load references/nonexistent.md from e2e-test-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains Resource not found

  @SkillsConfig @Authorized @flaky
  Scenario: load_skill_resource returns error for nonexistent resource file via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "Load references/nonexistent.md from e2e-test-skill using load_skill_resource.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | Resource not found        |


  # --- Context management: deduplication ---

  @SkillsConfig @Authorized @flaky
  Scenario: Duplicate skill activation in same conversation returns already-loaded note via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-auth-noop-token.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "Activate e2e-test-skill using the activate_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And I store conversation details
    When I use "query" to ask question with same conversation_id
    """
    {"query": "Activate e2e-test-skill again using the activate_skill tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains already loaded


  # --- Multiple skills ---

  @SkillsMultiConfig @Authorized @flaky
  Scenario: Multiple skills can be discovered via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The e2e-second-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-multi.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "List all available skills using the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains e2e-test-skill
      And The body of the response contains e2e-second-skill

  @SkillsMultiConfig @Authorized @flaky
  Scenario: Multiple skills can be discovered via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The e2e-second-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-multi.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "List all available skills using the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | e2e-test-skill            |
          | e2e-second-skill          |

  @SkillsMultiConfig @Authorized @flaky
  Scenario: Skills directory path discovers all skills in subdirectories via query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The e2e-second-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-directory.yaml configuration
      And The service is restarted
    When I use "query" to ask question with authorization header
    """
    {"query": "List all available skills using the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    Then The status code of the response is 200
      And The body of the response contains e2e-test-skill
      And The body of the response contains e2e-second-skill

  @SkillsMultiConfig @Authorized @flaky
  Scenario: Skills directory path discovers all skills in subdirectories via streaming_query endpoint
    Given The e2e-test-skill skill directory is present in the container
      And The e2e-second-skill skill directory is present in the container
      And The service uses the lightspeed-stack-skills-directory.yaml configuration
      And The service is restarted
    When I use "streaming_query" to ask question with authorization header
    """
    {"query": "List all available skills using the list_skills tool.", "model": "{MODEL}", "provider": "{PROVIDER}"}
    """
    When I wait for the response to be completed
    Then The status code of the response is 200
      And The streamed response contains following fragments
          | Fragments in LLM response |
          | e2e-test-skill            |
          | e2e-second-skill          |