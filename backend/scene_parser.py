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
    """True for Scene and *Scene bases (ThreeDScene, MovingCameraScene, ...) and
    manim-slides' Slide / ThreeDSlide, which subclass Scene."""
    return name.endswith("Scene") or name.endswith("Slide")


# Modules whose star import cannot bring in user scene classes.
_LIBRARY_MODULE_PREFIXES = ("manim", "manim_slides", "manimlib", "numpy", "math", "random")


def _base_name(base: ast.AST) -> Optional[str]:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _class_looks_like_scene(node: ast.ClassDef, scene_aliases: frozenset = frozenset()) -> bool:
    """Detect Manim Scene subclasses without treating every subclassed helper as a scene.

    Scene-like bases (Scene, ThreeDScene, MovingCameraScene, manim.Scene, ...) win.
    If the class declares bases and none look Scene-like, it is rejected even when
    its own name ends with ``Scene`` (e.g. ``NotAScene(dict)``). Only base-less
    classes fall back to their own name.
    """
    base_names = [_base_name(base) for base in node.bases]
    if any(name and (_identifier_looks_like_scene(name) or name in scene_aliases) for name in base_names):
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


_EMPTY_NAMES = (("has_class", False), ("names", frozenset()), ("open_namespace", False))

_COMPOUND_BLOCKS = (ast.If, ast.Try, ast.With, ast.For, ast.While, ast.AsyncWith, ast.AsyncFor)
if hasattr(ast, "TryStar"):
    _COMPOUND_BLOCKS += (ast.TryStar,)


def _module_level_nodes(body):
    """Statements that run at module level: the body plus nested if/try/with/loop blocks."""
    for node in body:
        yield node
        if isinstance(node, _COMPOUND_BLOCKS):
            for field in ("body", "orelse", "finalbody"):
                yield from _module_level_nodes(getattr(node, field, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                yield from _module_level_nodes(handler.body)


def _scene_aliases(nodes) -> set:
    """Local names bound to Scene-like classes by imports: ``from manim import Scene as S``."""
    aliases = set()
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname and _identifier_looks_like_scene(alias.name):
                    aliases.add(alias.asname)
    return aliases


def _assigned_names(target) -> set:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_assigned_names(item) for item in target.elts)) if target.elts else set()
    if isinstance(target, ast.Starred):
        return _assigned_names(target.value)
    return set()


def _module_bound_names(nodes) -> set:
    """Every name a module-level statement binds (classes, imports, assignments)."""
    names = set()
    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= _assigned_names(target)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names |= _assigned_names(node.target)
    return names


def _has_foreign_star_import(nodes) -> bool:
    """``from mystuff import *`` can bind names the AST can't see."""
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            module = (node.module or "").split(".")[0]
            if node.level or module not in _LIBRARY_MODULE_PREFIXES:
                return True
    return False


def _parse_code_ast(code_content: str) -> tuple:
    """Find scene classes and their play/wait timeline in one AST pass (cached).

    The third item is a syntax error dict (``message``, ``line``, ``column``) or None.
    The fourth is the :func:`get_render_names` summary.
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
        return ((), (), _syntax_error_info(exc), _EMPTY_NAMES)
    except (ValueError, RecursionError, MemoryError):
        # RecursionError/MemoryError: pathologically nested code.
        return ((), (), {"message": "Could not parse this file.", "line": 1, "column": 1}, _EMPTY_NAMES)

    # Manim renders classes bound at module level, including ones defined under
    # `if` / `try` / `with` blocks. Function and class bodies are skipped.
    module_nodes = list(_module_level_nodes(tree.body))
    classes = [node for node in module_nodes if isinstance(node, ast.ClassDef)]
    scene_aliases = frozenset(_scene_aliases(module_nodes))
    scene_names = {node.name for node in classes if _class_looks_like_scene(node, scene_aliases)}
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

    names = {
        "has_class": any(isinstance(node, ast.ClassDef) for node in ast.walk(tree)),
        "names": frozenset(_module_bound_names(module_nodes)),
        "open_namespace": _has_foreign_star_import(module_nodes),
    }
    return (tuple(ordered_scenes), tuple(scene_anims.items()), None, tuple(sorted(names.items())))


def get_scenes_from_code(code_content: str) -> List[str]:
    """Return renderable Scene class names in source order."""
    scenes, _, _, _ = _parse_code_ast(code_content)
    return list(scenes)


def get_scene_animations(code_content: str) -> dict:
    """Return ``{scene: [step, ...]}`` for the play/wait calls in each construct()."""
    _, anims, _, _ = _parse_code_ast(code_content)
    return {scene: [dict(items) for items in steps] for scene, steps in anims}


def get_syntax_error(code_content: str) -> Optional[dict]:
    """Return ``{message, line, column}`` when *code_content* is not valid Python."""
    _, _, error, _ = _parse_code_ast(code_content)
    return error


def get_render_names(code_content: str) -> dict:
    """What the AST can prove about renderable names.

    ``has_class``: the file defines at least one class anywhere.
    ``names``: names bound at module level (classes, imports, assignments).
    ``open_namespace``: a star import from a non-library module may bind more.
    """
    _, _, _, summary = _parse_code_ast(code_content)
    info = dict(summary)
    return {"has_class": info["has_class"], "names": set(info["names"]), "open_namespace": info["open_namespace"]}
