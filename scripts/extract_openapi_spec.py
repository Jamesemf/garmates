"""Fetch Garmin's Personal API OpenAPI spec.

Garmin doesn't publish the spec as a file: the Swagger docs page embeds it as a JSON string
inside its JavaScript bundle. This script finds that bundle and writes the spec out, so
parsers can be checked against the current field list when Garmin updates the API.

Usage:  python scripts/extract_openapi_spec.py [output.json]
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = "https://developer.garmin.com"
PAGE = f"{BASE}/gc-developer-program/personal/swagger-docs/"
MARKER = "JSON.parse('{\"openapi\""


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "garmates spec fetcher"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def js_string_literal(source: str, start: int) -> str:
    """Return the decoded single-quoted JS string literal beginning at ``start``."""
    out = []
    i = start
    while source[i] != "'":
        if source[i] == "\\":
            out.append(source[i : i + 2])
            i += 2
        else:
            out.append(source[i])
            i += 1
    raw = "".join(out)
    return raw.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/garmin-personal-api.openapi.json")
    html = fetch(PAGE)
    bundles = re.findall(
        r'src="(/component---src-pages-gc-developer-program-personal-swagger-docs-js-[^"]+\.js)"',
        html,
    )
    if not bundles:
        sys.exit("Couldn't find the Swagger docs bundle - Garmin may have changed the page.")
    source = fetch(BASE + bundles[0])
    index = source.find(MARKER)
    if index < 0:
        sys.exit("The bundle no longer embeds the spec in the expected form.")
    spec = json.loads(js_string_literal(source, index + len("JSON.parse('")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    info = spec["info"]
    print(f"Wrote {output} - {info['title']} {info['version']}, {len(spec['paths'])} paths")


if __name__ == "__main__":
    main()
