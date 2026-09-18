import ast
import os
import pytest

def get_imports(filepath):
    imports = []
    with open(filepath, 'r') as f:
        try:
            tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        imports.append(n.name)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module)
        except Exception:
            pass
    return imports

def get_python_files(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                yield os.path.join(root, file)

def test_domain_does_not_import_infrastructure_or_frameworks():
    domain_dir = os.path.join("core", "domain")
    forbidden = ["fastapi", "sqlalchemy", "core.infrastructure", "apps", "subprocess"]
    
    for filepath in get_python_files(domain_dir):
        imports = get_imports(filepath)
        for imp in imports:
            if imp:
                for f in forbidden:
                    assert not imp.startswith(f), f"{filepath} imports forbidden module {imp}"
                    
def test_application_does_not_import_frameworks():
    app_dir = os.path.join("core", "application")
    forbidden = ["fastapi", "sqlalchemy"]
    
    for filepath in get_python_files(app_dir):
        imports = get_imports(filepath)
        for imp in imports:
            if imp:
                for f in forbidden:
                    assert not imp.startswith(f), f"{filepath} imports forbidden module {imp}"
