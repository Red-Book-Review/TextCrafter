import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    PicklePersistence,
    ConversationHandler,
)
from telegram.ext.filters import TEXT, COMMAND, PHOTO
import logging
import os
from dotenv import load_dotenv

# Настройки логирования: Включаем логирование, чтобы видеть, что происходит.
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из файла .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в .env файле!")
    exit(1)  # Завершаем программу, если токен не найден
print(f"BOT_TOKEN: {BOT_TOKEN}")  # Вывод токена для отладки

# Константы для состояний (states) ConversationHandler.  Каждое состояние - это шаг в диалоге.
SELECTING_ACTION, SELECT_PHOTO_OR_TEXT, ADDING_PHOTO, ADDING_CAPTION, ADDING_BUTTON_TEXT, ADDING_BUTTON_URL, ADDING_CHANNEL, SETTING_CHANNEL = range(8)


async def start(update: Update, context: CallbackContext) -> int:
    """Начало диалога.  Отправляет приветственное сообщение и переводит бота в состояние SELECTING_ACTION."""
    await update.message.reply_text(
        "Привет!  Я бот для отправки сообщений с фото и кнопкой в канал.  "
        "Отправьте /add, чтобы добавить новое сообщение, /settings чтобы сменить канал, "
        "/preview, чтобы посмотреть предпросмотр."
    )
    return SELECTING_ACTION  # Возвращаем состояние, указывающее, что делать дальше.


