"""Source to be tokenized."""

from llama_stack_client import LlamaStackClient

client = LlamaStackClient(base_url="http://localhost:8321")

models = client.models.list()

for model in models:
    print(model)
