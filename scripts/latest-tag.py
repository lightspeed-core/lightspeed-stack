#!/usr/bin/env python3

import os
import subprocess


def version_split(value: str) -> tuple[int, ...]:
    """Split string into a tuple of ints."""
    try:
        return tuple(int(n) for n in value.split("."))
    except ValueError:
        return (-1,)


def is_prerelease(tag: str) -> bool:
    """Determine if a tag is a pre-release version."""
    omit = {"rc", "alpha", "beta", "dev"}

    return any(n in tag for n in omit)


def get_latest_stable() -> str | None:
    """Return the latest stable tag."""
    stdout = subprocess.check_output(["git", "tag"], text=True)
    tags = [tag for tag in stdout.splitlines() if not is_prerelease(tag)]
    tags.sort(key=version_split)

    return tags[-1] if tags else None


def main() -> None:
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
        with open(github_output, "a") as f:
            f.write(f"apply_latest={apply_latest}\n")


if __name__ == "__main__":
    main()
