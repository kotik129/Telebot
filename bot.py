from telebot import TeleBot
from config import *
from speechkit import text_to_speech, speech_to_text
from yandex_gpt import *
from validators import *
from database import *
from creds.creds import get_bot_token 

create_database()
bot = TeleBot(get_bot_token())
@bot.message_handler(commands=['debug'])
def debug(message):
    with open("logs.txt", "rb") as f:
        bot.send_document(message.chat.id, f)

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id,"приветствую я говоряший телеграмм бот пример моих возможностей в следуюшем собшении чтобы использовать мои возможности /tts если есть вопросы /help")
    with open('tts.ogg', 'rb') as voice:
        bot.send_voice(message.chat.id, voice.read())

@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.send_message(message.chat.id,"""Приветствую вас я телеграмм бот для озвучивания текста я обладаю лимитами 200 символов на сообшение и 1000 на пользователя чтобы начать озвучку /tts""")

@bot.message_handler(commands=['tts'])
def tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Отправь следующим сообщением текст, чтобы я его озвучил!')
    bot.register_next_step_handler(message, tts)

def tts(message):
    user_id = message.from_user.id
    text = message.text

    if message.content_type != 'text':
        bot.send_message(user_id, 'Отправь текстовое сообщение')
        return

    text_symbol = is_tts_symbol_limit(message, text)

    if text_symbol is None:
        return

    full_gpt_message = [message.text, 'user', 0, text_symbol, 0]
    add_message(user_id=user_id, full_message=full_gpt_message)
    status, content = text_to_speech(text)

    if status:
        bot.send_voice(user_id, content)
    else:
        bot.send_message(user_id, content)

@bot.message_handler(commands=['stt'])
def stt_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Отправь голосовое сообщение, чтобы я его распознал!')
    bot.register_next_step_handler(message, stt)

def stt(message):
    user_id = message.from_user.id

    if not message.voice:
        return

    stt_blocks = is_stt_block_limit(message, message.voice.duration)
    if not stt_blocks:
        return

    file_id = message.voice.file_id
    file_info = bot.get_file(file_id)
    file = bot.download_file(file_info.file_path)
    status, text = speech_to_text(file)

    if status:
        full_gpt_message = [text, 'user', 0, 0, stt_blocks]
        add_message(user_id=user_id, full_message=full_gpt_message)
        bot.send_message(user_id, text, reply_to_message_id=message.id)
    else:
        bot.send_message(user_id, text)


@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.chat.id
    status_check_users, error_message = check_number_of_users(user_id)

    if not status_check_users:
        bot.send_message(user_id, error_message)
        return

    stt_blocks, error_message = is_stt_block_limit(message, message.voice.duration)

    if not stt_blocks:
        bot.send_message(user_id, error_message)
        return

    file_id = message.voice.file_id
    file_info = bot.get_file(file_id)
    file = bot.download_file(file_info.file_path)
    status_stt, stt_text = speech_to_text(file)

    if not status_stt:
        bot.send_message(user_id, stt_text)
        return

    add_message(user_id=user_id, full_message=[stt_text, 'user', 0, 0, stt_blocks])
    last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
    total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)

    if error_message:
        bot.send_message(user_id, error_message)
        return

    status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)

    if not status_gpt:
        bot.send_message(user_id, answer_gpt)
        return

    total_gpt_tokens += tokens_in_answer
    tts_symbols, error_message = is_tts_symbol_limit(message, answer_gpt)
    add_message(user_id=user_id, full_message=[answer_gpt, 'assistant', total_gpt_tokens, tts_symbols, 0])

    if error_message:
        bot.send_message(user_id, error_message)
        return

    status_tts, voice_response = text_to_speech(answer_gpt)

    if status_tts:
        bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)
    else:
        bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)


@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        user_id = message.from_user.id
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)  # мест нет =(
            return

        full_user_message = [message.text, 'user', 0, 0, 0]
        add_message(user_id=user_id, full_message=full_user_message)
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)

        if error_message:
            bot.send_message(user_id, error_message)
            return

        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)

        if not status_gpt:
            bot.send_message(user_id, answer_gpt)
            return

        total_gpt_tokens += tokens_in_answer
        full_gpt_message = [answer_gpt, 'assistant', total_gpt_tokens, 0, 0]
        add_message(user_id=user_id, full_message=full_gpt_message)
        bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)  # отвечаем пользователю текстом

    except Exception as e:
        logging.error(e)
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")

@bot.message_handler(func=lambda: True)

def handler(message):
    bot.send_message(message.from_user.id, "Отправь мне голосовое или текстовое сообщение, и я тебе отвечу")

bot.polling()