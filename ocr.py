import os
import re
import time
import requests
import subprocess
import jupiter # Нейросетевой модуль
import win32gui
import threading
from PyPDF2 import PdfReader
from urllib.parse import unquote

SYSTEM_PROMPT = (
    """Ты — опытный аналитик и редактор текстов. На вход тебе подаётся HTML-код веб-страницы (например, статьи).

    Твоя задача:
        Проанализировать структуру HTML и выделить основное содержимое страницы (текст статьи, документа, новости и т.п.).
        Игнорировать рекламные блоки, футеры, навигационные меню, сайдбары, комментарии, виджеты, повторяющиеся ссылки и прочие элементы оформления.
        Не выдумывать и не добавлять информации, которой нет в исходном коде. Только то, что содержится в основном тексте.
        Оформить результат как красиво структурированный конспект в формате Markdown:
            Использовать заголовки, списки, выделения, параграфы.
            Сохранить логическую структуру оригинала (если есть подзаголовки — использовать их).
            При необходимости добавить краткие пометки и примечания.

        Если в статье есть примеры кода, таблицы, списки — сохранить их корректно, используя Markdown-синтаксис.
        Убедиться, что финальный текст читабельный, логичный и полезный для дальнейшего изучения.

    ⚠️ Не добавляй объяснений перед конспектом. Начни сразу с самого конспекта.
    Если текст содержит маркированные или нумерованные списки — переноси их корректно.
    Если есть определения терминов, важные факты, примеры — обязательно включай их в конспект.
    Конспект должен быть красиво оформлен в формате Markdown.
    Перед названием темы добавь "# 🚀", перед каждой подзаголовком — 💠, примеры через 🎯.
    """
)


def extract_text_from_pdf(file_path):
    """Достать текст из пдф"""
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def get_active_url():
    """Читает URL из файла 'url.txt'."""
    file_path = "url.txt"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            url = f.read().strip()
            print(f"✅ URL из файла: {url}")
            return url
    else:
        print("❌ Файл 'url.txt' не найден!")
        return None


def fetch_page_content(url):
    """Запрашивает HTML-код страницы."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers)
        response.encoding = "utf-8"
        if response.status_code == 200:
            print("✅ Код страницы получен")
            return response.text
        else:
            print(f"❌ Ошибка HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None


def save_markdown(summary):
    """Записывает конспект в 'debug.md'."""
    file_path = "debug.md"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(summary)
        print("✅ Конспект сохранён в 'debug.md'")
    except Exception as e:
        print(f"❌ Ошибка записи в 'debug.md': {e}")

def classify_pdf(file_path):
    from PyPDF2 import PdfReader
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        if num_pages < 30:
            classification = "Обычный"
        else:
            classification = "Книга"
        print(f"Классификация PDF: {classification} ({num_pages} страниц)")
        return classification
    except Exception as e:
        print(f"Ошибка при классификации PDF: {e}")
        return "Не определено"


def split_into_chapters(text):
    """
    Разбивает книгу на главы по заголовкам ('Глава 1', 'Часть 2', 'Эпилог' и т. д.)
    Если заголовки не найдены, делит текст на части по 30 страниц.
    """
    chapters = re.split(r'\n\s*(Глава|Часть|Эпилог) \d+\s*\n', text)

    if len(chapters) < 2:
        chapters = [text[i:i + 15000] for i in range(0, len(text), 15000)]

    print(f"✅ Найдено {len(chapters)} глав(ы)")
    return chapters

def summarize_pdf(file_path):
    """
    Разбивает книгу на главы, конспектирует каждую главу отдельно и собирает всё воедино.
    """
    print(f"🔄 Обработка книги (PDF): {file_path}")
    pdf_text = extract_text_from_pdf(file_path)

    classification = classify_pdf(file_path)

    if classification == "Обычный":
        combined_prompt = SYSTEM_PROMPT + "\n\n" + pdf_text
        summary = jupiter.ask_jupiter(combined_prompt)
        save_markdown(summary)
        return summary

    chapters = split_into_chapters(pdf_text)

    full_summary = "# 🚀 Конспект книги\n\n"

    for i, chapter_text in enumerate(chapters):
        chapter_prompt = SYSTEM_PROMPT + f"\n\n📖 **Глава {i + 1}**:\n" + chapter_text
        chapter_summary = jupiter.ask_jupiter(chapter_prompt)
        full_summary += f"## Глава {i + 1}\n\n{chapter_summary}\n\n"

    save_markdown(full_summary)
    return full_summary


def process_local_file(url):
    """Обрабатывает локальные файлы (например, PDF)."""
    local_path = url[7:] if url.lower().startswith("file://") else url

    if local_path.startswith("/"):
        local_path = local_path[1:]

    local_path = unquote(local_path)

    _, ext = os.path.splitext(local_path)
    ext = ext.lower()
    print(f"✅ Локальный файл: {local_path} (расширение: {ext})")

    if ext == ".pdf":
        return summarize_pdf(local_path)
    else:
        print(f"⚠ Конспектирование файлов типа {ext} пока не реализовано.")
        summary = f"Заглушка: конспектирование файлов типа {ext} пока не реализовано."
        save_markdown(summary)
        return summary


def run_consenting():
    """
    Получает URL из файла.
    Если URL содержит локальный файл (file://...), запускает обработку по типу файла.
    Иначе обрабатывает как HTML-страницу.
    """
    url = get_active_url()
    if url:
        if url.lower().startswith("file://"):
            print(f"⚠ Обнаружен локальный файл: {url}")
            process_local_file(url)
        else:
            page_content = fetch_page_content(url)
            if page_content:
                combined_prompt = SYSTEM_PROMPT + "\n\n" + page_content
                summary = jupiter.ask_jupiter(combined_prompt)
                save_markdown(summary)
                os.system("start debug.md")



def get_active_window_title():
    """Возвращает заголовок активного окна."""
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetWindowText(hwnd)





def main():
    run_consenting()


if __name__ == '__main__':
    main()
