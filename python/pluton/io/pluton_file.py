"""Zip container + manifest version gate for the native .pluton format (M6a).

The only part of pluton.io that touches the filesystem. A .pluton file is a zip
holding manifest.json (the version gate) + document.json (the codec payload).
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from pluton._core import version as _core_version
from pluton.io.document_codec import (
    LoadedDocument,
    document_from_dict,
    document_to_dict,
)
from pluton.io.errors import PlutonFormatError, PlutonVersionError

SCHEMA_VERSION = 1
_MANIFEST = "manifest.json"
_DOCUMENT = "document.json"


def save_document(path, model, camera, doc) -> None:
    """Write the document to `path` atomically (temp file + os.replace)."""
    path = Path(path)
    data = document_to_dict(model, camera, doc)
    manifest = {"format": "pluton", "schema_version": SCHEMA_VERSION,
                "app_version": _core_version()}
    tmp = path.with_name(path.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_MANIFEST, json.dumps(manifest, separators=(",", ":")))
            zf.writestr(_DOCUMENT, json.dumps(data, separators=(",", ":")))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def load_document(path) -> LoadedDocument:
    """Read a .pluton file. Raises PlutonFormatError / PlutonVersionError / OSError."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path, "r") as zf:
            manifest = json.loads(zf.read(_MANIFEST))
            if manifest.get("format") != "pluton":
                raise PlutonFormatError("not a Pluton file (bad 'format' in manifest)")
            ver = manifest.get("schema_version")
            # Equal-or-older than SCHEMA_VERSION is intentionally the accept path (no
            # migration branch needed until a v2 format lands); only newer is rejected.
            if not isinstance(ver, int) or ver > SCHEMA_VERSION:
                raise PlutonVersionError(
                    f"file schema_version {ver} is newer than supported ({SCHEMA_VERSION})")
            data = json.loads(zf.read(_DOCUMENT))
    except zipfile.BadZipFile as e:
        raise PlutonFormatError("not a valid .pluton file (not a zip archive)") from e
    except KeyError as e:
        raise PlutonFormatError(f"missing entry in .pluton archive: {e}") from e
    except json.JSONDecodeError as e:
        raise PlutonFormatError(f"corrupt JSON in .pluton archive: {e}") from e
    return document_from_dict(data)
