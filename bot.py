import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.parsemode import ParseMode

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = "https://strike-boy.github.io/tic-tac-toe_new/"

def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🎮 Играть в Tic-Tac-Toe", web_app={"url": WEB_APP_URL})]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Добро пожаловать в NEON Tic-Tac-Toe! 🎮\n\n"
        "Нажми кнопку ниже чтобы начать игру:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def help_command(update: Update, context: CallbackContext):
    """Обработчик команды /help"""
    help_text = (
        "🎮 *NEON Tic-Tac-Toe*\n\n"
        "🌟 *Возможности:*\n"
        "• 🤖 Игра с ИИ разных уровней\n" 
        "• 👥 Локальная игра на одном устройстве\n"
        "• 🌐 Онлайн-игра с друзьями\n"
        "• 💬 Чат во время игры\n\n"
        "🎯 *Как играть онлайн:*\n"
        "1. Создай комнату в игре\n"
        "2. Поделись кодом с другом\n"
        "3. Наслаждайтесь игрой!\n\n"
        "⚡ *Управление:*\n"
        "• Просто нажимай на клетки\n"
        "• Используй кнопку рестарт для новой игры"
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def error_handler(update: Update, context: CallbackContext):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    # Создаем updater и передаем токен
    updater = Updater(BOT_TOKEN, use_context=True)
    
    # Получаем диспетчер для регистрации обработчиков
    dp = updater.dispatcher
    
    # Добавляем обработчики
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    
    # Обработчик ошибок
    dp.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен и ожидает сообщений...")
    updater.start_polling()
    
    # Запускаем бота до принудительной остановки
    updater.idle()

if __name__ == "__main__":
    main()
