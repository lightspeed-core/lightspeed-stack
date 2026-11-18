# List of source files stored in `src/knowledge/sources` directory

## [__init__.py](__init__.py)

Knowledge Sources for Knowledge/RAG in Lightspeed Core.

## [base.py](base.py)

Abstract base for pluggable knowledge sources.

## [faiss.py](faiss.py)

Faiss vector store backed by a sqlite-faiss kvstore file.

## [okp.py](okp.py)

OKP knowledge source backed by the OKP MCP server.

## [pgvector.py](pgvector.py)

pgvector knowledge source that reads OGX ``remote::pgvector`` tables.

## [utils.py](utils.py)

Helpers for building knowledge sources from RAG configuration.

