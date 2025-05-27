import sys
import time
import os
import uuid
import ocr # Конспекты
import shutil
import re
import json
import pyautogui
import keyboard
import asyncio
import nest_asyncio
from datetime import datetime
import jupiter
from jupiter import ask_jupiter # Нейросетевой модуль
from unona import WeatherAPI # Погодный модуль
import explorer_control
from explorer_control import * # Управление проводником
import speech_recognition as sr
import pyttsx3
from presentation_api import generate_presentation_pdf # Генератор презентаций
import pygame
from pydub import AudioSegment
from notes import * # Заметочник

from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QHBoxLayout, QLabel, QDesktopWidget
from PyQt5.QtGui import QFont, QPainter, QLinearGradient, QColor, QBrush
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer

# Telegram imports
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import pyautogui
from fuzzywuzzy import process
from news import * # Новостной модуль
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyQt5")

nest_asyncio.apply()

with open('config.json', 'r') as f:
    config = json.load(f)
TELEGRAM_CONFIG = config.get("telegram", {})
TELEGRAM_BOT_TOKEN = TELEGRAM_CONFIG.get("bot_token")
TELEGRAM_USER_ID = TELEGRAM_CONFIG.get("user_id")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

current_date = datetime.now().strftime("%d %B %Y")


class VoiceWorker(QThread):
    recognized = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_listening = True
        self.is_paused = False
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        with self.microphone as src:
            print("Настраиваю микрофон, подождите...")
            self.recognizer.adjust_for_ambient_noise(src, duration=1.0)
            self.recognizer.dynamic_energy_threshold = False
            self.recognizer.energy_threshold = 400
            self.recognizer.pause_threshold = 1.0

    def run(self):
        """Голосовой ввод"""
        with self.microphone as src:
            while self.is_listening:
                if self.is_paused or (
                        hasattr(self, "assistant") and self.assistant.is_generating):
                    time.sleep(0.1)
                    continue
                try:
                    audio = self.recognizer.listen(src, timeout=3)
                    text = self.recognizer.recognize_google(audio, language="ru-RU").lower()
                    if "озвучиваю ответ" in text:
                        continue
                    if text:
                        self.recognized.emit(text)
                except sr.WaitTimeoutError:
                    self.recognized.emit("")
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    print("Ошибка сервиса:", e)
                except Exception as e:
                    print("Ошибка голосового потока:", e)
        self.finished.emit()

    def pause(self):
        """Остановка ввода"""
        print("Пауза...")
        self.is_paused = True

    def resume(self):
        """Возобновление ввода"""
        print("Возобновляю слушать...")
        self.is_paused = False

    def stop(self):
        """Остановка потока"""
        print("Остановка потока...")
        self.is_listening = False
        self.is_paused = False
        self.wait()


class SpeechWorker(QThread):
    finished = pyqtSignal()
    audio_ready = pyqtSignal(str, str)

    def __init__(self, text, filename, temp_filename, app, chat_id=None, assistant=None):
        super().__init__()
        self.text = text
        self.filename = filename
        self.temp_filename = temp_filename
        self.app = app
        self.chat_id = chat_id
        self.assistant = assistant
        self.is_playing = True

    def run(self):
        """Запуск голосового вывода"""
        try:
            if not self.text.strip():
                return

            if self.assistant and self.assistant.worker:
                self.assistant.worker.pause()

            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            rus_voice = None
            for v in voices:
                if "RU" in v.name:
                    rus_voice = v
                    break
            if rus_voice:
                engine.setProperty('voice', rus_voice.id)
            else:
                print("Русский голос не найден, используем стандартный")
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 1.0)

            engine.save_to_file(self.text, self.temp_filename)
            engine.runAndWait()

            aud = AudioSegment.from_wav(self.temp_filename)
            faster_aud = aud.speedup(playback_speed=1.2)
            faster_aud.export(self.filename, format="mp3")
            ogg_file = self.filename.replace(".mp3", ".ogg")
            aud = AudioSegment.from_mp3(self.filename)
            aud.export(ogg_file, format="ogg", codec="libopus")

            pygame.mixer.init()
            pygame.mixer.music.load(self.filename)
            pygame.mixer.music.play()

            if self.chat_id:
                self.audio_ready.emit(ogg_file, self.text)

            while pygame.mixer.music.get_busy() and self.is_playing:
                time.sleep(0.1)

            self.cleanup()
            time.sleep(0.5)
        except Exception as e:
            print("TTS ошибка:", e)
            self.cleanup()
        finally:
            if self.assistant and self.assistant.worker:
                self.assistant.worker.resume()
            self.finished.emit()

    def stop(self):
        self.is_playing = False
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception as e:
            print("Проблема при останове проигрывания:", e)
        self.cleanup()

    def cleanup(self):
        try:
            if os.path.exists(self.filename):
                os.remove(self.filename)
            if os.path.exists(self.temp_filename):
                os.remove(self.temp_filename)
            ogg_file = self.filename.replace(".mp3", ".ogg")
            if os.path.exists(ogg_file):
                os.remove(ogg_file)
        except Exception as e:
            print("Ошибка удаления временных файлов:", e)


