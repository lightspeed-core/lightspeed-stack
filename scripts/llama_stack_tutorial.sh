#!/bin/bash

# Llama Stack Tutorial - Interactive Guide 
# This tutorial demonstrates key features of the Llama Stack server

LLAMA_STACK_URL="http://localhost:8321"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Interactive mode (default: true, set to false with --no-wait flag)
INTERACTIVE=true

print_section() {
    echo ""
    echo "================================================================================"
    echo "  $1"
    echo "================================================================================"
    echo ""
}

print_header() {
    echo ""
    echo "🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀"
    echo " WELCOME TO THE QUICK LLAMA STACK TUTORIAL "
    echo "🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀"
    echo ""
}

wait_for_user() {
    if [ "$INTERACTIVE" = true ]; then
        echo ""
        echo -e "${CYAN}${BOLD}Press Enter to continue...${NC}"
        read -r
    fi
}

run_command() {
    local cmd="$1"
    echo ""
    echo -e "${YELLOW}${BOLD}▶ Running:${NC} ${GREEN}${cmd}${NC}"
    echo ""
    eval "$cmd"
}

# Parse command line arguments
for arg in "$@"; do
    case $arg in
        --no-wait)
            INTERACTIVE=false
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-wait    Run through all sections without pausing"
            echo "  --help, -h   Show this help message"
            exit 0
            ;;
    esac
done

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "⚠️  Warning: 'jq' is not installed. Output will be less formatted."
    echo "   Install with: apt-get install jq (Ubuntu/Debian), yum install jq (RHEL/CentOS), brew install jq (macOS). "
    JQ_CMD="cat"
else
    JQ_CMD="jq ."
fi

print_header

if [ "$INTERACTIVE" = true ]; then
    echo "This tutorial will guide you through the Llama Stack API step by step."
    echo "You'll explore models, tools, shields, and see example API calls."
    wait_for_user
fi

# Section 0: What is Llama Stack?
print_section "What is Llama Stack?"
cat << 'EOF'
Llama Stack serves as the AI INTEGRATION LAYER - it's the middleware that abstracts
away the complexity of working with different LLM providers and provides a unified
API for AI operations.

KEY FEATURES:

🤖 LLM Inference
   • Generates AI responses (streaming and non-streaming)
   • Handles complex streaming with tool calls and content interleaving

🛡️  Safety & Content Filtering
   • Retrieves input/output shields for content filtering
   • Provides safety mechanisms for AI responses

🔧 Tools & Agents
   • Manages agent sessions (create, retrieve, delete)
   • Supports tool-augmented AI interactions
   • Enables agents to call external tools/functions

📚 RAG Support
   • Integration with vector databases
   • Enables Retrieval-Augmented Generation for better context

🎯 Model & Provider Management
   • Lists available models and providers
   • Allows runtime switching between different LLM providers (OpenAI, Azure, etc.)

DEPLOYMENT MODES:
   1. Service Mode: Llama Stack runs as a separate service
   2. Library Mode: Llama Stack embedded directly in the app

BOTTOM LINE:
Think of Llama Stack as a UNIVERSAL ADAPTER for AI operations. Instead of coding
directly against OpenAI's API, Azure's API, etc., Lightspeed Stack uses Llama
Stack's unified interface. This makes it easy to switch providers, add new
capabilities (like agents or RAG), and maintain consistent behavior across
different LLM backends.

EOF
wait_for_user

# Section 1: Health Check
print_section "1. Health Check"
echo "Let's verify the Llama Stack server is running..."
run_command "curl -s ${LLAMA_STACK_URL}/v1/health | ${JQ_CMD}"
wait_for_user

# Section 2: Version
print_section "2. Server Version"
echo "Checking Llama Stack version..."
run_command "curl -s ${LLAMA_STACK_URL}/v1/version | ${JQ_CMD}"
wait_for_user

# Section 3: Models
print_section "3. Available Models"
echo "Llama Stack supports multiple models from different providers."
echo "Let's see what models are available..."

run_command "curl -s ${LLAMA_STACK_URL}/v1/models | ${JQ_CMD}"

echo ""
echo "Let me analyze the models for you..."
MODELS_JSON=$(curl -s ${LLAMA_STACK_URL}/v1/models)

if command -v jq &> /dev/null; then

    LLM_COUNT=$(echo "${MODELS_JSON}" | jq '[.data[] | select(.model_type == "llm")] | length')
    EMBED_COUNT=$(echo "${MODELS_JSON}" | jq '[.data[] | select(.model_type == "embedding")] | length')
    TOTAL_COUNT=$(echo "${MODELS_JSON}" | jq '.data | length')

    echo ""
    echo -e "${BOLD}📊 Summary:${NC}"
    echo "   Total Models: ${TOTAL_COUNT}"
    echo "   - LLM Models: ${LLM_COUNT}"
    echo "   - Embedding Models: ${EMBED_COUNT}"
    echo ""

    echo -e "${BOLD}Top LLM Models:${NC}"
    echo "${MODELS_JSON}" | jq -r '.data[] | select(.model_type == "llm") | "  • \(.identifier) (provider: \(.provider_id))"' | head -5

    echo ""
    echo -e "${BOLD}Embedding Models:${NC}"
    echo "${MODELS_JSON}" | jq -r '.data[] | select(.model_type == "embedding") | "  • \(.identifier) (dimension: \(.metadata.embedding_dimension // "unknown"))"'
fi
wait_for_user

