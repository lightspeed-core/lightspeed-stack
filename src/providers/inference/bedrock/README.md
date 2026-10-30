# List of source files stored in `src/providers/inference/bedrock` directory

## [__init__.py](__init__.py)

Bedrock inference provider package.

## [provider.py](provider.py)

AWS Bedrock runtime inference provider backed by Pydantic AI.
Discovers models via a separate boto3 control-plane client
(`ListFoundationModels` and `ListInferenceProfiles`) and runs
chat/embeddings through PAI's `BedrockProvider`.

## [specs.py](specs.py)

Wire models for Bedrock foundation-model and inference-profile summaries.

## [model_discovery.py](model_discovery.py)

List foundation models and system-defined inference profiles from the
control-plane client, then resolve invokable catalog wire ids: on-demand
foundation model ids, or the first matching inference profile id.
