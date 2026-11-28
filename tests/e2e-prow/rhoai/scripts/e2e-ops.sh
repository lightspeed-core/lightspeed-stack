#!/bin/bash
# Consolidated E2E operations script for OpenShift/Prow environment
# Usage: e2e-ops.sh <command> [args...]
#
# Architecture note (why logs look "fine" but CI flakes):
# - pipeline-konflux.sh keeps oc port-forward to localhost:8080 for the test run.
# - Behave hooks call restart-lightspeed, which must kill that forward and rebind.
# - E2E_LSC_PORT_FORWARD_PID_FILE coordinates the handoff.
# - Single pod: lightspeed-stack-service (OGX in-process). No separate OGX pod or :8321 forward.
# - OKP Solr: deploy-okp-solr from @cfg_okp features; reachability checked from the LCS pod.
#
# Commands:
#   restart-lightspeed                - Restart lightspeed-stack pod and port-forward
#   restart-jwks-port-forward         - Re-establish JWKS port-forward for LCS auth tests
#   restart-port-forward              - Re-establish port-forward for lightspeed
#   wait-for-pod <name> [attempts]    - Wait for a pod to be ready
#   update-configmap <name> <file>    - Update ConfigMap from file
#   get-configmap-content <name>      - Get ConfigMap content (outputs to stdout)
#   dump-pod-logs <pod> [tail-lines]  - Print init + container logs
#   check-okp-solr-from-llama         - GET Solr from inside lightspeed-stack-service (legacy name)
#   deploy-okp-solr                   - Deploy OKP Solr (idempotent; @cfg_okp before_feature)
#   delete-okp-solr                   - Delete OKP Solr pod
#   disrupt-okp-solr                  - Delete OKP Solr pod to disrupt connection
#   restore-okp-solr                  - Restore OKP Solr pod

set -e

NAMESPACE="${NAMESPACE:-e2e-rhoai-dsc}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_DIR="$SCRIPT_DIR/../manifests/lightspeed"

# Konflux always runs library mode (single lightspeed-stack pod).
if [[ "${E2E_KONFLUX_E2E:-0}" == "1" ]]; then
    export E2E_DEPLOYMENT_MODE=library
fi

# Written by pipeline-konflux.sh when it starts LCS port-forward; e2e-ops kills this PID before rebinding 8080.
E2E_LSC_PORT_FORWARD_PID_FILE="${E2E_LSC_PORT_FORWARD_PID_FILE:-/tmp/e2e-lightspeed-port-forward.pid}"
E2E_JWKS_PORT_FORWARD_PID_FILE="${E2E_JWKS_PORT_FORWARD_PID_FILE:-/tmp/e2e-jwks-port-forward.pid}"

# ============================================================================
# Helper functions
# ============================================================================

# Print container logs only (no events/describe). Used on failure paths.
e2e_ops_dump_pod_logs() {
    local pod_name="${1:?pod name required}"
    local log_tail="${2:-150}"
    local prefix="[e2e-ops] "
    local ctr tmp

    echo "${prefix}--- logs: pod/$pod_name ---"
    if ! oc get pod "$pod_name" -n "$NAMESPACE" &>/dev/null; then
        echo "${prefix}pod not found, cannot fetch logs"
        return 0
    fi
    while IFS= read -r ctr; do
        [[ -n "$ctr" ]] || continue
        echo "${prefix}--- oc logs -c $ctr ---"
        tmp=$(mktemp)
        oc logs "$pod_name" -n "$NAMESPACE" -c "$ctr" --tail="$log_tail" >"$tmp" 2>&1 \
            || true
        sed "s/^/${prefix}/" <"$tmp"
        rm -f "$tmp"
    done < <(
        oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}{end}{range .spec.containers[*]}{.name}{"\n"}{end}' 2>/dev/null \
            || true
    )
}

