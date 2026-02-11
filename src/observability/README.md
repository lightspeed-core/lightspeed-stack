# Observability Module

This module provides telemetry capabilities for sending inference events to external systems like Splunk HEC.

## Architecture

```
observability/
├── __init__.py          # Public API exports
├── splunk.py            # Async Splunk HEC client
└── formats/
    ├── __init__.py      # Format exports
    └── rlsapi.py        # rlsapi v1 event format
```

## Usage

### Sending Events to Splunk

```python
from fastapi import BackgroundTasks
from observability import send_splunk_event, build_inference_event, InferenceEventData

# Build the event payload
event_data = InferenceEventData(
    question="How do I configure SSH?",
    response="To configure SSH...",
    inference_time=2.34,
    model="granite-3-8b-instruct",
    org_id="12345678",
    system_id="abc-def-123",
    request_id="req_xyz789",
    cla_version="CLA/0.4.1",
    system_os="RHEL",
    system_version="9.3",
    system_arch="x86_64",
)

event = build_inference_event(event_data)

# Queue for async sending via BackgroundTasks
background_tasks.add_task(send_splunk_event, event, "infer_with_llm")
```

### Source Types

| Source Type | Description |
|-------------|-------------|
| `infer_with_llm` | Successful inference requests |
| `infer_error` | Failed inference requests |

## Creating Custom Event Formats

To add a new event format for a different endpoint:

1. Create a new module in `observability/formats/`:

```python
# observability/formats/my_endpoint.py
from dataclasses import dataclass
from typing import Any

@dataclass
class MyEventData:
    field1: str
    field2: int

def build_my_event(data: MyEventData) -> dict[str, Any]:
    return {
        "field1": data.field1,
        "field2": data.field2,
    }
```

2. Export from `observability/formats/__init__.py`

3. Use with `send_splunk_event()`:

```python
from observability import send_splunk_event
from observability.formats.my_endpoint import build_my_event, MyEventData

event = build_my_event(MyEventData(field1="value", field2=42))
background_tasks.add_task(send_splunk_event, event, "my_sourcetype")
```

## Graceful Degradation

The Splunk client is designed to never block or fail the main request:

- Skips sending when Splunk is disabled or not configured
- Logs warnings on HTTP errors (does not raise exceptions)
- Token is read from file on each request (supports rotation without restart)

## Configuration

See [docs/splunk.md](../../docs/splunk.md) for configuration options.
