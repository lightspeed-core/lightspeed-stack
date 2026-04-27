# Lightspeed Core

![LCORE](images/lcore.jpg)

---

## LCORE weak points for AI-driven agentic flow

Pavel Tišnovský,
ptisnovs@redhat.com

---

## AI-driven agentic flow

* An official RH plan to develop and maintain SW products
* It allows developers to be faster
    - more stress on reviewers
* But the whole source structure needs to be in a good state
* Context-awareness problem
    - both for humans and LLMs

---

## LCORE position in this environment

* Luckily the architecture is (still) pretty simple
    - But it can change rapidly with introducing new features
* Strict linting (compared to other Python-based apps)
* A bit level of complection was already "achieved"

---

## Weak points in LCORE

* Consistency
* Risk of complection
* Risk of having too many ad-hoc data transformations
  w/o proper types and/or dynamic dispatch
* Explicit dynamic type checks
* Magic numbers (bad for LLMs)
    - just few places

---

## Overall structure

* Stateful REST API
* Without global mutable state (exc. DB)
* Async code for streaming queries
* Lots of ad-hoc data transformations
    - Llama Stack API is pretty weak

---

## Static vs dynamic structure

* Might be critical for LLMs to understand the project

![Philosophy](images/APhilosophyOfSoftwareDesign.jpg)

---

* (live demo)

---

## Complection (Rich Hickey)

* Stronger than simple coupling
* Complected parts are entangled in purpose and behavior
* Not just connected by interfaces
* Often arises from mixing orthogonal concerns (e.g., state, identity, lifecycle, side effects) inside the same abstraction
* Complected systems resist decomposition, testing, and evolution
* Changes in one place ripple unpredictably.
* -> hard for AI to reason about

---

## Software enthropy

* "The Pragmatic Programmer" [Thomas & Hunt]
    - every time you make a change w/o thinking about the whole system
      the code will get worse

---

## Do you use AI to **add** new features?

---

## Do you use AI to **add** new features?

* Actually **no**
* You are introducing new change that needs to be integrated
* With the potential to worse the architecture

---

## AI in good code base behave very well!

* More pressure on this field
* Especially in times where "code is cheap" is repeatedly said

---

## Examples

---

```python
# hasattr + getattr - better data model needed?

    for key, value in entry.items():
        if not hasattr(tool, key):
            return False
        attr = getattr(tool, key)
        if attr is None:
            return False
        if attr != value and str(attr) != value:
            return False
    return True
```

---

```python
# weak API, can be fixed a bit by dynamic dispatch
for part in content:
    part_type = getattr(part, "type", None)
    if part_type == "input_text":
        input_text_part = cast(InputTextPart, part)
        if input_text_part.text:
            text_fragments.append(input_text_part.text.strip())
    elif part_type == "output_text":
        output_text_part = cast(OutputTextPart, part)
        if output_text_part.text:
            text_fragments.append(output_text_part.text.strip())
    elif part_type == "refusal":
        refusal_part = cast(ContentPartRefusal, part)
        if refusal_part.refusal:
            text_fragments.append(refusal_part.refusal.strip())
```

---

```python
# if-elif chain, can be refactored using pattern matching
if isinstance(event, TaskStatusUpdateEvent):
    if event.status.state == TaskState.failed:
        self._task_state = TaskState.failed
        self._task_status_message = event.status.message
    elif (
        event.status.state == TaskState.auth_required
        and self._task_state != TaskState.failed
    ):
        self._task_state = TaskState.auth_required
        self._task_status_message = event.status.message
    elif (
        event.status.state == TaskState.input_required
        and self._task_state not in (TaskState.failed, TaskState.auth_required)
    ):
        self._task_state = TaskState.input_required
        self._task_status_message = event.status.message
    elif self._task_state == TaskState.working:
        # Keep tracking the working message/status
        self._task_status_message = event.status.message
```

---

```python
# no type checks, no check for missing items
# no checks for typos in keys, etc.
return {
    "input_text": data.input_text,
    "response_text": data.response_text,
    "conversation_id": data.conversation_id,
    "inference_time": data.inference_time,
    "model": data.model,
    "deployment": configuration.deployment_environment,
    "org_id": data.org_id,
    "system_id": data.system_id,
    "total_llm_tokens": data.input_tokens + data.output_tokens,
}
```

---

