import ast
import glob
import os

class MethodChecker(ast.NodeVisitor):
    def __init__(self):
        self.classes = {} # class_name -> set of method names
        self.current_class = None
        self.calls = [] # list of (file, class, line, method_called)

    def visit_ClassDef(self, node):
        self.current_class = node.name
        self.classes[node.name] = set()
        
        # Add methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                self.classes[node.name].add(item.name)
                
        self.generic_visit(node)
        self.current_class = None

    def visit_Call(self, node):
        if self.current_class:
            # Check for self.method()
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    method_name = node.func.attr
                    self.calls.append((self.current_file, self.current_class, node.lineno, method_name))
        self.generic_visit(node)

def run():
    checker = MethodChecker()
    files = glob.glob("ui/*.py") + glob.glob("ui/dialogs/*.py") + glob.glob("ui/tabs/*.py")
    
    # First pass: collect all classes and their methods
    for f in files:
        checker.current_file = f
        try:
            with open(f, "r") as file:
                tree = ast.parse(file.read())
                checker.visit(tree)
        except Exception as e:
            print(f"Failed to parse {f}: {e}")

    # Second pass: check calls
    errors = []
    for file, cls, line, method in checker.calls:
        # If method is not defined in the class, it's a potential error
        # Note: it could be inherited, but in this specific UI refactoring, 
        # these classes (PipelineController, JobsController, PipelineGUI) don't inherit these methods from base classes.
        if method not in checker.classes.get(cls, set()):
            # Ignore built-in tkinter methods if it inherits from tkinter (e.g. destroy, after, etc)
            # but none of these controllers inherit from tkinter. PipelineGUI does not either (it takes root).
            # We'll just print them all and inspect manually.
            errors.append(f"{file}:{line} [{cls}] calls self.{method}() but it's not defined in {cls}")
            
    if errors:
        for err in errors:
            print(err)
    else:
        print("No missing method calls found!")

if __name__ == "__main__":
    run()
