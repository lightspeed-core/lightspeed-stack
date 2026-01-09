# Development Tools

This directory contains utilities and tools for local development and testing of Lightspeed Core Stack.

## Available Tools

### MCP Mock Server

A lightweight mock Model Context Protocol (MCP) server for testing MCP integrations and authorization headers locally.

**Location:** `dev-tools/mcp-mock-server/`

**Use Cases:**
- Test MCP server authentication headers without real MCP infrastructure
- Debug authorization header configuration
- Local development of MCP-related features
- Validate MCP server connectivity

See [`mcp-mock-server/README.md`](mcp-mock-server/README.md) for usage instructions.

## Testing MCP Integration with Lightspeed Core

For comprehensive step-by-step instructions on manually testing MCP authorization, see [`MANUAL_TESTING.md`](MANUAL_TESTING.md).

## Adding New Tools

When adding new development tools to this directory:
1. Create a subdirectory for the tool
2. Include a README.md explaining what it does and how to use it
3. Update this file to list the new tool
4. Keep tools self-contained with their own dependencies (if any)

