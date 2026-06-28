# Lightspeed Core Stack



---

# 📋 Schemas for error responses models



## AbstractErrorResponse


Base class for error responses.

Attributes:
    status_code: HTTP status code for the error response.
    detail: The detail model containing error summary and cause.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## BadRequestResponse


400 Bad Request. Invalid resource identifier.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## ConflictResponse


409 Conflict - Resource already exists.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## DetailModel


Nested detail model for error responses.


| Field | Type | Description |
|-------|------|-------------|
| response | string | Short summary of the error |
| cause | string | Detailed explanation of what caused the error |


## FileTooLargeResponse


413 Content Too Large - File upload exceeds size limit.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## ForbiddenResponse


403 Forbidden. Access denied.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## InternalServerErrorResponse


500 Internal Server Error.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## NotFoundResponse


404 Not Found - Resource does not exist.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## PromptTooLongResponse


413 Payload Too Large - Prompt is too long.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## QuotaExceededResponse


429 Too Many Requests - Quota limit exceeded.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## ServiceUnavailableResponse


503 Backend Unavailable.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## UnauthorizedResponse


401 Unauthorized - Missing or invalid credentials.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |


## UnprocessableEntityResponse


422 Unprocessable Entity - Request validation failed.


| Field | Type | Description |
|-------|------|-------------|
| status_code | integer | HTTP status code for the errors response |
| detail |  | The detail model containing error summary and cause |
