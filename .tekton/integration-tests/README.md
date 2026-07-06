# Konflux Integration Tests

## Pipelines

### OpenAI E2E (`lightspeed-stack-integration-test.yaml`)

Standard e2e test pipeline using OpenAI as the inference provider.

### RHEL AI E2E (`lightspeed-stack-rhelai-test.yaml`)

E2e test pipeline using a RHEL AI instance (vLLM) as the inference provider.

## RHEL AI Pipeline — MAPT

[MAPT](https://github.com/redhat-developer/mapt) (Multi-Architecture Provisioning Tool) provisions bare-metal-like cloud instances with GPU support. We use it to spin up RHEL AI instances on AWS with vLLM pre-configured, since the e2e tests need a real GPU-backed inference endpoint that OpenShift ephemeral clusters don't provide.

## RHEL AI Pipeline — S3 State Bucket

MAPT uses an S3 bucket to store Pulumi state for provisioning RHEL AI instances. Each pipeline run creates its own prefix under the bucket (`mapt/rhel-ai/<pipelinerun-name>/`) so concurrent runs don't conflict.

The bucket has a **31-day lifecycle rule** that auto-deletes stale state files from failed runs. MAPT's `CleanupState` also removes state after a successful destroy, but this doesn't always run if the pipeline is interrupted.

## RHEL AI Instance Provisioning

The pipeline supports two provisioning modes, controlled by the `spot` pipeline parameter (default: `true`):

- **Spot (default):** MAPT searches all AWS regions for the cheapest spot instance across multiple GPU instance types (g5.12xlarge, g6.12xlarge, g5.24xlarge, g6.24xlarge). Cheaper (~$2-4/hr) but instances can be evicted.
- **On-demand (`spot: false`):** Tries on-demand provisioning sequentially across regions (us-east-1, us-east-2, us-west-2, eu-west-1, eu-central-1, ap-northeast-1) with a 10-minute timeout per attempt. More expensive (~$5-6/hr) but guaranteed capacity once found.

The model used is `meta-llama/Llama-3.1-8B-Instruct` with a 131072-token context window. The VRAM requirement depends on the combination of model size and context window — changing any of these may require a different instance type. All configured instance types provide 96GB+ total VRAM across 4 GPUs.

## RHEL AI AMI Version

The pipeline defaults to RHEL AI version `3.4.0` (GA). This corresponds to a specific AWS AMI that MAPT looks up by name pattern (`rhel-ai-cuda-aws-3.4.0*`). When a new RHEL AI version is released, update the `rhelai-version` default in the pipeline YAML to use the new AMI. Available versions can be listed with:

```bash
mapt aws rhel-ai list-versions
```