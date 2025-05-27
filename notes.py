import os
import re
from idlelib.replace import replace

from jupiter import ask_jupiter  # Нейросетевой модуль
from fuzzywuzzy import process
import subprocess
import time


NOTES_DIR = "notes"

SYSTEM_PROMPT_NOTE = (
    "Ты помощник для создания заметок. Преобразуй текст пользователя в структурированную Markdown-заметку. "
    "Если пользователь просит, то расписывай подробнее её, от лишних деталей не будет вреда."
    "Первая строка ОБЯЗАНА начинаться со слов: `Заметка: \"<имя>\"`. <имя> ОБЯЗАНО быть коротким и понятным."
    "Если пользователь указал теги, добавь их в конец текста в формате `Теги: <список тегов>`. "
    "НЕ добавляй теги самостоятельно, если их нет в запросе пользователя. "
    "Сохраняй Markdown-структуру: заголовки, списки, выделение текста. Используй подходящие эмодзи, чтобы освежить заметку(КРОМЕ НАЗВАНИЯ И ТЕГОВ. Там нельзя)"
)
SYSTEM_PROMPT_UPDATE_NOTE = (
    "Ты помощник по ведению заметок. Сейчас тебе передана существующая заметка. "
    "Твоя задача — дополнить её новым содержимым по запросу пользователя, сохраняя Markdown-формат. "
    "НЕ удаляй существующий текст, просто расширь его. Добавляй новые пункты или пояснения, если это необходимо."
)

SHORT_PROMPT = (
    "Ты — помощник, который анализирует текст заметки и формирует краткий пересказ. "
    "Выдели основную суть и передай её естественным образом, как если бы объяснял человеку. "
    "Если текст короткий, просто уточни его суть. Пример ответа: 'Вы записали...' или 'В заметке говорится...' "
    "Пересказ должен быть максимально понятным, но не длинным."
)


