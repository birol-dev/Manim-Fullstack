"""Static analysis of Manim scripts: scene classes and their play/wait timeline."""

import ast
import hashlib
import re
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


# --- Run-time estimates -----------------------------------------------------------
# Manim's own defaults (manim/animation/*.py, v0.18-0.22). Anything not listed runs 1s.
_FIXED_RUN_TIMES = {"DrawBorderThenFill": 2.0, "SpiralIn": 2.0, "Circumscribe": 1.0}
# Write/Unwrite: ``run_time = 1 if len(family_members_with_points()) < 15 else 2``.
_LENGTH_BASED = {"Write", "Unwrite"}
# AddTextLetterByLetter: ``run_time = time_per_char * len(text)`` (time_per_char=0.1).
_PER_CHAR = {"AddTextLetterByLetter", "RemoveTextLetterByLetter"}
_GROUPS = {"AnimationGroup", "LaggedStart", "LaggedStartMap", "Succession"}
_TEXT_CLASSES = {"Text", "MarkupText", "Paragraph", "Tex", "MathTex", "SingleStringMathTex", "Title", "BulletedList"}
_TEX_COMMAND = re.compile(r"\\[a-zA-Z]+")


def _call_name(call: ast.Call) -> Optional[str]:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in {"manim", "mn", "m"}:
        return func.attr
    return None


def _root_call(expr: ast.AST) -> Optional[ast.Call]:
    """``Text("Hi").scale(2).to_edge(UP)`` -> the ``Text("Hi")`` call."""
    while isinstance(expr, ast.Call):
        if _call_name(expr) is not None:
            return expr
        func = expr.func
        if not isinstance(func, ast.Attribute):
            return None
        expr = func.value
    return None


