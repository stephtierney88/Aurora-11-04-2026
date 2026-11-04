"""Publish complete screenshots under immutable, collision-resistant identities."""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path


def save_capture(image, directory):
    """Save once, then atomically publish without replacing an existing image."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    capture_id = f"{time.time_ns()}-{uuid.uuid4().hex}"
    temporary = root / f".{capture_id}.tmp"
    owns_temporary = False
    try:
        with temporary.open("xb") as output:
            owns_temporary = True
            image.save(output, format="PNG")
            output.flush()
        for _ in range(5):
            target = root / f"{capture_id}.png"
            try:
                # link() publishes the fully written file and never overwrites.
                os.link(temporary, target)
                return str(target)
            except FileExistsError:
                capture_id = f"{time.time_ns()}-{uuid.uuid4().hex}"
        raise FileExistsError("Could not allocate a unique capture identity.")
    finally:
        if owns_temporary:
            temporary.unlink(missing_ok=True)
