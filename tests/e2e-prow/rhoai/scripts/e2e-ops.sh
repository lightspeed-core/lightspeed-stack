#!/bin/bash
# Consolidated E2E operations script for OpenShift/Prow environment
# Usage: e2e-ops.sh <command> [args...]
#
# Commands:
#   restart-lightspeed              - Restart lightspeed-stack pod and port-forward
#   restart-llama-stack             - Restart/restore llama-stack pod
#   restart-port-forward            - Re-establish port-forward for lightspeed
#   wait-for-pod <name> [attempts]  - Wait for a pod to be ready
#   update-configmap <name> <file>  - Update ConfigMap from file
#   get-configmap-content <name>    - Get ConfigMap content (outputs to stdout)
#   disrupt-llama-stack             - Delete llama-stack pod to disrupt connection

set -e

NAMESPACE="${NAMESPACE:-e2e-rhoai-dsc}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_DIR="$SCRIPT_DIR/../manifests/lightspeed"

# ============================================================================
# Helper functions
# ============================================================================

wait_for_pod() {
    local pod_name="$1"
    local max_attempts="${2:-24}"
    
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        local ready
        ready=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || echo "false")
        if [[ "$ready" == "true" ]]; then
            echo "✓ Pod $pod_name ready"
            return 0
        fi
        sleep 3
    done
    
    echo "Pod $pod_name not ready after $((max_attempts * 3))s"
    return 1
}

verify_connectivity() {
    local max_attempts="${1:-6}"
    local local_port="${LOCAL_PORT:-8080}"
    local http_code=""
    
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        # Check readiness endpoint - accept 200 or 401 (auth required but service is up)
        http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$local_port/readiness" 2>/dev/null) || http_code="000"
        
        if [[ "$http_code" == "200" || "$http_code" == "401" ]]; then
            return 0
        fi
        
        if [[ $attempt -lt $max_attempts ]]; then
            sleep 2
        fi
    done
    
    echo "Connectivity check failed (HTTP: ${http_code:-unknown})"
    return 1
}

# ============================================================================
# Command implementations
# ============================================================================

cmd_restart_lightspeed() {
    echo "Restarting lightspeed-stack service..."
    
    # Delete existing pod with timeout
    timeout 60 oc delete pod lightspeed-stack-service -n "$NAMESPACE" --ignore-not-found=true --wait=true || {
        oc delete pod lightspeed-stack-service -n "$NAMESPACE" --ignore-not-found=true --force --grace-period=0 2>/dev/null || true
        sleep 2
    }
    
    # Apply manifest
    oc apply -f "$MANIFEST_DIR/lightspeed-stack.yaml"
    
    # Wait for pod to be ready
    wait_for_pod "lightspeed-stack-service" 20
    
    # Re-label pod for service discovery
    oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n "$NAMESPACE" --overwrite
    
    # Re-establish port-forward
    cmd_restart_port_forward
    
    echo "✓ Lightspeed restart complete"
}

cmd_restart_llama_stack() {
    echo "===== Restoring llama-stack service ====="
    
    # Apply manifest (creates pod if not exists)
    # Use envsubst to expand ${LLAMA_STACK_IMAGE} and other env vars
    echo "Applying pod manifest..."
    envsubst < "$MANIFEST_DIR/llama-stack.yaml" | oc apply -f -
    
    # Wait for pod to be ready
    wait_for_pod "llama-stack-service" 24
    
    # Re-label pod for service discovery
    echo "Labeling pod for service..."
    oc label pod llama-stack-service pod=llama-stack-service -n "$NAMESPACE" --overwrite
    
    echo "===== Llama-stack restore complete ====="
}

cmd_restart_port_forward() {
    local local_port="${LOCAL_PORT:-8080}"
    local remote_port="${REMOTE_PORT:-8080}"
    local max_attempts=3
    
    echo "Re-establishing port-forward on $local_port:$remote_port..."
    
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        # Kill existing port-forward processes
        pkill -9 -f "oc port-forward.*lightspeed" 2>/dev/null || true
        sleep 1
        
        # Start new port-forward in background
        nohup oc port-forward svc/lightspeed-stack-service-svc "$local_port:$remote_port" -n "$NAMESPACE" > /tmp/port-forward.log 2>&1 &
        local pf_pid=$!
        disown $pf_pid 2>/dev/null || true
        sleep 5
        
        # Verify connectivity (more attempts for larger models)
        if verify_connectivity 10; then
            echo "✓ Port-forward established (PID: $pf_pid)"
            return 0
        fi
        
        if [[ $attempt -lt $max_attempts ]]; then
            echo "Attempt $attempt failed, retrying..."
            sleep 3
        fi
    done
    
    echo "Failed to establish port-forward"
    cat /tmp/port-forward.log 2>/dev/null | tail -5 || true
    return 1
}

cmd_wait_for_pod() {
    local pod_name="${1:?Pod name required}"
    local max_attempts="${2:-24}"
    wait_for_pod "$pod_name" "$max_attempts"
}

cmd_update_configmap() {
    local configmap_name="${1:?ConfigMap name required}"
    local source_file="${2:?Source file required}"
    
    echo "Updating ConfigMap $configmap_name from $source_file..."
    
    # Delete existing configmap
    oc delete configmap "$configmap_name" -n "$NAMESPACE" --ignore-not-found=true
    
    # Create new configmap from the source file
    oc create configmap "$configmap_name" -n "$NAMESPACE" \
        --from-file="lightspeed-stack.yaml=$source_file"
    
    echo "✓ ConfigMap $configmap_name updated successfully"
}

cmd_get_configmap_content() {
    local configmap_name="${1:?ConfigMap name required}"
    oc get configmap "$configmap_name" -n "$NAMESPACE" \
        -o 'jsonpath={.data.lightspeed-stack\.yaml}'
}

cmd_disrupt_llama_stack() {
    local pod_name="llama-stack-service"
    
    # Check if pod exists and is running
    local phase
    phase=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
    
    if [[ "$phase" == "Running" ]]; then
        # Delete the pod to disrupt connection
        oc delete pod "$pod_name" -n "$NAMESPACE" --wait=true
        sleep 2
        echo "Llama Stack connection disrupted successfully (pod deleted)"
        exit 0
    else
        echo "Llama Stack pod was not running (phase: $phase)"
        exit 2
    fi
}

# ============================================================================
# Main command dispatcher
# ============================================================================

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
    restart-lightspeed)
        cmd_restart_lightspeed
        ;;
    restart-llama-stack)
        cmd_restart_llama_stack
        ;;
    restart-port-forward)
        cmd_restart_port_forward
        ;;
    wait-for-pod)
        cmd_wait_for_pod "$@"
        ;;
    update-configmap)
        cmd_update_configmap "$@"
        ;;
    get-configmap-content)
        cmd_get_configmap_content "$@"
        ;;
    disrupt-llama-stack)
        cmd_disrupt_llama_stack
        ;;
    *)
        echo "Usage: $0 <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  restart-lightspeed              - Restart lightspeed-stack pod and port-forward"
        echo "  restart-llama-stack             - Restart/restore llama-stack pod"
        echo "  restart-port-forward            - Re-establish port-forward for lightspeed"
        echo "  wait-for-pod <name> [attempts]  - Wait for a pod to be ready"
        echo "  update-configmap <name> <file>  - Update ConfigMap from file"
        echo "  get-configmap-content <name>    - Get ConfigMap content (outputs to stdout)"
        echo "  disrupt-llama-stack             - Delete llama-stack pod to disrupt connection"
        exit 1
        ;;
esac
