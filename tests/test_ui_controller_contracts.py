from __future__ import annotations

import ast
from pathlib import Path


UI_PATHS = [path for path in Path("ui").rglob("*.py") if path.name != "__init__.py"]


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(class_node: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in class_node.body if isinstance(node, ast.FunctionDef)}


def _class_self_names(class_node: ast.ClassDef) -> set[str]:
    names = set(_class_methods(class_node))
    for node in ast.walk(class_node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            names.add(node.attr)
    return names


def _controller_class_names() -> dict[str, set[str]]:
    controller_classes = {
        "tools_ctrl": (Path("ui/gui_tools.py"), "ToolsController"),
        "pipeline_ctrl": (Path("ui/gui_pipeline.py"), "PipelineController"),
        "jobs_ctrl": (Path("ui/gui_jobs.py"), "JobsController"),
        "progress_ctrl": (Path("ui/gui_progress.py"), "ProgressController"),
        "validation_ctrl": (Path("ui/gui_validation.py"), "ValidationController"),
        "config_ctrl": (Path("ui/gui_config.py"), "ConfigController"),
        "registry_ctrl": (Path("ui/job_registry.py"), "JobRegistryController"),
        "remote_ctrl": (Path("ui/gui_remote.py"), "RemoteController"),
    }
    names: dict[str, set[str]] = {}
    for attr, (path, class_name) in controller_classes.items():
        tree = _module_tree(path)
        class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
        names[attr] = _class_self_names(class_node)
    return names


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


def test_controller_gui_public_attribute_calls_exist_on_pipeline_gui() -> None:
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
                if not node.attr.startswith("_") and node.attr not in gui_names:
                    missing.append(f"{path}:{node.lineno}: gui.{node.attr}")

    assert missing == []


def test_controller_cross_calls_target_existing_controller_methods() -> None:
    controller_methods = _controller_class_names()

    missing: list[str] = []
    for path in UI_PATHS:
        for node in ast.walk(_module_tree(path)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            if not isinstance(receiver, ast.Attribute) or receiver.attr not in controller_methods:
                continue
            owner = receiver.value
            is_gui_owner = isinstance(owner, ast.Name) and owner.id == "gui"
            is_self_gui_owner = (
                isinstance(owner, ast.Attribute)
                and owner.attr == "gui"
                and isinstance(owner.value, ast.Name)
                and owner.value.id in {"self", "ctrl"}
            )
            if (is_gui_owner or is_self_gui_owner) and node.func.attr not in controller_methods[receiver.attr]:
                missing.append(f"{path}:{node.lineno}: {receiver.attr}.{node.func.attr}()")

    assert missing == []


def test_controller_cross_attributes_exist_on_target_controller() -> None:
    controller_names = _controller_class_names()

    missing: list[str] = []
    for path in UI_PATHS:
        for node in ast.walk(_module_tree(path)):
            if not isinstance(node, ast.Attribute):
                continue
            receiver = node.value
            if not isinstance(receiver, ast.Attribute) or receiver.attr not in controller_names:
                continue
            owner = receiver.value
            is_gui_owner = isinstance(owner, ast.Name) and owner.id == "gui"
            is_self_gui_owner = (
                isinstance(owner, ast.Attribute)
                and owner.attr == "gui"
                and isinstance(owner.value, ast.Name)
                and owner.value.id in {"self", "ctrl"}
            )
            if (is_gui_owner or is_self_gui_owner) and node.attr not in controller_names[receiver.attr]:
                missing.append(f"{path}:{node.lineno}: {receiver.attr}.{node.attr}")

    assert missing == []


def test_progress_tab_context_does_not_treat_controller_as_gui() -> None:
    tree = _module_tree(Path("ui/tabs/progress_tab.py"))
    build_progress_tab = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_progress_tab"
    )

    progress_ctrl_refs = [
        node.lineno
        for node in ast.walk(build_progress_tab)
        if isinstance(node, ast.Attribute)
        and node.attr == "progress_ctrl"
        and isinstance(node.value, ast.Name)
        and node.value.id == "gui"
    ]

    assert progress_ctrl_refs == []


def test_attach_job_dialog_private_calls_exist_on_jobs_controller() -> None:
    jobs_tree = _module_tree(Path("ui/gui_jobs.py"))
    jobs_controller = next(node for node in jobs_tree.body if isinstance(node, ast.ClassDef) and node.name == "JobsController")
    jobs_methods = set(_class_methods(jobs_controller))
    dialog_tree = _module_tree(Path("ui/dialogs/job_dialogs.py"))
    attach_dialog = next(
        node for node in dialog_tree.body if isinstance(node, ast.FunctionDef) and node.name == "show_attach_job_dialog"
    )

    missing = [
        f"ui/dialogs/job_dialogs.py:{node.lineno}: ctrl.{node.func.attr}()"
        for node in ast.walk(attach_dialog)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.startswith("_")
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ctrl"
        and node.func.attr not in jobs_methods
    ]

    assert missing == []


def test_job_dialog_ctrl_private_access_matches_controller_owner() -> None:
    controller_specs = {
        "show_attach_job_dialog": (Path("ui/gui_jobs.py"), "JobsController"),
        "show_resume_job_dialog": (Path("ui/gui_jobs.py"), "JobsController"),
        "show_upload_remote_job_dialog": (Path("ui/gui_pipeline.py"), "PipelineController"),
    }
    dialog_tree = _module_tree(Path("ui/dialogs/job_dialogs.py"))

    missing: list[str] = []
    for function_name, (controller_path, controller_class) in controller_specs.items():
        controller_tree = _module_tree(controller_path)
        class_node = next(
            node for node in controller_tree.body if isinstance(node, ast.ClassDef) and node.name == controller_class
        )
        controller_names = _class_self_names(class_node)
        function_node = next(
            node for node in dialog_tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        for node in ast.walk(function_node):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name) or node.value.id != "ctrl" or not node.attr.startswith("_"):
                continue
            if node.attr not in controller_names:
                missing.append(f"ui/dialogs/job_dialogs.py:{node.lineno}: {function_name} ctrl.{node.attr}")

    assert missing == []
