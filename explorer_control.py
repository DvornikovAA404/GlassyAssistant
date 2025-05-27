import win32gui
import win32con
import subprocess
import time
import os
from transliterate import translit
import difflib

path = "C:\\"
_explorer_hwnd = None

SYSTEM_FOLDERS = {'$Recycle.Bin', 'System Volume Information', '$SysReset', 'Config.Msi', 'PerfLogs', 'Recovery'}

TRANSLATIONS = {
    "Documents": "Документы",
    "Downloads": "Загрузки",
    "Music": "Музыка",
    "Pictures": "Изображения",
    "Videos": "Видео",
    "Desktop": "Рабочий стол",
    "Users": "Пользователи",
    "Program Files": "Программы",
    "Windows": "Виндовс",
    "Документы": "Documents",
    "Загрузки": "Downloads",
    "Музыка": "Music",
    "Изображения": "Pictures",
    "Видео": "Videos",
    "Рабочий стол": "Desktop",
    "Пользователи": "Users",
    "Программы": "Program Files",
    "Виндовс": "Windows"
}

def open_explorer(target_path="C:\\"):
    """
    Открывает проводник Windows в указанном пути и сохраняет дескриптор окна.
    """
    global path, _explorer_hwnd
    try:
        target_path = os.path.normpath(target_path)
        if not os.path.isdir(target_path):
            return f"Ошибка: Путь '{target_path}' не существует"

        if _explorer_hwnd and win32gui.IsWindow(_explorer_hwnd):
            win32gui.PostMessage(_explorer_hwnd, win32con.WM_CLOSE, 0, 0)
            _explorer_hwnd = None
            time.sleep(1)

        subprocess.run(["explorer", target_path])
        time.sleep(5)

        def enum_windows_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                class_name = win32gui.GetClassName(hwnd)
                if class_name in ["CabinetWClass", "ExplorerWClass"]:
                    windows.append(hwnd)

        windows = []
        win32gui.EnumWindows(enum_windows_callback, windows)

        if windows:
            _explorer_hwnd = windows[0]
            path = target_path
            return f"Открыл проводник. Текущая папка {path}"
        else:
            return "Ошибка: Окно проводника не найдено"

    except Exception as e:
        return f"Ошибка: {str(e)}"

def open_folder(folder):
    """
    Открывает папку в проводнике Windows, находя максимально похожую по имени (включая транслитерацию, перевод и частичное совпадение).
    Если папка найдена, закрывает текущее окно проводника, открывает новое и обновляет path.
    """
    global path, _explorer_hwnd
    try:
        folders = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f)) and f not in SYSTEM_FOLDERS]
        if not folders:
            return f"Ошибка: В '{path}' нет доступных папок"

        folder_lower = folder.lower()
        translit_folder = translit(folder, 'ru', reversed=True).lower()
        translated_folder = TRANSLATIONS.get(folder, folder).lower()
        translated_translit = TRANSLATIONS.get(translit_folder, translit_folder).lower()

        candidates = []
        for f in folders:
            f_lower = f.lower()
            translit_f = translit(f, 'ru', reversed=True).lower()
            candidates.extend([f_lower, translit_f])
            if f in TRANSLATIONS:
                candidates.append(TRANSLATIONS[f].lower())
            if translit_f in TRANSLATIONS:
                candidates.append(TRANSLATIONS[translit_f].lower())

        matches = difflib.get_close_matches(folder_lower, candidates, n=1, cutoff=0.6) + \
                  difflib.get_close_matches(translit_folder, candidates, n=1, cutoff=0.6) + \
                  difflib.get_close_matches(translated_folder, candidates, n=1, cutoff=0.6) + \
                  difflib.get_close_matches(translated_translit, candidates, n=1, cutoff=0.6)

        partial_matches = []
        for f in folders:
            f_lower = f.lower()
            translit_f = translit(f, 'ru', reversed=True).lower()
            translated_f = TRANSLATIONS.get(f, f).lower()
            translated_translit_f = TRANSLATIONS.get(translit_f, translit_f).lower()
            if (folder_lower in f_lower or translit_folder in f_lower or
                translated_folder in f_lower or translated_translit in f_lower or
                folder_lower in translit_f or translit_folder in translit_f or
                translated_folder in translit_f or translated_translit in translit_f or
                folder_lower in translated_f or translit_folder in translated_f or
                translated_folder in translated_f or translated_translit in translated_f or
                folder_lower in translated_translit_f or translit_folder in translated_translit_f or
                translated_folder in translated_translit_f or translated_translit in translated_translit_f):
                partial_matches.append(f)

        if not matches and not partial_matches:
            return f"Ошибка: Папка '{folder}' не найдена в '{path}'"

        match = partial_matches[0] if partial_matches else matches[0]
        for f in folders:
            f_lower = f.lower()
            translit_f = translit(f, 'ru', reversed=True).lower()
            translated_f = TRANSLATIONS.get(f, f).lower()
            translated_translit_f = TRANSLATIONS.get(translit_f, translit_f).lower()
            if match.lower() in [f_lower, translit_f.lower(), translated_f.lower(), translated_translit_f.lower()]:
                match = f
                break

        target_path = os.path.normpath(os.path.join(path, match))

        if _explorer_hwnd and win32gui.IsWindowVisible(_explorer_hwnd):
            win32gui.PostMessage(_explorer_hwnd, win32con.WM_CLOSE, 0, 0)
            _explorer_hwnd = None
            time.sleep(1)

        subprocess.run(["explorer", target_path])
        time.sleep(5)

        def enum_windows():
            windows = []
            def callback(hwnd, data):
                if win32gui.IsWindowVisible(hwnd):
                    class_name = win32gui.GetClassName(hwnd)
                    if class_name in ["CabinetWClass", "ExplorerWClass"]:
                        windows.append(hwnd)
            win32gui.EnumWindows(callback, None)
            return windows

        windows = enum_windows()
        if windows:
            _explorer_hwnd = windows[0]
            path = target_path
            return f"Открыл проводник. Текущая папка {path}"
        else:
            return "Ошибка: Окно проводника не найдено"

    except Exception as e:
        return f"Ошибка: {str(e)}"

