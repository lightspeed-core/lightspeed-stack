from llama_stack_client.types import Tool, ToolCall, ToolResponseMessage

# NOTE: This doesn't work (yet)
class DocumentSummarizerTool(Tool):
    name = "summarize_document"
    description = "Summarizes a long document using a language model."
    parameters = [
        {
            "name" : "documents",
            "description": "the list of documents to be summarized",
            "param_type": "list",
            "required": True,
        },
    ]
    tool_host = "client"
    type = "tool"

    def __init__(self, client, model_id):
        super().__init__()
        self.client = client
        self.model_id = model_id

    async def __call__(self, tool_call: ToolCall) -> ToolResponseMessage:
        text = tool_call.arguments.get("text", "")
        response = await self.client.inference.chat_completion(
            model_id=self.model_id,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes documents."},
                {"role": "user", "content": f"Summarize this:\n{text}"}
            ]
        )
        return ToolResponseMessage(content=response.message.content)