def _glyph_count(expr: ast.AST, texts: dict) -> Optional[int]:
    """Approximate number of glyphs (submobjects with points) a text mobject has."""
    if isinstance(expr, ast.Name):
        return texts.get(expr.id)
    call = _root_call(expr)
    if call is None or _call_name(call) not in _TEXT_CLASSES:
        return None
    strings = [arg.value for arg in call.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
    if not strings:
        return None
    if _call_name(call) in {"Text", "MarkupText", "Paragraph"}:
        return sum(len("".join(part.split())) for part in strings)
    # LaTeX: each \command is roughly one glyph; braces and scripts markers draw nothing.
    total = 0
    for part in strings:
        commands = len(_TEX_COMMAND.findall(part))
        rest = re.sub(r"[{}^_&\s]", "", _TEX_COMMAND.sub("", part))
        total += commands + len(rest)
    return total


def _collect_texts(construct: ast.AST) -> dict:
    """``name = Text("...")`` assignments in construct(), mapped to their glyph counts."""
    texts = {}
    for node in ast.walk(construct):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            count = _glyph_count(node.value, texts)
            if count is not None:
                texts[node.targets[0].id] = count
    return texts


def _animation_seconds(expr: ast.AST, texts: dict) -> float:
    """Best static guess of one animation's run time, following Manim's defaults."""
    if not isinstance(expr, ast.Call):
        return 1.0  # mobject.animate..., variables holding animations
    explicit = _numeric_constant(_keyword(expr, "run_time"))
    if explicit is not None:
        return explicit
    name = _call_name(expr)
    if name is None:
        return 1.0  # x.animate.shift(...), helper calls
    if name in _LENGTH_BASED:
        count = _glyph_count(expr.args[0], texts) if expr.args else None
        return 2.0 if count is not None and count >= 15 else 1.0
    if name in _PER_CHAR:
        count = _glyph_count(expr.args[0], texts) if expr.args else None
        per_char = _numeric_constant(_keyword(expr, "time_per_char")) or 0.1
        return round(max(per_char * count, 1 / 15), 2) if count else 1.0
    if name in _GROUPS:
        children = [arg for arg in expr.args if not isinstance(arg, ast.Starred)]
        if not children:
            return 1.0
        durations = [_animation_seconds(child, texts) for child in children]
        if name == "Succession":
            return sum(durations)
        if name.startswith("Lagged"):
            lag = _numeric_constant(_keyword(expr, "lag_ratio"))
            lag = 0.05 if lag is None else lag
            return round(max(durations) * (1 + lag * (len(durations) - 1)), 2)
        return max(durations)
    return _FIXED_RUN_TIMES.get(name, 1.0)


def _animation_step(call: ast.Call, texts: Optional[dict] = None) -> Optional[dict]:
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
        else:
            # self.play() runs as long as its longest animation.
            animations = [arg for arg in call.args if not isinstance(arg, ast.Starred)]
            seconds = max((_animation_seconds(arg, texts or {}) for arg in animations), default=1.0)
            step["duration"] = float(seconds)
            step["estimated"] = True
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

_COMPOUND_BLOCKS = (ast.If, ast.Try, ast.With, ast.For, ast.While, ast.AsyncWith, ast.AsyncFor, ast.Match)
if hasattr(ast, "TryStar"):
    _COMPOUND_BLOCKS += (ast.TryStar,)


def _module_level_nodes(body):
    """Statements that run at module level: the body plus nested if/try/with/loop/match blocks."""
    for node in body:
        yield node
        if isinstance(node, _COMPOUND_BLOCKS):
            for field in ("body", "orelse", "finalbody"):
                yield from _module_level_nodes(getattr(node, field, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                yield from _module_level_nodes(handler.body)
            for case in getattr(node, "cases", []) or []:  # match / case
                yield from _module_level_nodes(case.body)


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


def _iteration_count(iterable: ast.AST) -> Optional[int]:
    """Items in ``range(3)``, ``[a, b]`` or ``"abc"``; None when unknown."""
    if isinstance(iterable, (ast.List, ast.Tuple, ast.Set)) and not any(isinstance(e, ast.Starred) for e in iterable.elts):
        return len(iterable.elts)
    if isinstance(iterable, ast.Constant) and isinstance(iterable.value, str):
        return len(iterable.value)
    if (
        isinstance(iterable, ast.Call)
        and isinstance(iterable.func, ast.Name)
        and iterable.func.id == "range"
        and not iterable.keywords
        and 1 <= len(iterable.args) <= 3
    ):
        values = [_numeric_constant(arg) for arg in iterable.args]
        if all(value is not None and float(value).is_integer() for value in values):
            try:
                return len(range(*(int(value) for value in values)))
            except ValueError:  # range() step of 0
                return None
    return None


def _loop_count(node: ast.AST) -> Optional[int]:
    """Iterations of ``for _ in range(3)`` or ``for x in [a, b]``; None when unknown."""
    if not isinstance(node, (ast.For, ast.AsyncFor)):
        return None  # while loops: unknown
    return _iteration_count(node.iter)


def _generator_count(generator: ast.comprehension) -> Optional[int]:
    """Iterations of one ``for ... in ...`` clause of a comprehension (unknown with ``if``)."""
    if generator.ifs:
        return None
    return _iteration_count(generator.iter)


_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


def _repeat_of(loops: tuple) -> Optional[int]:
    """Total runs of a call nested in *loops*: the product of the counts, None if any is unknown."""
    total = 1
    for _, _, count in loops:
        if count is None:
            return None
        total *= count
    return total


def _collect_steps(construct: ast.AST) -> List[dict]:
    """play/wait calls in source order, tagged with the loops that repeat them.

    Each looped step gets ``repeat`` (total runs: the product of the enclosing loop
    counts, so ``range(0)`` anywhere gives 0), ``loop_line`` (the outermost loop) and
    ``loops``: ``[[line, column, count], ...]`` from the outermost loop inward, so the
    UI can replay a loop body in execution order (a, b, a, b, ...).

    Limits: only literal ``range(...)`` and list/tuple/string literals give an iteration
    count. ``while`` loops, loops over variables and comprehension clauses with ``if``
    are marked as repeating an unknown number of times (``repeat: None``).
    Comprehensions (``[self.play(x) for x in (a, b)]``) count as loops.
    """
    texts = _collect_texts(construct)
    steps: List[dict] = []

    def visit(node: ast.AST, loops: tuple) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                # The loop header (iterable / condition) runs once; only the body repeats.
                header = child.iter if isinstance(child, (ast.For, ast.AsyncFor)) else child.test
                visit_expr(header, loops)
                inner = loops + ((child.lineno, child.col_offset, _loop_count(child)),)
                for stmt in child.body:
                    visit_stmt(stmt, inner)
                for stmt in child.orelse:
                    visit_stmt(stmt, loops)
                continue
            if isinstance(child, _COMPREHENSIONS):
                inner = loops
                for index, generator in enumerate(child.generators):
                    # The first iterable is evaluated once, outside the comprehension.
                    visit_expr(generator.iter, loops if index == 0 else inner)
                    inner = inner + ((child.lineno, child.col_offset + index, _generator_count(generator)),)
                    for condition in generator.ifs:
                        visit_expr(condition, inner)
                for part in ("key", "value") if isinstance(child, ast.DictComp) else ("elt",):
                    visit_expr(getattr(child, part), inner)
                continue
            if isinstance(child, ast.Call):
                step = _animation_step(child, texts)
                if step is not None:
                    if loops:
                        step["repeat"] = _repeat_of(loops)
                        step["loop_line"] = loops[0][0]
                        step["loops"] = tuple((line, col, count) for line, col, count in loops)
                    steps.append(step)
            visit(child, loops)

    def visit_stmt(stmt: ast.AST, loops: tuple) -> None:
        wrapper = ast.Module(body=[stmt], type_ignores=[])
        visit(wrapper, loops)

    def visit_expr(expr: ast.AST, loops: tuple) -> None:
        visit(ast.Expr(value=expr), loops)

    visit(construct, ())
    steps.sort(key=lambda step: step["line"])
    return steps


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
        steps = _collect_steps(construct)
        if steps:
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
    return {scene: [_step_dict(items) for items in steps] for scene, steps in anims}


def _step_dict(items) -> dict:
    """A cached (hashable) step as a plain dict; ``loops`` becomes a list of lists."""
    step = dict(items)
    if "loops" in step:
        step["loops"] = [list(loop) for loop in step["loops"]]
    return step


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
