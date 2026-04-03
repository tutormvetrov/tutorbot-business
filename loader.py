from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from data import config
from utils.fsm_storage import JsonFileStorage

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = JsonFileStorage(config.FSM_STORAGE_FILE)
dp = Dispatcher(storage=storage)
