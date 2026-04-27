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
