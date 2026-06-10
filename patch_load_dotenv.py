import os

with open("src/pptx_generator.py", "r", encoding="utf-8") as f:
    code = f.read()

old_func_start = """def translate_to_russian_via_gemini(text: str) -> str:
    \"\"\"Проверяет наличие английских слов в тексте и переводит его на русский язык через Gemini API.
    
    Для обучения:
    - re.search(r'[a-zA-Z]') — регулярное выражение для поиска латинских букв в тексте.
    - В ООП мы используем genai.Client() для создания объекта-клиента и выполнения API-методов.
    \"\"\"
    import re
    import os
    if not text or not re.search(r'[a-zA-Z]', text):"""

new_func_start = """def translate_to_russian_via_gemini(text: str) -> str:
    \"\"\"Проверяет наличие английских слов в тексте и переводит его на русский язык через Gemini API.
    
    Для обучения:
    - re.search(r'[a-zA-Z]') — регулярное выражение для поиска латинских букв в тексте.
    - В ООП мы используем genai.Client() для создания объекта-клиента и выполнения API-методов.
    \"\"\"
    import re
    import os
    from dotenv import load_dotenv
    load_dotenv() # Загружаем ключи из .env для корректной авторизации API
    if not text or not re.search(r'[a-zA-Z]', text):"""

if old_func_start in code:
    code = code.replace(old_func_start, new_func_start)
    with open("src/pptx_generator.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("Successfully added load_dotenv to translation function.")
else:
    print("Error: Could not locate function start in pptx_generator.py")
