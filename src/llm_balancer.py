import os
# Модуль dotenv загружает пары ключ-значение из файла .env в переменные среды окружения.
# Это позволяет настраивать приложение, не изменяя исходный код.
from dotenv import load_dotenv

# Класс LLM из CrewAI — это ООП-обертка для взаимодействия с различными языковыми моделями.
# Мы создаем экземпляры (объекты) этого класса, передавая название модели и наш секретный API-ключ.
from crewai import LLM

# Загружаем переменные окружения при первом импорте этого модуля
load_dotenv()

# =====================================================================
# ХАРАКТЕРИСТИКИ МОДЕЛЕЙ GOOGLE GEMINI (ДЛЯ СПРАВКИ И БЕНЧМАРКА)
# Свойства моделей оцениваются по шкале от 1 до 10.
# В ООП эта структура данных (словарь/dict) служит базой знаний для балансировщика.
# =====================================================================
GEMINI_MODELS_BENCHMARKS = {
    "gemini-2.5-pro": {
        "name": "Google Gemini 2.5 Pro",
        "structured_output": 9.8, # Самый точный анализ схем Pydantic
        "reasoning": 9.8,          # Высочайший уровень логики для критиков
        "russian_language": 9.5,
        "reliability": 8.0,        # Ниже надежность из-за строгих лимитов бесплатных квот (2 RPM)
        "model_string": "gemini/gemini-2.5-pro"
    },
    "gemini-2.5-flash": {
        "name": "Google Gemini 2.5 Flash",
        "structured_output": 9.5,
        "reasoning": 9.0,          # Отличная логика для исследований
        "russian_language": 9.5,
        "reliability": 9.5,        # Хорошие лимиты квот (15 RPM)
        "model_string": "gemini/gemini-2.5-flash"
    },
    "gemini-flash-lite-latest": {
        "name": "Google Gemini Flash Lite",
        "structured_output": 9.5, # Отличная поддержка Pydantic/JSON схем
        "reasoning": 8.0,          # Упрощенная логика
        "russian_language": 9.0,
        "reliability": 9.8,        # Максимальная скорость и огромные бесплатные квоты
        "model_string": "gemini/gemini-flash-lite-latest"
    }
}

def get_base_llm_instance(model_name: str) -> LLM:
    """Вспомогательная функция (метод) создания экземпляра класса LLM от CrewAI.
    
    В ООП функции внутри модулей помогают инкапсулировать (скрывать) детали реализации.
    Агентам не нужно знать, как создается LLM, они просто вызывают функцию.
    """
    # Достаем API-ключ из системных переменных окружения, куда его загрузил load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("[ОШИБКА] GEMINI_API_KEY не найден в файле .env! Пожалуйста, добавьте его.")
    
    # Возвращаем созданный объект класса LLM. 
    # Префикс 'gemini/' сообщает CrewAI, что нужно использовать провайдер Google Gemini.
    return LLM(
        model=model_name,
        api_key=api_key
    )