```python
# cyclomatic complexity: outside human brain capacity!
async def _filter_tools_for_response(
    self,
    input: str | list[OpenAIResponseInput],
    tools: list[OpenAIResponseInputTool],
    model: str,
    conversation: Optional[str],
) -> list[OpenAIResponseInputTool]:
    always_included_tools = set(self.config.tools_filter.always_include_tools)

    # Previously called tools from conversation history
    if conversation:
        try:
            previously_called_tools = await self._get_previously_called_tools(
                conversation
            )
            always_included_tools.update(previously_called_tools)
            logger.info(
                "Always included tools (config + previously called): %s",
                always_included_tools,
            )
        except Exception as e:
            logger.warning("Failed to retrieve conversation history: %s", e)

    tools_for_filtering, tool_to_endpoint = await self._extract_tool_definitions(
        tools
    )

    if not tools_for_filtering:
        logger.warning("No tool definitions found for filtering")
        return tools

    if len(tools_for_filtering) <= self.config.tools_filter.min_tools:
        logger.info(
            "Skipping tool filtering - %d tools (threshold: %d)",
            len(tools_for_filtering),
            self.config.tools_filter.min_tools,
        )
        return tools

    logger.info(
        "Tool filtering enabled - filtering %d tools (threshold: %d)",
        len(tools_for_filtering),
        self.config.tools_filter.min_tools,
    )

    # Extract user prompt text from input
    if isinstance(input, str):
        user_prompt = input
    elif isinstance(input, list):
        user_prompt = "\n".join(
            [
                msg.get("content", "") if isinstance(msg, dict) else str(msg)
                for msg in input
            ]
        )
    else:
        user_prompt = str(input)

    # Call LLM to filter tools
    tools_filter_model_id = self.config.tools_filter.model_id or model
    logger.debug("Using model %s for tool filtering", tools_filter_model_id)
    logger.debug("System prompt: %s", self.config.tools_filter.system_prompt)

    filter_prompt = (
        "Filter the following tools list, the list is a list of dictionaries "
        "that contain the tool name and it's corresponding description \n"
        f"Tools List:\n {tools_for_filtering} \n"
        f'User Prompt: "{user_prompt}" \n'
        "return a JSON list of strings that correspond to the Relevant Tools, \n"
        "a strict top 10 items list is needed,\n"
        "use the tool_name and description for the correct filtering.\n"
        "return an empty list when no relevant tools found."
    )

    request = OpenAIChatCompletionRequestWithExtraBody(
        model=tools_filter_model_id,
        messages=[
            OpenAISystemMessageParam(
                role="system", content=self.config.tools_filter.system_prompt
            ),
            OpenAIUserMessageParam(role="user", content=filter_prompt),
        ],
        stream=False,
        temperature=0.1,
    )
    response = await self.inference_api.openai_chat_completion(request)

    # Parse filtered tool names from LLM response
    content: str = response.choices[0].message.content
    logger.debug("LLM filter response: %s", content)

    filtered_tool_names = []
    if "[" in content and "]" in content:
        list_str = content[content.rfind("[") : content.rfind("]") + 1]
        try:
            filtered_tool_names = json.loads(list_str)
            logger.info("Filtered tool names from LLM: %s", filtered_tool_names)
        except Exception as exp:
            logger.error("Failed to parse LLM response as JSON: %s", exp)
            filtered_tool_names = []

    # Merge always-included tools into filtered list
    filtered_tool_names = list(set(filtered_tool_names) | always_included_tools)

    # Filter using expanded tool definitions
    if filtered_tool_names:
        result = []
        for tool in tools:
            tool_dict = tool if isinstance(tool, dict) else tool.model_dump()
            tool_type = tool_dict.get("type")

            if tool_type == "mcp" and len(filtered_tool_names) > 0:
                # Get the endpoint for this MCP config
                mcp_endpoint = tool_dict.get("server_url", "")
                server_label = tool_dict.get("server_label", "unknown")

                # Filter to only include tools that belong to this endpoint
                endpoint_tools = [
                    tool_name
                    for tool_name in filtered_tool_names
                    if tool_to_endpoint.get(tool_name) == mcp_endpoint
                ]

                if endpoint_tools:
                    if isinstance(tool, dict):
                        tool["allowed_tools"] = endpoint_tools
                    else:
                        tool.allowed_tools = endpoint_tools
                    result.append(tool)
                else:
                    logger.warning(
                        "MCP server %s (%s) has no matching tools - skipping from result",
                        server_label,
                        mcp_endpoint,
                    )
            else:
                # Non-MCP tools (file_search, function) are always included
                logger.debug(
                    "Including non-MCP tool: type=%s, config=%s",
                    tool_type,
                    tool_dict.get("name") if tool_type == "function" else tool_type,
                )
                result.append(tool)

        )
        return result
    return []
```

---

```python
# magic constants are in fact described in comments
# if it can be commented, why not use named constants?
# (LLMs are bad handling pure numbers)
if len(value) > 16:
    raise ValueError(f"attributes can have at most 16 pairs, got {len(value)}")

for key, val in value.items():
    if len(key) > 64:
        raise ValueError(f"attribute key '{key}' exceeds 64 characters")

    if isinstance(val, str) and len(val) > 512:
        raise ValueError(f"attribute value for '{key}' exceeds 512 characters")
```