wait_for_pod() {
    local pod_name="$1"
    local max_attempts="${2:-24}"
    local attempt phase

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        local ready
        ready=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || echo "false")
        if [[ "$ready" == "true" ]]; then
            echo "✓ Pod $pod_name ready (after $((attempt * 3))s)"
            return 0
        fi
        if (( max_attempts >= 60 && attempt % 20 == 0 )); then
            phase=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "?")
            echo "[e2e-ops] Still waiting for $pod_name ($attempt/${max_attempts}, phase=${phase})..."
        fi
        sleep 3
    done

    echo "Pod $pod_name not ready after $((max_attempts * 3))s"
    e2e_ops_dump_pod_logs "$pod_name" 200
    return 1
}

# Linux: find PIDs with a LISTEN socket on TCP port (decimal) via /proc when lsof/ss are missing.
kill_tcp_listen_pids_via_procfs() {
    local port="${1:?port required}"
    local port_hex inode pid fd link
    port_hex=$(printf '%04X' "$port")
    local -a inodes=()
    while read -r inode; do
        [[ -n "$inode" ]] && inodes+=("$inode")
    done < <(
        {
            awk -v p=":${port_hex}\$" '$1 ~ /^[0-9]+:$/ && $4 == "0A" && $2 ~ p { print $10 }' /proc/net/tcp 2>/dev/null
            awk -v p=":${port_hex}\$" '$1 ~ /^[0-9]+:$/ && $4 == "0A" && $2 ~ p { print $10 }' /proc/net/tcp6 2>/dev/null
        } | sort -u
    )
    for inode in "${inodes[@]}"; do
        for fd in /proc/[0-9]*/fd/*; do
            [[ -e "$fd" ]] || continue
            link=$(readlink "$fd" 2>/dev/null) || continue
            if [[ "$link" == "socket:[$inode]" ]]; then
                pid="${fd#/proc/}"
                pid="${pid%%/*}"
                if [[ "$pid" =~ ^[0-9]+$ && "$pid" != "1" ]]; then
                    kill -9 "$pid" 2>/dev/null || true
                fi
            fi
        done
    done
}

# Free a local TCP port. Stale oc port-forward often survives "lost connection" but still
# listens on 8080. Try every method: lsof, fuser, ss, then /proc (Konflux often has no lsof/ss).
free_local_tcp_port() {
    local port="${1:?port required}"
    local pid
    if command -v lsof >/dev/null >&2; then
        for pid in $(lsof -ti:"$port" -sTCP:LISTEN 2>/dev/null); do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
    if command -v fuser >/dev/null >&2; then
        fuser -k "${port}/tcp" 2>/dev/null || true
    fi
    if command -v ss >/dev/null >&2; then
        # LISTEN ... users:(("oc",pid=1234,fd=7))
        while read -r pid; do
            [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
        done < <(ss -lptnH "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u)
    fi
    if [[ -r /proc/net/tcp ]]; then
        kill_tcp_listen_pids_via_procfs "$port"
    fi
    sleep 1
}

# Kill anything likely to hold the Lightspeed local forward; then free the port (twice for races).
kill_stale_lightspeed_forward() {
    local port="${1:-8080}"
    local saved_pf
    # Pipeline leaves oc port-forward on 8080; pkill patterns can miss (argv wrapping). PID file is authoritative.
    if [[ -f "$E2E_LSC_PORT_FORWARD_PID_FILE" ]]; then
        read -r saved_pf <"$E2E_LSC_PORT_FORWARD_PID_FILE" 2>/dev/null || true
        if [[ "$saved_pf" =~ ^[0-9]+$ ]]; then
            kill -9 "$saved_pf" 2>/dev/null || true
        fi
    fi
    pkill -9 -f "port-forward.*lightspeed-stack-service-svc" 2>/dev/null || true
    pkill -9 -f "kubectl port-forward.*lightspeed-stack-service-svc" 2>/dev/null || true
    pkill -9 -f "oc port-forward svc/lightspeed-stack-service-svc" 2>/dev/null || true
    pkill -9 -f "port-forward pod/lightspeed-stack-service" 2>/dev/null || true
    pkill -9 -f "port-forward.*${port}:${port}" 2>/dev/null || true
    free_local_tcp_port "$port"
    sleep 1
    free_local_tcp_port "$port"
}

# Kill anything likely to hold the mock-jwks local forward (localhost:8000).
kill_stale_jwks_forward() {
    local port="${1:-8000}"
    local saved_pf
    if [[ -f "$E2E_JWKS_PORT_FORWARD_PID_FILE" ]]; then
        read -r saved_pf <"$E2E_JWKS_PORT_FORWARD_PID_FILE" 2>/dev/null || true
        if [[ "$saved_pf" =~ ^[0-9]+$ ]]; then
            kill -9 "$saved_pf" 2>/dev/null || true
        fi
    fi
    pkill -9 -f "port-forward.*mock-jwks.*${port}:${port}" 2>/dev/null || true
    pkill -9 -f "oc port-forward svc/mock-jwks ${port}:${port}" 2>/dev/null || true
    free_local_tcp_port "$port"
    sleep 1
    free_local_tcp_port "$port"
}

# After oc port-forward dies in <2s, show recent oc stderr from the log file.
e2e_ops_emit_port_forward_immediate_failure_diag() {
    echo "[e2e-ops] /tmp/port-forward.log (tail 25):"
    if [[ -s /tmp/port-forward.log ]]; then
        tail -25 /tmp/port-forward.log 2>/dev/null | sed 's/^/[e2e-ops] /' || true
    else
        echo "[e2e-ops] (log empty or missing)"
    fi
}

e2e_ops_diagnose_forward_failure() {
    echo "[e2e-ops] Port-forward failed after all retries."
    if [[ -s /tmp/port-forward.log ]]; then
        echo "[e2e-ops] /tmp/port-forward.log (tail 30):"
        tail -30 /tmp/port-forward.log 2>/dev/null | sed 's/^/[e2e-ops] /' || true
    fi
    e2e_ops_dump_pod_logs "lightspeed-stack-service" 10000
}

verify_connectivity() {
    local max_attempts="${1:-6}"
    local local_port="${LOCAL_PORT:-8080}"
    local http_code=""

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        # First check /readiness to see if port-forward is alive (accept 200, 401, or 503)
        http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$local_port/readiness" 2>/dev/null) || http_code="000"

        # LCS returns 503 when provider health fails (see health.py). Only accept 503
        # on the last attempt so normal restarts keep retrying while providers warm up
        # (transient 503 then 200) and we do not short-circuit other suites on first 503.
        if [[ "$http_code" == "503" ]]; then
            if [[ "$attempt" -eq "$max_attempts" ]]; then
                echo "[e2e-ops] /readiness=503 after $max_attempts attempts — LCS reachable; providers still unhealthy (expected for some e2e)"
                return 0
            fi
            echo "[e2e-ops] /readiness=503 (attempt $attempt/$max_attempts); retrying in case providers recover..."
        fi

        if [[ "$http_code" == "200" || "$http_code" == "401" ]]; then
            # Port-forward works; now verify the app is fully initialized by hitting
            # a real endpoint. /v1/models requires the OGX handshake to complete.
            # Accept 200 (no auth) or 401/403 (auth) — both prove the full app stack is up.
            # Some e2e scenarios misconfigure inference; /v1/models may return 5xx while
            # LCS is still reachable — treat that as success for restart-lightspeed.
            local models_code
            models_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://localhost:$local_port/v1/models" 2>/dev/null) || models_code="000"
            if [[ "$models_code" == "200" || "$models_code" == "401" || "$models_code" == "403" ]]; then
                return 0
            fi
            if [[ "$models_code" =~ ^5[0-9][0-9]$ ]]; then
                echo "[e2e-ops] /v1/models=$models_code (LCS reachable; provider error expected in some e2e)"
                return 0
            fi
            echo "[e2e-ops] /readiness=$http_code but /v1/models=$models_code (app still initializing, attempt $attempt/$max_attempts)"
        fi

        if [[ $attempt -lt $max_attempts ]]; then
            sleep 5
        fi
    done

    echo "Connectivity check failed (readiness: ${http_code:-unknown})"
    return 1
}

# ============================================================================
# Command implementations
# ============================================================================

# RHEL AI matrix: after LCS restart, wait until /v1/models lists the configured vLLM model.
_wait_for_vllm_model_in_lcs_registry() {
    if ! oc get secret vllm-url-secret -n "$NAMESPACE" &>/dev/null; then
        return 0
    fi
    local model_id
    model_id="$(oc get secret vllm-model-secret -n "$NAMESPACE" -o jsonpath='{.data.key}' 2>/dev/null | base64 -d 2>/dev/null || true)"
    if [[ -z "$model_id" ]]; then
        return 0
    fi
    local needle="vllm/${model_id}"
    local local_port="${LOCAL_PORT:-8080}"
    echo "[e2e-ops] Waiting for ${needle} in LCS GET /v1/models..."
    local attempt
    for ((attempt=1; attempt<=60; attempt++)); do
        if curl -sf --max-time 15 "http://127.0.0.1:${local_port}/v1/models" 2>/dev/null | grep -Fq "$needle"; then
            echo "[e2e-ops] LCS registry lists ${needle} (attempt ${attempt})"
            return 0
        fi
        sleep 5
    done
    echo "[e2e-ops] ERROR: ${needle} not registered in LCS after restart (5m)"
    return 1
}

# LCS pod recreate + :8080 port-forward.
_restart_lightspeed_core() {
    echo "Restarting lightspeed-stack service..."

    timeout 20 oc delete pod lightspeed-stack-service -n "$NAMESPACE" --ignore-not-found=true --wait=true 2>/dev/null || {
        oc delete pod lightspeed-stack-service -n "$NAMESPACE" --ignore-not-found=true --force --grace-period=0 2>/dev/null || true
        sleep 2
    }

    LIGHTSPEED_STACK_IMAGE="${LIGHTSPEED_STACK_IMAGE:-quay.io/lightspeed-core/lightspeed-stack:dev-latest}"
    export LIGHTSPEED_STACK_IMAGE
    _ls_manifest="$MANIFEST_DIR/lightspeed-stack.yaml"
    sed "s|\${LIGHTSPEED_STACK_IMAGE}|${LIGHTSPEED_STACK_IMAGE}|g" "$_ls_manifest" |
        oc apply -n "$NAMESPACE" -f -

    local pod_ready=true
    if ! wait_for_pod "lightspeed-stack-service" 40; then
        pod_ready=false
        echo "⚠️  Pod not ready within 120s"
    fi

    oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n "$NAMESPACE" --overwrite

    if ! cmd_restart_port_forward; then
        echo "⚠️  Lightspeed port-forward failed"
        return 1
    fi
    cmd_restart_jwks_port_forward || echo "⚠️  Mock JWKS port-forward failed (RBAC tests may fail)"

    if ! _wait_for_vllm_model_in_lcs_registry; then
        return 1
    fi

    if [[ "$pod_ready" == "false" ]]; then
        echo "⚠️  Lightspeed restart completed but pod was slow to become ready"
        return 1
    fi
    echo "✓ Lightspeed restart complete"
    return 0
}

cmd_restart_lightspeed() {
    _restart_lightspeed_core
}

cmd_restart_port_forward() {
    local local_port="${LOCAL_PORT:-8080}"
    local remote_port="${REMOTE_PORT:-8080}"
    local max_attempts=6
    local pf_pid
    local pf_resource

    echo "Re-establishing port-forward on $local_port:$remote_port..."

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        kill_stale_lightspeed_forward "$local_port"
        # Let the kernel release LISTEN sockets after pkill (avoids immediate "address already in use")
        sleep 3

        # Service can lag endpoints after pod recreate; pod-direct forward is more reliable.
        if [[ $attempt -le 2 ]]; then
            pf_resource="svc/lightspeed-stack-service-svc"
        else
            pf_resource="pod/lightspeed-stack-service"
        fi
        echo "Port-forward attempt $attempt/$max_attempts -> $pf_resource"

        : > /tmp/port-forward.log
        # Redirect stdin from /dev/null so oc does not see a closed pipe when the parent is a short-lived subprocess.
        nohup oc port-forward "$pf_resource" "$local_port:$remote_port" -n "$NAMESPACE" \
            </dev/null >/tmp/port-forward.log 2>&1 &
        pf_pid=$!
        disown "$pf_pid" 2>/dev/null || true
        sleep 3

        # Bind error or API error: process exits quickly — surface /tmp/port-forward.log every time
        if ! kill -0 "$pf_pid" 2>/dev/null; then
            echo "Port-forward process exited immediately:"
            e2e_ops_emit_port_forward_immediate_failure_diag
            kill_stale_lightspeed_forward "$local_port"
            sleep 2
            continue
        fi
        sleep 6

        if verify_connectivity 15; then
            echo "$pf_pid" >"$E2E_LSC_PORT_FORWARD_PID_FILE"
            local readiness_code
            readiness_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$local_port/readiness" 2>/dev/null) || readiness_code="000"
            echo "[e2e-ops] LCS through port-forward: GET http://127.0.0.1:$local_port/readiness -> HTTP $readiness_code (expect 200 or 401)"
            echo "✓ Port-forward established (PID: $pf_pid, $pf_resource)"
            return 0
        fi

        if grep -q "address already in use" /tmp/port-forward.log 2>/dev/null; then
            echo "Bind error in port-forward log; clearing listeners and retrying..."
            kill_stale_lightspeed_forward "$local_port"
        fi
        if [[ $attempt -lt $max_attempts ]]; then
            echo "Attempt $attempt failed, retrying..."
            kill -9 "$pf_pid" 2>/dev/null || true
            sleep 2
        fi
    done

    echo "Failed to establish port-forward"
    e2e_ops_diagnose_forward_failure
    return 1
}

cmd_restart_jwks_port_forward() {
    local local_port="${LOCAL_JWKS_PORT:-8000}"
    local remote_port="${REMOTE_JWKS_PORT:-8000}"
    local max_attempts=4
    local pf_pid
    local jwks_pf_log="/tmp/port-forward-jwks.log"

    # Check if existing forward is still alive
    if [[ -f "$E2E_JWKS_PORT_FORWARD_PID_FILE" ]]; then
        local saved_pf
        read -r saved_pf <"$E2E_JWKS_PORT_FORWARD_PID_FILE" 2>/dev/null || true
        if [[ "$saved_pf" =~ ^[0-9]+$ ]] && kill -0 "$saved_pf" 2>/dev/null; then
            local http_code
            http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$local_port/tokens" 2>/dev/null) || http_code="000"
            if [[ "$http_code" != "000" ]]; then
                echo "✓ Mock JWKS port-forward already healthy (PID: $saved_pf)"
                return 0
            fi
        fi
    fi

    echo "Re-establishing mock-jwks port-forward on $local_port:$remote_port..."

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        kill_stale_jwks_forward "$local_port"
        sleep 2

        echo "JWKS port-forward attempt $attempt/$max_attempts"

        : >"$jwks_pf_log"
        nohup oc port-forward svc/mock-jwks "$local_port:$remote_port" -n "$NAMESPACE" \
            </dev/null >"$jwks_pf_log" 2>&1 &
        pf_pid=$!
        disown "$pf_pid" 2>/dev/null || true
        sleep 3

        if ! kill -0 "$pf_pid" 2>/dev/null; then
            echo "JWKS port-forward process exited immediately"
            continue
        fi

        local http_code
        http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$local_port/tokens" 2>/dev/null) || http_code="000"
        if [[ "$http_code" != "000" ]]; then
            echo "$pf_pid" >"$E2E_JWKS_PORT_FORWARD_PID_FILE"
            echo "✓ Mock JWKS port-forward established (PID: $pf_pid)"
            return 0
        fi

        if [[ $attempt -lt $max_attempts ]]; then
            echo "JWKS forward attempt $attempt failed, retrying..."
            kill -9 "$pf_pid" 2>/dev/null || true
            sleep 2
        fi
    done

    echo "Failed to establish mock-jwks port-forward on :$local_port"
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
    local configmap_key="${3:-lightspeed-stack.yaml}"

    echo "Updating ConfigMap $configmap_name from $source_file..."

    if [[ ! -f "$source_file" ]]; then
        echo "ERROR: source file does not exist: $source_file" >&2
        return 1
    fi

    # Use dry-run + apply to avoid the delete-then-create race.
    # If delete succeeds but create fails the ConfigMap is gone and every
    # subsequent attempt cascades into failure.
    if ! oc create configmap "$configmap_name" -n "$NAMESPACE" \
            --from-file="${configmap_key}=${source_file}" \
            --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f -; then
        echo "ERROR: oc apply for ConfigMap $configmap_name failed" >&2
        return 1
    fi

    echo "✓ ConfigMap $configmap_name updated successfully"
}

cmd_get_configmap_content() {
    local configmap_name="${1:?ConfigMap name required}"
    local configmap_key="${2:-lightspeed-stack.yaml}"
    oc get configmap "$configmap_name" -n "$NAMESPACE" \
        -o "go-template={{index .data \"$configmap_key\"}}"
}

cmd_dump_pod_logs() {
    e2e_ops_dump_pod_logs "${1:?pod name required}" "${2:-150}"
}

# Prove OGX can reach Solr in-cluster (same path as okp-solr.yaml probes).
# /solr and /solr/ are the Solr Admin UI; current OKP/Mimir images return HTTP 404 there.
cmd_check_okp_solr_from_llama() {
    local pod="lightspeed-stack-service"
    local ctr="lightspeed-stack-container"
    local url="http://okp-solr-service-svc:8080/solr/portal-rag/select?q=*:*&rows=0"

    echo "Checking OKP Solr from cluster at ${url} (pod=$pod)..."
    if oc exec -n "$NAMESPACE" "$pod" -c "$ctr" -- \
        curl -sf --max-time 10 -o /dev/null "$url" 2>/dev/null; then
        echo "✓ Pod can reach OKP Solr"
        return 0
    fi
    if oc exec -n "$NAMESPACE" "$pod" -c "$ctr" -- \
        python3 -c \
        "import urllib.request; urllib.request.urlopen('${url}', timeout=10).read()"; then
        echo "✓ Pod can reach OKP Solr"
        return 0
    fi
    echo "ERROR: Pod cannot reach OKP Solr at $url"
    return 1
}

cmd_deploy_okp_solr() {
    local pod_name="okp-solr-service"
    # First pull of the ~7GB OKP image is typically 10-15 min. 300 attempts × 3s = 900s.
    local wait_attempts=300
    local ready

    ready=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || echo "false")
    if [[ "$ready" == "true" ]]; then
        echo "✓ OKP Solr already ready — skipping deploy"
        return 0
    fi

    echo "Deploying OKP Solr service in namespace $NAMESPACE..."
    if oc get secret redhat-registry-pull-secret -n "$NAMESPACE" &>/dev/null; then
        echo "✓ redhat-registry-pull-secret exists"
    else
        echo "WARNING: redhat-registry-pull-secret NOT found — image pull will fail"
        oc get secrets -n "$NAMESPACE" --field-selector type=kubernetes.io/dockerconfigjson -o name 2>/dev/null || \
            echo "No dockerconfigjson secrets found"
    fi

    oc apply -n "$NAMESPACE" -f "$MANIFEST_DIR/okp-solr.yaml"
    echo "Waiting for OKP Solr to be ready (${wait_attempts} attempts, ~$((wait_attempts * 3))s for 7GB image pull)..."
    if ! wait_for_pod "$pod_name" "$wait_attempts"; then
        echo "=========================================="
        echo "OKP Solr not ready — diagnostics"
        echo "=========================================="
        oc get pod "$pod_name" -n "$NAMESPACE" -o wide || true
        oc get pod "$pod_name" -n "$NAMESPACE" \
            -o jsonpath='{.status.containerStatuses[*].state}' && echo "" || true
        oc get events -n "$NAMESPACE" --sort-by='.lastTimestamp' \
            --field-selector involvedObject.name="$pod_name" \
            --limit=30 2>/dev/null || echo "No events found for $pod_name"
        oc describe pod "$pod_name" -n "$NAMESPACE" || true
        if oc get secret redhat-registry-pull-secret -n "$NAMESPACE" &>/dev/null; then
            echo "redhat-registry-pull-secret: present"
        else
            echo "redhat-registry-pull-secret: NOT FOUND"
        fi
        echo "OKP Solr failed to become ready (7GB image — check node network to registry.redhat.io)"
        return 1
    fi
    echo "✓ OKP Solr service deployed and ready"

    # Log which image was actually pulled for debugging
    echo "=========================================="
    echo "OKP Solr image details"
    echo "=========================================="
    local image_spec image_id
    image_spec=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].image}' 2>/dev/null || echo "unknown")
    image_id=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.containerStatuses[0].imageID}' 2>/dev/null || echo "unknown")
    echo "Image in manifest: $image_spec"
    echo "Actual imageID pulled: $image_id"
    echo "=========================================="
}

cmd_delete_okp_solr() {
    echo "Deleting OKP Solr pod from namespace $NAMESPACE..."
    timeout 60 oc delete pod okp-solr-service -n "$NAMESPACE" --ignore-not-found=true --wait=true 2>/dev/null || {
        oc delete pod okp-solr-service -n "$NAMESPACE" --ignore-not-found=true --force --grace-period=0 2>/dev/null || true
        sleep 2
    }
    echo "✓ OKP Solr pod deleted"
}

cmd_disrupt_okp_solr() {
    local pod_name="okp-solr-service"

    local phase
    phase=$(oc get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")

    if [[ "$phase" == "Running" ]]; then
        oc delete pod "$pod_name" -n "$NAMESPACE" --wait=true
        sleep 2
        echo "OKP Solr connection disrupted successfully (pod deleted)"
        exit 0
    else
        echo "OKP Solr pod was not running (phase: $phase)"
        exit 2
    fi
}

cmd_restore_okp_solr() {
    echo "Restoring OKP Solr service in namespace $NAMESPACE..."
    oc apply -n "$NAMESPACE" -f "$MANIFEST_DIR/okp-solr.yaml"
    wait_for_pod "okp-solr-service" 60
    echo "✓ OKP Solr pod restored and ready"
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
    restart-jwks-port-forward)
        cmd_restart_jwks_port_forward
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
    dump-pod-logs)
        cmd_dump_pod_logs "$@"
        ;;
    check-okp-solr-from-llama)
        cmd_check_okp_solr_from_llama
        ;;
    deploy-okp-solr)
        cmd_deploy_okp_solr
        ;;
    delete-okp-solr)
        cmd_delete_okp_solr
        ;;
    disrupt-okp-solr)
        cmd_disrupt_okp_solr
        ;;
    restore-okp-solr)
        cmd_restore_okp_solr
        ;;
    *)
        echo "Usage: $0 <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  restart-lightspeed              - Restart lightspeed-stack pod and port-forward"
        echo "  restart-port-forward            - Re-establish port-forward for lightspeed"
        echo "  restart-jwks-port-forward         - Re-establish JWKS port-forward"
        echo "  wait-for-pod <name> [attempts]  - Wait for a pod to be ready"
        echo "  update-configmap <name> <file>  - Update ConfigMap from file"
        echo "  get-configmap-content <name>    - Get ConfigMap content (outputs to stdout)"
        echo "  dump-pod-logs <pod> [tail-lines]  - Print init + container logs"
        echo "  check-okp-solr-from-llama       - GET Solr from inside lightspeed-stack-service"
        echo "  deploy-okp-solr                 - Deploy OKP Solr (idempotent; @cfg_okp before_feature)"
        echo "  delete-okp-solr                 - Delete OKP Solr pod"
        echo "  disrupt-okp-solr                - Delete OKP Solr pod to disrupt connection"
        echo "  restore-okp-solr                - Restore OKP Solr pod"
        exit 1
        ;;
esac
