from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import bpy


INVENTORY_MARKER = "AURORA_BLENDER_INVENTORY_JSON="


def _tool_arguments() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _vector(value: Any, size: int = 3) -> list[float]:
    try:
        return [round(float(value[index]), 6) for index in range(size)]
    except (IndexError, TypeError, ValueError):
        return []


def _name(value: Any) -> str:
    return str(getattr(value, "name", "") or "")


def _decoded_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="replace")
    return str(value or "")


def _object_row(obj: Any) -> dict[str, Any]:
    data = getattr(obj, "data", None)
    materials = []
    for slot in list(getattr(obj, "material_slots", ()) or ())[:16]:
        material = getattr(slot, "material", None)
        if material is not None:
            materials.append(_name(material))
    collections = sorted(_name(row) for row in getattr(obj, "users_collection", ()) or ())
    return {
        "name": _name(obj),
        "type": str(getattr(obj, "type", "") or ""),
        "data_name": _name(data),
        "parent": _name(getattr(obj, "parent", None)),
        "collections": collections[:32],
        "collections_truncated": len(collections) > 32,
        "location": _vector(getattr(obj, "location", ())),
        "rotation_euler": _vector(getattr(obj, "rotation_euler", ())),
        "scale": _vector(getattr(obj, "scale", ())),
        "dimensions": _vector(getattr(obj, "dimensions", ())),
        "hide_render": bool(getattr(obj, "hide_render", False)),
        "hide_viewport": bool(getattr(obj, "hide_viewport", False)),
        "modifier_types": [
            str(getattr(row, "type", "") or "")
            for row in list(getattr(obj, "modifiers", ()) or ())[:32]
        ],
        "materials": materials,
        "animation_data": getattr(obj, "animation_data", None) is not None,
    }


def _scene_row(scene: Any) -> dict[str, Any]:
    scene_objects = list(getattr(scene, "objects", ()) or ())
    object_types = Counter(str(getattr(obj, "type", "") or "UNKNOWN") for obj in scene_objects)
    render = getattr(scene, "render", None)
    collection = getattr(scene, "collection", None)
    child_collections = getattr(collection, "children_recursive", ()) if collection else ()
    return {
        "name": _name(scene),
        "object_count": len(scene_objects),
        "object_types": dict(sorted(object_types.items())),
        "collection_count": 1 + len(list(child_collections or ())),
        "camera": _name(getattr(scene, "camera", None)),
        "world": _name(getattr(scene, "world", None)),
        "frame": {
            "current": int(getattr(scene, "frame_current", 0) or 0),
            "start": int(getattr(scene, "frame_start", 0) or 0),
            "end": int(getattr(scene, "frame_end", 0) or 0),
            "step": int(getattr(scene, "frame_step", 1) or 1),
        },
        "render": {
            "engine": str(getattr(render, "engine", "") or ""),
            "resolution_x": int(getattr(render, "resolution_x", 0) or 0),
            "resolution_y": int(getattr(render, "resolution_y", 0) or 0),
            "resolution_percentage": int(
                getattr(render, "resolution_percentage", 0) or 0
            ),
            "fps": float(getattr(render, "fps", 0) or 0),
        },
        "timeline_marker_count": len(list(getattr(scene, "timeline_markers", ()) or ())),
        "animation_data": getattr(scene, "animation_data", None) is not None,
    }


def _external_asset_summary() -> dict[str, Any]:
    image_counts = Counter()
    for image in bpy.data.images:
        source = str(getattr(image, "source", "") or "UNKNOWN")
        if getattr(image, "packed_file", None) is not None:
            image_counts["packed"] += 1
        elif source in {"GENERATED", "VIEWER"}:
            image_counts["generated_or_viewer"] += 1
        elif str(getattr(image, "filepath", "") or ""):
            image_counts["external"] += 1
    libraries = sorted(
        Path(str(getattr(row, "filepath", "") or "")).name
        for row in bpy.data.libraries
        if str(getattr(row, "filepath", "") or "")
    )
    return {
        "image_counts": dict(sorted(image_counts.items())),
        "external_existence_checked": False,
        "linked_library_count": len(bpy.data.libraries),
        "linked_library_names": libraries[:100],
        "linked_library_names_truncated": len(libraries) > 100,
    }


def build_scene_inventory(object_limit: int = 100) -> dict[str, Any]:
    limit = max(0, min(500, int(object_limit)))
    objects = sorted(bpy.data.objects, key=lambda row: _name(row).casefold())
    scenes = sorted(bpy.data.scenes, key=lambda row: _name(row).casefold())
    scene_limit = 100
    type_counts = Counter(str(getattr(obj, "type", "") or "UNKNOWN") for obj in objects)
    active_scene = getattr(bpy.context, "scene", None)
    build_hash = getattr(bpy.app, "build_hash", b"")
    if isinstance(build_hash, bytes):
        build_hash = build_hash.decode("ascii", errors="replace")
    counts = {
        "scenes": len(bpy.data.scenes),
        "objects": len(objects),
        "collections": len(bpy.data.collections),
        "meshes": len(bpy.data.meshes),
        "curves": len(bpy.data.curves),
        "materials": len(bpy.data.materials),
        "images": len(bpy.data.images),
        "actions": len(bpy.data.actions),
        "cameras": len(bpy.data.cameras),
        "lights": len(bpy.data.lights),
        "armatures": len(bpy.data.armatures),
        "node_groups": len(bpy.data.node_groups),
        "libraries": len(bpy.data.libraries),
    }
    return {
        "schema_version": "blender_readonly_scene_inventory_v1",
        "read_only": True,
        "authority": {
            "save": False,
            "render": False,
            "import": False,
            "export": False,
            "operators": False,
            "arbitrary_python": False,
            "gui_control": False,
        },
        "blender": {
            "version": str(bpy.app.version_string),
            "version_tuple": list(bpy.app.version),
            "build_hash": str(build_hash),
            "build_platform": _decoded_text(getattr(bpy.app, "build_platform", b"")),
            "background": bool(bpy.app.background),
        },
        "file": {
            "path": str(bpy.data.filepath or ""),
            "saved": bool(getattr(bpy.data, "is_saved", bool(bpy.data.filepath))),
            "blend_version": list(getattr(bpy.data, "version", ()) or ()),
        },
        "active_scene": _name(active_scene),
        "counts": counts,
        "object_types": dict(sorted(type_counts.items())),
        "scenes": [_scene_row(scene) for scene in scenes[:scene_limit]],
        "scenes_returned": min(scene_limit, len(scenes)),
        "scenes_truncated": len(scenes) > scene_limit,
        "objects": [_object_row(obj) for obj in objects[:limit]],
        "objects_returned": min(limit, len(objects)),
        "objects_truncated": len(objects) > limit,
        "external_assets": _external_asset_summary(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Blender scene inventory helper.")
    parser.add_argument("--object-limit", type=int, default=100)
    return parser


def main() -> int:
    args = build_parser().parse_args(_tool_arguments())
    payload = build_scene_inventory(args.object_limit)
    print(INVENTORY_MARKER + json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
