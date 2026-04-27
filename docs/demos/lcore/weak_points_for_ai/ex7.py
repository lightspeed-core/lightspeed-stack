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
