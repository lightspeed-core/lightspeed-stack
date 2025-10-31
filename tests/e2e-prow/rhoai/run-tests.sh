git clone https://github.com/lightspeed-core/lightspeed-stack.git
cd lightspeed-stack

echo "pod started"
echo $LCS_IP

curl -f http://$LCS_IP:8080/v1/models || {
    echo "❌ Basic connectivity failed - showing logs before running full tests"
    exit 1
}

echo "Installing test dependencies..."
pip install uv
uv sync

export E2E_LSC_HOSTNAME=$LCS_IP
export E2E_LLAMA_HOSTNAME=$LLAMA_IP

echo "Running comprehensive e2e test suite..."
make test-e2e