# Section 4: Shields
print_section "4. Safety Shields"
echo "Shields provide content filtering and safety mechanisms."
echo "Let's see what shields are configured..."
run_command "curl -s ${LLAMA_STACK_URL}/v1/shields | ${JQ_CMD}"
wait_for_user

# Section 5: Tool Groups
print_section "5. Tool Groups"
echo "Llama Stack supports tool groups that organize related tools."
echo "Let's explore available tool groups..."
run_command "curl -s ${LLAMA_STACK_URL}/v1/toolgroups | ${JQ_CMD}"
wait_for_user

# Section 6: Tools
print_section "6. Available Tools"
echo "Tools allow agents to perform specific actions."
echo "Let's see what tools are available..."
run_command "curl -s ${LLAMA_STACK_URL}/v1/tools | ${JQ_CMD}"

echo ""
echo "Let me show you the tool details..."
TOOLS_JSON=$(curl -s ${LLAMA_STACK_URL}/v1/tools)

if command -v jq &> /dev/null; then
    echo ""
    echo -e "${BOLD}Tool Details:${NC}"
    echo "${TOOLS_JSON}" | jq -r '.data[] | "\n  🔧 \(.identifier)\n     Description: \(.description)\n     Tool Group: \(.toolgroup_id)"'
fi
wait_for_user

# Section 7: Inference Examples
print_section "7. Example API Calls"
echo "Here are some example API calls you can try on your own..."
echo -e "${YELLOW}(Note: These require API keys to be configured)${NC}"
echo ""

echo -e "${BLUE}${BOLD}Example 1: Chat Completion${NC}"
echo "Copy and paste this command to try it:"
echo "----------------------------------------"
cat << 'EOF'
curl -X POST http://localhost:8321/v1/inference/chat-completion \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "openai/gpt-4o-mini",
    "messages": [
      {
        "role": "user",
        "content": "Explain Llama Stack in one sentence."
      }
    ],
    "stream": false
  }' | jq .
EOF

echo ""
echo -e "${BLUE}${BOLD}Example 2: Generate Embeddings${NC}"
echo "Copy and paste this command to try it:"
echo "----------------------------------------"
cat << 'EOF'
curl -X POST http://localhost:8321/v1/inference/embeddings \
  -H 'Content-Type: application/json' \
  -d '{
    "model_id": "openai/text-embedding-3-small",
    "contents": ["Llama Stack is awesome!"]
  }' | jq .
EOF

echo ""
echo -e "${BLUE}${BOLD}Example 3: List All Routes${NC}"
echo "Copy and paste this command to try it:"
echo "----------------------------------------"
echo "curl http://localhost:8321/v1/inspect/routes | jq ."
wait_for_user

# Section 8: API Reference
print_section "8. Quick API Reference"
echo "Here are the key endpoints available:"
echo ""

cat << 'EOF'
  GET    /v1/version                         - Get server version
  GET    /v1/health                          - Health check
  GET    /v1/models                          - List all models
  GET    /v1/shields                         - List safety shields
  GET    /v1/tools                           - List available tools
  GET    /v1/toolgroups                      - List tool groups
  POST   /v1/inference/chat-completion       - Chat completion (LLM)
  POST   /v1/inference/completion            - Text completion
  POST   /v1/inference/embeddings            - Generate embeddings
  GET    /v1/inspect/routes                  - List all available routes

  OpenAPI Documentation: http://localhost:8321/docs
EOF
wait_for_user

# Section 9: Integration
print_section "9. How Lightspeed Stack Uses Llama Stack"
cat << 'EOF'
Lightspeed Stack integrates with Llama Stack to provide:

1. 🤖 Multi-Provider LLM Support
   - Llama Stack abstracts different providers (OpenAI, Azure, etc.)
   - Lightspeed Stack uses this to support multiple models seamlessly

2. 🛡️  Safety & Content Filtering
   - Shields provide input/output content filtering
   - Ensures safe AI responses for production use

3. 🔧 Tool-Augmented AI
   - Agents can use tools (like RAG search)
   - Enables more capable AI assistants

4. 📊 Unified API
   - Single interface for chat, embeddings, and more
   - Simplifies AI integration in the Lightspeed Stack codebase

Key Integration Points in Lightspeed Stack:
- src/client.py: Llama Stack client wrapper
- src/app/endpoints/: API endpoints using Llama Stack
- src/configuration.py: Configuration for Llama Stack connection
EOF
wait_for_user

# Section 10: Try It Now
print_section "10. Try It Yourself!"
echo "Let's make a real API call to see all available routes!"
run_command "curl -s ${LLAMA_STACK_URL}/v1/inspect/routes | ${JQ_CMD}"
wait_for_user

# Conclusion
print_section "🎉 Tutorial Complete!"
cat << 'EOF'
You've learned about:
✅ Llama Stack server capabilities
✅ Available models (LLMs and embeddings)
✅ Safety shields for content filtering
✅ Tools and tool groups
✅ How to make API calls
✅ How Lightspeed Stack integrates with Llama Stack

Next Steps:
1. Explore the OpenAPI docs: http://localhost:8321/docs
2. Try the example commands above
3. Look at how Lightspeed Stack uses Llama Stack in src/client.py
4. Experiment with different models and tools

Resources:
- This tutorial script: ./llama_stack_tutorial.sh
- Run without pauses: ./llama_stack_tutorial.sh --no-wait
- Python version: ./llama_stack_tutorial.py (requires: uv run python3)
- Interactive docs: http://localhost:8321/docs

Happy exploring! 🚀
EOF

echo ""
