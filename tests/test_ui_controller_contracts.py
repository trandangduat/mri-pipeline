from __future__ import annotations

import ast
from pathlib import Path


UI_PATHS = [path for path in Path("ui").rglob("*.py") if path.name != "__init__.py"]


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(class_node: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in class_node.body if isinstance(node, ast.FunctionDef)}


def _self_call_nodes(class_node: ast.ClassDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(class_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ]


def test_ui_controllers_do_not_call_missing_private_self_methods() -> None:
    missing: list[str] = []
    for path in UI_PATHS:
        for node in _module_tree(path).body:
            if not isinstance(node, ast.ClassDef):
                continue
            methods = _class_methods(node)
            for call in _self_call_nodes(node):
                assert isinstance(call.func, ast.Attribute)
                name = call.func.attr
                if name.startswith("_") and name not in methods:
                    missing.append(f"{path}:{call.lineno}: {node.name}.self.{name}()")

    assert missing == []


def test_ui_controllers_self_calls_match_method_positional_arity() -> None:
    mismatches: list[str] = []
    for path in UI_PATHS:
        for node in _module_tree(path).body:
            if not isinstance(node, ast.ClassDef):
                continue
            methods = _class_methods(node)
            for call in _self_call_nodes(node):
                assert isinstance(call.func, ast.Attribute)
                target = methods.get(call.func.attr)
                if target is None or call.keywords or any(isinstance(arg, ast.Starred) for arg in call.args):
                    continue
                args = target.args.args[1:]
                required = len(args) - len(target.args.defaults)
                has_vararg = target.args.vararg is not None
                provided = len(call.args)
                if provided < required or (provided > len(args) and not has_vararg):
                    mismatches.append(
                        f"{path}:{call.lineno}: {node.name}.self.{call.func.attr}() "
                        f"expects {required}-{len(args)} positional args, got {provided}"
                    )

    assert mismatches == []


def test_controller_gui_private_facade_calls_exist_on_pipeline_gui() -> None:
    main_tree = _module_tree(Path("ui/main.py"))
    pipeline_gui = next(node for node in main_tree.body if isinstance(node, ast.ClassDef) and node.name == "PipelineGUI")
    gui_names = set(_class_methods(pipeline_gui))
    for node in ast.walk(pipeline_gui):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            gui_names.add(node.attr)

    missing: list[str] = []
    for path in UI_PATHS:
        if path == Path("ui/main.py"):
            continue
        for node in ast.walk(_module_tree(path)):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
                continue
            owner = node.value
            if isinstance(owner.value, ast.Name) and owner.value.id in {"self", "ctrl"} and owner.attr == "gui":
                if node.attr.startswith("_") and node.attr not in gui_names:
                    missing.append(f"{path}:{node.lineno}: gui.{node.attr}")

    assert missing == []
