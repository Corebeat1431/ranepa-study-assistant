import os
import sys
import json
import math
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# Reconfigure stdout for Windows console (just in case)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Corporate Maroon Color Theme
COLOR_BG = (255, 255, 255)         # Pure White
COLOR_BOX_FILL = (255, 245, 245)   # Light Maroon Tint
COLOR_BORDER = (128, 0, 0)         # Maroon / Dark Red
COLOR_TEXT_MAIN = (0, 0, 0)        # Black
COLOR_TEXT_MUTED = (80, 80, 80)    # Dark Grey
COLOR_ARROW = (128, 0, 0)          # Maroon

def get_fonts(size_title=22, size_body=16):
    """Loads Times New Roman fonts from Windows directory or defaults to standard."""
    paths_title = [
        r"C:\Windows\Fonts\timesbd.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "arial.ttf"
    ]
    paths_body = [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "arial.ttf"
    ]
    
    font_title = None
    for p in paths_title:
        try:
            font_title = ImageFont.truetype(p, size_title)
            break
        except Exception:
            pass
    if not font_title:
        font_title = ImageFont.load_default()
        
    font_body = None
    for p in paths_body:
        try:
            font_body = ImageFont.truetype(p, size_body)
            break
        except Exception:
            pass
    if not font_body:
        font_body = ImageFont.load_default()
        
    return font_title, font_body

