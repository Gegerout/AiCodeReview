import os
from PyPDF2 import PdfReader
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT
from whoosh.qparser import QueryParser
from huggingface_hub import snapshot_download
import json
import functools
from typing import List
import torch
from mistral_inference.transformer import Transformer
from mistral_inference.generate import generate
from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
from mistral_common.protocol.instruct.messages import UserMessage, AssistantMessage
from mistral_common.protocol.instruct.request import ChatCompletionRequest
from mistral_common.protocol.instruct.tool_calls import Tool, Function


# Чтение данных из pdf регламента
def extract_text_from_pdf(file_path):
    reader = PdfReader(file_path)
    text = []
    for page in reader.pages:
        text.append(page.extract_text())
    return "\n".join(text)


# Индексирование файлов документации
def create_search_index(documentation_folder: str, index_dir: str = "index"):
    schema = Schema(title=TEXT(stored=True), content=TEXT(stored=True))

    if not os.path.exists(index_dir):
        os.mkdir(index_dir)

    ix = create_in(index_dir, schema)

    writer = ix.writer()

    for root, _, files in os.walk(documentation_folder):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            try:
                if file_name.lower().endswith(".pdf"):
                    content = extract_text_from_pdf(file_path)
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                writer.add_document(title=file_name, content=content)
                print(f"Indexed: {file_name}")
            except Exception as e:
                print(f"Failed to index {file_name}: {e}")

    writer.commit()
    print("Index created successfully.")


# Получение документации по ключевым словам
def get_documentation(keywords: List[str], index_dir: str = "index") -> str:
    print(keywords)

    ix = open_dir(index_dir)

    search_results = []

    for keyword in keywords:
        with ix.searcher() as searcher:
            query = QueryParser("content", ix.schema).parse(keyword)

            results = searcher.search(query)

            if results:
                search_results.append(f"Results for keyword: {keyword}")
                for result in results:
                    search_results.append(f"From file {result['title']}:\n{result['content'][:300]}...\n")

    if search_results:
        print(search_results)
        return "\n".join(search_results)
    else:
        return "No relevant documentation found for the given keywords. Make your own review based on your knowledge"


# Загрузка модели LLM
def download_mistral_model(model_repo_id: str, local_model_path: str):
    print(f"Downloading model '{model_repo_id}' to '{local_model_path}'...")
    snapshot_download(
        repo_id=model_repo_id,
        local_dir=local_model_path,
        allow_patterns=[
            "params.json",
            "consolidated.safetensors",
            "tokenizer.model.v3"
        ],
        token="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"
    )
    print("Model download completed.")
    return local_model_path


mistral_repo_id = "mistralai/Mistral-7B-Instruct-v0.3"
mistral_models_path = "mistral_models/7B-Instruct-v0.3/"

model_path = download_mistral_model(mistral_repo_id, mistral_models_path)

print(f"Model is ready for use at: {model_path}")

names_to_functions = {
    "get_documentation": functools.partial(get_documentation),
}

tokenizer_path = model_path + "tokenizer.model.v3"

# Инициализация модели и токенизатора
tokenizer = MistralTokenizer.from_file(tokenizer_path)
model = Transformer.from_folder(str(model_path), device="cuda", dtype=torch.float16)


# Обработка кода
def process_code_and_get_documentation(
        code: str,
        project_structure: str,
        file_location: str,
        project_type: str,
        max_tokens: int = 256,
):
    # Данные о function calling
    tools = [
        Tool(
            function=Function(
                name="get_documentation",
                description="Get documentation by keywords after code analysis",
                parameters={
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "The keywords to search",
                        }
                    },
                    "required": ["keywords"],
                },
            )
        )
    ]

    # Системный промпт модели
    messages = [
        UserMessage(
            content=(
                "Make a professional code review for this code. Check for hexagonal architecture. Don't check for linter, naming, and so on insignificant problems. Check the arcthitecture mostly, that business logic is written correctly and layers not intersect.  Write answer only in Russian language. "
                "Return response only in JSON data format with scheme: "
                "results: [line_number: int or list[int], comment: str, fix: str, error_class: str, file_name: str]. If no significant mistakes return empty array "
                "Comment is about our error, description of problem, fix is a proposed solution to fix problem (maybe code samples highlighted with markdown), "
                "error_class is a error classification, for example architecture error, naming error and so on, and file name. "
                "If you don't have enought information about file and code, just don't write for it "
                f"Current project type: {project_type}\n"
                f"Current project structure:\n{project_structure}\n"
                f"Current file location:\n{file_location}\n"
                f"Code:\n{code}"
            )
        )
    ]

    tokenizer_path = mistral_models_path + "tokenizer.model.v3"
    tokenizer = MistralTokenizer.from_file(tokenizer_path)
    model = Transformer.from_folder(str(mistral_models_path))

    completion_request = ChatCompletionRequest(
        tools=tools,
        messages=messages,
    )
    tokens = tokenizer.encode_chat_completion(completion_request).tokens

    out_tokens, _ = generate(
        [tokens], model, max_tokens=max_tokens, temperature=0.0, eos_id=tokenizer.instruct_tokenizer.tokenizer.eos_id
    )
    response_text = tokenizer.instruct_tokenizer.tokenizer.decode(out_tokens[0])

    response_json = json.loads(response_text)
    tool_call = response_json.get("tool_calls", [])[0]
    function_name = tool_call["function"]["name"]
    function_params = tool_call["function"]["arguments"]

    # Получение ключевых слов из модели
    keywords = json.loads(function_params).get("keywords", [])

    # Получение документации
    function_result = names_to_functions[function_name](keywords=keywords)

    # Добавление документации к модели
    messages.append(
        AssistantMessage(
            role="tool",
            name=function_name,
            content=function_result,
            tool_call_id=tool_call["id"],
        )
    )

    completion_request = ChatCompletionRequest(messages=messages)
    final_tokens = tokenizer.encode_chat_completion(completion_request).tokens
    final_out_tokens, _ = generate(
        [final_tokens], model, max_tokens=max_tokens, temperature=0.0,
        eos_id=tokenizer.instruct_tokenizer.tokenizer.eos_id
    )
    final_response = tokenizer.instruct_tokenizer.tokenizer.decode(final_out_tokens[0])

    return final_response