def close_explorer():
    """
    Закрывает окно проводника, используя сохраненный дескриптор.
    """
    global _explorer_hwnd
    try:
        if _explorer_hwnd and win32gui.IsWindow(_explorer_hwnd):
            win32gui.PostMessage(_explorer_hwnd, win32con.WM_CLOSE, 0, 0)
            _explorer_hwnd = None
            return "Закрыл проводник"
        else:
            return "Ошибка: Окно не открыто или дескриптор недействителен"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def back():
    """
    Возвращается в родительскую папку относительно текущего пути.
    Закрывает текущее окно проводника, открывает новое в родительской папке и обновляет path.
    """
    global path, _explorer_hwnd
    try:
        parent_path = os.path.normpath(os.path.dirname(path))
        if parent_path == path:
            return f"Ошибка: '{path}' - корень диска, нет родительской папки"

        if _explorer_hwnd and win32gui.IsWindow(_explorer_hwnd):
            win32gui.PostMessage(_explorer_hwnd, win32con.WM_CLOSE, 0, 0)
            _explorer_hwnd = None
            time.sleep(1)

        subprocess.run(["explorer", parent_path])
        time.sleep(5)

        def enum_windows_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                class_name = win32gui.GetClassName(hwnd)
                if class_name in ["CabinetWClass", "ExplorerWClass"]:
                    windows.append(hwnd)

        windows = []
        win32gui.EnumWindows(enum_windows_callback, windows)

        if windows:
            _explorer_hwnd = windows[0]
            path = parent_path
            return f"Открыл проводник. Текущая папка {path}"
        else:
            return "Ошибка: Окно проводника не найдено"

    except Exception as e:
        return f"Ошибка: {str(e)}"

def open_file(filename):
    """
    Открывает файл в текущей папке, находя максимально похожий по имени (включая транслитерацию, перевод и частичное совпадение).
    """
    try:
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        if not files:
            return f"Ошибка: В '{path}' нет доступных файлов"

        filename_lower = filename.lower()
        translit_filename = translit(filename, 'ru', reversed=True).lower()
        translated_filename = TRANSLATIONS.get(filename, filename).lower()
        translated_translit = TRANSLATIONS.get(translit_filename, translit_filename).lower()

        candidates = []
        for f in files:
            f_lower = f.lower()
            translit_f = translit(f, 'ru', reversed=True).lower()
            candidates.extend([f_lower, translit_f])
            if f in TRANSLATIONS:
                candidates.append(TRANSLATIONS[f].lower())
            if translit_f in TRANSLATIONS:
                candidates.append(TRANSLATIONS[translit_f].lower())

        matches = difflib.get_close_matches(filename_lower, candidates, n=1, cutoff=0.6) + \
                  difflib.get_close_matches(translit_filename, candidates, n=1, cutoff=0.6) + \
                  difflib.get_close_matches(translated_filename, candidates, n=1, cutoff=0.6) + \
                  difflib.get_close_matches(translated_translit, candidates, n=1, cutoff=0.6)

        partial_matches = []
        for f in files:
            f_lower = f.lower()
            translit_f = translit(f, 'ru', reversed=True).lower()
            translated_f = TRANSLATIONS.get(f, f).lower()
            translated_translit_f = TRANSLATIONS.get(translit_f, translit_f).lower()
            if (filename_lower in f_lower or translit_filename in f_lower or
                translated_filename in f_lower or translated_translit in f_lower or
                filename_lower in translit_f or translit_filename in translit_f or
                translated_filename in translit_f or translated_translit in translit_f or
                filename_lower in translated_f or translit_filename in translated_f or
                translated_filename in translated_f or translated_translit in translated_f or
                filename_lower in translated_translit_f or translit_filename in translated_translit_f or
                translated_filename in translated_translit_f or translated_translit in translated_translit_f):
                partial_matches.append(f)

        if not matches and not partial_matches:
            return f"Ошибка: Файл '{filename}' не найден в '{path}'"

        match = partial_matches[0] if partial_matches else matches[0]
        for f in files:
            f_lower = f.lower()
            translit_f = translit(f, 'ru', reversed=True).lower()
            translated_f = TRANSLATIONS.get(f, f).lower()
            translated_translit_f = TRANSLATIONS.get(translit_f, translit_f).lower()
            if match.lower() in [f_lower, translit_f.lower(), translated_f.lower(), translated_translit_f.lower()]:
                match = f
                break

        target_file = os.path.join(path, match)
        os.startfile(target_file)
        return f"Открыл файл {match}"

    except Exception as e:
        return f"Ошибка: {str(e)}"