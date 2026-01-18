from telethon import TelegramClient
import os

api_id = 38564520
api_hash = "61b5819b845231a2ddb7e951acaca002"

client = TelegramClient("phantom_session", api_id, api_hash)

with client:
    print("✅ LOGIN OK — session saved")
