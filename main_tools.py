import os
import urllib.request
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

# Загружаем переменные окружения
load_dotenv()
gemini_key = os.getenv("GEMINI_API_KEY")

if not gemini_key or gemini_key == "your_gemini_api_key_here":
    print("\n[ВНИМАНИЕ] Пожалуйста, укажите ваш реальный API-ключ в файле .env!")
    exit(1)

# Создаем объект нашей модели
my_llm = LLM(
    model="gemini/gemini-2.5-flash",
    api_key=gemini_key
)

# =====================================================================
# ШАГ 1. СОЗДАНИЕ КАСТОМНОГО ИНСТРУМЕНТА (CUSTOM TOOL)
# Декоратор @tool превращает обычную функцию Python в инструмент для агента.
# Описание (docstring) критически важно: агент читает его, чтобы понять, 
# когда и как использовать этот инструмент.
# =====================================================================

@tool("Поиск научных статей на arXiv")
def search_arxiv(query: str) -> str:
    """Ищет научные публикации на портале arXiv.org по заданной теме.
    Возвращает заголовки, авторов, дату публикации и аннотации (summary) статей.
    Параметр query (поисковый запрос) должен быть на АНГЛИЙСКОМ языке."""
    
    # Форматируем поисковый запрос (заменяем пробелы на плюсы)
    formatted_query = query.strip().replace(" ", "+")
    
    # Ссылка для запроса к бесплатному API arXiv (запрашиваем 3 самые актуальные статьи)
    url = f"http://export.arxiv.org/api/query?search_query=all:{formatted_query}&max_results=3&sortBy=submittedDate&sortOrder=descending"
    
    try:
        # Делаем HTTP-запрос к API
        with urllib.request.urlopen(url) as response:
            xml_data = response.read()
        
        # Парсим XML-ответ
        root = ET.fromstring(xml_data)
        results = []
        
        # Пространство имен Atom XML (нужно для корректного поиска тегов)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        # Ищем все статьи (теги entry)
        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            published = entry.find('atom:published', ns).text[:10]
            authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
            
            results.append(
                f"Название: {title}\n"
                f"Авторы: {', '.join(authors)}\n"
                f"Опубликовано: {published}\n"
                f"Аннотация: {summary}\n"
                f"--------------------------------------------------"
            )
        
        if not results:
            return f"По запросу '{query}' научных статей не найдено."
        
        return "\n".join(results)
        
    except Exception as e:
        return f"Произошла ошибка при поиске на arXiv: {e}"

# =====================================================================
# ШАГ 2. НАСТРОЙКА АГЕНТОВ (Исследователю передаем созданный инструмент)
# =====================================================================

researcher = Agent(
    role="Исследователь учебных материалов",
    goal="Найти реальные научные статьи по теме '{topic}' на arXiv и сделать выжимку ключевых подходов",
    backstory=(
        "Вы — опытный академический исследователь. Вы умеете пользоваться поиском по научным базам, "
        "анализировать аннотации статей на английском языке и вытягивать из них математические и практические методы."
    ),
    tools=[search_arxiv],  # Подключаем инструмент поиска к агенту!
    verbose=True,
    llm=my_llm
)

writer = Agent(
    role="Академический писатель и методист",
    goal="Создать подробный структурированный план работы на основе реальных статей, найденных Researcher",
    backstory=(
        "Вы — профессор университета. Вы умеете интегрировать передовые научные исследования "
        "в учебные программы и выстраивать идеальную логику структуры дипломных работ."
    ),
    verbose=True,
    llm=my_llm
)

critic = Agent(
    role="Строгий академический рецензент",
    goal="Проверить план работы на соответствие реальным научным трендам и предложить правки",
    backstory=(
        "Вы — член диссертационного совета. Вы следите за тем, чтобы структура работы опиралась "
        "на реальные современные научные методы, а не на общие рассуждения."
    ),
    verbose=True,
    llm=my_llm
)

# =====================================================================
# ШАГ 3. НАСТРОЙКА ЗАДАЧ (С указанием использовать поиск)
# =====================================================================

task_research = Task(
    description=(
        "Используя инструмент поиска на arXiv, найдите 2-3 последние статьи по теме '{topic}'. "
        "Вам нужно передать в поиск точный запрос на английском языке (например, 'machine learning financial time series'). "
        "Сделайте подробный конспект найденных статей: запишите их точные названия, авторов и кратко опишите "
        "используемые в них методы машинного обучения."
    ),
    expected_output="Аналитический конспект со ссылками на реальные статьи с arXiv, их авторами и методами.",
    agent=researcher
)

task_write_draft = Task(
    description=(
        "На основе конспекта от Researcher составьте черновую структуру "
        "работы по теме: '{topic}'. Обязательно включите в структуру главы, "
        "посвященные конкретным методам из найденных статей."
    ),
    expected_output="Черновой план работы с упоминанием конкретных источников.",
    agent=writer
)

task_critique = Task(
    description=(
        "Оцените черновой план от Writer. Проверьте, корректно ли встроены "
        "методологии из найденных статей с arXiv. Дайте рекомендации по улучшению."
    ),
    expected_output="Рецензионный отчет с рекомендациями.",
    agent=critic
)

task_final_revision = Task(
    description=(
        "Доработайте план с учетом замечаний Критика. Создайте финальный академический план "
        "по теме '{topic}', опирающийся на реальные научные статьи."
    ),
    expected_output="Итоговый высококачественный структурированный отчет в формате Markdown.",
    agent=writer,
    output_file="tools_approved_report.md"  # Запишется в новый файл
)

# =====================================================================
# ШАГ 4. СБОРКА И ЗАПУСК
# =====================================================================
crew = Crew(
    agents=[researcher, writer, critic],
    tasks=[task_research, task_write_draft, task_critique, task_final_revision],
    process=Process.sequential,
    verbose=True
)

if __name__ == "__main__":
    print("\n=== Запуск системы с поиском по реальной базе arXiv ===\n")
    user_topic = "Machine learning in financial time series analysis"
    
    result = crew.kickoff(inputs={"topic": user_topic})
    
    print("\n=== Работа завершена! ===")
    print("Итоговый отчет сохранен в файл: tools_approved_report.md")
    print("Посмотрите его в вашей IDE!\n")
