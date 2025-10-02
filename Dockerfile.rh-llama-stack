# Custom Red Hat llama-stack image with missing dependencies
FROM quay.io/opendatahub/llama-stack:rhoai-v2.25-latest

# Install missing dependencies
USER root
RUN pip install faiss-cpu==1.11.0

# Switch back to the original user
USER 1001
