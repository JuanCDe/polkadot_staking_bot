import yaml
import logging
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from init_functions import core
from utils import validate_addr, generate_legend, generate_bot_disclaimer

config = yaml.safe_load(open("./config.yml"))
in_prod = config["in_prod"]
tk = config["TGTOKEN_prod"] if in_prod else config["TGTOKEN_dev"]

updater = Updater(token=tk)
dispatcher = updater.dispatcher


def button(update, context: CallbackContext):
    # Lo que hace tras darle a un botón
    query = update.callback_query
    query.answer()

    # query contiene el valor asignado al botón presionado
    # Aquí irían las funciones principales de legend, core, help, stats, mensaje de disclaimer, etc
    if query.data == "/legend":
        legend(update, context)
    elif query.data == "/info":
        context.bot.send_message(text=f"Just paste a valid Polkadot nominator address",
                                 chat_id=update.effective_chat.id)
    elif query.data == "/disclaimer":
        disclaimer(update, context)
    else:
        context.bot.send_message(text=f"{query.data} will be available soon",
                                 chat_id=update.effective_chat.id)


def start(update, context: CallbackContext):
    keyboard = [
        [
            InlineKeyboardButton("\U0001F969 Info", callback_data='/info'),
            InlineKeyboardButton("\U0001F4D1 Legend", callback_data='/legend')
        ],
        [
            InlineKeyboardButton("\U0001F913 Stats", callback_data='/stats'),
            InlineKeyboardButton("Disclaimer", callback_data='/disclaimer')
         ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Please choose:', reply_markup=reply_markup)


def legend(update, context):
    text_out = generate_legend()
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=text_out, parse_mode='Markdown')


def disclaimer(update, context):
    text_out = generate_bot_disclaimer()
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=text_out, parse_mode='Markdown')


def info(update, context):
    logger = logging.getLogger("polkadot_staking_bot")
    logger.info("Asked")
    addr = update.message.text
    wordnumber = len(str.split(addr))
    if wordnumber == 1:
        valid_addr = validate_addr(addr)
        if valid_addr == "polkadot":
            nom_shorted = addr.replace(addr[4:-4], "...")
            querying_msg = f'Querying info for {nom_shorted}\n' \
                           f'It can take a while.'
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=querying_msg, parse_mode='Markdown')
            try:
                text_out = core(addr)
            except Exception as ex:
                logger.error(f'> 82: {ex}')
        elif valid_addr == "Invalid address":
            text_out = "Invalid address"
        else:
            text_out = f'Sorry, "{valid_addr}" addresses are not supported yet'
    else:
        text_out = "Paste one valid Polkadot nominator address"
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=text_out, parse_mode='Markdown',
                             disable_web_page_preview=True)
    logger.info("Replied")


def start_bot():
    logger = logging.getLogger("polkadot_staking_bot")
    try:
        # Función de botones
        updater.dispatcher.add_handler(CallbackQueryHandler(button))

        # Función de start
        start_handler = CommandHandler("start", start)
        dispatcher.add_handler(start_handler)

        # Función de legenda
        legend_handler = CommandHandler("legend", legend)
        dispatcher.add_handler(legend_handler)

        # función de disclaimer
        disclaimer_handler = CommandHandler("disclaimer", disclaimer)
        dispatcher.add_handler(disclaimer_handler)

        # Qué hacer cuando se pone un comando no recogido o un texto simple
        dispatcher.add_handler(MessageHandler(Filters.command, start))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, info))

        updater.start_polling()
        logger.info(f'> Telegram initialized')

    except Exception as ex:
        logger.error(f'> 121: {ex}')


def stop_bot():
    updater.stop()
