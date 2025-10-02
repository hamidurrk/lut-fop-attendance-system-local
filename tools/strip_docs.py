from __future__ import annotations
import ast
from pathlib import Path

def strip_docstrings(node: ast.AST) -> ast.AST:
    for child in ast.walk(node):
        if isinstance(child, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if child.body and isinstance(child.body[0], ast.Expr):
                expr = child.body[0]
                if isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                    child.body = child.body[1:]
    return node

def rewrite_file(path: Path) -> None:
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    stripped = strip_docstrings(tree)
    new_source = ast.unparse(stripped)
    if not new_source.endswith('\n'):
        new_source += '\n'
    path.write_text(new_source, encoding='utf-8')

def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    for py_file in project_root.rglob('*.py'):
        if '__pycache__' in py_file.parts:
            continue
        rewrite_file(py_file)
if __name__ == '__main__':
    main()
