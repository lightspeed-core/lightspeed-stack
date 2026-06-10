"""
DataUtils MCP Server — data, math, statistics, unit conversion,
text analysis, and datetime utilities.
"""

import json
import math
import statistics
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "DataUtils",
    instructions="Data, math, statistics, conversion, and text analysis tools.",
    host="0.0.0.0",
    port=3000,
)


@mcp.tool()
def descriptive_stats(numbers: list[float]) -> str:
    """
    Compute descriptive statistics for a list of numbers.

    Returns mean, median, mode, standard deviation, variance, min, max, sum, and count.

    Args:
        numbers: A list of numeric values (at least 1 element).
    """
    if not numbers:
        return "Error: list must contain at least one number."
    result = {
        "count": len(numbers),
        "sum": sum(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "mean": statistics.mean(numbers),
        "median": statistics.median(numbers),
    }
    try:
        result["mode"] = statistics.mode(numbers)
    except statistics.StatisticsError:
        result["mode"] = None
    if len(numbers) >= 2:
        result["stdev"] = statistics.stdev(numbers)
        result["variance"] = statistics.variance(numbers)
    return json.dumps(result, indent=2)


@mcp.tool()
def percentile(numbers: list[float], p: float) -> str:
    """
    Compute the p-th percentile of a list of numbers.

    Args:
        numbers: A list of numeric values.
        p: Percentile to compute (0-100).
    """
    if not numbers:
        return "Error: list must contain at least one number."
    if not 0 <= p <= 100:
        return "Error: p must be between 0 and 100."
    sorted_nums = sorted(numbers)
    k = (p / 100) * (len(sorted_nums) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return json.dumps({"percentile": p, "value": sorted_nums[f]})
    val = sorted_nums[f] * (c - k) + sorted_nums[c] * (k - f)
    return json.dumps({"percentile": p, "value": round(val, 6)})


@mcp.tool()
def linear_regression(x_values: list[float], y_values: list[float]) -> str:
    """
    Perform simple linear regression (y = mx + b) on paired data.

    Args:
        x_values: Independent variable values.
        y_values: Dependent variable values (same length as x_values).
    """
    if len(x_values) != len(y_values):
        return "Error: x_values and y_values must have the same length."
    n = len(x_values)
    if n < 2:
        return "Error: need at least 2 data points."
    x_mean = statistics.mean(x_values)
    y_mean = statistics.mean(y_values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return "Error: x_values have zero variance."
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    y_pred = [slope * x + intercept for x in x_values]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(y_values, y_pred))
    ss_tot = sum((y - y_mean) ** 2 for y in y_values)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 1.0
    return json.dumps({
        "slope": round(slope, 6),
        "intercept": round(intercept, 6),
        "r_squared": round(r_squared, 6),
        "equation": f"y = {round(slope, 4)}x + {round(intercept, 4)}",
    }, indent=2)


@mcp.tool()
def unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert a value between common units.

    Supported categories:
      - Length: m, km, mi, ft, in, cm, mm, yd
      - Weight: kg, g, lb, oz
      - Temperature: C, F, K

    Args:
        value: The numeric value to convert.
        from_unit: Source unit abbreviation.
        to_unit: Target unit abbreviation.
    """
    length_to_m = {
        "m": 1, "km": 1000, "mi": 1609.344, "ft": 0.3048,
        "in": 0.0254, "cm": 0.01, "mm": 0.001, "yd": 0.9144,
    }
    weight_to_kg = {"kg": 1, "g": 0.001, "lb": 0.453592, "oz": 0.0283495}
    temp_units = {"c", "f", "k"}

    fu, tu = from_unit.lower(), to_unit.lower()

    if fu in length_to_m and tu in length_to_m:
        result = value * length_to_m[fu] / length_to_m[tu]
        return json.dumps({"value": round(result, 6), "from": from_unit, "to": to_unit})

    if fu in weight_to_kg and tu in weight_to_kg:
        result = value * weight_to_kg[fu] / weight_to_kg[tu]
        return json.dumps({"value": round(result, 6), "from": from_unit, "to": to_unit})

    if fu in temp_units and tu in temp_units:
        celsius = value
        if fu == "f":
            celsius = (value - 32) * 5 / 9
        elif fu == "k":
            celsius = value - 273.15
        if tu == "c":
            result = celsius
        elif tu == "f":
            result = celsius * 9 / 5 + 32
        else:
            result = celsius + 273.15
        return json.dumps({"value": round(result, 4), "from": from_unit, "to": to_unit})

    return f"Cannot convert between '{from_unit}' and '{to_unit}'. Units must be in the same category."


@mcp.tool()
def number_base_convert(value: str, from_base: int, to_base: int) -> str:
    """
    Convert a number string between bases (2-36).

    Args:
        value: The number as a string in the source base.
        from_base: Source base (2-36).
        to_base: Target base (2-36).
    """
    if not (2 <= from_base <= 36 and 2 <= to_base <= 36):
        return "Error: bases must be between 2 and 36."
    try:
        decimal_val = int(value, from_base)
    except ValueError:
        return f"Error: '{value}' is not a valid base-{from_base} number."

    if to_base == 10:
        result = str(decimal_val)
    elif to_base == 16:
        result = hex(decimal_val)[2:]
    elif to_base == 8:
        result = oct(decimal_val)[2:]
    elif to_base == 2:
        result = bin(decimal_val)[2:]
    else:
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        if decimal_val == 0:
            result = "0"
        else:
            negative = decimal_val < 0
            decimal_val = abs(decimal_val)
            chars = []
            while decimal_val:
                chars.append(digits[decimal_val % to_base])
                decimal_val //= to_base
            result = ("-" if negative else "") + "".join(reversed(chars))

    return json.dumps({"decimal": int(value, from_base), "result": result, "from_base": from_base, "to_base": to_base})


@mcp.tool()
def date_difference(date1: str, date2: str) -> str:
    """
    Calculate the difference between two ISO-8601 dates.

    Args:
        date1: First date (ISO-8601, e.g. 2024-01-15 or 2024-01-15T10:30:00).
        date2: Second date (ISO-8601).
    """
    try:
        d1 = datetime.fromisoformat(date1.replace("Z", "+00:00"))
        d2 = datetime.fromisoformat(date2.replace("Z", "+00:00"))
    except ValueError as e:
        return f"Error parsing dates: {e}"
    diff = d2 - d1
    total_seconds = int(diff.total_seconds())
    abs_seconds = abs(total_seconds)
    days, remainder = divmod(abs_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    return json.dumps({
        "total_days": diff.days,
        "total_seconds": total_seconds,
        "breakdown": f"{days}d {hours}h {minutes}m {secs}s",
        "is_future": total_seconds > 0,
    }, indent=2)


@mcp.tool()
def date_add(date: str, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> str:
    """
    Add (or subtract with negative values) a duration to a date.

    Args:
        date: Starting date (ISO-8601).
        days: Days to add.
        hours: Hours to add.
        minutes: Minutes to add.
        seconds: Seconds to add.
    """
    try:
        dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
    except ValueError as e:
        return f"Error parsing date: {e}"
    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    result = dt + delta
    return json.dumps({
        "original": dt.isoformat(),
        "result": result.isoformat(),
        "delta": str(delta),
    }, indent=2)


@mcp.tool()
def word_frequency(text: str, top_n: int = 10) -> str:
    """
    Analyze word frequency in a body of text.

    Args:
        text: The text to analyze.
        top_n: Number of top words to return. Defaults to 10.
    """
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return "No words found in text."
    freq = Counter(words)
    top = freq.most_common(top_n)
    return json.dumps({
        "total_words": len(words),
        "unique_words": len(freq),
        "top_words": [{"word": w, "count": c, "pct": round(c / len(words) * 100, 2)} for w, c in top],
    }, indent=2)


@mcp.tool()
def text_statistics(text: str) -> str:
    """
    Compute readability and structural statistics for a text.

    Returns character count, word count, sentence count, paragraph count,
    average word length, and average sentence length.

    Args:
        text: The text to analyze.
    """
    chars = len(text)
    chars_no_spaces = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
    words = re.findall(r"\S+", text)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    avg_word_len = round(sum(len(w) for w in words) / len(words), 2) if words else 0
    avg_sentence_len = round(len(words) / len(sentences), 2) if sentences else 0
    return json.dumps({
        "characters": chars,
        "characters_no_spaces": chars_no_spaces,
        "words": len(words),
        "sentences": len(sentences),
        "paragraphs": len(paragraphs),
        "avg_word_length": avg_word_len,
        "avg_sentence_length": avg_sentence_len,
    }, indent=2)


@mcp.tool()
def evaluate_expression(expression: str) -> str:
    """
    Safely evaluate a mathematical expression.

    Supports: +, -, *, /, **, %, parentheses, and math functions
    (sqrt, sin, cos, tan, log, log10, exp, abs, ceil, floor, pi, e).

    Args:
        expression: A mathematical expression string.
    """
    allowed_names = {
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
        "tan": math.tan, "log": math.log, "log10": math.log10,
        "exp": math.exp, "abs": abs, "ceil": math.ceil,
        "floor": math.floor, "pi": math.pi, "e": math.e,
        "pow": pow, "round": round,
    }
    sanitized = expression.replace("^", "**")
    if re.search(r"[a-zA-Z_]\w*", sanitized):
        for name in re.findall(r"[a-zA-Z_]\w*", sanitized):
            if name not in allowed_names:
                return f"Error: '{name}' is not allowed. Permitted names: {', '.join(sorted(allowed_names))}."
    try:
        result = eval(sanitized, {"__builtins__": {}}, allowed_names)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except Exception as e:
        return f"Error evaluating expression: {e}"


@mcp.tool()
def matrix_multiply(matrix_a: list[list[float]], matrix_b: list[list[float]]) -> str:
    """
    Multiply two matrices (2D arrays).

    Args:
        matrix_a: First matrix as a list of rows.
        matrix_b: Second matrix as a list of rows.
    """
    if not matrix_a or not matrix_b:
        return "Error: matrices must not be empty."
    cols_a = len(matrix_a[0])
    rows_b = len(matrix_b)
    if cols_a != rows_b:
        return f"Error: incompatible dimensions — A has {cols_a} columns but B has {rows_b} rows."
    rows_a = len(matrix_a)
    cols_b = len(matrix_b[0])
    result = [[0.0] * cols_b for _ in range(rows_a)]
    for i in range(rows_a):
        for j in range(cols_b):
            for k in range(cols_a):
                result[i][j] += matrix_a[i][k] * matrix_b[k][j]
    result = [[round(v, 6) for v in row] for row in result]
    return json.dumps({"rows": rows_a, "cols": cols_b, "result": result}, indent=2)


@mcp.tool()
def correlation(x_values: list[float], y_values: list[float]) -> str:
    """
    Compute the Pearson correlation coefficient between two lists of numbers.

    Args:
        x_values: First list of numeric values.
        y_values: Second list of numeric values (same length as x_values).
    """
    if len(x_values) != len(y_values):
        return "Error: lists must have the same length."
    n = len(x_values)
    if n < 2:
        return "Error: need at least 2 data points."
    x_mean = statistics.mean(x_values)
    y_mean = statistics.mean(y_values)
    cov = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / (n - 1)
    sx = statistics.stdev(x_values)
    sy = statistics.stdev(y_values)
    if sx == 0 or sy == 0:
        return "Error: one of the variables has zero variance."
    r = cov / (sx * sy)
    strength = "strong" if abs(r) >= 0.7 else "moderate" if abs(r) >= 0.4 else "weak"
    direction = "positive" if r > 0 else "negative" if r < 0 else "none"
    return json.dumps({
        "pearson_r": round(r, 6),
        "r_squared": round(r ** 2, 6),
        "interpretation": f"{strength} {direction} correlation",
    }, indent=2)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
