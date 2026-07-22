"""Source to be tokenized."""

# # GenAI a Python
#
#                                 Apache License
#                           Version 2.0, January 2004
#                        http://www.apache.org/licenses/
#
#

# Získání seznamu všech dostupných modelů

from ogx.core.library_client import OGXAsLibraryClient
from ogx_client import OgxClient

client = OgxClient(base_url="http://localhost:8321")

print(f"Using Llama Stack version {client._version}")

models = client.models.list()

for model in models:
    print(model)

# ---
#
# ### Llama Stack je použit jako běžná knihovna
#

# Získání seznamu všech dostupných modelů

client = OGXAsLibraryClient("run.yaml")
client.initialize()

print(f"Using Llama Stack version {client._version}")

models = client.models.list()

for model in models:
    print(model)

# ---
#
# ### Komunikace s LLM

client = OgxClient(base_url="http://localhost:8321")

print(f"Using Llama Stack version {client._version}")

models = client.models.list()
model_id = models[0].identifier

print(f"Using model {model_id}")

response = client.chat.completions.create(
    model=model_id,
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)

print(response.to_json())

# ---
#
# ### Vývoj Llama Stacku
#
# * Změny v API
# * Plány na ukončení podpory starších API
#     - deprecation
# * Náhrada agent API za OpenAI API
# * Stabilizace ve verzi 0.7.0 ???
#
# ---

# ### Využití novějšího API

client = OgxClient(base_url="http://localhost:8321")

print(f"Using Llama Stack version {client._version}")

models = client.models.list()
model_id = models[0].identifier

print(f"Using model {model_id}")

response = client.chat.completions.create(
    model=model_id,
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)

print(response.to_json())

# ---
#
# ### Získávání informací z poskytnutých dokumentů
#
# * RAG
# * Ovšem i další vstupy
#     - sémantické vyhledávání
#     - fulltext vyhledávání
#     - hybridní vyhledávání