async def add(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /add.  Начинает процесс добавления нового сообщения."""
    await update.message.reply_text("Хотите добавить фото к сообщению? Отправьте фото или /skip, чтобы пропустить.")
    return SELECT_PHOTO_OR_TEXT  # Переходим к вопросу о фото


async def handle_photo_or_skip(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ответ пользователя на вопрос о фото (или команду /skip)."""
    if update.message.text and update.message.text.lower() == '/skip':
        # Пользователь пропустил добавление фото
        context.user_data['photo_file_id'] = None  # Явно сохраняем, что фото нет
        await update.message.reply_text("Хорошо, без фото. Теперь введите текст подписи:")
        return ADDING_CAPTION  # Переходим к вводу подписи
    elif update.message.photo:
        # Пользователь отправил фото
        photo_file_id = update.message.photo[-1].file_id  # Получаем ID файла фото (самого большого размера)
        context.user_data['photo_file_id'] = photo_file_id  # Сохраняем ID файла в user_data
        await update.message.reply_text("Отлично! Теперь введите текст подписи к изображению.")
        return ADDING_CAPTION  # Переходим к вводу подписи
    else:
        # Пользователь отправил что-то не то
        await update.message.reply_text("Пожалуйста, отправьте фото или /skip")
        return SELECT_PHOTO_OR_TEXT #Остаемся в том же состоянии


async def handle_caption(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод подписи (текста сообщения)."""
    context.user_data['caption'] = update.message.text  # Сохраняем текст подписи в user_data
    await update.message.reply_text("Введите текст для кнопки:")
    return ADDING_BUTTON_TEXT  # Переходим к вводу текста кнопки


async def handle_button_text(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод текста для кнопки."""
    context.user_data['button_text'] = update.message.text  # Сохраняем текст кнопки
    await update.message.reply_text("Введите URL для кнопки:")
    return ADDING_BUTTON_URL  # Переходим к вводу URL кнопки


async def handle_button_url(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод URL для кнопки, проверяет URL и переходит к предпросмотру/отправке."""
    button_url = update.message.text
    # Простая проверка URL: начинается с http:// или https://
    if not (button_url.startswith("http://") or button_url.startswith("https://")):
        await update.message.reply_text("Пожалуйста, введите корректный URL, начинающийся с http:// или https://")
        return ADDING_BUTTON_URL  # Остаемся в том же состоянии, ожидаем правильный URL

    context.user_data['button_url'] = button_url  # Сохраняем URL
    await update.message.reply_text("Чтобы увидеть предпросмотр, введите /preview. Для отправки введите название канала (если вы еще не настроили его с помощью /settings).")
    return ADDING_CHANNEL  # Переходим к запросу имени канала (или отправке, если канал уже настроен)


async def send_message_to_channel(update: Update, context: CallbackContext) -> int:
    """
    Отправляет сообщение в канал. Эта функция вызывается, когда пользователь вводит имя канала
    ИЛИ когда канал уже сохранен в bot_data (после /settings).
    """
    logger.info(f"send_message_to_channel called. bot_data: {context.bot_data}")  # ЛОГИРУЕМ

    # 1. ОПРЕДЕЛЯЕМ, КУДА ОТПРАВЛЯТЬ (chat_id)
    if 'channel' in context.bot_data and context.bot_data['channel']:
        # Канал УЖЕ установлен (через /settings). Используем его.
        chat_id = context.bot_data['channel']
        logger.info(f"Using saved channel: {chat_id}")  # ЛОГИРУЕМ
    else:
        # Канал НЕ установлен.  Берем из сообщения пользователя.
        chat_identifier = update.message.text
        logger.info(f"Received channel identifier: {chat_identifier}")  # ЛОГИРУЕМ

        try:
            # Пытаемся преобразовать в число (chat_id может быть числом)
            chat_id = int(chat_identifier)
        except ValueError:
            # chat_identifier - это строка (username)
            chat_id = chat_identifier
            if not chat_id.startswith('@'):
                await update.message.reply_text("Пожалуйста, введите имя канала, начиная с символа @ (например, @mychannel), или его числовой ID.")
                return ADDING_CHANNEL  # Остаемся в том же состоянии

    # 2. ПОЛУЧАЕМ ДАННЫЕ ДЛЯ ОТПРАВКИ
    photo_file_id = context.user_data.get('photo_file_id')  # Может быть None
    caption = context.user_data.get('caption')
    button_text = context.user_data.get('button_text')
    button_url = context.user_data.get('button_url')

    # 3. ПРОВЕРКА НАЛИЧИЯ ДАННЫХ
    if not (photo_file_id or caption):
        await update.message.reply_text("Ошибка: Должно быть фото и/или текст. Пожалуйста, начните сначала (/add).")
        return ConversationHandler.END  # Завершаем диалог

    # 4. ОТПРАВКА СООБЩЕНИЯ (с обработкой ошибок)
    try:
        if photo_file_id:
            success = await send_photo_with_caption_and_button(chat_id, photo_file_id, caption, button_text, button_url)
        elif caption: #добавил проверку на наличие текста
            success = await send_text_with_button(chat_id, caption, button_text, button_url)
        else: #Если нет ни фото ни текста
            await update.message.reply_text("Ошибка: нечего отправлять")
            return ConversationHandler.END

        if success:
            await update.message.reply_text(f"Сообщение отправлено в канал {chat_id}!")
        else:
            await update.message.reply_text(
                f"Не удалось отправить сообщение в канал {chat_id}.  "
                f"Убедитесь, что бот добавлен в канал и имеет права администратора."
            )

    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка при отправке: {e}")
        logger.exception("Ошибка при отправке сообщения:")  # ЛОГИРУЕМ с traceback

    return ConversationHandler.END  # Завершаем диалог


async def send_photo_with_caption_and_button(chat_id: str | int, photo_file_id: str, caption: str, button_text: str, button_url: str) -> bool:
    """Отправляет фото с подписью и кнопкой. Возвращает True при успехе, False при ошибке."""
    try:
        keyboard = [[InlineKeyboardButton(button_text, url=button_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot = telegram.Bot(token=BOT_TOKEN)  # Создаем объект бота
        await bot.send_photo(chat_id=chat_id, photo=photo_file_id, caption=caption, reply_markup=reply_markup)
        logger.info(f"Фото успешно отправлено в чат {chat_id}")
        return True  # Успешная отправка
    except telegram.error.Forbidden:
        logger.error(f"Бот не авторизован (чат {chat_id}).")
        return False  # Бот заблокирован в канале
    except telegram.error.BadRequest as e:
        if "Chat not found" in str(e):
            logger.error(f"Чат {chat_id} не найден.")
        elif "Not enough rights" in str(e):
            logger.error(f"Недостаточно прав (чат {chat_id}).")
        elif "Photo must be non-empty" in str(e):
            logger.error(f"Получено пустое фото.")
        else:
            logger.error(f"Ошибка BadRequest: {e}")
        return False  # Ошибка BadRequest (разные причины)
    except telegram.error.TelegramError as e:
        logger.error(f"Ошибка Telegram API: {e}")
        return False  # Другая ошибка Telegram API
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}")
        return False  # Непредвиденная ошибка


async def send_text_with_button(chat_id: str | int, text: str, button_text: str, button_url: str) -> bool:
    """Отправляет текстовое сообщение с кнопкой.  Возвращает True при успехе, False при ошибке."""
    try:
        keyboard = [[InlineKeyboardButton(button_text, url=button_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot = telegram.Bot(token=BOT_TOKEN)  # Создаем объект бота
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        logger.info(f"Текстовое сообщение успешно отправлено в чат {chat_id}")
        return True  # Успешная отправка
    except telegram.error.TelegramError as e:
        logger.error(f"Ошибка отправки текстового сообщения: {e}")
        return False  # Ошибка Telegram API


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущую операцию и завершает диалог."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text("Операция отменена.")
    context.user_data.clear() #Очистка
    return ConversationHandler.END  # Завершаем диалог


async def settings(update: Update, context: CallbackContext) -> int:
    """Начинает диалог установки канала."""
    await update.message.reply_text("Введите имя канала (@username), куда будут отправляться сообщения:")
    return SETTING_CHANNEL  # Переходим к ожиданию ввода имени канала


async def set_channel(update: Update, context: CallbackContext) -> int:
    """Сохраняет введенное имя канала в bot_data."""
    channel_name = update.message.text
    if not channel_name.startswith('@'):
        await update.message.reply_text("Имя канала должно начинаться с @")
        return SETTING_CHANNEL

    context.bot_data['channel'] = channel_name  # Сохраняем имя канала
    logger.info(f"Установлен канал: {channel_name}")  # ЛОГИРУЕМ
    await update.message.reply_text(f"Канал {channel_name} сохранен.")
    return ConversationHandler.END  # Завершаем диалог


async def preview(update: Update, context: CallbackContext) -> int:
    """Отправляет предпросмотр сообщения (показывает пользователю, как будет выглядеть сообщение)."""
    photo_file_id = context.user_data.get('photo_file_id')
    caption = context.user_data.get('caption')
    button_text = context.user_data.get('button_text')
    button_url = context.user_data.get('button_url')

    if not (photo_file_id or caption):
        await update.message.reply_text("Нечего предпросматривать. Добавьте фото и/или текст с помощью /add.")
        return SELECTING_ACTION #Возврат в начало

    if photo_file_id:
        await send_photo_with_caption_and_button(update.effective_chat.id, photo_file_id, caption, button_text, button_url)
    else:
        await send_text_with_button(update.effective_chat.id, caption, button_text, button_url)

    await update.message.reply_text("Это предпросмотр.")
    return ADDING_CHANNEL  # Возвращаемся к запросу канала (или отправке)


def main():
    """Основная функция бота."""
    # Создаем объект persistence (для сохранения данных между перезапусками)
    persistence = PicklePersistence(filepath="bot_data.pickle")

    # Создаем Application (приложение Telegram-бота)
    application = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()

    # Создаем ConversationHandler для добавления поста (/add)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add)],  # Точка входа - команда /add
        states={
            # Состояния (шаги диалога)
            SELECT_PHOTO_OR_TEXT: [MessageHandler(PHOTO | TEXT, handle_photo_or_skip)],
            ADDING_CAPTION: [MessageHandler(TEXT & ~COMMAND, handle_caption)],
            ADDING_BUTTON_TEXT: [MessageHandler(TEXT & ~COMMAND, handle_button_text)],
            ADDING_BUTTON_URL: [MessageHandler(TEXT & ~COMMAND, handle_button_url)],
            ADDING_CHANNEL: [MessageHandler(TEXT & ~COMMAND, send_message_to_channel)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("preview", preview)],
        # allow_reentry = True #Разрешаем повторный вход в диалог
    )

    # Создаем ConversationHandler для настроек канала (/settings)
    settings_handler = ConversationHandler(
        entry_points=[CommandHandler("settings", settings)],  # Точка входа - команда /settings
        states={
            SETTING_CHANNEL: [MessageHandler(TEXT & ~COMMAND, set_channel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Добавляем обработчики в приложение
    application.add_handler(CommandHandler("start", start))  # Обработчик команды /start
    application.add_handler(conv_handler)  # Обработчик диалога добавления поста
    application.add_handler(settings_handler) # Обработчик диалога настроек
    # application.add_handler(CommandHandler("preview", preview)) # preview теперь часть conv_handler, поэтому отдельный обработчик не нужен

    # Запускаем бота
    application.run_polling()


if __name__ == '__main__':
    main()