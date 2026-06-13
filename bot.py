import os
import sys
import shutil
import logging
import asyncio
import warnings
import traceback
import time
# Совместимость с Python 3.13: устраняем баг CrewAI/Pydantic с фильтром предупреждений
_orig_warn = warnings.warn
def _safe_warn(message, category=None, stacklevel=1, source=None, *args, **kwargs):
    kwargs.pop('skip_file_prefixes', None)
    try:
        return _orig_warn(message, category, stacklevel, source, *args, **kwargs)
    except Exception:
        return None
warnings.warn = _safe_warn
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
# run_process импортируется отложенно в run_agents_async

# Загружаем ключи из .env
load_dotenv()
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

# Настраиваем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальный перехватчик исключений для записи в temp/bot_error.txt
def global_excepthook(exctype, value, tb):
    tb_str = "".join(traceback.format_exception(exctype, value, tb))
    logger.critical(f"Необработанное исключение: {tb_str}")
    try:
        os.makedirs("temp", exist_ok=True)
        with open(os.path.join("temp", "bot_error.txt"), "w", encoding="utf-8") as err_f:
            err_f.write(f"=== НЕОБРАБОТАННОЕ ИСКЛЮЧЕНИЕ ===\n{tb_str}")
    except Exception:
        pass
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_excepthook

# Переменные состояния для контроля неактивности и горячей выгрузки
last_activity_time = time.time()
last_chat_id = None

async def shutdown_bot(application: Application):
    """Метод для корректной остановки бота и выгрузки из памяти."""
    logger.info("[ВЫГРУЗКА] Запуск процесса остановки ИИ-агентов...")
    # Даем небольшую задержку (0.5 сек), чтобы последнее сообщение гарантированно ушло в Telegram
    await asyncio.sleep(0.5)
    await application.stop()

async def idle_timeout_monitor(application: Application):
    """Фоновая задача, которая проверяет неактивность пользователя и выгружает бот при бездействии."""
    global last_activity_time, last_chat_id
    while True:
        await asyncio.sleep(15)  # проверяем каждые 15 секунд
        if not application.running:
            break
            
        # В облаке (на Hugging Face Spaces) бот должен работать 24/7 и не выгружаться по таймауту
        if os.getenv("SPACE_ID"):
            await asyncio.sleep(30)
            continue
            
        # Если прошло более 300 секунд (5 минут) с момента последнего сообщения
        if time.time() - last_activity_time > 300:
            logger.warning("[ТАЙМАУТ-МОНИТОР] Пользователь бездействует более 5 минут. Выгружаем бота...")
            if last_chat_id:
                try:
                    # Отправляем сообщение перед завершением
                    keyboard = [["🚀 Начать новую работу"]]
                    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                    await application.bot.send_message(
                        chat_id=last_chat_id,
                        text="💤 **Сессия закрыта по таймауту неактивности (5 минут).**\n\n"
                             "Бот переведен в спящий режим. Нажмите кнопку ниже, чтобы начать новую работу.",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"[ТАЙМАУТ-МОНИТОР] Не удалось отправить сообщение о таймауте: {e}")
            
            # Запускаем выгрузку
            asyncio.create_task(shutdown_bot(application))
            break

async def update_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перехватчик всех обновлений для фиксации активности пользователя."""
    global last_activity_time, last_chat_id
    last_activity_time = time.time()
    logger.info(f"[АКТИВНОСТЬ] Получено обновление: update_id={update.update_id}")
    if update.effective_chat:
        last_chat_id = update.effective_chat.id

# Состояния диалога
STATE_THEME, STATE_PRESET, STATE_CUSTOM_CONTEXT, STATE_CUSTOM_RESEARCHER, STATE_CUSTOM_CRITIC, STATE_MODE, STATE_CHOICE, STATE_FILE, STATE_IMAGES = range(9)

# =====================================================================
# ОБРАБОТЧИКИ КОМАНД И ДИАЛОГА
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога. Приветствуем пользователя и просим тему."""
    # Очищаем данные сессии
    context.user_data.clear()
    
    await update.message.reply_text(
        "🎓 **Приветствую!** Я ваш академический ассистент РАНХиГС.\n\n"
        "Я помогу вам написать исследование по теме и сгенерировать готовую презентацию "
        "для защиты перед комиссией администрации города.\n\n"
        "Отправьте мне **тему вашего проекта** (любую, какую захотите):",
        parse_mode="Markdown"
    )
    return STATE_THEME


