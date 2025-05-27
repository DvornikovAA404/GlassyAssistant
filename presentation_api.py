import os
import subprocess
import tempfile
import shutil

from jupiter import ask_jupiter  # Нейросетевой модуль


def generate_presentation_pdf(theme: str, num_slides: int, output_pdf: str = None) -> str:
    """
    Генерирует презентацию по заданной теме на указанное число листов.
    """
    prompt = (
        f"Создай презентацию по теме \"{theme}\" на {num_slides} листов. "
        "Каждый лист должен начинаться с заголовка, оформленного через \\section{}, "
        "затем следует краткий список ключевых пунктов с использованием \\begin{itemize} "
        "\\item ... \\end{itemize} и абзац подробного описания. "
        "Выдай полный корректный LaTeX-код (с преамбулой и окружением \\begin{document} ... \\end{document}), "
        "который можно сразу скомпилировать в PDF."
    )
    print("Отправляю промпт в jupiter:\n", prompt)

    latex_code = ask_jupiter(prompt)
    latex_code = ask_jupiter(prompt)
    latex_code = latex_code.replace("```latex", "").replace("```", "").strip()
    if not latex_code or "documentclass" not in latex_code:
        err_msg = "Полученный LaTeX-код некорректен. Убедись, что функция ask_jupiter корректно генерирует код."
        print(err_msg)
        raise ValueError(err_msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = os.path.join(tmpdir, "presentation.tex")
        pdf_file = os.path.join(tmpdir, "presentation.pdf")

        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(latex_code)
        print(f"Сохранен LaTeX-код в файл: {tex_file}")

        cmd = ["pdflatex", "-interaction=nonstopmode", tex_file]
        try:
            print("Компиляция первого раза...")
            subprocess.run(cmd, cwd=tmpdir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("Компиляция второго раза...")
            subprocess.run(cmd, cwd=tmpdir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print("Ошибка компиляции LaTeX:")
            print(e.stdout.decode("utf-8", errors="ignore"))
            print(e.stderr.decode("utf-8", errors="ignore"))
            raise e

        if output_pdf:
            result_pdf = output_pdf
        else:
            safe_theme = theme.replace(" ", "_")
            result_pdf = os.path.join(os.getcwd(), f"pdf_presentations/{safe_theme}_presentation.pdf")

        shutil.copy(pdf_file, result_pdf)
        print("PDF успешно создан:", result_pdf)

    return result_pdf


if __name__ == "__main__":
    try:
        pdf_path = generate_presentation_pdf("Искусственный интеллект", 5)
        print("Сгенерированный PDF находится по пути:", pdf_path)
    except Exception as ex:
        print("Произошла ошибка при генерации презентации:", ex)
