import os
import time
import zipfile
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from evraz_cr.utils.project_cont import get_project_structure_and_type
from model.mistral_model import process_code_and_get_documentation

DOCUMENTATION_DIR = os.path.join("model", "documentations")
PROJECTS_DIR = os.path.join("media", "projects")
CODE_EXTENSIONS = {".py", ".cs", ".ts", ".tsx", ".yaml", ".yml", ".json", ".md", ".java", ".cpp", ".c", ".go", ".rs"}


class GetReviewView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file', None)

        if not file:
            return Response({"error": "Файл не предоставлен"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            os.makedirs(PROJECTS_DIR, exist_ok=True)

            timestamp = int(time.time())
            file_name, file_extension = os.path.splitext(file.name)
            folder_name = f"{file_name}_{timestamp}"

            folder_path = os.path.join(PROJECTS_DIR, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            # Если файл - ZIP
            if file_extension == ".zip":
                zip_temp_path = os.path.join(PROJECTS_DIR, f"{folder_name}.zip")
                with open(zip_temp_path, "wb") as f:
                    for chunk in file.chunks():
                        f.write(chunk)

                try:
                    with zipfile.ZipFile(zip_temp_path, "r") as zip_ref:
                        zip_ref.extractall(folder_path)
                    os.remove(zip_temp_path)
                except zipfile.BadZipFile:
                    return Response({"error": "Некорректный zip-файл"}, status=status.HTTP_400_BAD_REQUEST)

                # Строим структуру проекта для распакованного архива
                try:
                    structure_graph, project_type = get_project_structure_and_type(folder_path)
                except Exception as e:
                    return Response({"error": f"Ошибка при анализе проекта: {str(e)}"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                # Функция для обработки файлов кода внутри архива
                def process_files_in_folder(folder):
                    results = []
                    for root, dirs, files in os.walk(folder):
                        dirs[:] = [d for d in dirs if not d.startswith('__MACOSX')]

                        for file in files:
                            file_path = os.path.join(root, file)
                            _, ext = os.path.splitext(file)

                            if ext not in CODE_EXTENSIONS:
                                continue

                            try:
                                with open(file_path, "r", encoding="utf-8") as code_file:
                                    code_content = code_file.read()

                                result = process_code_and_get_documentation(
                                    code=code_content,
                                    project_structure=structure_graph,
                                    file_location=file_path,
                                    project_type=project_type
                                )

                                try:
                                    if result["results"] != []:
                                        results.append(result)
                                except:
                                    continue

                            except UnicodeDecodeError as e:
                                results.append({
                                    "file": file_path,
                                    "error": f"Ошибка обработки файла: {str(e)}"
                                })
                            except Exception as e:
                                results.append({
                                    "file": file_path,
                                    "error": f"Ошибка обработки файла: {str(e)}"
                                })

                    return results

                try:
                    processed_results = process_files_in_folder(folder_path)
                except Exception as e:
                    return Response({"error": f"Ошибка обработки файлов проекта: {str(e)}"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                return Response({
                    "folder_path": folder_path,
                    "project_structure": structure_graph,
                    "project_type": project_type,
                    "result": processed_results
                }, status=status.HTTP_201_CREATED)

            # Если файл не архив, то обработаем его как одиночный код
            else:
                file_path = os.path.join(folder_path, file.name)
                with open(file_path, "wb") as f:
                    for chunk in file.chunks():
                        f.write(chunk)

                try:
                    structure_graph, project_type = get_project_structure_and_type(folder_path)
                except Exception as e:
                    return Response({"error": f"Ошибка при анализе проекта: {str(e)}"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                try:
                    with open(file_path, "r", encoding="utf-8") as code_file:
                        code_content = code_file.read()

                    result = process_code_and_get_documentation(
                        code=code_content,
                        project_structure=structure_graph,
                        file_location=file_path,
                        project_type=project_type
                    )

                    return Response({
                        "folder_path": folder_path,
                        "project_structure": structure_graph,
                        "project_type": project_type,
                        "result": result
                    }, status=status.HTTP_201_CREATED)

                except Exception as e:
                    return Response({"error": f"Ошибка обработки файла: {str(e)}"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddDocView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    # Сохранение новых регламентов
    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file', None)

        if not file:
            return Response({"error": "Файл не предоставлен"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            os.makedirs(DOCUMENTATION_DIR, exist_ok=True)

            file_path = os.path.join(DOCUMENTATION_DIR, file.name)

            with open(file_path, 'wb') as f:
                for chunk in file.chunks():
                    f.write(chunk)

            return Response({"message": "Файл успешно загружен", "file_path": file_path},
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