---

```python
async def run_shield(
    self,
    request: RunShieldRequest,
) -> RunShieldResponse:
    messages = request.messages
    for message in messages:
        # weak API forces us to use runtime checks
        if hasattr(message, "content") and isinstance(message.content, str):
            original_content: str = message.content
            redacted_content: str = self._apply_redaction_rules(original_content)

            if redacted_content != original_content:
                message.content = redacted_content  # Mutating in-place

    return RunShieldResponse(violation=None)
```

---

## Consistency

* Brief description stored in `AGENTS.md`
* Low level consistency
    - syntax level
    - easy to check
* High level consistency
    - architecture level
    - hard to check and maintain

---

## Python features

* Pure functions
* Immutable values
* Immutable variables
* Pydantic models
* Data classes
* Pattern matching
* Dynamic dispatch

---

```python
# True constants are possible in Python

# Max seconds to wait for topic summary in background task after interrupt persist.
TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS: Final[float] = 30.0

# Supported attachment types
ATTACHMENT_TYPES: Final[frozenset] = frozenset(
    {
        "alert",
        "api object",
        "configuration",
        "error message",
        "event",
        "log",
        "stack trace",
    }
)
```

---

```python
# Pydantic model utilization

class ShieldModerationBlocked(BaseModel):
    """Shield moderation blocked the content; refusal details are present."""

    decision: Literal["blocked"] = "blocked"
    message: str
    moderation_id: str
    refusal_response: ResponseMessage
```

---

```python
# Pydantic model utilization

class TranscriptMetadata(BaseModel):
    """Metadata for a transcript entry."""

    provider: Optional[str] = None
    model: str
    query_provider: Optional[str] = None
    query_model: Optional[str] = None
    user_id: str
    conversation_id: str
    timestamp: str


def create_transcript_metadata(
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: Optional[str],
    query_provider: Optional[str],
    query_model: Optional[str],
) -> TranscriptMetadata:
    hashed_user_id = _hash_user_id(user_id)

    return TranscriptMetadata(
        provider=provider_id,
        model=model_id,
        query_provider=query_provider,
        query_model=query_model,
        user_id=hashed_user_id,
        conversation_id=conversation_id,
        timestamp=datetime.now(UTC).isoformat(),
    )
```

---

```python
# Dynamic dispatch: functional style

@singledispatch
def function(arg: Any) -> None:
    print("Original function with argument", arg, "that has type", type(arg))


@function.register
def _(arg: int | str) -> None:
    print("Integer variant with int or str argument:", arg)


@function.register(list | tuple)
def _(arg: list[Any] | tuple[Any, ...]) -> None:
    print("List or tuple variant with argument:", arg)


@function.register
def _(arg: None) -> None:
    print("None variant with argument:", arg)


function(42)
function("foo")
function(["foo", "bar", "baz"])
function(("foo", "bar", "baz"))
function(1.4142)
function(None)
```

---

## Concurrency

* Coroutines (async, await)
    - might be a bit more hard to reason about
* True concurrency
    - multithreading
    - multiprocessing
    - multiple interpreters (new)
    - noGIL (new)
* Dunno
    - I prefer CSP style, but coroutines seems to be preferred

---

## Hints to help with context-awareness problem

* AGENTS.md
    - global one or specific one (e2e etc.)?
    - use caveman?
    - need better metrics
* Avoiding runtime ad-hoc "polymorphism"
    - structural pattern matching
    - dynamic dispatch if really needed

---

## Hints to help with context-awareness problem

* Strongly typed code
    - it reduces problem space a lot
    - we talk about 10x, 100x, 1000x factor!
    - usage of `Any` is cheating in most cases
* Skills

---

## BDD

* Can it help LLMs to understand the code?
* I don't think so, because LLMs seems to be focused on static structure
    - just IMHO
    - can be hacked by agents running BDD???
* A dynamic (runtime) behaviour
* An interesting area to research
    - IMHO more important than having tens of agents eating tokens

---

## Skills

* Definitely an area that will need improvement
* Skills common for multiple teams/projects
* Skills designed directly for LCORE
* Common ground between humans and AI
    - basically shared language with the AI
    - `UBIQUITUOUS_LANGUAGE.md` idea
    - terms used in project with definition
    - should be used in code (functions, vars, comments)
    - https://github.com/mattpocock/skills/blob/main/ubiquitous-language/SKILL.md

---

<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="340" height="320" viewBox="0 0 320 320" fill="none">
    <rect x="320" y="300" width="20" height="20" fill="black" stroke="white">
        <animate
            attributeType="XML"
            attributeName="fill"
            values="black;black;white;white;black"
            dur="0.5s"
            repeatCount="indefinite"/>
    </rect>
</svg>

