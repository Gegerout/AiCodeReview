import os
from collections import defaultdict

CODE_EXTENSIONS = {".py", ".cs", ".ts", ".tsx", ".yaml", ".yml", ".json", ".md", ".java", ".cpp", ".c", ".go", ".rs"}
IGNORE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".ico", ".mp4", ".avi", ".xlsx",
                     ".csv", ".sqlite", ".db", ".zip", ".tar", ".rar", ".tar.gz"}


def get_project_structure_and_type(root_dir):
    """
    Строит структуру проекта и определяет его тип.

    :param root_dir: Путь к корневой папке проекта
    :return: Tuple из строки с графом проекта и типа проекта (python, c#, typescript)
    """
    structure = defaultdict(list)
    file_extensions = {
        ".py": "python",
        ".cs": "c#",
        ".ts": "typescript",
        ".tsx": "typescript"
    }
    detected_types = set()

    def traverse(directory, prefix=""):
        """
        Рекурсивно обходит директории и записывает их структуру.
        """
        items = sorted(os.listdir(directory))
        for idx, item in enumerate(items):
            path = os.path.join(directory, item)
            if item.startswith('__MACOSX') or item.startswith('.'):
                continue

            connector = "├── " if idx < len(items) - 1 else "└── "
            structure[prefix].append(connector + item)

            if os.path.isdir(path):
                traverse(path, prefix + "    ")

            elif os.path.isfile(path):
                _, ext = os.path.splitext(item)

                if ext in IGNORE_EXTENSIONS:
                    continue

                if ext in file_extensions:
                    detected_types.add(file_extensions[ext])

    traverse(root_dir)

    project_type = "unknown"
    if detected_types:
        project_type = ", ".join(detected_types)

    structure_graph = f"{root_dir}\n"
    for prefix, items in structure.items():
        for item in items:
            structure_graph += prefix + item + "\n"

    return structure_graph, project_type
