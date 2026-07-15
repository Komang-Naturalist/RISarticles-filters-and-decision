"""Thin, testable adapters for scholarly workflow integrations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:  # Adapters are optional until the connector is configured.
    httpx = None  # type: ignore[assignment]


class ZoteroClient:
    def __init__(self, library_id: str | None = None, api_key: str | None = None):
        self.library_id = library_id or os.environ["ZOTERO_LIBRARY_ID"]
        self.headers = {"Zotero-API-Key": api_key or os.environ["ZOTERO_API_KEY"], "Zotero-API-Version": "3"}

    async def sync_items(self, items: list[dict[str, Any]], decision: str) -> dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for Zotero sync; install requirements.txt")
        payload = [{**item, "tags": [*item.get("tags", []), {"tag": f"lattice:{decision}"}]} for item in items]
        async with httpx.AsyncClient() as client:
            response = await client.post(f"https://api.zotero.org/users/{self.library_id}/items", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()


def write_vosviewer_gml(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], output: Path) -> None:
    lines = ["graph [", "  directed 0"]
    for index, node in enumerate(nodes):
        lines += ["  node [", f"    id {index}", f'    label "{str(node.get("label", index)).replace(chr(34), chr(39))}"', "  ]"]
    for edge in edges:
        lines += ["  edge [", f"    source {edge['source']}", f"    target {edge['target']}", f"    weight {edge.get('weight', 1)}", "  ]"]
    lines.append("]")
    output.write_text("\n".join(lines), encoding="utf-8")


class GoogleDriveExporter:
    """Uploads prepared artifacts with a short-lived OAuth bearer token."""

    async def upload(self, path: Path, folder_id: str, access_token: str) -> dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for Google Drive upload; install requirements.txt")
        metadata = {"name": path.name, "parents": [folder_id]}
        async with httpx.AsyncClient() as client:
            response = await client.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                                         headers={"Authorization": f"Bearer {access_token}"},
                                         files={"metadata": (None, __import__("json").dumps(metadata), "application/json"), "file": (path.name, path.read_bytes())})
            response.raise_for_status()
            return response.json()
