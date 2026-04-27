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