class TelegramBot:
    def __init__(self, token, user_id, assistant):
        self.token = token
        self.user_id = user_id
        self.assistant = assistant
        self.application = Application.builder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.Text() & ~filters.Command(), self.handle_message))

    async def start(self, update: Update, context):
        """Действие на /start"""
        if update.effective_user.id != int(self.user_id):
            await update.message.reply_text("❌ Доступ запрещён.")
            return
        await update.message.reply_text(
            "🚀 Юпитер готов! Отправляйте команды типа 'Юпитер, расскажи о Python' или 'Открой проводник'.")

    async def handle_message(self, update: Update, context):
        """Обработка сообщений"""
        if update.effective_user.id != int(self.user_id):
            await update.message.reply_text("❌ Доступ запрещён.")
            return
        txt = update.message.text.lower()
        print("Получил Telegram команду:", txt)
        self.assistant.handle_telegram_command(txt, update.effective_chat.id)

    def run(self):
        """Запуск бота"""
        print("Запускаю Telegram-бота...")
        try:
            asyncio.run(self.application.run_polling())
        except Exception as e:
            print("Ошибка в Telegram-боте:", e)
        finally:
            print("Telegram-бот завершён.")

    def stop(self):
        """Остановка бота"""
        print("Останавливаю Telegram-бота...")
        asyncio.run_coroutine_threadsafe(self.application.stop(), asyncio.get_running_loop())
        asyncio.run_coroutine_threadsafe(self.application.shutdown(), asyncio.get_running_loop())


class TelegramBotThread(QThread):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    def run(self):
        self.bot.run()


class GlassyAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.is_active = False
        self.is_generating = False
        self.worker = None
        self.speech_worker = None
        self.is_talking = False
        self.conversation_history = []

        self.selected_files = []
        self.full_text = ""
        self.message_history = [{
            "role": "system",
            "content": "Ты голосовой ассистент Юпитер. Отвечай коротко и по делу."
        }]

        self.telegram_bot = None
        self.telegram_thread = None

        self.commands = {
            "открой проводник": lambda text: explorer_control.open_explorer(),
            "закрой проводник": lambda text: explorer_control.close_explorer(),
            "открой папку": lambda text: explorer_control.open_folder(text.replace("открой папку ", "")),
            "вернись": lambda text: explorer_control.back(),
            "открой файл": lambda text: explorer_control.open_file(text.replace("открой файл ", "")),
            "вставь текст": lambda text: self._insert_text(text),
            "мышку": lambda text: self._move_cursor(text),
            "курсор": lambda text: self._move_cursor(text),
            "создай презентацию по теме": lambda text: self.dispatch_create_pdf_presentation(text),
            "законспектируй сайт": lambda text: self.run_ocr(),
            "законспектируй статью": lambda text: self.run_ocr(),
            "сделай конспект сайта": lambda text: self.run_ocr(),
            "конспект сайта": lambda text: self.run_ocr(),
            "сохрани конспект": lambda text: self.save_summary(text),
            "закрой окно": lambda text: self.close_active_window(),
            "видишь сайт": lambda text: self.send_current_url_to_telegram(),
            "слушай": lambda text: self.activate_voice(),
            "замолчи": lambda text: self.deactivate_voice(),
            "сколько время": lambda text: self.say_time(),
            "который час": lambda text: self.say_time(),
            "какое сегодня число": lambda text: self.say_date(),
            "какая сегодня дата": lambda text: self.say_date(),
            "чувствительность микрофона": lambda text: self.set_microphone_sensitivity(text),
            "чувствительность микрофона на": lambda text: self.set_microphone_sensitivity(text),
            "запиши заметку": lambda text: save_note(text),
            "открой заметку": lambda text: open_note(text),
            "установи чувствительность": lambda text: self.set_microphone_sensitivity(text),
            "список заметок": lambda text: list_notes(),
            "удали заметки с тегом": lambda text: delete_notes_by_tag(text),
            "дополни заметку": lambda text: update_note(text),
            "удали заметку с названием": lambda text: delete_note_by_name(text),
            "прочитай заметку": lambda text: self.speak(summarize_note(text)),
            "перескажи заметку": lambda text: self.speak(summarize_note(text)),
            "давай поговорим": lambda text: self.enable_talk_mode(),
            "хватит": lambda text: self.disable_talk_mode(),
            "юнона": lambda text: self.summarize_weather_and_traffic(),
            "погода": lambda text: self._handle_weather_request(text),
            "трафик": lambda text: summarize_traffic(),
            "новости": lambda text: self.handle_news_request()
        }

        self.initUI()
        self.button.clicked.connect(self.toggle_voice)
        self.update_button_style()

        self.start_telegram_bot()

    def reset_generating_state(func):
        """Декоратор: автоматически снимает блокировку генерации после выполнения команды"""

        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if hasattr(args[0], "is_generating"):
                args[0].is_generating = False
            return result

        return wrapper

    @reset_generating_state
    def enable_talk_mode(self):
        """Включить разговорный режим"""
        self.is_talking = True
        return "🗣 Разговорный режим включён. Просто спрашивай, я отвечу!"

    @reset_generating_state
    def disable_talk_mode(self):
        """Выключить разговорный режим"""
        self.is_talking = False
        return "🔇 Разговорный режим выключен. Теперь задавай вопросы с 'Юпитер, ...'"

    def pause_worker(self):
        """Приостанавливает голосовой ввод, чтобы избежать конфликтов с озвучкой."""
        if self.worker:
            self.worker.pause()

    @reset_generating_state
    def handle_news_request(user_input):
        """Определяет, какие новости нужны пользователю и вызывает `fetch_news()`."""

        user_input = str(user_input) if user_input else "новости"

        categories = ["спорт", "экономика", "мировые", "технологии", "политика", "культура"]
        selected_category = next((cat for cat in categories if cat in user_input.lower()), "все")

        count_match = re.search(r"(\d+) новост", user_input)
        count = int(count_match.group(1)) if count_match else 5

        city_match = re.search(r"в ([А-Яа-яA-Za-z]+)", user_input)
        city = city_match.group(1) if city_match else None

        return main(topic=selected_category, count=count, city="Новосибирск")

    @reset_generating_state
    def summarize_weather_and_traffic(self):
        """Создаёт объединённую сводку по погоде и трафику"""
        weather_api = WeatherAPI("Novosibirsk")
        traffic_summary = summarize_traffic()
        weather_data = weather_api.get_weather_now()

        prompt = f"""Ты — Юнона, аналитический ассистент. 
        Тебе даны данные о трафике и погоде: 

        🌤 Погода: {weather_data} 
        🚦 Дорожная ситуация: {traffic_summary} 

        Сформулируй единый удобный ответ для пользователя.  
        Определи, как эти факторы влияют друг на друга, 
        предложи рекомендации по одежде и маршруту, но коротко и по делу."""

        full_report = ask_jupiter(prompt)

        self.speak(full_report)

        return full_report

    @reset_generating_state
    def _handle_weather_request(self, text):
        """Определяет, какую функцию погодного модуля вызвать"""
        weather_api = WeatherAPI("Novosibirsk")  # TODO: Можно сделать динасическим
        PROMPT = """Ты - Юнона. Ассистент, специализирующийся на прогнозе погоды. Тебе дается json-код с параметрами погоды. 
            Посоветуй, во что одеться. Предложи чего-нибудь. Но коротко, не расписывая это в поэму, и при этом живо."""

        text = text.lower().strip()
        text = re.sub(r"^(юнона|скажи|расскажи|ответь|погода),?\s*", "", text)  

        if "послезавтра" in text:
            return ask_jupiter(f"{PROMPT}\nДанные о погоде: {weather_api.get_forecast(days_ahead=2)}")
        elif "завтра" in text:
            return ask_jupiter(f"{PROMPT}\nДанные о погоде: {weather_api.get_forecast(days_ahead=1)}")
        elif "выходные" in text or "суббота" in text or "воскресенье" in text:
            return ask_jupiter(f"{PROMPT}\nДанные о погоде: {weather_api.get_weekend_weather()}")

        match = re.search(
            r"(\d{1,2}) (января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)", text,
            re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month_names = {
                "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
                "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
            }
            month = month_names[match.group(2).lower()]
            year = datetime.now().year

            date_str = f"{year}-{month:02d}-{day:02d}"
            return ask_jupiter(f"{PROMPT}\nДанные о погоде: {weather_api.get_specific_date_weather(date_str)}")

        return ask_jupiter(f"{PROMPT}\nДанные о погоде: {weather_api.get_weather_now()}")

    @reset_generating_state
    def set_microphone_sensitivity(self, text):
        """Меняет чувствительность микрофона"""
        match = re.search(r"\d+", text)
        if match:
            sensitivity = int(match.group(0))
            if 100 >= sensitivity >= 1000:
                return "❌ Ошибка: Чувствительность должна быть от 100 до 1000."

            self.worker.recognizer.energy_threshold = sensitivity
            return f"🔊 Чувствительность микрофона установлена на {sensitivity}."
        return "❌ Ошибка: Укажите числовое значение чувствительности!"

    @reset_generating_state
    def say_time(self):
        """Озвучивает текущее время"""
        now = datetime.now().strftime("%H:%M")
        return f"⏰ Сейчас {now}"

    @reset_generating_state
    def say_date(self):
        """Озвучивает сегодняшнюю дату"""
        today = datetime.now().strftime("%d %B %Y")
        return f"📅 Сегодня {today}"

    @reset_generating_state
    def _press_key(self, text):
        """Нажимает указанную клавишу."""
        key = text.replace("нажми клавишу", "").strip()
        key_mapping = {"энтер": "enter", "контрол": "ctrl", "шифт": "shift", "альт": "alt", "пробел": "space"} # TODO: Сделать полную поддержку клавиатуры
        key = key_mapping.get(key, key)

        try:
            pyautogui.press(key)
            return f" Нажата клавиша {key}."
        except Exception as e:
            print(f"❌ Ошибка нажатия клавиши: {e}")
            return f" Не удалось нажать {key}."

    @reset_generating_state
    def close_active_window(self):
        """Закрывает текущее активное окно"""
        try:
            pyautogui.hotkey("alt", "f4")
            return "Озвучиваю: Окно закрыто!"
        except Exception as e:
            print(f"❌ Ошибка закрытия окна: {e}")
            return "Озвучиваю: Не удалось закрыть окно!"

    @reset_generating_state
    def activate_voice(self):
        """Активирует голосовой ввод"""
        if not self.is_active:
            self.is_active = True
            self.full_text = ""
            self.text_label.setText("Слушаю...")
            self.update_button_style()
            self.start_worker()
            return "🚀 Голосовой ввод активирован!"
        return "🔊 Уже слушаю!"

    @reset_generating_state
    def deactivate_voice(self):
        """Отключает голосовой ввод"""
        if self.is_active:
            self.is_active = False
            self.text_label.setText("Остановлено")
            self.update_button_style()
            self.cleanup_worker()
            self.stop_speech()
            QTimer.singleShot(1000, lambda: self.text_label.setText("Нажми кнопку"))
            return "🤐 Голосовой ввод выключен!"
        return "🔇 Уже молчу!"

    @reset_generating_state
    def send_current_url_to_telegram(self):
        """Отправляет текущий URL в Telegram"""
        file_path = "url.txt"

        if not os.path.exists(file_path):
            return "Озвучиваю: Не удалось найти текущий URL."

        with open(file_path, "r", encoding="utf-8") as f:
            current_url = f.read().strip()

        response = f"👀 Сейчас я вижу сайт: {current_url}"

        if self.telegram_bot:
            if not hasattr(self, "last_sent_url") or self.last_sent_url != current_url:
                self.last_sent_url = current_url
                asyncio.run_coroutine_threadsafe(
                    self.telegram_bot.application.bot.send_message(chat_id=TELEGRAM_USER_ID, text=response),
                    asyncio.get_event_loop()
                )

        return response

    def _hold_key(self, text):
        """Зажимает указанную клавишу."""
        key = text.replace("зажми клавишу", "").strip()
        key_mapping = {"энтер": "enter", "контрол": "ctrl", "шифт": "shift", "альт": "alt", "пробел": "space"} # TODO: Сделать полную поддержку клавиатуры
        key = key_mapping.get(key, key)

        try:
            keyboard.press(key)
            return f" Зажата клавиша {key}."
        except Exception as e:
            print(f"❌ Ошибка зажатия клавиши: {e}")
            return f" Не удалось зажать {key}."

    def on_speech_finished(self):
        """Слушать после завершения голосового вывода"""
        self.is_generating = False
        if self.is_active and self.worker:
            self.worker.resume()
            self.text_label.setText("Слушаю...")

    def speak(self, text):
        """Голосовой вывод"""
        if not text.strip():
            return

        self.is_generating = True
        QTimer.singleShot(50, self.pause_worker)

        temp_dir = os.path.join(os.getenv("TEMP") or os.getcwd(), "tts_cache")
        os.makedirs(temp_dir, exist_ok=True)

        fname = os.path.join(temp_dir, f"{uuid.uuid4()}.mp3")
        temp_fname = os.path.join(temp_dir, f"{uuid.uuid4()}_temp.wav")

        self.speech_worker = SpeechWorker(text, fname, temp_fname, QApplication.instance(), assistant=self)
        self.speech_worker.finished.connect(self.on_speech_finished)
        self.speech_worker.start()

    @reset_generating_state
    def save_summary(self, user_input):
        """Сохраняет конспект в указанную папку внутри `summary/`, или в 'Несортированные' по умолчанию"""
        base_dir = "summary"

        match = re.search(r"сохрани конспект в (.+)", user_input, re.IGNORECASE)
        if match:
            folder_name = match.group(1).strip()
            if not folder_name:
                return "❌ Ошибка: Название папки не может быть пустым!"
        else:
            folder_name = "Несортированные"

        target_folder = os.path.join(base_dir, folder_name)
        os.makedirs(target_folder, exist_ok=True)

        debug_file = "debug.md"
        if not os.path.exists(debug_file):
            return "❌ Ошибка: Файл `debug.md` не найден!"

        with open(debug_file, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()

        match = re.match(r"#\s*(.+)", first_line)
        if not match:
            return "❌ Ошибка: Не удалось извлечь заголовок!"

        filename = match.group(1).strip().replace(" ", "_") + ".md"
        target_path = os.path.join(target_folder, filename)

        shutil.copy(debug_file, target_path)
        return f"✅ Конспект сохранён в `{target_path}`"

    def _release_key(self, text):
        """Отпускает зажатую клавишу."""
        key = text.replace("отпусти клавишу", "").strip()
        key_mapping = {"энтер": "enter", "контрол": "ctrl", "шифт": "shift", "альт": "alt", "пробел": "space"} # TODO: Добавить полную поддержку клавиатуры
        key = key_mapping.get(key, key)

        try:
            keyboard.release(key)
            return f" Клавиша {key} отпущена."
        except Exception as e:
            print(f"❌ Ошибка освобождения клавиши: {e}")
            return f" Не удалось отпустить {key}."

    def _click_mouse(self, text):
        """Нажимает левую или правую кнопку мыши."""
        button = "left" if "левую" in text else "right" if "правую" in text else "left"

        try:
            pyautogui.click(button=button)
            return f" Нажата {button} кнопка мыши."
        except Exception as e:
            print(f"❌ Ошибка нажатия кнопки мыши: {e}")
            return f" Не удалось нажать {button} кнопку."

    @reset_generating_state
    def _move_cursor(self, text):
        """Перемещает курсор на заданное количество пикселей."""
        dx, dy = 0, 0

        match = re.search(r'на (\d+) пиксел', text)
        pixels = int(match.group(1)) if match else 100

        if "вправо" in text:
            dx = pixels
        elif "влево" in text:
            dx = -pixels
        elif "вверх" in text:
            dy = -pixels
        elif "вниз" in text:
            dy = pixels

        try:
            pyautogui.moveRel(dx, dy)
            return f"Курсор перемещён на {pixels} пикселей."
        except Exception as e:
            print(f"❌ Ошибка перемещения курсора: {e}")
            return "Не удалось переместить курсор."

    @reset_generating_state
    def _press_combination(self, text):
        """Нажимает комбинацию клавиш, например: 'нажми комбинацию Ctrl+Shift+Esc'."""
        keys = text.replace("нажми комбинацию", "").strip()
        key_list = [key.strip() for key in keys.split("+")]

        try:
            pyautogui.hotkey(*key_list)
            return f"Комбинация клавиш {' + '.join(key_list)} нажата."
        except Exception as e:
            print(f"❌ Ошибка нажатия комбинации клавиш: {e}")
            return "Не удалось выполнить комбинацию."

    def _scroll_mouse(self, direction):
        """Выполняет скроллирование вверх или вниз."""
        amount = -100 if direction == "up" else 100
        try:
            pyautogui.scroll(amount)
            return f" Скролл выполнен {direction}."
        except Exception as e:
            print(f"❌ Ошибка скроллирования: {e}")
            return f" Не удалось выполнить скролл {direction}."

    @reset_generating_state
    def _select_files_by_name(self, text):
        """Выбирает один или несколько файлов по имени"""
        file_list = text.replace("выбери файл", "").replace("выбери файлы", "").strip()
        if file_list:
            filenames = [name.strip() for name in file_list.split(",")]
            self.selected_files = self.explorer.select_files_by_name(filenames)
            return f"Озвучиваю: Выбраны файлы: {', '.join(self.selected_files) or 'ничего не выбрано'}."
        return "Озвучиваю: Укажите имя файла или несколько файлов через запятую."

    @reset_generating_state
    def run_ocr(self):
        """Запускает конспект сайта или книги"""
        try:
            ocr.main()
            return "Озвучиваю: Конспектирование начато!"
        except Exception as e:
            return f"❌ Ошибка вызова `ocr.py`: {e}"

    @reset_generating_state
    def dispatch_create_pdf_presentation(self, text):
        """Создаёт презентацию"""
        import re
        match = re.search(r"создай презентацию по теме\s+(.+?)\s+на\s+(\d+)\s*лист", text, re.IGNORECASE)
        if match:
            theme = match.group(1).strip()
            num_slides = int(match.group(2))
            try:
                pdf_path = generate_presentation_pdf(theme, num_slides)
                response = f"Озвучиваю: Презентация создана, файл сохранен: {pdf_path}"
            except Exception as e:
                response = f"Озвучиваю: Ошибка создания презентации: {e}"
        else:
            response = ("Озвучиваю: Неверный формат команды. Пример: "
                        "'Создай презентацию по теме искусственный интеллект на 5 листов'")
        return response

    def handle_telegram_command(self, text, chat_id):
        self.handle_command(text, chat_id)

    def initUI(self):
        """Создаёт интерфейс"""
        self.setFixedSize(600, 60)
        self.setWindowTitle('Голосовой помощник')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen = QDesktopWidget().screenGeometry()
        x = (screen.width() - self.width()) // 2
        self.move(x, 0)

        layout = QHBoxLayout()
        layout.setContentsMargins(20, 0, 15, 0)
        layout.setSpacing(10)

        self.text_label = QLabel("Нажми кнопку", self)
        self.text_label.setFont(QFont("Segoe UI", 12))
        self.text_label.setStyleSheet("""
            color: white;
            background-color: transparent;
        """)
        layout.addWidget(self.text_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        layout.addStretch()

        self.button = QPushButton()
        self.button.setFixedSize(34, 34)
        layout.addWidget(self.button)

        self.setLayout(layout)

    def update_button_style(self):
        """Меняет цвет кнопки"""
        clr = "#FF4C4C" if self.is_active else "#007BFF"
        self.button.setStyleSheet(f"background-color: {clr}; border-radius: 17px; border: none;")

    def toggle_voice(self):
        """Вкл/выкл голосовой ввод"""
        if not self.is_active:
            self.is_active = True
            self.full_text = ""
            self.text_label.setText("Слушаю...")
            self.update_button_style()
            self.start_worker()
        else:
            self.is_active = False
            self.text_label.setText("Остановлено")
            self.update_button_style()

            print("⏳ Завершаю все выполняющиеся процессы...")
            self.cleanup_worker()

            self.stop_speech()
            QTimer.singleShot(1000, lambda: self.text_label.setText("Нажми кнопку"))

    def start_worker(self):
        """Запуск голосового ввода"""
        self.worker = VoiceWorker()
        self.worker.recognized.connect(self.handle_command)
        self.worker.finished.connect(self.restart_worker)
        self.worker.start()

    def start_telegram_bot(self):
        """Запуск телеграм-бота"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
            print("Телеграм токен или ID отсутствуют! Бот не запускается.")
            return
        print("Запускаю Telegram-бота с токеном: " + TELEGRAM_BOT_TOKEN[:5] + "...")
        self.telegram_bot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, self)
        self.telegram_thread = TelegramBotThread(self.telegram_bot)
        self.telegram_thread.start()
        print("Telegram-бот запущен!")

    def stop_telegram_bot(self):
        """Остановка тг-бота"""
        if self.telegram_bot and self.telegram_thread:
            self.telegram_bot.stop()
            self.telegram_thread.wait(5000)
            self.telegram_bot = None
            self.telegram_thread = None
            print("Телеграм бот остановлен!")

    def ask_ai_directly(self, text):
        """Разговорный режим"""
        CONVERSATION_PROMPT = (
            "Ты — голосовой ассистент, ведущий непринуждённый разговор. "
            "Отвечай кратко и дружелюбно, избегая сухих объяснений. "
            "Не используй формулы, программный код или технические термины. "
            "Если объясняешь что-то сложное, делай это простыми словами, как если бы рассказывал другу. "
            "Формат ответа должен быть естественным, в стиле обычной беседы. "
            "Если пользователь спрашивает что-то, не отвечай слишком длинно — лучше коротко и понятно."
        )

        if not self.is_talking:
            return ask_jupiter(text)

        self.conversation_history.append(text)

        MAX_HISTORY = 5
        if len(self.conversation_history) > MAX_HISTORY:
            self.conversation_history.pop(0)

        context = "\n".join(self.conversation_history)
        prompt = CONVERSATION_PROMPT + f"\nВот предыдущий контекст:\n{context}\nОтветь на новый вопрос:\n{text}"

        response = ask_jupiter(prompt)

        self.conversation_history.append(response)

        self.speak(response)

        return response

    def _select_all_files(self):
        """Выбрать все файлы"""
        try:
            self.selected_files = self.explorer.select_all_files()
            if self.selected_files:
                return "Озвучиваю: Выбраны файлы: " + ", ".join(self.selected_files)
            else:
                return "Озвучиваю: Файлы не найдены."
        except Exception as ex:
            print("Ошибка при выборе файлов:", ex)
            return "Озвучиваю: Ошибка выбора файлов."

    def handle_command(self, text, chat_id=None):
        """Обработчик команд"""
        start = time.time()
        print("Получена команда:", text)

        if self.is_generating:
            print("Другая команда выполняется, жди!")
            if chat_id and self.telegram_bot:
                asyncio.run_coroutine_threadsafe(
                    self.telegram_bot.application.bot.send_message(chat_id=chat_id, text="⏳ Пожалуйста, подождите..."),
                    asyncio.get_event_loop()
                )
            return

        self.is_generating = True
        self.text_label.setText("Генерирую ответ...")

        if self.worker:
            self.worker.pause()

        QApplication.processEvents()

        if not text:
            response = "Ничего не услышал, повтори."
        else:
            text = text.strip()

            if self.is_talking and text.lower() not in ["замолчи", "слушай", "хватит"]:
                response = self.ask_ai_directly(text)
            else:
                is_ai_query = text.lower().startswith("юпитер")
                if is_ai_query:
                    text = re.sub(r'^юпитер,?\s*', '', text)

                if is_ai_query or "юпитер" in text.lower():
                    self.message_history.append({"role": "user", "content": text})
                    response = ask_jupiter(text, self.explorer)
                    self.message_history.append({"role": "assistant", "content": response})
                else:
                    best_match, score = process.extractOne(text[:40], list(self.commands.keys()))
                    print(f"Лучшее совпадение: '{best_match}' с score: {score}")

                    response = self.commands[best_match](text) if score > 70 else ""


        print("Ответ:", response)

        if chat_id and self.telegram_bot:
            asyncio.run_coroutine_threadsafe(
                self.telegram_bot.application.bot.send_message(chat_id=chat_id, text=response),
                asyncio.get_event_loop()
            )

        self.full_text += " " + response
        final_text = "🔹 " + self.full_text.strip()

        self.is_generating = False
        if self.is_active and self.worker:
            self.worker.resume()
            self.text_label.setText("Слушаю...")

        print("Время обработки команды: {:.2f} сек".format(time.time() - start))

    def split_text(self, text):
        parts = text.split('. ')
        return [p + ('.' if not p.endswith('.') else '') for p in parts if p]

    def send_audio_to_telegram(self, ogg_filename, text, chat_id):
        if not self.telegram_bot:
            print("Telegram-бот не запущен, аудио не отправлю.")
            return
        try:
            if os.path.exists(ogg_filename):
                with open(ogg_filename, 'rb') as audio:
                    asyncio.run_coroutine_threadsafe(
                        self.telegram_bot.application.bot.send_voice(chat_id=chat_id, voice=audio, caption=text[:200]),
                        asyncio.get_event_loop()
                    )
            else:
                print("⚠️ OGG-файл не найден:", ogg_filename)
        except Exception as e:
            print("Ошибка отправки аудио в Telegram:", e)

    def on_speech_finished(self):
        """Когда голосовой вывод завершен, перейти к прослушиванию"""
        self.is_generating = False
        if self.is_active and self.worker:
            self.worker.resume()
            self.text_label.setText("Слушаю...")
        self.speech_worker = None

    def stop_speech(self):
        """Остановка голосового вывода"""
        if self.speech_worker and self.speech_worker.isRunning():
            self.speech_worker.stop()
            self.speech_worker.wait()
            self.speech_worker = None

        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception as e:
            print(f"⚠ Ошибка при остановке музыки: {e}")

    def cleanup_worker(self):
        """Корректно завершает все процессы перед выключением голосового ввода"""
        self.stop_speech()

        if self.worker and self.worker.isRunning():
            print("⏳ Принудительно останавливаю `VoiceWorker`...")
            self.worker.terminate()
            self.worker.wait()
            self.worker = None

    def restart_worker(self):
        """Перезапуск голосового ввода"""
        if self.is_active:
            QTimer.singleShot(500, self.start_worker)

    def paintEvent(self, event):
        """Окраска фона приложения"""
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, self.height(), self.width(), 0)
        grad.setColorAt(0, QColor(255, 255, 255, 30))
        grad.setColorAt(1, QColor(240, 240, 240, 180))
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(grad))
        qp.drawRoundedRect(self.rect(), 20, 20)

    def mousePressEvent(self, event):
        """Ивент на нажатие кнопки"""
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Перемещение окна мышью"""
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_pos'):
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def closeEvent(self, event):
        """Закрытие приложения"""
        self.cleanup_worker()
        self.stop_telegram_bot()
        event.accept()


if __name__ == '__main__':
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('myappid')
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseSoftwareOpenGL, False)
    win = GlassyAssistant()
    win.show()
    sys.exit(app.exec_())
