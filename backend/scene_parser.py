"""Static analysis of Manim scripts: scene classes and their play/wait timeline."""

import ast
import hashlib
import threading
from collections import OrderedDict
from typing import List, Optional

# Results keyed by a digest of the source, so the cache never holds the code itself
# (the editor re-parses a slightly different copy of a file after every pause).
_CACHE_SIZE = 64
_cache: "OrderedDict[str, tuple]" = OrderedDict()
_cache_lock = threading.Lock()


def _identifier_looks_like_scene(name: str) -> bool:
    """True if *name* is exactly Scene or ends with Scene (not a mid-string substring)."""
    return name == "Scene" or name.endswith("Scene")


def _base_name(base: ast.AST) -> Optional[str]:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _class_looks_like_scene(node: ast.ClassDef) -> bool:
    """Detect Manim Scene subclasses without treating every subclassed helper as a scene.

    Scene-like bases (Scene, ThreeDScene, MovingCameraScene, manim.Scene, ...) win.
    If the class declares bases and none look Scene-like, it is rejected even when
    its own name ends with ``Scene`` (e.g. ``NotAScene(dict)``). Only base-less
    classes fall back to their own name.
    """
    base_names = [_base_name(base) for base in node.bases]
    if any(name and _identifier_looks_like_scene(name) for name in base_names):
        return True
    if node.bases:
        return False
    return _identifier_looks_like_scene(node.name)


def _numeric_constant(expr: Optional[ast.AST]) -> Optional[float]:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool):
        return float(expr.value)
    return None


def _keyword(call: ast.Call, *names: str) -> Optional[ast.AST]:
    return next((kw.value for kw in call.keywords if kw.arg in names), None)


def _safe_unparse(expr: ast.AST, fallback: str) -> str:
    try:
        return ast.unparse(expr)
    except Exception:
        return fallback


def _animation_step(call: ast.Call) -> Optional[dict]:
    """Describe a ``self.play(...)`` or ``self.wait(...)`` call for the timeline."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self"):
        return None

    if func.attr == "play":
        labels = [_safe_unparse(arg, "") for arg in call.args]
        label = ", ".join(part for part in labels if part) or "animation"
        step = {"type": "play", "label": label, "line": call.lineno}
        run_time = _numeric_constant(_keyword(call, "run_time"))
        if run_time is not None:
            step["duration"] = run_time
        return step

    if func.attr == "wait":
        expr = call.args[0] if call.args else _keyword(call, "duration", "run_time")
        if expr is None:
            duration = 1.0
        else:
            numeric = _numeric_constant(expr)
            duration = numeric if numeric is not None else _safe_unparse(expr, "?")
        label = f"Wait {duration:g}s" if isinstance(duration, float) else f"Wait {duration}"
        return {"type": "wait", "label": label, "duration": duration, "line": call.lineno}

    return None


def _parse_code_ast(code_content: str) -> tuple:
    """Find scene classes and their play/wait timeline in one AST pass (cached).

    The third item is a syntax error dict (``message``, ``line``, ``column``) or None.
    """
    key = hashlib.sha1(code_content.encode("utf-8", "surrogatepass")).hexdigest()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
    result = _analyze(code_content)
    with _cache_lock:
        _cache[key] = result
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return result


def _syntax_error_info(exc: SyntaxError) -> dict:
    return {
        "message": (exc.msg or "Invalid syntax").strip(),
        "line": exc.lineno or 1,
        "column": exc.offset or 1,
    }


def _analyze(code_content: str) -> tuple:
    try:
        tree = ast.parse(code_content)
    except SyntaxError as exc:
        return ((), (), _syntax_error_info(exc))
    except (ValueError, RecursionError, MemoryError):
        # RecursionError/MemoryError: pathologically nested code.
        return ((), (), {"message": "Could not parse this file.", "line": 1, "column": 1})

    # Manim only renders module-level classes.
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    scene_names = {node.name for node in classes if _class_looks_like_scene(node)}
    # Subclasses of scenes defined in the same file (class Intro(BaseScene)) are scenes too.
    changed = True
    while changed:
        changed = False
        for node in classes:
            if node.name not in scene_names and any(_base_name(b) in scene_names for b in node.bases):
                scene_names.add(node.name)
                changed = True

    ordered_scenes: List[str] = []
    scene_anims = {}
    for node in classes:
        if node.name not in scene_names or node.name in ordered_scenes:
            continue
        ordered_scenes.append(node.name)

        construct = next(
            (
                sub
                for sub in node.body
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == "construct"
            ),
            None,
        )
        if construct is None:
            continue
        steps = [
            step
            for sub in ast.walk(construct)
            if isinstance(sub, ast.Call)
            for step in [_animation_step(sub)]
            if step is not None
        ]
        if steps:
            steps.sort(key=lambda step: step["line"])
            scene_anims[node.name] = tuple(tuple(step.items()) for step in steps)

    return (tuple(ordered_scenes), tuple(scene_anims.items()), None)


def get_scenes_from_code(code_content: str) -> List[str]:
    """Return renderable Scene class names in source order."""
    scenes, _, _ = _parse_code_ast(code_content)
    return list(scenes)


def get_scene_animations(code_content: str) -> dict:
    """Return ``{scene: [step, ...]}`` for the play/wait calls in each construct()."""
    _, anims, _ = _parse_code_ast(code_content)
    return {scene: [dict(items) for items in steps] for scene, steps in anims}


def get_syntax_error(code_content: str) -> Optional[dict]:
    """Return ``{message, line, column}`` when *code_content* is not valid Python."""
    _, _, error = _parse_code_ast(code_content)
    return error
