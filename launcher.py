import os
import sys
import subprocess
import asyncio
import logging
import time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Загружаем ключи из .env
load_dotenv()
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

# Настраиваем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("Launcher")

# Глобальные переменные состояния
should_start_bot = False
last_chat_id = None

async def start_launcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды запуска."""
    global should_start_bot, last_chat_id
    chat_id = update.effective_chat.id
    last_chat_id = chat_id
    logger.info(f"[ЛАУНЧЕР] Получен запрос на запуск от чата {chat_id}")
    
    await update.message.reply_text(
        "🎓 **Инициализация ИИ-агентов РАНХиГС**\n\n"
        "Поднимаю локальные соединения и запускаю исследовательскую команду. "
        "Это займет около 15 секунд... 🚀",
        parse_mode="Markdown"
    )
    
    should_start_bot = True
    # Останавливаем приложение лаунчера, чтобы освободить токен Telegram
    await context.application.stop()

def run_main_bot():
    """Запускает bot.py как подпроцесс и блокирует поток до его завершения."""
    logger.info("[ЛАУНЧЕР] Запуск основного процесса bot.py...")
    python_exe = sys.executable
    cmd = [python_exe, "-u", "bot.py"]
    
    try:
        # Запускаем и ожидаем завершения
        res = subprocess.run(cmd, check=False)
        logger.info(f"[ЛАУНЧЕР] bot.py завершил работу с кодом {res.returncode}")
    except Exception as e:
        logger.error(f"[ЛАУНЧЕР] Ошибка при запуске bot.py: {e}")

async def send_standby_message():
    """Отправляет одноразовое сообщение о переходе в спящий режим."""
    global last_chat_id
    if not last_chat_id:
        return
        
    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        keyboard = [["🚀 Начать новую работу"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await bot.send_message(
            chat_id=last_chat_id,
            text="😴 **Бот переведен в спящий режим для экономии памяти.**\n\n"
                 "Когда вам снова понадобятся ИИ-агенты, просто нажмите кнопку ниже.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"[ЛАУНЧЕР] Не удалось отправить сообщение о спящем режиме: {e}")

def main():
    global should_start_bot
    
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        print("[ОШИБКА] Пожалуйста, укажите ваш токен TELEGRAM_BOT_TOKEN в файле .env!")
        return
        
    print("=== ЗАПУСК ДИСПЕТЧЕРА БОТА РАНХиГС (STANDBY) ===")
    print("Диспетчер ожидает команду запуска в Telegram...")
    
    while True:
        should_start_bot = False
        
        # Создаем легковесный инстанс бота
        app = Application.builder().token(bot_token).build()
        
        # Регистрируем только базовые команды запуска
        app.add_handler(CommandHandler("start", start_launcher))
        app.add_handler(MessageHandler(filters.Regex("^(🚀 Начать новую работу|/start)$"), start_launcher))
        
        # Запускаем поллинг лаунчера (это блокирующий синхронный вызов)
        app.run_polling(close_loop=False)
        
        # Если вышли из run_polling с флагом запуска
        if should_start_bot:
            # Запуск основного тяжелого бота в блокирующем режиме
            run_main_bot()
            
            # После завершения работы основного бота отправляем пользователю уведомление
            asyncio.run(send_standby_message())
            
            # Небольшая пауза перед повторным стартом лаунчера
            time.sleep(2)
        else:
            # Если лаунчер был остановлен обычным способом (Ctrl+C), прерываем цикл
            break

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print("\nДиспетчер успешно остановлен.")
