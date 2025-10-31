#========================================
# 1. GLOBAL CONFIG
#========================================
NAMESPACE="e2e-rhoai-dsc"
MODEL_NAME="meta-llama/Llama-3.2-1B-Instruct"


#========================================
# 2. ENVIRONMENT SETUP
#========================================
echo "===== Setting up environment variables ====="
export HUGGING_FACE_HUB_TOKEN=$(cat /var/run/huggingface/hf-token-ces-lcore-test || true)
export VLLM_API_KEY=$(cat /var/run/vllm/vllm-api-key-lcore-test || true)
export ROBOT_USERNAME=$(cat /var/run/robot-username/robot-username-quay || true)
export ROBOT_PASSWORD=$(cat /var/run/robot-password/robot-password-quay || true)

[[ -n "$HUGGING_FACE_HUB_TOKEN" ]] && echo "✅ HUGGING_FACE_HUB_TOKEN is set" || { echo "❌ Missing HUGGING_FACE_HUB_TOKEN"; exit 1; }
[[ -n "$VLLM_API_KEY" ]] && echo "✅ VLLM_API_KEY is set" || { echo "❌ Missing VLLM_API_KEY"; exit 1; }
[[ -n "$ROBOT_USERNAME" ]] && echo "✅ ROBOT_USERNAME is set" || { echo "❌ Missing ROBOT_USERNAME"; exit 1; }
[[ -n "$ROBOT_PASSWORD" ]] && echo "✅ ROBOT_PASSWORD is set" || { echo "❌ Missing ROBOT_PASSWORD"; exit 1; }

# Mirror upstream VLLM official AWS image
echo "Logging in Quay.io"
echo $ROBOT_PASSWORD | podman login quay.io -u $ROBOT_USERNAME --password-stdin

echo "Mirroring vLLM..."
oc image mirror \
  public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:latest \
  quay.io/rh-ee-cpompeia/vllm-cpu:latest

# Basic info
ls -A || true
oc version
oc whoami

#========================================
# 3. CREATE NAMESPACE & SECRETS
#========================================
echo "===== Creating namespace & secrets ====="
oc get ns "$NAMESPACE" >/dev/null 2>&1 || oc create namespace "$NAMESPACE"

create_secret() {
    local name=$1; shift
    echo "Creating secret $name..."
    oc create secret generic "$name" "$@" -n "$NAMESPACE" 2>/dev/null || echo "Secret $name exists"
}

create_secret hf-token-secret --from-literal=token="$HUGGING_FACE_HUB_TOKEN"
create_secret vllm-api-key-secret --from-literal=key="$VLLM_API_KEY"


#========================================
# 4. CONFIGMAPS
#========================================
echo "===== Setting up configmaps ====="
curl -sL -o tool_chat_template_llama3.2_json.jinja \
    https://raw.githubusercontent.com/vllm-project/vllm/main/examples/tool_chat_template_llama3.2_json.jinja

oc create configmap vllm-chat-template -n "$NAMESPACE" \
    --from-file=tool_chat_template_llama3.2_json.jinja --dry-run=client -o yaml | oc apply -f -


#========================================
# 5. DEPLOY vLLM
#========================================
echo "===== Deploying vLLM ====="
./pipeline-vllm.sh
oc get pods -n "$NAMESPACE"


#========================================
# 6. WAIT FOR POD & TEST API
#========================================
source pod.env
oc wait --for=condition=Ready pod/$POD_NAME -n $NAMESPACE --timeout=300s

echo "===== Testing vLLM endpoint ====="
start_time=$(date +%s)
timeout=200

while true; do
  response=$(curl -sk -w "%{http_code}" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $VLLM_API_KEY" \
      -d "{
          \"model\": \"$MODEL_NAME\",
          \"prompt\": \"Who won the world series in 2020?\",
          \"max_new_tokens\": 100
          }" \
      "$KSVC_URL/v1/completions")

  if [[ ${#response} -ge 3 ]]; then
    http_code="${response: -3}"
    body="${response:0:${#response}-3}"
  else
    http_code="000"
    body="$response"
  fi

  if [[ "$http_code" == "200" && "$body" == *'"object":"text_completion"'* ]]; then
    echo "✅ API test passed."
    break
  else
    echo "❌ API test failed (HTTP $http_code)"
    echo "$body" | jq . 2>/dev/null || echo "$body"
  fi

  current_time=$(date +%s)
  elapsed=$((current_time - start_time))

  if (( elapsed >= timeout )); then
      echo "⏰ Timeout reached ($timeout seconds). Stopping test."
      exit 1
  fi

  sleep 20
done


#========================================
# 7. DEPLOY LIGHTSPEED STACK AND LLAMA STACK
#========================================
echo "===== Deploying Services ====="

create_secret api-url-secret --from-literal=key="$KSVC_URL"
oc create configmap llama-stack-config -n "$NAMESPACE" --from-file=configs/run.yaml
oc create configmap lightspeed-stack-config -n "$NAMESPACE" --from-file=configs/lightspeed-stack.yaml
oc create configmap test-script-cm -n "$NAMESPACE" --from-file=run-tests.sh

./pipeline-services.sh

oc wait pod/lightspeed-stack-service pod/llama-stack-service \
    -n "$NAMESPACE" --for=condition=Ready --timeout=300s
sleep 30

oc get pods -n "$NAMESPACE"

echo "logs lightspeed"
oc logs lightspeed-stack-service -n "$NAMESPACE" || true
echo "logs llama"
oc logs llama-stack-service -n "$NAMESPACE" || true

oc describe pod lightspeed-stack-service -n "$NAMESPACE" || true
oc describe pod llama-stack-service -n "$NAMESPACE" || true


#========================================
# 8. EXTRACT LCS IP & STORE
#========================================
oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n $NAMESPACE

oc expose pod lightspeed-stack-service \
  --name=lightspeed-stack-service-svc \
  --port=8080 \
  --type=ClusterIP \
  -n $NAMESPACE

LCS_IP="lightspeed-stack-service-svc.$NAMESPACE.svc.cluster.local"
echo "LCS IP: $LCS_IP"

create_secret lcs-ip-secret --from-literal=key="$LCS_IP"


#========================================
# 9. LOGGING & TEST EXECUTION
#========================================
echo "===== Running test pod ====="
./pipeline-test-pod.sh 

sleep 20
oc get pods -n "$NAMESPACE"

# Wait until tests are complete
oc wait --for=condition=Ready=True pod/test-pod -n $NAMESPACE --timeout=900s

start_time=$(date +%s)
timeout=2400
while true; do
  sleep 120
  
  PHASE=$(oc get pod test-pod -n $NAMESPACE -o jsonpath='{.status.phase}')
  echo "Current phase test-pod: $PHASE"
  if [[ "$PHASE" == "Succeeded" || "$PHASE" == "Failed" ]]; then
      break
  fi

  current_time=$(date +%s)
  elapsed=$((current_time - start_time))

  if (( elapsed >= timeout )); then
      echo "⏰ Timeout reached ($timeout seconds). Stopping test."
      exit 1
  fi

  oc get pods -n "$NAMESPACE"
done
oc logs test-pod -n $NAMESPACE || oc describe pod test-pod -n $NAMESPACE || true


TEST_EXIT_CODE=$(oc get pod test-pod -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}')

echo "===== E2E COMPLETE ====="

if [ "${TEST_EXIT_CODE:-2}" -ne 0 ]; then
    echo "❌ E2E tests failed with exit code $TEST_EXIT_CODE (pod/test-pod failed)"
else
    echo "✅ E2E tests succeeded"
fi

exit $TEST_EXIT_CODE