def generate_note(user_text):
    """Отправляет текст и промпт в `jupiter.py`, получает Markdown-заметку"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_NOTE},
        {"role": "user", "content": user_text}
    ]
    return ask_jupiter(SYSTEM_PROMPT_NOTE + "\nВот текст пользователя: " + user_text)  # 🚀 Запрос в AI

import os
from fuzzywuzzy import process
from jupiter import ask_jupiter

NOTES_DIR = "notes"

def update_note(user_text):
    """Находит заметку, отправляет её в AI для дополнения, обновляет файл"""
    if not os.path.exists(NOTES_DIR):
        return "📂 Папка с заметками отсутствует."

    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    if not note_files:
        return "❌ В папке `notes/` нет заметок."

    best_match, score = process.extractOne(user_text, note_files)
    if score < 60:
        return f"⚠ Не удалось найти заметку похожую на '{user_text}'."

    filepath = os.path.join(NOTES_DIR, best_match)
    with open(filepath, "r", encoding="utf-8") as f:
        existing_text = f.read()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_UPDATE_NOTE},
        {"role": "user", "content": f"Дополните эту заметку:\n{existing_text}\n\nЗапрос: {user_text}"}
    ]
    updated_text = ask_jupiter(SYSTEM_PROMPT_UPDATE_NOTE + f"Дополните эту заметку:\n{existing_text}\n\nЗапрос: {user_text}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(updated_text)

    return f"📖 Заметка `{best_match}` обновлена!"


def safe_delete(filepath):
    """Удаляет файл, если он не занят другим процессом"""
    retries = 3
    for _ in range(retries):
        try:
            os.remove(filepath)
            return True
        except PermissionError:
            print(f"⚠ Файл `{filepath}` занят другим процессом. Повторная попытка...")
            time.sleep(1)
    return False

def save_note(user_text):
    """Генерирует заметку, извлекает название, сохраняет в Markdown"""
    os.makedirs(NOTES_DIR, exist_ok=True)

    markdown_text = generate_note(user_text)
    match = re.match(r'Заметка:\s*["\'](.+?)["\']', markdown_text)
    if not match:
        title = "Без_названия"
    else:
        title = match.group(1).strip()
        markdown_text = markdown_text.replace(match.group(0), "").strip()

    filename = f"{title.replace(' ', '_')}.md"
    filepath = os.path.join(NOTES_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_text)

    print(f"✅ Заметка сохранена: {filepath}")
    return f"📂 Заметка успешно сохранена в `notes/{filename}`!"

def summarize_note(note_name: str):
    """Ищет заметку по похожему названию и отправляет её на обработку нейросети"""
    if not os.path.exists(NOTES_DIR):
        return "📂 Папка с заметками отсутствует."

    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    if not note_files:
        return "❌ В папке `notes/` нет заметок."

    best_match, score = process.extractOne(note_name, note_files)
    if score < 60:
        return f"⚠ Не удалось найти заметку похожую на '{note_name}'."

    filepath = os.path.join(NOTES_DIR, best_match)

    with open(filepath, "r", encoding="utf-8") as f:
        note_text = f.read()

    summary_request = SHORT_PROMPT + "\nВот текст заметки:\n" + note_text
    return ask_jupiter(summary_request)

def open_note(user_text):
    """Открывает заметку с ближайшим совпадающим названием"""
    if not os.path.exists(NOTES_DIR):
        return "📂 Папка с заметками отсутствует."

    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    if not note_files:
        return "❌ В папке `notes/` нет заметок."

    best_match, score = process.extractOne(user_text, note_files)
    if score < 60:
        return f"⚠ Не удалось найти заметку похожую на '{user_text}'."

    note_path = os.path.join(NOTES_DIR, best_match)
    subprocess.run(["start", note_path], shell=True)

    return f"📖 Открываю заметку `{best_match}`!"

def list_notes():
    """Выводит список всех заметок с их тегами"""
    if not os.path.exists(NOTES_DIR):
        return "📂 Папка с заметками отсутствует."

    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    if not note_files:
        return "❌ В папке `notes/` нет заметок."

    notes_list = []
    for filename in sorted(note_files):
        filepath = os.path.join(NOTES_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r"Теги:\s*(.+)", content)
            tags = "#" + match.group(1).replace(", ", " #").replace("# ", "#") if match else ""  # 📌 Форматируем теги
        notes_list.append(f"- {filename}\n  {tags}")

    return f"📜 Список заметок:\n" + "\n".join(notes_list)


def delete_notes_by_tag(user_text):
    """Удаляет заметки с указанным тегом, сначала собирая список, затем закрывая файлы и удаляя их"""
    if not os.path.exists(NOTES_DIR):
        return "📂 Папка с заметками отсутствует."

    match = re.search(r"(тегом|с тегом)\s+(.+)", user_text, re.IGNORECASE)
    if not match:
        return "❌ Не удалось определить тег в запросе."

    tag = match.group(2).strip()
    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    to_delete = []

    for filename in note_files:
        filepath = os.path.join(NOTES_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            if re.search(r"Теги:\s*.*?\b" + re.escape(tag) + r"\b", content, re.IGNORECASE):
                to_delete.append(filepath)

    deleted_notes = []
    for filepath in to_delete:
        try:
            os.remove(filepath)
            deleted_notes.append(os.path.basename(filepath))
        except PermissionError:
            return f"❌ Файл `{filepath}` занят другим процессом. Закрой его и попробуй снова."

    if not deleted_notes:
        return f"❌ Не найдено заметок с тегом `{tag}`."

    notes_list = "\n".join(f"- {name}" for name in sorted(deleted_notes))
    return f"🗑 Удалены заметки с тегом `{tag}`:\n{notes_list}"

def delete_note_by_name(user_text):
    """Удаляет заметку по имени (самое близкое совпадение)"""
    if not os.path.exists(NOTES_DIR):
        return "📂 Папка с заметками отсутствует."

    note_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
    if not note_files:
        return "❌ В папке `notes/` нет заметок."

    best_match, score = process.extractOne(user_text, note_files)
    if score < 60:
        return f"⚠ Не удалось найти заметку похожую на '{user_text}'."

    note_path = os.path.join(NOTES_DIR, best_match)
    os.remove(note_path)

    return f"🗑 Заметка `{best_match}` удалена!"