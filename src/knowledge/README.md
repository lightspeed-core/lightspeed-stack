# List of source files stored in `src/knowledge` directory

## [__init__.py](__init__.py)

Lightspeed Core Knowledge/RAG Module.

## [capability.py](capability.py)

``Knowledge`` capability: vector-similarity search ("RAG") over knowledge sources.

## [errors.py](errors.py)

Exceptions raised by the knowledge source registry.

## [registry.py](registry.py)

Singleton registry of configured knowledge sources.

## [reranker.py](reranker.py)

Cross-encoder reranking for `Knowledge` search results.

## [search.py](search.py)

Concurrent multi-source knowledge search with optional cross-encoder reranking.

## [toolset.py](toolset.py)

Function-tool toolset for the ``Knowledge`` capability's tool-callable search.

## [types.py](types.py)

Shared types for knowledge capability.

## [utils.py](utils.py)

Shared helpers for reading and editing the current model request's messages.

