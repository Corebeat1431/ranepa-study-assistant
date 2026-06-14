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
stop_event = None

async def start_launcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды запуска."""
    global should_start_bot, last_chat_id, stop_event
    chat_id = update.effective_chat.id
    last_chat_id = chat_id
    logger.info(f"[ЛАУНЧЕР] Получен запрос на запуск от чата {chat_id}")
    
    try:
        await update.message.reply_text(
            "🎓 **Инициализация ИИ-агентов РАНХиГС**\n\n"
            "Поднимаю локальные соединения и запускаю исследовательскую команду. "
            "Это займет около 15 секунд... 🚀",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"[ЛАУНЧЕР] Не удалось отправить сообщение об инициализации: {e}")
    
    should_start_bot = True
    
    # Сигнализируем событию остановки завершить опрос
    if stop_event:
        stop_event.set()

def run_main_bot():
    """Запускает bot.py как подпроцесс и блокирует поток до его завершения."""
    global last_chat_id
    logger.info("[ЛАУНЧЕР] Запуск основного процесса bot.py...")
    python_exe = sys.executable
    cmd = [python_exe, "-u", "bot.py"]
    if last_chat_id:
        cmd.append(f"--start-chat-id={last_chat_id}")
    
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

async def run_launcher_async(bot_token_val):
    """Инициализирует и запускает опрос Telegram в асинхронном режиме."""
    global should_start_bot, stop_event
    should_start_bot = False
    stop_event = asyncio.Event()
    
    # Создаем легковесный инстанс бота
    app = Application.builder().token(bot_token_val).build()
    
    # Регистрируем только базовые команды запуска
    app.add_handler(CommandHandler("start", start_launcher))
    app.add_handler(MessageHandler(filters.Regex("^(🚀 Начать новую работу|/start)$"), start_launcher))
    
    # Ручной запуск компонентов апдейта без блокировки в run_polling()
    await app.initialize()
    if app.updater:
        await app.updater.start_polling()
    await app.start()
    
    logger.info("[ЛАУНЧЕР] Ожидание команды запуска в Telegram...")
    
    # Блокируем выполнение этой функции до тех пор, пока не сработает событие
    await stop_event.wait()
    
    logger.info("[ЛАУНЧЕР] Завершение опроса диспетчера...")
    
    # Чистый graceful shutdown
    if app.updater:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()

def main():
    global should_start_bot
    
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        print("[ОШИБКА] Пожалуйста, укажите ваш токен TELEGRAM_BOT_TOKEN в файле .env!")
        return
        
    print("=== ЗАПУСК ДИСПЕТЧЕРА БОТА РАНХиГС (STANDBY) ===")
    print("Диспетчер ожидает команду запуска в Telegram...")
    
    try:
        while True:
            # Запускаем асинхронный опрос в текущем цикле событий
            asyncio.run(run_launcher_async(bot_token))
            
            # Если вышли из опроса с флагом запуска
            if should_start_bot:
                run_main_bot()
                
                # После завершения работы основного бота отправляем пользователю уведомление
                asyncio.run(send_standby_message())
                
                # Небольшая пауза перед повторным стартом лаунчера
                time.sleep(2)
            else:
                # Если выход был вызван прерыванием (без флага should_start_bot), завершаем работу
                break
    except KeyboardInterrupt:
        print("\n[ЛАУНЧЕР] Работа диспетчера прервана пользователем.")

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print("\nДиспетчер успешно остановлен.")
