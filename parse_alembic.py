import os
import ast

def get_revisions(folder):
    for f in os.listdir(folder):
        if f.endswith('.py'):
            with open(os.path.join(folder, f)) as file:
                content = file.read()
                tree = ast.parse(content)
                rev = None
                down_rev = None
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                if target.id == 'revision':
                                    rev = node.value.value
                                elif target.id == 'down_revision':
                                    if isinstance(node.value, ast.Constant):
                                        down_rev = node.value.value
                                    elif isinstance(node.value, ast.Name) and node.value.id == 'None':
                                        down_rev = None
                print(f"{rev} -> {down_rev} ({f})")

get_revisions('alembic/versions')
