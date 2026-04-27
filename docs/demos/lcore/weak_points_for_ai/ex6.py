# magic constants are in fact described in comments
# if it can be commented, why not use named constants?
# (LLMs are bad handling pure numbers)
if len(value) > 16:
    raise ValueError(f"attributes can have at most 16 pairs, got {len(value)}")

for key, val in value.items():
    if len(key) > 64:
        raise ValueError(f"attribute key '{key}' exceeds 64 characters")

    if isinstance(val, str) and len(val) > 512:
        raise ValueError(f"attribute value for '{key}' exceeds 512 characters")
