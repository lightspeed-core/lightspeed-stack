#!/usr/bin/env python3

"""Script to retrieve latest tag defined on GitHub."""

import os
import subprocess
from typing import Optional


def version_split(value: str) -> tuple[int, ...]:
    """Parse dot-separated integers, returning ``(-1,)`` if any part is invalid."""
    try:
        return tuple(int(n) for n in value.split("."))
    except ValueError:
        return (-1,)


def is_prerelease(tag: str) -> bool:
    """Return whether a tag contains ``rc``, ``alpha``, ``beta``, or ``dev``.

    Matching is case-sensitive and does not otherwise validate the version.
    """
    omit = {"rc", "alpha", "beta", "dev"}

    return any(n in tag for n in omit)


def get_latest_stable() -> Optional[str]:
    """Return the highest local Git tag by dot-separated integer ordering.

    Excludes tags matched by ``is_prerelease``. Nonnumeric tags sort as
    ``(-1,)``; returns None when no tags remain. Does not fetch remote tags.

    Raises:
        subprocess.CalledProcessError: If ``git tag`` fails.
        OSError: If Git cannot be started.
    """
    stdout = subprocess.check_output(["git", "tag"], text=True)
    tags = [tag for tag in stdout.splitlines() if not is_prerelease(tag)]
    tags.sort(key=version_split)

    return tags[-1] if tags else None


def main() -> None:
    """Entry point to this script, retrieves latest tag defined on GitHub.

    Append ``apply_latest=true`` or ``apply_latest=false`` when GITHUB_OUTPUT
    is set. An unset or prerelease GIT_TAG produces false without querying Git.
    Git command and output-file errors propagate to the caller.
    """
    if not (current_tag := os.environ.get("GIT_TAG")):
        reason = "GIT_TAG environment variable not set, skipping latest tag"
        apply_latest = "false"
    elif is_prerelease(current_tag):
        reason = f"{current_tag} is a pre-release"
        apply_latest = "false"
    else:
        latest_stable = get_latest_stable()
        if current_tag == latest_stable:
            reason = f"{current_tag} is the latest stable"
            apply_latest = "true"
        else:
            reason = f"{current_tag} is not the latest stable ({latest_stable} is)"
            apply_latest = "false"

    print(reason)

    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"apply_latest={apply_latest}\n")


if __name__ == "__main__":
    main()
