from telegram.ext import CommandHandler, Updater, Job
from logging.handlers import RotatingFileHandler
from datetime import timedelta
from time import time
import requests
import logging
import random
import pickle
import json
import os


def porfirevich_request(user_text):
    porfirevich_endpoint = "https://models.dobro.ai/gpt2/medium/"
    payload_data = {"length": 50,
                    "num_samples": 5,
                    "prompt": "{0}".format(
                        user_text)}
    try:
        req = requests.post(porfirevich_endpoint, json=payload_data)
        return "{0}{1}".format(user_text, random.choice(
            req.json()['replies']))
    except requests.exceptions.RequestException as exception:
        logging.error(
            "Exception while connecting to Porfirevich: {0}".format(
                exception
            ))
        return user_text


def bot_start(update, context):
    bot_user_name = update.message.from_user.first_name
    bot_chat_desc = update.effective_chat.id
    context.bot.send_message(chat_id=bot_chat_desc,
                             text="Теперь все будет, {0} :3".format(
                                 bot_user_name
                             ))
    if "job" in context.chat_data:
        previous_job = context.chat_data["job"]
        previous_job.schedule_removal()
    new_job = context.job_queue.run_repeating(call_back,
                                              interval=timedelta(hours=1),
                                              context=update.message.chat_id,
                                              first=1)
    context.chat_data["job"] = new_job
    with open("bot_users.json", "r+") as file:
        try:
            user_data = json.load(file)
        except json.decoder.JSONDecodeError:
            user_data = {}
        if bot_chat_desc not in user_data.keys():
            user_data[bot_chat_desc] = bot_user_name
            file.seek(0)
            json.dump(user_data, file)


def bot_leave(update, context):
    if "job" not in context.chat_data:
        update.message.reply_text("Подписки еще нет! Жми /start")
        return
    job = context.chat_data["job"]
    job.schedule_removal()
    del context.chat_data["job"]
    update.message.reply_text("Больше никаких уведомлений."
                              "Если снова надо - жми /start")
    with open("bot_users.json", "w") as file:
        user_data = json.load(file)
        try:
            del user_data["{}".format(update.message.chat_id)]
            file.seek(0)
            json.dump(user_data, file)
        except KeyError:
            pass


def bot_random(update, context):
    bot_chat_desc = update.effective_chat.id
    context.bot.send_message(chat_id=bot_chat_desc,
                             text=porfirevich_request(
                                 "Я тебя люблю."))


def call_back(context):
    job = context.job
    context.bot.send_message(job.context,
                             text=porfirevich_request(
                                 "Я тебя люблю."))


def bot_error(update, context):
    logging.warning("Update {0} encountered error {1}".format(
        update, context.error))


def queue_load_jobs(job_queue):
    with open("bot_queue", "rb") as persistent_file:
        while True:
            try:
                next_run, data, state = pickle.load(persistent_file)
            except EOFError:
                break
            job = Job(**{var: val for var, val in zip((
                'callback',
                'interval',
                'repeat',
                'context',
                'days',
                'name',
                'tzinfo'
            ), data)})
            for var, val in zip(('_remove', '_enabled'), state):
                attribute = getattr(job, var)
                getattr(attribute, 'set' if val else 'clear')()

            job.job_queue = job_queue
            next_run -= time()
            job_queue._put(job, next_run)
    logging.info("Successfully loaded job queue")


def queue_save_jobs(job_queue):
    with job_queue._queue.mutex:
        if job_queue:
            jobs = job_queue._queue.queue
        else:
            jobs = []
        with open("bot_queue", "wb+") as persistent_file:
            for next_time, job in jobs:

                if job.name == "bot_queue_save":
                    continue

                data = tuple(getattr(job, var) for var in (
                    'callback',
                    'interval',
                    'repeat',
                    'context',
                    'days',
                    'name',
                    'tzinfo'))
                state = tuple(getattr(job, var).is_set() for var in (
                    '_remove', '_enabled'))
                pickle.dump((next_time, data, state), persistent_file)
    logging.info("Successfully saved job queue")


def bot_queue_save(context):
    queue_save_jobs(
        context.jobs)


def main():
    bot_token = os.environ["BOT_TOKEN"]

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler("bot_log.log",
                                  maxBytes=1000000,
                                  backupCount=5)
    formatter = logging.Formatter('%(asctime)s - '
                                  '%(name)s - '
                                  '%(levelname)s - '
                                  '%(message)s')

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    updater = Updater(token=bot_token,
                      use_context=True)



    dispatcher = updater.dispatcher

    start_handler = CommandHandler("start", bot_start,
                                   pass_job_queue=True)
    leave_handler = CommandHandler("leave", bot_leave,
                                   pass_job_queue=True)
    random_handler = CommandHandler("random", bot_random,
                                    pass_job_queue=True)

    job_queue = updater.job_queue
    job_queue.run_repeating(bot_queue_save, timedelta(
        minutes=1))
    try:
        queue_load_jobs(job_queue)
    except FileNotFoundError:
        pass

    dispatcher.add_handler(
        start_handler)
    dispatcher.add_handler(
        leave_handler)
    dispatcher.add_handler(
        random_handler)
    dispatcher.add_error_handler(
        bot_error)

    updater.start_polling()
    updater.idle()

    bot_queue_save(job_queue)


if __name__ == "__main__":
    main()
