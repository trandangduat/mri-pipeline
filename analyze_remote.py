import ast

with open("ui/main.py", "r") as f:
    src = f.read()

tree = ast.parse(src)
remote_funcs = []
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "PipelineGUI":
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and "remote" in child.name.lower() or "server" in child.name.lower() or "ssh" in child.name.lower():
                remote_funcs.append(child.name)
print(remote_funcs)
