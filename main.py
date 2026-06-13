import os
import sys
import shutil
import warnings
# Совместимость с Python 3.13: устраняем баг CrewAI/Pydantic с фильтром предупреждений
_orig_warn = warnings.warn
def _safe_warn(message, category=None, stacklevel=1, source=None, *args, **kwargs):
    kwargs.pop('skip_file_prefixes', None)
    try:
        return _orig_warn(message, category, stacklevel, source, *args, **kwargs)
    except Exception:
        return None
warnings.warn = _safe_warn



# Убедимся, что кодировка вывода UTF-8 (для корректного русского языка в Windows)
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

def describe_image(image_path: str) -> str:
    """Описывает изображение с помощью Gemini API для передачи ИИ-агенту с авто-повторами."""
    import mimetypes
    import time
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types
    
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "unknown image content"
        
    mime_type, _ = mimetypes.guess_type(image_path)
    mime_type = mime_type or "image/jpeg"
    
    try:
        with open(image_path, 'rb') as f:
            img_data = f.read()
    except Exception as e:
        print(f"[АНАЛИЗ КАРТИНКИ] Ошибка чтения файла {image_path}: {e}")
        return "unknown image content"
        
    # Попытки с использованием разных моделей в случае перегрузки API
    for attempt in range(3):
        try:
            client = genai.Client(api_key=api_key)
            model_to_use = "gemini-flash-lite-latest" if attempt == 0 else ("gemini-2.5-flash-lite" if attempt == 1 else "gemini-2.5-flash")
            response = client.models.generate_content(
                model=model_to_use,
                contents=[
                    types.Part.from_bytes(data=img_data, mime_type=mime_type),
                    "Briefly describe what is in this image using 3-5 English keywords. Output only the keywords separated by comma. Example: cargo ship, harbor, sea"
                ]
            )
            desc = response.text.strip()
            print(f"[АНАЛИЗ КАРТИНКИ] Успешно распознан {os.path.basename(image_path)}: {desc}")
            return desc
        except Exception as e:
            print(f"[АНАЛИЗ КАРТИНКИ] Попытка {attempt+1}/3 завершилась ошибкой: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                return "unrecognized objects"

def write_status(session_id, progress, message):
    """Вспомогательная функция записи статуса для отображения лоадбара в боте."""
    if not session_id:
        return
    import json
    try:
        status_path = os.path.join("output", f"status_{session_id}.json")
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump({"progress": progress, "message": message}, f, ensure_ascii=False)
    except Exception as e:
        print(f"[СТАТУС] Ошибка записи: {e}")

def retry_crew_kickoff(crew_instance, inputs, max_retries=4, delay_secs=15):
    """Вспомогательная функция для повторного запуска CrewAI с авто-ротацией моделей при 503 / 429 ошибках."""
    import time
    from crewai import LLM
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    qwen_coder_model = "openrouter/qwen/qwen-2.5-coder-32b-instruct:free" if openrouter_key else "gemini/gemini-2.5-flash"
    qwen_reasoner_model = "openrouter/qwen/qwen-2.5-72b-instruct:free" if openrouter_key else "gemini/gemini-2.5-flash"
    
    # Карта авто-переключения моделей при сбоях (работает без префиксов для надежного сопоставления)
    # При сбоях Gemini (например, при сетевой ошибке SSL) пробуем уйти на другого провайдера (Qwen или DeepSeek)
    FALLBACK_MAP = {
        "gemini-2.5-flash": "gemini/gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite": qwen_coder_model,
        "gemini-flash-lite-latest": qwen_coder_model,
        "gemini-2.5-flash-lite": qwen_coder_model,
        
        "deepseek-chat": qwen_coder_model,
        "deepseek-reasoner": qwen_reasoner_model,
        
        # Если Qwen-Coder на OpenRouter падает, переключаем его на Gemini или DeepSeek
        "qwen/qwen-2.5-coder-32b-instruct:free": "gemini/gemini-2.5-flash",
        "qwen/qwen-2.5-72b-instruct:free": "openai/deepseek-reasoner",
    }
    
    api_key = os.getenv("GEMINI_API_KEY")
    
    for attempt in range(max_retries):
        try:
            return crew_instance.kickoff(inputs=inputs)
        except Exception as e:
            err_str = str(e)
            print(f"[LLM RECOVERY] Попытка {attempt+1}/{max_retries} завершилась ошибкой: {err_str}")
            
            is_temporary = any(term in err_str.lower() or term in err_str for term in [
                "503", "unavailable", "overloaded", "rate", "limit", "429", "exhausted",
                "connect", "timeout", "getaddrinfo", "fetch failed", "dns", "network", "ssl",
                "502", "504"
            ])
            
            if attempt < max_retries - 1 and is_temporary:
                print(f"[LLM RECOVERY] Обнаружен временный сбой API (503/429/Network). Выполняем ротацию моделей для агентов...")
                
                # Переключаем модели для всех агентов
                for agent in crew_instance.agents:
                    if hasattr(agent, 'llm') and agent.llm:
                        curr_model = agent.llm.model
                        # Очищаем префиксы для сравнения с картой ротации
                        model_key = curr_model.replace("gemini/", "").replace("openai/", "").replace("openrouter/", "")
                        if model_key in FALLBACK_MAP:
                            next_model = FALLBACK_MAP[model_key]
                            print(f"[LLM RECOVERY] Ротация: Агент '{agent.role}' переключен с '{curr_model}' на '{next_model}'")
                            
                            if "openrouter/" in next_model:
                                agent.llm = LLM(
                                    model=next_model,
                                    base_url="https://openrouter.ai/api/v1",
                                    api_key=openrouter_key
                                )
                            elif "gemini/" in next_model:
                                agent.llm = LLM(
                                    model=next_model,
                                    api_key=api_key
                                )
                            elif "deepseek" in next_model:
                                agent.llm = LLM(
                                    model=next_model if next_model.startswith("openai/") else f"openai/{next_model}",
                                    base_url=os.getenv("DEEPSEEK_BASE_URL", "http://localhost:9655/v1"),
                                    api_key=os.getenv("DEEPSEEK_API_KEY", "dummy-key")
                                )
                            else:
                                agent.llm = LLM(model=next_model)
                
                print(f"[LLM RECOVERY] Ожидаем {delay_secs} сек перед повторной попыткой...")
                time.sleep(delay_secs)
            else:
                raise e

def run_process(
    topic: str,
    uploaded_file_path: str = "",
    user_images_dir: str = "",
    session_id: str = "",
    mode: str = "both",
    preset: str = "ranepa",
    custom_context: str = "",
    custom_researcher: str = "",
    custom_critic: str = ""
) -> tuple:
    """Запускает цикл генерации презентации и/или отчета РАНХиГС по заданной теме.
    
    Параметры:
    - topic: тема презентации (вводится пользователем)
    - uploaded_file_path: путь к файлу с текстом работы (если есть)
    - user_images_dir: путь к папке с загруженными пользователем картинками (если есть)
    - session_id: уникальный ID сессии пользователя для отслеживания прогресса
    - mode: режим генерации ('both' - презентация и отчет, 'presentation' - только презентация, 'work' - только отчет)
    
    Возвращает:
    - кортеж (путь_к_презентации, путь_к_отчету) (пустые строки для негенерируемых форматов)
    """
    # Ленивый импорт тяжелых библиотек и наших модулей
    from crewai import Crew, Process
    from src.agents import get_agents
    from src.tasks import get_tasks
    from src.pptx_generator import build_presentation
    from src.docx_generator import build_word_report

    # Создаем папку output в самом начале, чтобы CrewAI задачи могли сохранять свои output_file без ошибок
    os.makedirs("output", exist_ok=True)
    write_status(session_id, 5, "Инициализация процессов и очистка папок...")
    
    # Очищаем старые файлы сгенерированных изображений, схем и графиков, чтобы избежать конфликтов при повторном запуске
    print("[ИНФО] Очистка старых графиков и диаграмм из папки output...")
    for fname in os.listdir("output"):
        if fname.lower().endswith(('_theme.jpg', '_theme.png', '_chart.png', '.jpg', '.png')) and not fname.startswith('user_image_'):
            try:
                os.remove(os.path.join("output", fname))
            except Exception as e:
                print(f"[ОЧИСТКА] Ошибка удаления файла {fname}: {e}")
                
    print(f"\n[ИНФО] Запуск генератора (режим: {mode}) по теме: '{topic}'")
    if uploaded_file_path and os.path.exists(uploaded_file_path):
        print(f"[ИНФО] Будет использован готовый текст ВКР из файла: {uploaded_file_path}")
    else:
        print("[ИНФО] Готового текста работы нет, запускается глубокое исследование с нуля...")
        uploaded_file_path = "" # сбрасываем в пустую строку для промпта задач
        
    # Обработка пользовательских изображений
    user_images_prompt = "Собственных изображений пользователя нет."
    if user_images_dir and os.path.exists(user_images_dir) and mode in ["both", "presentation"]:
        write_status(session_id, 10, "Анализ и распознавание ваших изображений...")
        user_images_list = []
        print(f"[ИНФО] Обнаружена папка с пользовательскими картинками: {user_images_dir}. Начинаем анализ...")
        for fname in os.listdir(user_images_dir):
            if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                src_path = os.path.join(user_images_dir, fname)
                dest_path = os.path.join("output", fname)
                shutil.copy2(src_path, dest_path)
                
                desc = describe_image(dest_path)
                user_images_list.append((fname, desc))
                
        if user_images_list:
            user_images_prompt = (
                "Пользователь загрузил собственные изображения, которые вы ОБЯЗАНЫ распределить по соответствующим слайдам. "
                "Укажите имя файла в поле 'image' (например, 'image1.jpg'), а поле 'image_keywords' оставьте пустым (null).\n"
                "Вот список загруженных файлов и их описание:\n"
                "Итоговый отчет должен быть возвращен строго в структурированном виде согласно Pydantic-модели ReportData."
            )
            for fname, desc in user_images_list:
                user_images_prompt += f"- Файл '{fname}': содержит [{desc}]\n"
            user_images_prompt += "\nЕсли слайд по смыслу совпадает с одним из этих файлов, укажите его имя в поле 'image'. Одно изображение может быть использовано не более одного раза."
        
    # Динамическая инициализация ИИ-агентов
    agents = get_agents(topic, preset=preset, custom_context=custom_context, custom_researcher=custom_researcher, custom_critic=custom_critic)
    tool_selector, researcher, critic, slide_designer = agents

    # Динамическая инициализация исследовательских задач (проходим шаг исследования темы)
    task_tool_selection, task_research, task_critique, task_revision, _, _ = get_tasks(
        topic=topic,
        uploaded_file_path=uploaded_file_path,
        user_images_prompt=user_images_prompt,
        research_text="",
        agents=agents,
        preset=preset,
        custom_context=custom_context,
        custom_researcher=custom_researcher,
        custom_critic=custom_critic
    )

    # 1. Исследовательская команда (Selector + Researcher + Critic)
    research_crew = Crew(
        agents=[tool_selector, researcher, critic],
        tasks=[task_tool_selection, task_research, task_critique, task_revision],
        process=Process.sequential,
        verbose=True
    )
    
    # Входные параметры для первой команды
    research_inputs = {
        "topic": topic,
        "uploaded_file_path": uploaded_file_path
    }
    
    # Запуск исследовательской части
    write_status(session_id, 15, "Шаг 1/4: Агенты исследуют тему и готовят текстовый материал...")
    print("\n[MAS] Шаг 1: Запуск исследовательской команды (Исследователь + Критик)...")
    research_result = retry_crew_kickoff(research_crew, research_inputs)
    print("[MAS] Шаг 1 завершен. Текст исследования готов.")
    
    # Читаем итоговый текст исследования
    research_text_path = os.path.join("output", "research_text.md")
    if os.path.exists(research_text_path):
        with open(research_text_path, "r", encoding="utf-8") as f:
            research_text = f.read()
    else:
        research_text = str(research_result)
        
    # Инициализируем дизайнерские задачи на основе уже готового и вычитанного текста исследования
    _, _, _, _, task_slide_design, task_report_design = get_tasks(
        topic=topic,
        uploaded_file_path=uploaded_file_path,
        user_images_prompt=user_images_prompt,
        research_text=research_text,
        agents=agents,
        preset=preset,
        custom_context=custom_context,
        custom_researcher=custom_researcher,
        custom_critic=custom_critic
    )

    # Настраиваем задачи дизайнера в зависимости от выбранного режима
    design_tasks = []
    if mode in ["both", "presentation"]:
        design_tasks.append(task_slide_design)
    if mode in ["both", "work"]:
        design_tasks.append(task_report_design)
        
    # 2. Дизайнерская команда (Slide Designer)
    design_crew = Crew(
        agents=[slide_designer],
        tasks=design_tasks,
        process=Process.sequential,
        verbose=True
    )
    
    # Входные параметры для второй команды
    design_inputs = {
        "topic": topic,
        "research_text": research_text,
        "user_images_prompt": user_images_prompt
    }
    
    # Запуск дизайнерской части
    write_status(session_id, 50, "Шаг 2/4: Разработка структуры слайдов и детального отчета...")
    print("\n[MAS] Шаг 2: Запуск команды дизайна слайдов (Дизайнер слайдов)...")
    design_result = retry_crew_kickoff(design_crew, design_inputs)
    print("[MAS] Шаг 2 завершен. Структурирование данных выполнено.")
    
    # Формируем имя файла на основе темы (заменяем запрещенные символы)
    safe_topic_name = "".join([c if c.isalnum() or c in (' ', '_') else '_' for c in topic])
    safe_topic_name = safe_topic_name.strip().replace(" ", "_")[:50]
    
    final_pptx_path = ""
    final_docx_path = ""
    
    # Сборка презентации из JSON-файла, который создал Slide Designer (только если режим presentation или both)
    if mode in ["both", "presentation"]:
        slides_json_path = os.path.join("output", "slides_data.json")
        output_filename = f"Презентация_{safe_topic_name}.pptx"
        write_status(session_id, 75, "Шаг 3/4: Отрисовка презентации PowerPoint и подбор графики...")
        print("\n[ГЕНЕРАТОР] Сборка .pptx файла презентации...")
        final_pptx_path = build_presentation(slides_json_path, output_filename)
        
    # Сборка Word-отчета из JSON-файла (только если режим work или both)
    if mode in ["both", "work"]:
        report_json_path = os.path.join("output", "report_data.json")
        output_docx_filename = f"Отчет_{safe_topic_name}.docx"
        write_status(session_id, 88, "Шаг 4/4: Генерация официального Word-отчета (штабной стиль)...")
        print("\n[ГЕНЕРАТОР] Сборка .docx файла отчета...")
        final_docx_path = build_word_report(report_json_path, "templaredoc.docx", output_docx_filename)
        
    write_status(session_id, 98, "Завершение сборки и сохранение документов...")
    write_status(session_id, 100, "Завершено!")
    return final_pptx_path, final_docx_path


if __name__ == "__main__":
    print("=== ТЕСТОВЫЙ ЗАПУСК CLI СИСТЕМЫ ===")
    test_topic = "Развитие транспортной инфраструктуры города и снижение заторов"
    try:
        presentation_path, report_path = run_process(topic=test_topic)
        print(f"\n[УСПЕХ] Презентация и отчет созданы!")
        print(f"Путь к презентации: {presentation_path}")
        print(f"Путь к отчету: {report_path}")
    except Exception as e:
        print(f"\n[ОШИБКА] Процесс завершился с ошибкой: {e}")
