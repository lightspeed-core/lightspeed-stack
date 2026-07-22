"""Source to be tokenized."""

from ogx_client import OgxClient

client = OgxClient(base_url="http://localhost:8321")

models = client.models.list()

for model in models:
    print(model)