def get_balanced_llm(role: str, session_id: str = None) -> LLM:
    """Основной роутер (балансировщик). 
    
    Выбирает модель (Gemini, DeepSeek или гибридный вариант) в зависимости от роли агента.
    """
    provider = os.getenv("LLM_PROVIDER", "hybrid").strip().lower()
    
    # Режим OpenRouter (например, для использования бесплатных моделей Qwen-Coder)
    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "dummy-key")
        model_name = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-coder-32b-instruct:free").strip()
        
        # Для критика можно использовать более мощную бесплатную модель, если доступно
        if role == "critic":
            selected_model = "qwen/qwen-2.5-72b-instruct:free"
        elif role == "selector":
            selected_model = "google/gemini-2.5-flash:free"
        else:
            selected_model = model_name
            
        print(f"[LLM-BALANCER] Роль '{role}' назначена на OpenRouter модель: {selected_model}")
        return LLM(
            model=f"openrouter/{selected_model}",
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        
    # Режим Ollama (локальный запуск без интернета)
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        model_name = os.getenv("OLLAMA_MODEL", "gemma2:9b").strip()
        
        print(f"[LLM-BALANCER] Роль '{role}' назначена на локальную модель Ollama: {model_name}")
        return LLM(
            model=f"ollama/{model_name}",
            base_url=f"{base_url}/v1"
        )
        
    # Режим GigaChat от Сбера
    if provider == "gigachat":
        credentials = os.getenv("GIGACHAT_CREDENTIALS", "")
        # Для GigaChat используется интеграция с langchain_community или специальный эндпоинт
        print(f"[LLM-BALANCER] Роль '{role}' назначена на GigaChat (через GigaChat API)")
        # LiteLLM поддерживает gigachat с префиксом gigachat/
        return LLM(
            model="gigachat/GigaChat-Pro" if role in ["critic", "researcher"] else "gigachat/GigaChat",
            api_key=credentials,
            base_url="https://gigachat.devices.sberbank.ru/api/v1"
        )

    # Режим Hybrid: Selector на Gemini, тяжелые агенты на DeepSeek
    if provider == "hybrid":
        if role == "selector":
            # Навигатор легкий, делаем быстрый Gemini запрос
            print(f"[LLM-BALANCER] Роль '{role}' назначена на модель Gemini (Гибридный режим): gemini/gemini-3.1-flash-lite")
            return get_base_llm_instance("gemini/gemini-3.1-flash-lite")
        elif role == "designer":
            # Дизайнер слайдов и отчета делает тяжелые Pydantic-запросы, 
            # которые на веб-прокси DeepSeek падают по тайм-ауту (fetch failed) из-за огромного объема текста (50 000+ символов).
            # Переводим его на надежный, быстрый и квотно-легкий Google Gemini 3.1 Flash Lite.
            print(f"[LLM-BALANCER] Роль '{role}' перенаправлена на Google Gemini 3.1 Flash Lite для стабильности генерации: gemini/gemini-3.1-flash-lite")
            return get_base_llm_instance("gemini/gemini-3.1-flash-lite")
        else:
            base_url = os.getenv("DEEPSEEK_BASE_URL", "http://localhost:9655/v1")
            api_key = os.getenv("DEEPSEEK_API_KEY", "dummy-key")
            
            # Критик на глубоком рассуждении (reasoner/R1)
            # Исследователь на DeepSeek Chat
            role_to_model = {
                "researcher": "openai/deepseek-chat",
                "critic": "openai/deepseek-reasoner"
            }
            selected_model = role_to_model.get(role, "openai/deepseek-chat")
            
            headers = {}
            if session_id:
                headers["X-Agent-Session"] = f"session-{session_id}-{role}"
            else:
                headers["X-Agent-Session"] = f"session-default-{role}"
                
            print(f"[LLM-BALANCER] Роль '{role}' назначена на модель DeepSeek (Гибридный режим): {selected_model} с сессией {headers['X-Agent-Session']}")
            return LLM(
                model=selected_model,
                base_url=base_url,
                api_key=api_key,
                extra_headers=headers
            )
            
    # Режим Чистый DeepSeek
    if provider == "deepseek":
        base_url = os.getenv("DEEPSEEK_BASE_URL", "http://localhost:9655/v1")
        api_key = os.getenv("DEEPSEEK_API_KEY", "dummy-key")
        
        role_to_model = {
            "selector": "openai/deepseek-chat",
            "researcher": "openai/deepseek-chat",
            "critic": "openai/deepseek-reasoner",
            "designer": "openai/deepseek-chat"
        }
        selected_model = role_to_model.get(role, "openai/deepseek-chat")
        
        headers = {}
        if session_id:
            headers["X-Agent-Session"] = f"session-{session_id}-{role}"
        else:
            headers["X-Agent-Session"] = f"session-default-{role}"
            
        print(f"[LLM-BALANCER] Роль '{role}' назначена на модель DeepSeek: {selected_model} с сессией {headers['X-Agent-Session']}")
        return LLM(
            model=selected_model,
            base_url=base_url,
            api_key=api_key,
            extra_headers=headers
        )

    # Режим Чистый Gemini (по умолчанию или при ошибках)
    tier = os.getenv("GEMINI_TIER", "balanced").strip().lower()
    
    if tier == "high":
        # Режим максимального качества (премиум логика)
        role_to_model = {
            "selector": "gemini/gemini-3.1-flash-lite",
            "researcher": "gemini/gemini-3.1-flash-lite",
            "critic": "gemini/gemini-3.1-flash-lite",
            "designer": "gemini/gemini-3.1-flash-lite"
        }
    elif tier == "light":
        # Легкий режим: распределяем роли по разным моделям семейства Lite для обхода суточных лимитов (20 запросов/день)
        role_to_model = {
            "selector": "gemini/gemini-flash-lite-latest",
            "researcher": "gemini/gemini-3.1-flash-lite",
            "critic": "gemini/gemini-3.1-flash-lite",
            "designer": "gemini/gemini-flash-lite-latest"
        }
    else:
        # Режим 'balanced' (Распределяем по разным моделям для защиты от суточных лимитов)
        role_to_model = {
            "selector": "gemini/gemini-flash-lite-latest",
            "researcher": "gemini/gemini-3.1-flash-lite",
            "critic": "gemini/gemini-3.1-flash-lite",
            "designer": "gemini/gemini-flash-lite-latest"
        }
        
    # Выбираем модель под конкретную роль
    selected_model = role_to_model.get(role, "gemini/gemini-3.1-flash-lite")
    
    print(f"[LLM-BALANCER] Роль '{role}' назначена на модель: {selected_model} (Режим: {tier})")
    
    # Возвращаем настроенный экземпляр LLM
    return get_base_llm_instance(selected_model)

def test_llm_compatibility() -> tuple[bool, str]:
    """Pre-flight диагностика для проверки работоспособности Gemini API.
    
    Эта функция отправляет тестовый промпт, чтобы убедиться, что ключ рабочий
    и у нас есть доступ к моделям Google AI.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False, "GEMINI_API_KEY отсутствует в файле .env"
        
    try:
        # Пытаемся импортировать библиотеку для прямого общения с API Google
        from google import genai
        client = genai.Client(api_key=api_key)
        
        # Делаем сверхлегкий тестовый вызов
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents="Hello. Respond with OK."
        )
        
        if response and response.text:
            return True, "Успешное подключение к Google Gemini API!"
        return False, "Получен пустой ответ от API."
        
    except Exception as e:
        return False, f"Ошибка проверки соединения: {str(e)}"
