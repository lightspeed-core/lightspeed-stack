# OpenAPI tags and Spectral

## Global tag list (`_OPENAPI_TAGS`)

In `src/app/endpoints/`, route tags come from **`APIRouter(tags=[...])`**, which FastAPI uses when it builds the OpenAPI description for each operation.

The OpenAPI document must list those tags at the top level for tools like [Spectral](https://stoplight.io/open-api/) rule **`operation-tag-defined`** to pass, so we keep **`_OPENAPI_TAGS`** in **`src/app/main.py`** and pass it into the **`FastAPI`** app as **`openapi_tags`**.

**When you add a new router or change `tags=[...]` to use a new tag name**, add a matching entry to **`_OPENAPI_TAGS`** (same `name` string, plus a short `description` for the docs).

The schema generator **`scripts/generate_openapi_schema.py`** passes **`tags=app.openapi_tags`** into **`get_openapi()`** so **`docs/openapi.json`** includes the top-level `tags` array. Regenerate after tag changes:

```bash
uv run scripts/generate_openapi_schema.py docs/openapi.json
```
