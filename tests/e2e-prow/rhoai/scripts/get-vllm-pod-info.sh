#!/bin/bash
set -e

NAMESPACE="e2e-rhoai-dsc"
ISVC_NAME="${1:-vllm-model}"
ENV_FILE="${ENV_FILE:-pod.env}"

KSVC_NAME="${ISVC_NAME}-predictor"

echo "--> Finding the pod for InferenceService '$ISVC_NAME'..."

# Find the running pod for the InferenceService
POD_NAME=""
TIMEOUT=240  # seconds
INTERVAL=5   # check interval
ELAPSED=0

until [ -n "$POD_NAME" ] || [ $ELAPSED -ge $TIMEOUT ]; do
  POD_NAME=$(oc get pods -n "$NAMESPACE" \
    -l "serving.kserve.io/inferenceservice=$ISVC_NAME" \
    -o jsonpath="{.items[?(@.status.phase=='Running')].metadata.name}" 2>/dev/null)
  echo "Waiting for pod $POD_NAME in namespace $NAMESPACE"

  if [ -z "$POD_NAME" ]; then
    echo "  -> Pod not running yet, waiting $INTERVAL seconds..."
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
  fi
done

oc describe pod $POD_NAME -n $NAMESPACE || true
oc logs $POD_NAME -n $NAMESPACE || true

POD_NAME=$(oc get pods -n $NAMESPACE -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
  echo "  -> Timeout reached after $TIMEOUT seconds. Pod is not running."
else
  echo "  -> Pod is running: $POD_NAME"
fi

# Get the 'app' label for Service selector
APP_LABEL=$(oc get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.metadata.labels.app}')
if [ -z "$APP_LABEL" ]; then
  echo "Error: Could not find 'app' label on pod $POD_NAME"
  exit 1
fi
echo "  -> Found 'app' label: $APP_LABEL"

# Get the Knative Service URL
KSVC_URL=$(oc get ksvc "$KSVC_NAME" -n "$NAMESPACE" -o jsonpath='{.status.url}')
if [ -z "$KSVC_URL" ]; then
  echo "Error: Could not retrieve Knative URL for $KSVC_NAME"
  exit 1
fi
echo "  -> Found Knative URL: $KSVC_URL"

# Save all info to pod.env
cat <<EOF > "$ENV_FILE"
# Environment variables for the vLLM service
POD_NAME=$POD_NAME
APP_LABEL=$APP_LABEL
NAMESPACE=$NAMESPACE
ISVC_NAME=$ISVC_NAME
KSVC_NAME=$KSVC_NAME
KSVC_URL=$KSVC_URL
EOF

echo "✅ Success! Details saved in $ENV_FILE."