async def handle_theme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем тему и предлагаем выбор направленности/ролей агентов."""
    theme = update.message.text.strip()
    context.user_data["theme"] = theme
    
    # Кнопки выбора пресета
    keyboard = [
        ["🏛️ РАНХиГС (Горадминистрация)"],
        ["💼 Бизнес-стартап (Инвесторы)"],
        ["🎓 Академический (Научный совет)"],
        ["✏️ Свой контекст", "⚙️ Настроить роли ИИ"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"Отличная тема: *«{theme}»*.\n\n"
        "Выберите направленность исследования и роли агентов:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return STATE_PRESET


async def handle_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем пресет и переходим к настройке или выбору формата."""
    choice = update.message.text.strip()
    
    # Сбрасываем кастомные настройки перед установкой
    context.user_data["preset"] = "ranepa"
    context.user_data["custom_context"] = ""
    context.user_data["custom_researcher"] = ""
    context.user_data["custom_critic"] = ""
    
    if "РАНХиГС" in choice:
        context.user_data["preset"] = "ranepa"
    elif "Бизнес-стартап" in choice:
        context.user_data["preset"] = "business"
    elif "Академический" in choice:
        context.user_data["preset"] = "academic"
    elif choice == "✏️ Свой контекст":
        context.user_data["preset"] = "custom"
        await update.message.reply_text(
            "Введите ваше описание контекста или особые требования к исследованию (общий промпт):",
            reply_markup=ReplyKeyboardRemove()
        )
        return STATE_CUSTOM_CONTEXT
    elif choice == "⚙️ Настроить роли ИИ":
        context.user_data["preset"] = "custom"
        keyboard = [["Далее ➡️"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "По умолчанию Исследователь ориентирован на РАНХиГС.\n"
            "Введите ваше описание роли/задач для Исследователя (или нажмите «Далее ➡️», чтобы использовать по умолчанию):",
            reply_markup=reply_markup
        )
        return STATE_CUSTOM_RESEARCHER
    else:
        # Если введено что-то другое, считаем это кастомным контекстом напрямую
        context.user_data["preset"] = "custom"
        context.user_data["custom_context"] = choice
    
    # Если выбран стандартный пресет, переходим к STATE_MODE (выбор формата)
    keyboard = [
        ["Презентацию и отчет 📝📊"],
        ["Только презентацию (.pptx) 📊"],
        ["Только отчет по работе (.docx) 📝"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Направленность выбрана! Теперь укажите, что именно вы хотите подготовить по этой теме:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return STATE_MODE


async def handle_custom_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем кастомный контекст и переходим к выбору формата."""
    text = update.message.text.strip()
    context.user_data["custom_context"] = text
    
    keyboard = [
        ["Презентацию и отчет 📝📊"],
        ["Только презентацию (.pptx) 📊"],
        ["Только отчет по работе (.docx) 📝"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Контекст сохранен! Теперь укажите, что именно вы хотите подготовить по этой теме:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return STATE_MODE


async def handle_custom_researcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем роль исследователя и запрашиваем роль критика."""
    text = update.message.text.strip()
    if text != "Далее ➡️":
        context.user_data["custom_researcher"] = text
        
    keyboard = [["Далее ➡️"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Роль Исследователя задана.\n"
        "По умолчанию роль Критика ориентирована на вице-мэра города.\n"
        "Введите ваше описание роли/критериев для Критика (или нажмите «Далее ➡️», чтобы использовать по умолчанию):",
        reply_markup=reply_markup
    )
    return STATE_CUSTOM_CRITIC


async def handle_custom_critic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем роль критика и переходим к выбору формата."""
    text = update.message.text.strip()
    if text != "Далее ➡️":
        context.user_data["custom_critic"] = text
        
    keyboard = [
        ["Презентацию и отчет 📝📊"],
        ["Только презентацию (.pptx) 📊"],
        ["Только отчет по работе (.docx) 📝"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Роли настроены! Теперь укажите, что именно вы хотите подготовить по этой теме:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return STATE_MODE


async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняем формат работы и предлагаем выбор источника."""
    choice = update.message.text.strip()
    
    if "оба" in choice.lower() or "и отчет" in choice.lower():
        context.user_data["mode"] = "both"
    elif "презентаци" in choice.lower():
        context.user_data["mode"] = "presentation"
    elif "отчет" in choice.lower() or "работа" in choice.lower() or "docx" in choice.lower():
        context.user_data["mode"] = "work"
    else:
        context.user_data["mode"] = "both"
        
    # Кнопки выбора источника
    keyboard = [["Исследовать с нуля", "Загрузить документ (.txt/.md/.pdf/.docx/.pptx)"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Принято! Теперь укажите источник данных:\n\n"
        "У вас есть готовый текст работы (ВКР), на основе которого нужно собрать материалы, "
        "или агенты должны провести исследование с нуля?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return STATE_CHOICE


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора пользователя."""
    choice = update.message.text.strip()
    
    if choice == "Исследовать с нуля":
        context.user_data["text_file_path"] = ""
        
        # Проверяем режим генерации
        mode = context.user_data.get("mode", "both")
        if mode == "work":
            # Если только отчет (Word), слайды не генерируются, картинки не нужны
            await update.message.reply_text(
                "Начинаем сборку вашего отчета. Агенты-исследователи приступают к работе...\n"
                "Это займет около 1-2 минут. Я пришлю готовый файл отчета сразу после сборки!",
                reply_markup=ReplyKeyboardRemove()
            )
            # Запуск CrewAI в фоновом потоке
            asyncio.create_task(
                run_agents_async(
                    update, 
                    context, 
                    theme=context.user_data.get("theme", ""), 
                    file_path="",
                    user_images_dir=""
                )
            )
            return ConversationHandler.END
            
        # Инициализируем папку для картинок пользователя
        chat_id = update.effective_chat.id
        images_dir = os.path.join("temp", f"user_images_{chat_id}")
        if os.path.exists(images_dir):
            try:
                shutil.rmtree(images_dir)
            except Exception:
                pass
        os.makedirs(images_dir, exist_ok=True)
        context.user_data["images_dir"] = images_dir
        context.user_data["image_count"] = 0
        
        keyboard = [["Собрать презентацию! 🚀"], ["Отмена"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "📝 Отлично! Тема принята для исследования с нуля.\n\n"
            "Хотите ли вы добавить **собственные изображения** (чертежи, таблицы, схемы, фото) для слайдов презентации?\n"
            "Вы можете отправить мне одну или несколько картинок по одной.\n\n"
            "Если картинки не нужны, просто нажмите кнопку ниже **«Собрать презентацию! 🚀»** (я сам подберу иллюстрации из интернета).",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return STATE_IMAGES
        
    elif choice in ["Загрузить файл (.txt/.md/.pdf)", "Загрузить документ (.txt/.md/.pdf/.docx)", "Загрузить документ (.txt/.md/.pdf/.docx/.pptx)"]:
        await update.message.reply_text(
            "Пожалуйста, отправьте мне файл вашей работы в формате **.txt**, **.md**, **.pdf**, **.docx**, **.ppt** или **.pptx**.\n\n"
            "Я автоматически извлеку из него текст и передам агентам для сборки.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        return STATE_FILE
        
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки на клавиатуре.")
        return STATE_CHOICE


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Скачивание файла и переход к загрузке картинок."""
    document = update.message.document
    
    # Проверяем расширение
    file_name = document.file_name.lower()
    if not (file_name.endswith('.txt') or file_name.endswith('.md') or file_name.endswith('.pdf') or 
            file_name.endswith('.docx') or file_name.endswith('.ppt') or file_name.endswith('.pptx')):
        await update.message.reply_text("Ошибка! Пожалуйста, отправьте файл в формате .txt, .md, .pdf, .docx, .ppt или .pptx.")
        return STATE_FILE
        
    await update.message.reply_text("Файл получен и сохранен.")
    
    # Скачиваем файл во временную папку
    tg_file = await context.bot.get_file(document.file_id)
    os.makedirs("temp", exist_ok=True)
    ext = os.path.splitext(file_name)[1]
    local_path = os.path.join("temp", f"user_thesis_{update.effective_user.id}{ext}")
    await tg_file.download_to_drive(local_path)
    context.user_data["text_file_path"] = local_path
    
    # Проверяем режим генерации
    mode = context.user_data.get("mode", "both")
    if mode == "work":
        # Если только отчет (Word), слайды не генерируются, картинки не нужны
        await update.message.reply_text(
            "Текст работы успешно загружен! Начинаем сборку вашего отчета. Агенты-исследователи приступают к работе...\n"
            "Это займет около 1-2 минут. Я пришлю готовый файл отчета сразу после сборки!",
            reply_markup=ReplyKeyboardRemove()
        )
        # Запуск CrewAI в фоновом потоке
        asyncio.create_task(
            run_agents_async(
                update, 
                context, 
                theme=context.user_data.get("theme", ""), 
                file_path=local_path,
                user_images_dir=""
            )
        )
        return ConversationHandler.END
        
    # Инициализируем папку для картинок пользователя
    chat_id = update.effective_chat.id
    images_dir = os.path.join("temp", f"user_images_{chat_id}")
    if os.path.exists(images_dir):
        try:
            shutil.rmtree(images_dir)
        except Exception:
            pass
    os.makedirs(images_dir, exist_ok=True)
    context.user_data["images_dir"] = images_dir
    context.user_data["image_count"] = 0
    
    keyboard = [["Собрать презентацию! 🚀"], ["Отмена"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "📝 Текст работы успешно загружен!\n\n"
        "Хотите ли вы добавить **собственные изображения** (чертежи, таблицы, схемы, фото) для слайдов презентации?\n"
        "Вы можете отправить мне одну или несколько картинок по одной.\n\n"
        "Если картинки не нужны, просто нажмите кнопку ниже **«Собрать презентацию! 🚀»** (я сам подберу иллюстрации из интернета).",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return STATE_IMAGES


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Прием изображений от пользователя и сохранение в папку."""
    photo = update.message.photo
    
    if photo:
        # Берем фото в самом высоком разрешении (последнее в списке)
        largest_photo = photo[-1]
        tg_file = await context.bot.get_file(largest_photo.file_id)
        
        images_dir = context.user_data.get("images_dir")
        image_count = context.user_data.get("image_count", 0) + 1
        
        if not images_dir or not os.path.exists(images_dir):
            chat_id = update.effective_chat.id
            images_dir = os.path.join("temp", f"user_images_{chat_id}")
            os.makedirs(images_dir, exist_ok=True)
            context.user_data["images_dir"] = images_dir
            
        file_path = os.path.join(images_dir, f"user_image_{image_count}.jpg")
        await tg_file.download_to_drive(file_path)
        context.user_data["image_count"] = image_count
        
        keyboard = [["Собрать презентацию! 🚀"], ["Отмена"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            f"📸 Картинка №{image_count} успешно загружена!\n"
            "Вы можете отправить еще изображения или нажать кнопку ниже, чтобы начать сборку презентации.",
            reply_markup=reply_markup
        )
        return STATE_IMAGES
        
    # Обработка текстовых команд
    msg_text = update.message.text.strip() if update.message.text else ""
    if msg_text == "Собрать презентацию! 🚀":
        await update.message.reply_text(
            "Начинаем сборку презентации. Агенты-исследователи приступают к работе...\n"
            "Это займет около 1-2 минут. Я пришлю готовый файл презентации сразу после сборки!",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Получаем данные сессии
        theme = context.user_data.get("theme", "")
        file_path = context.user_data.get("text_file_path", "")
        images_dir = context.user_data.get("images_dir", "")
        
        # Если картинок загружено не было, сбрасываем папку
        if context.user_data.get("image_count", 0) == 0:
            images_dir = ""
            
        # Запуск CrewAI в фоновом потоке
        asyncio.create_task(
            run_agents_async(
                update, 
                context, 
                theme=theme, 
                file_path=file_path,
                user_images_dir=images_dir
            )
        )
        return ConversationHandler.END
        
    elif msg_text == "Отмена":
        return await cancel(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте мне фотографию (как фото) или нажмите кнопку «Собрать презентацию! 🚀»."
        )
        return STATE_IMAGES


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Прерывание диалога."""
    keyboard = [["🚀 Начать новую работу"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Диалог сброшен. Чтобы начать заново, нажмите на кнопку «🚀 Начать новую работу» или выберите команду /start в меню.",
        reply_markup=reply_markup
    )
    
    # Удаляем временную папку картинок пользователя, если она была создана
    images_dir = context.user_data.get("images_dir")
    if images_dir and os.path.exists(images_dir):
        try:
            shutil.rmtree(images_dir)
        except Exception:
            pass
            
    context.user_data.clear()
    # Выход по отмене - возвращаем токен лаунчеру
    asyncio.create_task(shutdown_bot(context.application))
    return ConversationHandler.END

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СЕТЕВОЙ СТАБИЛЬНОСТИ
# =====================================================================
async def send_message_with_retry(context, chat_id, text, reply_markup=None, parse_mode=None, retries=3, delay=5):
    """Отправка текстового сообщения с автоматическими повторами при таймаутах."""
    for attempt in range(retries):
        try:
            return await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                connect_timeout=30.0,
                read_timeout=30.0
            )
        except Exception as e:
            if attempt == retries - 1:
                raise e
            logger.warning(f"Ошибка отправки сообщения (попытка {attempt+1}/{retries}): {e}. Повтор через {delay} сек...")
            await asyncio.sleep(delay)

async def send_document_with_retry(context, chat_id, file_path, caption, retries=3, delay=5):
    """Отправка тяжелого файла (презентации или отчета) с автоматическими повторами."""
    for attempt in range(retries):
        try:
            with open(file_path, "rb") as doc_file:
                return await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc_file,
                    filename=os.path.basename(file_path),
                    caption=caption,
                    connect_timeout=120.0,
                    read_timeout=120.0,
                    write_timeout=120.0
                )
        except Exception as e:
            if attempt == retries - 1:
                raise e
            logger.warning(f"Ошибка отправки файла {os.path.basename(file_path)} (попытка {attempt+1}/{retries}): {e}. Повтор через {delay} сек...")
            await asyncio.sleep(delay)

# =====================================================================
# ФОНОВЫЙ ЗАПУСК MAS ЧЕРЕЗ АСИНХРОННЫЙ ПОТОК
# =====================================================================
async def track_progress(chat_id, status_message, session_id):
    """Каждые 4 секунды считывает статус из JSON и обновляет лоадбар в Telegram."""
    status_path = os.path.join("output", f"status_{session_id}.json")
    
    # Очищаем старый файл статуса
    if os.path.exists(status_path):
        try:
            os.remove(status_path)
        except Exception:
            pass
            
    progress_chars = ["░", "█"]
    last_text = ""
    spinners = ["⏳", "⌛", "⚙️", "🧠", "💼", "📈", "📐", "📑"]
    
    # 360 итераций по 4 секунды = максимум 24 минуты
    for i in range(360):
        await asyncio.sleep(4)
        if not os.path.exists(status_path):
            continue
            
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
                progress = data.get("progress", 0)
                msg = data.get("message", "Сборка материалов...")
        except Exception:
            continue
            
        # Формируем графический лоадбар (10 символов)
        num_blocks = int(progress / 10)
        bar = progress_chars[1] * num_blocks + progress_chars[0] * (10 - num_blocks)
        current_spinner = spinners[i % len(spinners)]
        
        text = (
            f"🔄 **Прогресс выполнения запроса:**\n\n"
            f"[{bar}] {progress}%\n\n"
            f"{current_spinner} {msg}\n\n"
            f"_Это может занять 3-5 минут, так как агенты пишут подробные академические тексты объемом от 500 слов на раздел._"
        )
        
        if text != last_text:
            try:
                await status_message.edit_text(text, parse_mode="Markdown")
                last_text = text
            except Exception:
                pass
                
        if progress >= 100:
            break

async def run_agents_async(update: Update, context: ContextTypes.DEFAULT_TYPE, theme: str, file_path: str = "", user_images_dir: str = ""):
    """Обертка для запуска синхронного CrewAI в асинхронном потоке (to_thread)"""
    chat_id = update.effective_chat.id
    progress_task = None
    
    try:
        # Отправляем начальное сообщение с прогресс-баром
        status_message = await send_message_with_retry(
            context=context,
            chat_id=chat_id,
            text="🔄 **Прогресс выполнения запроса:**\n\n"
                 "[░░░░░░░░░░] 0%\n\n"
                 "⏳ Инициализация исследовательской группы...",
            parse_mode="Markdown"
        )
        
        # Запускаем отслеживание прогресса в фоновом режиме
        progress_task = asyncio.create_task(track_progress(chat_id, status_message, chat_id))
        
        # Получаем выбранный режим генерации
        mode = context.user_data.get("mode", "both")
        
        # Получаем настройки пресета и кастомные роли
        preset = context.user_data.get("preset", "ranepa")
        custom_context = context.user_data.get("custom_context", "")
        custom_researcher = context.user_data.get("custom_researcher", "")
        custom_critic = context.user_data.get("custom_critic", "")
        
        # Запуск блокирующей функции run_process в отдельном системном потоке
        # Это защищает event loop бота от блокировки
        from main import run_process
        from functools import partial
        loop = asyncio.get_running_loop()
        
        run_func = partial(
            run_process,
            topic=theme,
            uploaded_file_path=file_path,
            user_images_dir=user_images_dir,
            session_id=str(chat_id),
            mode=mode,
            preset=preset,
            custom_context=custom_context,
            custom_researcher=custom_researcher,
            custom_critic=custom_critic
        )
        
        final_pptx_path, final_docx_path = await loop.run_in_executor(
            None, 
            run_func
        )
        
        # Ждем, пока трекер закончит работу (или прерываем его, так как процесс завершен)
        if progress_task:
            progress_task.cancel()
        
        # Отправляем готовые файлы пользователю в Telegram с повторными попытками
        if os.path.exists(final_pptx_path) or os.path.exists(final_docx_path):
            await send_message_with_retry(
                context=context,
                chat_id=chat_id,
                text="🎉 **Готово!** Материалы успешно сгенерированы и оформлены по стандартам РАНХиГС.\n"
                     "Отправляю файлы...",
                parse_mode="Markdown"
            )
            
            if os.path.exists(final_pptx_path):
                await send_document_with_retry(
                    context=context,
                    chat_id=chat_id,
                    file_path=final_pptx_path,
                    caption="Ваша презентация для доклада комиссии. Удачи на защите!"
                )
                
            if os.path.exists(final_docx_path):
                await send_document_with_retry(
                    context=context,
                    chat_id=chat_id,
                    file_path=final_docx_path,
                    caption="Ваш текстовый отчет по теме исследования. Удачи на защите!"
                )
            
            # Предлагаем начать новую работу с помощью клавиатуры
            keyboard = [["🚀 Начать новую работу"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            await send_message_with_retry(
                context=context,
                chat_id=chat_id,
                text="Хотите подготовить еще одну тему? Нажмите кнопку ниже.",
                reply_markup=reply_markup
            )
        else:
            await send_message_with_retry(
                context=context,
                chat_id=chat_id,
                text="⚠️ Ошибка: сгенерированные файлы не были найдены на диске."
            )
            
        # Успешный выход - возвращаем токен лаунчеру
        asyncio.create_task(shutdown_bot(context.application))
            
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Ошибка во время генерации для чата {chat_id}: {e}", exc_info=True)
        try:
            os.makedirs("temp", exist_ok=True)
            with open(os.path.join("temp", "bot_error.txt"), "w", encoding="utf-8") as err_f:
                err_f.write(f"=== ОШИБКА ГЕНЕРАЦИИ ДЛЯ ЧАТА {chat_id} ===\n{tb_str}")
        except Exception as write_err:
            logger.error(f"Не удалось записать ошибку в temp/bot_error.txt: {write_err}")
            
        # В случае ошибки возвращаем кнопку для перезапуска
        keyboard = [["🚀 Начать новую работу"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await send_message_with_retry(
            context=context,
            chat_id=chat_id,
            text=f"❌ Произошла ошибка во время работы агентов:\n`{str(e)}`",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        # Выход по ошибке - возвращаем токен лаунчеру
        asyncio.create_task(shutdown_bot(context.application))
        
    finally:
        # Отменяем задачу отслеживания прогресса, если она активна
        if progress_task:
            progress_task.cancel()
        status_path = os.path.join("output", f"status_{chat_id}.json")
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass
                
        # Удаляем временный текстовый файл после завершения процесса
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        # Удаляем временную папку картинок пользователя после завершения процесса
        if user_images_dir and os.path.exists(user_images_dir):
            try:
                shutil.rmtree(user_images_dir)
            except Exception:
                pass

# =====================================================================
# НАСТРОЙКА КНОПОК И МЕНЮ ПРИ СТАРТЕ
# =====================================================================
async def handle_health_check(reader, writer):
    try:
        await reader.read(1024)
        response = "HTTP/1.1 200 OK\r\nContent-Length: 14\r\nContent-Type: text/plain\r\n\r\nBot is running\n"
        writer.write(response.encode('utf-8'))
        await writer.drain()
    except Exception as e:
        logger.error(f"[HEALTH-CHECK] Ошибка HTTP-запроса: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def start_health_check_server():
    port = int(os.getenv("PORT", 7860))
    try:
        server = await asyncio.start_server(handle_health_check, '0.0.0.0', port)
        logger.info(f"[HEALTH-CHECK] HTTP-сервер для проверки доступности запущен на порту {port}")
        async with server:
            await server.serve_forever()
    except Exception as e:
        logger.error(f"[HEALTH-CHECK] Не удалось запустить HTTP-сервер: {e}")

async def post_init(application: Application) -> None:
    """Установка меню команд бота в левом нижнем углу интерфейса Telegram"""
    await application.bot.set_my_commands([
        BotCommand("start", "🚀 Запустить / Начать сначала"),
        BotCommand("cancel", "❌ Сбросить текущий диалог")
    ])
    # Запускаем фоновый монитор таймаута неактивности
    asyncio.create_task(idle_timeout_monitor(application))
    # Запускаем фоновый HTTP-сервер для прохождения Health check на Hugging Face
    asyncio.create_task(start_health_check_server())

# =====================================================================
# ТОЧКА ВХОДА БОТА
# =====================================================================
def check_and_start_deepseek_proxy():
    """Проверяет провайдера ИИ и запускает локальный прокси-сервер DeepSeek на порту 9655 в фоновом режиме."""
    provider = os.getenv("LLM_PROVIDER", "hybrid").strip().lower()
    if provider not in ["hybrid", "deepseek"]:
        print("[LLM-BALANCER] Провайдер ИИ не требует локального прокси DeepSeek. Пропускаем запуск.")
        return

    import socket
    port = 9655
    # Проверяем, запущен ли уже прокси-сервер на порту 9655
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_running = s.connect_ex(('127.0.0.1', port)) == 0
        
    if is_running:
        print(f"[DS-PROXY] Локальный прокси-сервер уже запущен на порту {port}.")
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    node_path = os.path.join(base_dir, "node-portable", "node-v22.11.0-win-x64", "node.exe")
    server_path = os.path.join(base_dir, "FreeDeepseekAPI", "server.js")
    
    # Проверка наличия Node.js (локального переносного или системного)
    if not (os.path.exists(node_path) and os.path.exists(server_path)):
        import shutil
        system_node = shutil.which("node")
        if system_node and os.path.exists(server_path):
            node_path = system_node
        else:
            print("[DS-PROXY] Внимание: Node.js или server.js не найдены. Невозможно запустить прокси автоматически.")
            return
        
    print(f"[DS-PROXY] Запуск локального прокси-сервера DeepSeek на порту {port}...")
    import subprocess
    env = os.environ.copy()
    env["NON_INTERACTIVE"] = "1"
    
    try:
        # Настройки кроссплатформенного запуска
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        
        # Создаем лог-файл для прокси в папке temp
        os.makedirs(os.path.join(base_dir, "temp"), exist_ok=True)
        log_path = os.path.join(base_dir, "temp", "deepseek_proxy.log")
        log_file = open(log_path, "a", encoding="utf-8")
        
        proc = subprocess.Popen(
            [node_path, server_path],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        print(f"[DS-PROXY] Прокси-сервер запущен с PID {proc.pid}. Логи пишутся в temp/deepseek_proxy.log")
    except Exception as e:
        print(f"[DS-PROXY] Ошибка запуска прокси-сервера: {e}")

def main():
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        print("[ОШИБКА] Пожалуйста, укажите ваш токен TELEGRAM_BOT_TOKEN в файле .env!")
        return
        
    print("=== ЗАПУСК TELEGRAM-БОТА РАНХиГС ===")
    
    # Автоматически проверяем и запускаем локальный прокси
    check_and_start_deepseek_proxy()
    
    print("Бот успешно подключен и слушает команды в Telegram...")
    
    # Увеличиваем таймауты подключения и чтения до 60 секунд для борьбы с сетевыми задержками
    request_config = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0
    )
    
    # Проверяем, задан ли кастомный URL для API Telegram (например, прокси на Cloudflare Workers)
    # По умолчанию используется стандартный https://api.telegram.org/bot
    telegram_base_url = os.getenv("TELEGRAM_BASE_URL", "https://api.telegram.org/bot").strip()
    if not telegram_base_url.endswith("/bot"):
        if telegram_base_url.endswith("/"):
            telegram_base_url += "bot"
        else:
            telegram_base_url += "/bot"
            
    print(f"Использую Telegram API Endpoint: {telegram_base_url}")
    
    application = (
        Application.builder()
        .token(bot_token)
        .base_url(telegram_base_url)
        .request(request_config)
        .post_init(post_init)
        .build()
    )
    
    # Регистрируем перехватчик активности во главе очереди (группа -1)
    from telegram.ext import TypeHandler
    application.add_handler(TypeHandler(Update, update_activity), group=-1)
    
    # Настройка ConversationHandler с поддержкой как /start, так и кнопки
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^(🚀 Начать новую работу|/start)$"), start)
        ],
        states={
            STATE_THEME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme)],
            STATE_PRESET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_preset)],
            STATE_CUSTOM_CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_context)],
            STATE_CUSTOM_RESEARCHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_researcher)],
            STATE_CUSTOM_CRITIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_critic)],
            STATE_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mode)],
            STATE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)],
            STATE_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
            STATE_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_image)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    
    # Запускаем бесконечный цикл опроса сообщений (polling). close_loop=False предотвращает закрытие event loop лаунчера.
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == "__main__":
    main()
