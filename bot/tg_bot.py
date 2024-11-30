import asyncio
import json
import logging
import sys
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session import aiohttp
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, Document, FSInputFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors
import os
from datetime import datetime
import textwrap
import re

pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))  # Обычный
pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'DejaVuSans-Bold.ttf'))  # Жирный
pdfmetrics.registerFont(TTFont('DejaVuSans-Oblique', 'DejaVuSans-Oblique.ttf'))  # Курсив
pdfmetrics.registerFont(TTFont('DejaVuSansMono', 'DejaVuSansMono.ttf'))  # Моноширинный (код)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 50
LINE_HEIGHT = 14
MAX_WIDTH = PAGE_WIDTH - 2 * MARGIN


def draw_markdown_text(c, text, x, y):
    """
    Рисует текст с поддержкой форматирования Markdown:
    - **жирный текст**
    - *курсив*
    - `код`
    """
    lines = text.split('\n')
    for line in lines:
        y = draw_wrapped_markdown_line(c, line, x, y)
    return y


def draw_wrapped_markdown_line(c, text, x, y):
    wrapped_lines = textwrap.wrap(text, width=int(MAX_WIDTH // (7)))
    for line in wrapped_lines:
        if line.startswith('### '):
            c.setFont("DejaVuSans-Bold", 12)
            c.setFillColor(colors.darkblue)
            line = line[4:]
        elif line.startswith('## '):
            c.setFont("DejaVuSans-Bold", 14)
            line = line[3:]
        elif line.startswith('# '):
            c.setFont("DejaVuSans-Bold", 16)
            line = line[2:]
        elif '**' in line:
            c.setFont("DejaVuSans-Bold", 10)
            line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        elif '*' in line:
            c.setFont("DejaVuSans-Oblique", 10)
            line = re.sub(r'\*(.*?)\*', r'\1', line)
        elif '`' in line:
            c.setFont("DejaVuSansMono", 10)
            c.setFillColor(colors.darkblue)
            line = line.replace('`', '')
        else:
            c.setFont("DejaVuSans", 10)
            c.setFillColor(colors.black)

        c.drawString(x, y, line)
        y -= LINE_HEIGHT
    return y


def create_review_pdf(data, file_path):
    """
    Создает PDF-файл с результатами анализа.
    """
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4
    margin = 50

    project_name = os.path.basename(data['folder_path'])

    c.setFont("DejaVuSans-Bold", 16)
    c.drawString(margin, height - margin, f"# Анализ проекта: {project_name}")
    c.setFont("DejaVuSans", 12)
    c.drawString(margin, height - margin - 20, f"Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    y_pos = height - margin - 60

    y_pos -= 20
    y_pos = draw_markdown_text(c, "## Обнаруженные проблемы:", margin, y_pos)

    if isinstance(data['result'], dict):
        for result in data['result']['results']:
            if y_pos < margin + 100:
                c.showPage()
                y_pos = height - margin

            line_number = result.get('line_number', 'Не указано')
            y_pos = draw_markdown_text(c, f"{result.get('error_class', 'Неизвестная ошибка')}", margin,
                                       y_pos)

            y_pos = draw_markdown_text(c, f"**Файл:** `{result.get('file_name', 'Неизвестный файл')}`",
                                       margin, y_pos)
            y_pos = draw_markdown_text(c, f"**Линия:** `{line_number}`", margin, y_pos)

            y_pos = draw_markdown_text(c,
                                       f"**Комментарий:**\n*{result.get('comment', 'Комментарий отсутствует')}*",
                                       margin, y_pos - 10)

            y_pos = draw_markdown_text(c,
                                       f"**Предложенное исправление:**\n```{result.get('fix', '')}```",
                                       margin, y_pos - 10)

            y_pos -= 20
    else:
        for result_d in data['result']:
            print(result_d, "Result_d")
            if result_d['results']:
                for result in result_d['results']:
                    print(result, "RESULT")
                    try:
                        if y_pos < margin + 100:
                            c.showPage()
                            y_pos = height - margin

                        line_number = result.get('line_number', 'Не указано')
                        y_pos = draw_markdown_text(c, f"{result.get('error_class', 'Неизвестная ошибка')}", margin,
                                                   y_pos)

                        y_pos = draw_markdown_text(c, f"**Файл:** `{result.get('file_name', 'Неизвестный файл')}`",
                                                   margin, y_pos)
                        y_pos = draw_markdown_text(c, f"**Линия:** `{line_number}`", margin, y_pos)

                        y_pos = draw_markdown_text(c,
                                                   f"**Комментарий:**\n*{result.get('comment', 'Комментарий отсутствует')}*",
                                                   margin, y_pos - 10)

                        y_pos = draw_markdown_text(c,
                                                   f"**Предложенное исправление:**\n```{result.get('fix', '')}```",
                                                   margin, y_pos - 10)

                        y_pos -= 20

                    except Exception as e:
                        continue

    c.save()


TOKEN = open("token.txt", "r").readline().strip()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
user_states = {}

ZIP_DIR = "downloaded_files"
REVIEWS_DIR = "reviews"
os.makedirs(ZIP_DIR, exist_ok=True)


def main_kb(user_telegram_id: int) -> ReplyKeyboardMarkup:
    kb_list = [
        [KeyboardButton(text="📁 Загрузить проект"), KeyboardButton(text="📄 Загрузить регламент")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True)
    return keyboard


def unique_name(file_name):
    timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    unique_file_name = f"{timestamp}_{file_name}"
    return unique_file_name


async def send_file_to_server(file_path):
    url = 'http://127.0.0.1:8000/get_review/'
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            async with session.post(url, data={'file': f}) as response:
                if response.status == 201:
                    data = await response.text()
                    return json.loads(data)
                else:
                    return None


async def send_file_to_add_doc(file_path):
    url = 'http://127.0.0.1:8000/add_doc/'
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            async with session.post(url, data={'file': f}) as response:
                if response.status == 201:
                    data = await response.text()
                    return json.loads(data)
                else:
                    return None


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Здравствуй, {message.from_user.full_name}!",
        reply_markup=main_kb(message.from_user.id)
    )


@router.message(F.text == "📁 Загрузить проект")
async def upload_file_prompt(message: Message):
    user_states[message.from_user.id] = "awaiting_file"
    await message.answer("Отправьте проект или файл")


@router.message(F.document)
async def save_file(message: Message):
    user_id = message.from_user.id

    if user_states.get(user_id) == "awaiting_doc":
        document: Document = message.document

        file = await bot.get_file(document.file_id)
        file_path = os.path.join(ZIP_DIR, unique_name(document.file_name))

        await bot.download_file(file.file_path, file_path)

        user_states.pop(user_id, None)

        try:
            response = await send_file_to_add_doc(file_path)

            if response:
                await message.answer("📄 Ваше регламент успешно загружен")
            else:
                await message.answer("Произошла ошибка при обработке файла на сервере.")
        except Exception as e:
            await message.answer(f"Ошибка при соединении с сервером: {str(e)}")
    else:
        if user_states.get(user_id) != "awaiting_file" and user_states.get(user_id) != "awaiting_doc":
            await message.answer("Пожалуйста, нажмите '📁 Загрузить проект' перед загрузкой файла.")
            return

        document: Document = message.document

        file = await bot.get_file(document.file_id)
        file_path = os.path.join(ZIP_DIR, unique_name(document.file_name))

        await bot.download_file(file.file_path, file_path)

        user_states.pop(user_id, None)

        try:
            response = await send_file_to_server(file_path)

            if response:
                data = response

                pdf_file_path = os.path.join(ZIP_DIR, unique_name("review.pdf"))
                create_review_pdf(data, pdf_file_path)

                file_to_send = FSInputFile(pdf_file_path)
                await bot.send_document(message.chat.id, file_to_send,
                                        caption="📄 Ваше ревью успешно сгенерировано.")
            else:
                await message.answer("Произошла ошибка при обработке файла на сервере.")
        except Exception as e:
            await message.answer(f"Ошибка при соединении с сервером: {str(e)}")


@router.message(F.text == "📄 Загрузить регламент")
async def get_review(message: Message):
    user_states[message.from_user.id] = "awaiting_doc"
    await message.answer("Отправьте регламент")


@router.message()
async def echo_handler(message: Message) -> None:
    try:
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer("Nice try!")


async def main() -> None:
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
