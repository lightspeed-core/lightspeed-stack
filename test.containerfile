# Custom Red Hat llama-stack image with missing dependencies
FROM quay.io/rhoai/odh-llama-stack-core-rhel9:rhoai-3.4 

# Install missing dependencies and create required directories
USER root
RUN pip install azure-identity && \
    mkdir -p /app-root && \
    chown -R 1001:0 /app-root && \
    chmod -R 775 /app-root && \
    mkdir -p /opt/app-root/src/.llama/storage /opt/app-root/src/.llama/providers.d && \
    chown -R 1001:0 /opt/app-root/src/.llama && \
    mkdir -p /opt/app-root/src/.cache/huggingface && \
    chown -R 1001:0 /opt/app-root/src/.cache

# Copy enrichment scripts for runtime config enrichment
COPY src/llama_stack_configuration.py /opt/app-root/llama_stack_configuration.py
COPY scripts/llama-stack-entrypoint.sh /opt/app-root/enrich-entrypoint.sh
RUN chmod +x /opt/app-root/enrich-entrypoint.sh && \
    chown 1001:0 /opt/app-root/enrich-entrypoint.sh /opt/app-root/llama_stack_configuration.py

# Switch back to the original user
USER 1001

ENTRYPOINT ["/opt/app-root/enrich-entrypoint.sh"]