def draw_arrow(draw, start, end, color=COLOR_ARROW, width=3, arrow_size=15):
    """Draws a line with an arrowhead pointing to the end point."""
    draw.line([start, end], fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    angle = math.atan2(dy, dx)
    p1 = (x2 - arrow_size * math.cos(angle - math.pi/6), y2 - arrow_size * math.sin(angle - math.pi/6))
    p2 = (x2 - arrow_size * math.cos(angle + math.pi/6), y2 - arrow_size * math.sin(angle + math.pi/6))
    draw.polygon([end, p1, p2], fill=color)

def draw_wrapped_text(draw, text, font, color, box_coords, line_spacing=4):
    """Helper to wrap and center text within a box."""
    x_min, y_min, x_max, y_max = box_coords
    width = x_max - x_min
    height = y_max - y_min
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        w = draw.textlength(test_line, font=font)
        if w < width - 20:  # Padding
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
        
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
    
    y = y_min + (height - total_h) / 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = x_min + (width - w) / 2
        draw.text((x, y), line, fill=color, font=font)
        y += line_h + line_spacing

def draw_box(draw, box_coords, title="", body="", font_title=None, font_body=None):
    """Draws a rounded rectangle box with borders, title, and body text."""
    x_min, y_min, x_max, y_max = box_coords
    
    # Draw box fill & border
    draw.rounded_rectangle(box_coords, radius=10, fill=COLOR_BOX_FILL, outline=COLOR_BORDER, width=3)
    
    # Calculate text layout
    ascent_t, descent_t = font_title.getmetrics()
    h_title = ascent_t + descent_t if title else 0
    
    if title and body:
        # Title at the top half, body at the bottom half
        title_box = (x_min, y_min + 10, x_max, y_min + h_title + 15)
        body_box = (x_min, y_min + h_title + 15, x_max, y_max - 10)
        draw_wrapped_text(draw, title, font_title, COLOR_BORDER, title_box)
        draw_wrapped_text(draw, body, font_body, COLOR_TEXT_MAIN, body_box)
    elif title:
        draw_wrapped_text(draw, title, font_title, COLOR_BORDER, box_coords)
    elif body:
        draw_wrapped_text(draw, body, font_body, COLOR_TEXT_MAIN, box_coords)

def extract_nodes_via_gemini(text, diagram_type, topic):
    """Uses Gemini API to extract key points for diagrams, or returns rule-based fallbacks."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[СХЕМА] GEMINI_API_KEY не найден в окружении. Используем локальный парсер.")
        return get_fallback_nodes(text, diagram_type, topic)
        
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        if diagram_type == "problem_tree":
            prompt = (
                f"Мы пишем отчет на тему: «{topic}».\n"
                f"Вот текст Приложения 1 (Проблемы):\n{text}\n\n"
                "Выдели из текста ровно:\n"
                "1. Одну корневую проблему (root_problem) - до 8 слов.\n"
                "2. Три основные причины (causes) - каждая до 7 слов.\n"
                "3. Три основные негативные последствия (effects) - каждое до 7 слов.\n\n"
                "Выведи результат в формате JSON:\n"
                "{\n"
                '  "root_problem": "строка",\n'
                '  "causes": ["причина1", "причина2", "причина3"],\n'
                '  "effects": ["эффект1", "эффект2", "эффект3"]\n'
                "}\n"
                "Не используй markdown-разметку (никаких ```json), верни ТОЛЬКО чистый JSON-текст."
            )
        else:  # solution_map
            prompt = (
                f"Мы пишем отчет на тему: «{topic}».\n"
                f"Вот текст Приложения 2 (Решения):\n{text}\n\n"
                "Выдели из текста решения:\n"
                "1. Одно главное название решения (solution_title) - до 6 слов.\n"
                "2. Четыре ключевых модуля/компонента этого решения (modules). Для каждого укажи короткое имя (name, до 4 слов) и краткую суть (desc, до 7 слов).\n\n"
                "Выведи результат в формате JSON:\n"
                "{\n"
                '  "solution_title": "строка",\n'
                '  "modules": [\n'
                '    {"name": "имя1", "desc": "суть1"},\n'
                '    {"name": "имя2", "desc": "суть2"},\n'
                '    {"name": "имя3", "desc": "суть3"},\n'
                '    {"name": "имя4", "desc": "суть4"}\n'
                '  ]\n'
                "}\n"
                "Не используй markdown-разметку (никаких ```json), верни ТОЛЬКО чистый JSON-текст."
            )
            
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        resp_text = response.text.strip()
        # Clean markdown wrappers if any
        if resp_text.startswith("```"):
            resp_text = resp_text.split("```")[1]
            if resp_text.startswith("json"):
                resp_text = resp_text[4:]
        resp_text = resp_text.strip()
        
        data = json.loads(resp_text)
        print(f"[СХЕМА] Успешно получены данные через Gemini для {diagram_type}")
        return data
    except Exception as e:
        print(f"[СХЕМА] Ошибка извлечения через Gemini: {e}. Используем локальный парсер.")
        return get_fallback_nodes(text, diagram_type, topic)

def get_fallback_nodes(text, diagram_type, topic):
    """Fallback rule-based text splitter if Gemini API fails."""
    # Split text into clean sentences
    sentences = []
    import re
    # Simple split by dot and filter short lines
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    for s in raw_sentences:
        clean = s.strip()
        # remove numbering like 1., 2.
        clean = re.sub(r'^\d+[\.\)]\s*', '', clean)
        if len(clean) > 15:
            sentences.append(clean)
            
    # Default structures based on theme
    if diagram_type == "problem_tree":
        # Fill defaults
        root = f"Низкая эффективность процессов по теме «{topic}»"
        causes = [
            "Отсутствие единой платформы данных",
            "Сложные межведомственные согласования",
            "Неактуальность и фрагментарность сведений"
        ]
        effects = [
            "Увеличение сроков запуска проектов",
            "Снижение инвестиционной привлекательности",
            "Рост издержек участников рынка"
        ]
        
        # Try to use sentences from text
        if len(sentences) >= 1:
            root = truncate_words(sentences[0], 8)
        if len(sentences) >= 4:
            causes = [truncate_words(sentences[1], 7), truncate_words(sentences[2], 7), truncate_words(sentences[3], 7)]
        if len(sentences) >= 7:
            effects = [truncate_words(sentences[4], 7), truncate_words(sentences[5], 7), truncate_words(sentences[6], 7)]
            
        return {
            "root_problem": root,
            "causes": causes,
            "effects": effects
        }
    else:  # solution_map
        title = f"Модернизация процессов: {topic}"
        modules = [
            {"name": "Единая MDM-платформа", "desc": "Централизация и очистка ключевых данных"},
            {"name": "Интерактивная карта", "desc": "Отображение свободных инвест-площадок"},
            {"name": "Личный кабинет", "desc": "Прозрачный трекинг этапов согласования"},
            {"name": "ИИ-ассистент", "desc": "Автоматический подбор лотов для бизнеса"}
        ]
        
        if len(sentences) >= 1:
            title = truncate_words(sentences[0], 8)
        if len(sentences) >= 5:
            modules = [
                {"name": "Интеграционная шина", "desc": truncate_words(sentences[1], 7)},
                {"name": "Личный кабинет", "desc": truncate_words(sentences[2], 7)},
                {"name": "Сервисный модуль", "desc": truncate_words(sentences[3], 7)},
                {"name": "Аналитика и NPS", "desc": truncate_words(sentences[4], 7)}
            ]
        return {
            "solution_title": title,
            "modules": modules
        }

def truncate_words(text, num_words):
    words = text.split()
    if len(words) <= num_words:
        return text
    return " ".join(words[:num_words]) + "..."

def draw_problem_tree_diagram(nodes, output_path):
    """Draws a vertical Problem Tree (Effects at Top, Root in Middle, Causes at Bottom)"""
    img = Image.new('RGB', (1200, 900), COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title, font_body = get_fonts(22, 16)
    font_main_title, _ = get_fonts(26, 16)
    
    # 1. Draw Main Canvas Title
    draw.text((600 - draw.textlength("ДЕРЕВО ПРОБЛЕМ И ПРИЧИННО-СЛЕДСТВЕННЫХ СВЯЗЕЙ", font=font_main_title)/2, 35), 
              "ДЕРЕВО ПРОБЛЕМ И ПРИЧИННО-СЛЕДСТВЕННЫХ СВЯЗЕЙ", fill=COLOR_BORDER, font=font_main_title)
    
    # 2. Coordinates & Nodes
    # Y-Levels: Effects Y=180, Root Y=450, Causes Y=720
    # X-Centers: Left=250, Center=600, Right=950
    
    coords_effects = [
        (250 - 160, 180 - 65, 250 + 160, 180 + 65),
        (600 - 160, 180 - 65, 600 + 160, 180 + 65),
        (950 - 160, 180 - 65, 950 + 160, 180 + 65)
    ]
    
    coords_root = (600 - 250, 450 - 70, 600 + 250, 450 + 70)
    
    coords_causes = [
        (250 - 160, 720 - 65, 250 + 160, 720 + 65),
        (600 - 160, 720 - 65, 600 + 160, 720 + 65),
        (950 - 160, 720 - 65, 950 + 160, 720 + 65)
    ]
    
    # 3. Draw Connecting Arrows
    # Causes to Root (pointing UP)
    for start_x in [250, 600, 950]:
        draw_arrow(draw, (start_x, 720 - 65), (600 if start_x==600 else (450 if start_x==250 else 750), 450 + 70))
        
    # Root to Effects (pointing UP)
    for end_x in [250, 600, 950]:
        draw_arrow(draw, (600 if end_x==600 else (450 if end_x==250 else 750), 450 - 70), (end_x, 180 + 65))
        
    # 4. Draw Boxes
    # Effects (Top)
    effects = nodes.get("effects", ["Эффект 1", "Эффект 2", "Эффект 3"])
    for i, box in enumerate(coords_effects):
        text = effects[i] if i < len(effects) else f"Эффект {i+1}"
        draw_box(draw, box, title=f"ПОСЛЕДСТВИЕ {i+1}", body=text, font_title=font_title, font_body=font_body)
        
    # Root Problem (Middle)
    root_problem = nodes.get("root_problem", "Критическая проблема")
    draw_box(draw, coords_root, title="КЛЮЧЕВАЯ ПРОБЛЕМА ПРОЕКТА", body=root_problem, font_title=font_title, font_body=font_body)
    
    # Causes (Bottom)
    causes = nodes.get("causes", ["Причина 1", "Причина 2", "Причина 3"])
    for i, box in enumerate(coords_causes):
        text = causes[i] if i < len(causes) else f"Причина {i+1}"
        draw_box(draw, box, title=f"ПЕРВОПРИЧИНА {i+1}", body=text, font_title=font_title, font_body=font_body)
        
    # Save Image
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"[СХЕМА] Схема дерева проблем успешно сохранена в: {output_path}")

def draw_solution_map_diagram(nodes, output_path):
    """Draws a Hub-and-Spoke Solution Map Architecture diagram."""
    img = Image.new('RGB', (1200, 900), COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    font_title, font_body = get_fonts(22, 16)
    font_main_title, _ = get_fonts(26, 16)
    
    # 1. Draw Main Canvas Title
    draw.text((600 - draw.textlength("АРХИТЕКТУРА И МОДУЛИ ЦИФРОВОГО РЕШЕНИЯ", font=font_main_title)/2, 35), 
              "АРХИТЕКТУРА И МОДУЛИ ЦИФРОВОГО РЕШЕНИЯ", fill=COLOR_BORDER, font=font_main_title)
    
    # 2. Coordinates & Nodes
    # Hub: Center X=600, Y=450
    # Spokes: Top=(600, 180), Right=(980, 450), Bottom=(600, 720), Left=(220, 450)
    
    coords_hub = (600 - 200, 450 - 75, 600 + 200, 450 + 75)
    
    coords_spokes = [
        (600 - 160, 180 - 65, 600 + 160, 180 + 65),   # Top
        (980 - 160, 450 - 65, 980 + 160, 450 + 65),   # Right
        (600 - 160, 720 - 65, 600 + 160, 720 + 65),   # Bottom
        (220 - 160, 450 - 65, 220 + 160, 450 + 65)    # Left
    ]
    
    # 3. Draw Connecting Arrows (Hub out to Spokes, and Spokes in to Hub)
    # Top
    draw_arrow(draw, (600, 450 - 75), (600, 180 + 65))
    # Right
    draw_arrow(draw, (600 + 200, 450), (980 - 160, 450))
    # Bottom
    draw_arrow(draw, (600, 450 + 75), (600, 720 - 65))
    # Left
    draw_arrow(draw, (600 - 200, 450), (220 + 160, 450))
    
    # 4. Draw Boxes
    # Hub
    solution_title = nodes.get("solution_title", "Цифровое проектное решение")
    draw_box(draw, coords_hub, title="ЯДРО РЕШЕНИЯ", body=solution_title, font_title=font_title, font_body=font_body)
    
    # Spokes (Modules)
    modules = nodes.get("modules", [
        {"name": "Модуль 1", "desc": "Суть 1"},
        {"name": "Модуль 2", "desc": "Суть 2"},
        {"name": "Модуль 3", "desc": "Суть 3"},
        {"name": "Модуль 4", "desc": "Суть 4"}
    ])
    
    labels = ["КОМПОНЕНТ A", "КОМПОНЕНТ B", "КОМПОНЕНТ C", "КОМПОНЕНТ D"]
    for i, box in enumerate(coords_spokes):
        mod = modules[i] if i < len(modules) else {"name": f"Модуль {i+1}", "desc": f"Описание {i+1}"}
        draw_box(draw, box, title=mod.get("name", labels[i]), body=mod.get("desc", ""), font_title=font_title, font_body=font_body)
        
    # Save Image
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"[СХЕМА] Схема решения успешно сохранена в: {output_path}")

def generate_report_diagrams(json_data_path, safe_topic_name):
    """Main entry point: loads report JSON, extracts nodes and generates PNG files."""
    print(f"[СХЕМА] Генерация диаграмм для отчета на основе JSON: {json_data_path}...")
    with open(json_data_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
        
    topic = report_data.get("topic", "")
    app1_text = report_data.get("appendix_1_problems", "")
    app2_text = report_data.get("appendix_2_solutions", "")
    
    # Extract & Draw Diagram 1 (Problem Tree)
    nodes_1 = extract_nodes_via_gemini(app1_text, "problem_tree", topic)
    diag1_path = os.path.join("output", f"diagram_app1_{safe_topic_name}.png")
    draw_problem_tree_diagram(nodes_1, diag1_path)
    
    # Extract & Draw Diagram 2 (Solution Map)
    nodes_2 = extract_nodes_via_gemini(app2_text, "solution_map", topic)
    diag2_path = os.path.join("output", f"diagram_app2_{safe_topic_name}.png")
    draw_solution_map_diagram(nodes_2, diag2_path)
    
    return diag1_path, diag2_path

if __name__ == "__main__":
    # Test generation
    test_json = r"output\report_data.json"
    if os.path.exists(test_json):
        generate_report_diagrams(test_json, "test_topic")
    else:
        print("Test report_data.json not found")
