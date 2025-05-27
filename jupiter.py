import g4f
from g4f.Provider import *
from fuzzywuzzy import process
from transliterate import translit
import os
import re
import inspect

SYSTEM_PROMPT = (
    "Ты голосовой ассистент Юпитер. Отвечай на русском языке, коротко и по делу. Старайся достаточно живо рассказать тему. "
    "Если спрашивают, кто ты такой, отвечай, что ты Юпитер - голосовой помощник и кратенько, то, что ты можешь. "
    "Поддерживай команды для работы с проводником Windows: "
    "'открой проводник', 'открой диск D', 'открой папку <имя>', "
    "'перейди к <путь>', 'открой файл <имя>', 'открой случайный файл', "
    "'выбери все', 'выбери <число> файлов', 'выбери файлы <имя1, имя2>', "
    "'копировать', 'вырезать', 'вставить', 'назад', 'вернись'. "
    "Если название папки или файла не совпадает точно, используй ближайшее по звучанию, учитывая возможный транслит (например, 'Корабли' → 'Korabli'). "
    "Не добавляй лишнего. Не используй смайлики, IP-адреса или китайские символы в ответах."
)


def ask_jupiter(user_text: str, explorer_controller=None) -> str:
    """Запрос нейросети"""
    if isinstance(user_text, list):
        user_text = " ".join(user_text)
    user_text = user_text.replace("юпитер", "").strip()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]

    providers = []
    excluded_providers = {
        'ARTA',
        'StableDiffusion',
        'Dalle',
        'ImageGen',
    }

    for name, obj in inspect.getmembers(g4f.Provider):
        if (inspect.isclass(obj) and
                name not in ['BaseProvider', 'AsyncProvider'] and
                not name.startswith('_') and
                name not in excluded_providers):
            providers.append(obj)

    print(f"ℹ️ Найдено {len(providers)} провайдеров для перебора: {[provider.__name__ for provider in providers]}")

    response = None
    for provider in providers:
        try:
            result = g4f.ChatCompletion.create(
                model=g4f.models.default,
                provider=provider,
                messages=messages
            )
            if isinstance(result, str):
                response = result
                print(f"✅ Успешно получен текстовый ответ от провайдера {provider.__name__}: {response}")
                break
            else:
                print(
                    f"⚠️ Провайдер {provider.__name__} вернул не текстовый результат (например, изображение), пропускаем.")
                continue
        except Exception as e:
            print(f"⚠️ Ошибка провайдера {provider.__name__}: {e}")
            continue

    if response is None:
        print("❌ Все провайдеры недоступны или не вернули текст.")
        return "Ошибка генерации ответа: все провайдеры недоступны или не вернули текст. Попробуйте позже."

    response = re.sub(r'[\u4e00-\u9fff]', '', response)
    response = re.sub(r'[\U0001F600-\U0001F64F]', '', response)
    response = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '', response)
    response = response.strip()
    if not response:
        response = "Не удалось сгенерировать ответ."

    if explorer_controller and ("открой папку" in user_text or "открой файл" in user_text):
        current_path = explorer_controller.get_current_path()
        if current_path:
            folders_files = os.listdir(current_path)
            name = user_text.replace("открой папку", "").replace("открой файл", "").strip()
            if name and folders_files:
                translit_name = translit(name, 'en', reversed=True)
                best_match, score = process.extractOne(translit_name, folders_files)
                if score > 60:
                    response = response.replace(name, best_match)
                else:
                    best_match, score = process.extractOne(name, folders_files)
                    if score > 50:
                        response = response.replace(name, best_match)

    return response