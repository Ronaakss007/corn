import os
import sys
import asyncio
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from threading import Thread
import signal

import pytz
from pyrogram import Client
from pyrogram.enums import ParseMode
from flask import Flask
import pyrogram.utils

from config import Config

pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

user_client = None
FLASK_PORT = 8087

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "🤖 ᴠɪᴅxᴛʀᴀᴄᴛᴏʀ ɪs ʀᴜɴɴɪɴɢ!"

@flask_app.route('/status')
def status():
    return {
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "service": "ᴠɪᴅxᴛʀᴀᴄᴛᴏʀ ʙᴏᴛ"
    }

def run_flask():
    try:
        flask_app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ ғʟᴀsᴋ sᴇʀᴠᴇʀ ᴇʀʀᴏʀ: {e}")

def keep_alive():
    thread = Thread(target=run_flask, daemon=True)
    thread.start()
    print(f"✅ ᴋᴇᴇᴘ-ᴀʟɪᴠᴇ sᴇʀᴠᴇʀ sᴛᴀʀᴛᴇᴅ ᴏɴ ᴘᴏʀᴛ {FLASK_PORT}")

async def initialize_user_client():
    global user_client
    try:
        if Config.USER_SESSION:
            user_client = Client(
                "user_session",
                session_string=Config.USER_SESSION,
                api_id=Config.API_ID,
                api_hash=Config.API_HASH
            )
            await user_client.start()
            print("✅ ᴜsᴇʀ sᴇssɪᴏɴ ɪɴɪᴛɪᴀʟɪᴢᴇᴅ")
        else:
            print("⚠️ ɴᴏ ᴜsᴇʀ sᴇssɪᴏɴ ᴘʀᴏᴠɪᴅᴇᴅ")
    except Exception as e:
        print(f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ɪɴɪᴛɪᴀʟɪᴢᴇ ᴜsᴇʀ sᴇssɪᴏɴ: {e}")
        user_client = None

def get_indian_time():
    ist_timezone = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist_timezone)

def setup_directories():
    try:
        os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
        print(f"✅ ᴅᴏᴡɴʟᴏᴀᴅ ᴅɪʀᴇᴄᴛᴏʀʏ ᴄʀᴇᴀᴛᴇᴅ: {Config.DOWNLOAD_DIR}")
        return True
    except Exception as e:
        print(f"❌ ᴇʀʀᴏʀ ᴄʀᴇᴀᴛɪɴɢ ᴅɪʀᴇᴄᴛᴏʀɪᴇs: {e}")
        return False

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="ytdl_bot",
            api_hash=Config.API_HASH,
            api_id=Config.API_ID,
            plugins={"root": "commands"},
            bot_token=Config.BOT_TOKEN
        )
        self.is_running = False

    async def start(self):
        try:
            await super().start()
            self.is_running = True
            
            bot_info = await self.get_me()
            self.username = bot_info.username
            self.uptime = get_indian_time()
            
            print(f"🚀 sᴛᴀʀᴛɪɴɢ {bot_info.first_name} (@{bot_info.username})")
            
            if not setup_directories():
                print("❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴇᴛᴜᴘ ᴅɪʀᴇᴄᴛᴏʀɪᴇs")
                await self.stop()
                return False
            
            self.set_parse_mode(ParseMode.HTML)
            await self._send_startup_notification()
            
            print("🎉 ʙᴏᴛ ɪs ɴᴏᴡ ғᴜʟʟʏ ᴏᴘᴇʀᴀᴛɪᴏɴᴀʟ!")
            return True
            
        except Exception as e:
            print(f"❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴛᴀʀᴛ ʙᴏᴛ: {e}")
            self.is_running = False
            return False

    async def stop(self, *args):
        if self.is_running:
            try:
                await super().stop()
                self.is_running = False
                print("🛑 ʙᴏᴛ sᴛᴏᴘᴘᴇᴅ ɢʀᴀᴄᴇғᴜʟʟʏ")
            except Exception as e:
                print(f"❌ ᴇʀʀᴏʀ ᴅᴜʀɪɴɢ ʙᴏᴛ sʜᴜᴛᴅᴏᴡɴ: {e}")

    def run(self):
        loop = None
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            def signal_handler(signum, frame):
                print(f"\n🛑 ʀᴇᴄᴇɪᴠᴇᴅ sɪɢɴᴀʟ {signum}, sʜᴜᴛᴛɪɴɢ ᴅᴏᴡɴ...")
                if self.is_running:
                    loop.create_task(self.stop())
                loop.stop()
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            startup_success = loop.run_until_complete(self.start())
            
            if not startup_success:
                print("❌ ʙᴏᴛ sᴛᴀʀᴛᴜᴘ ғᴀɪʟᴇᴅ")
                return
                
            print("🔄 ʙᴏᴛ ᴇᴠᴇɴᴛ ʟᴏᴏᴘ sᴛᴀʀᴛᴇᴅ")
            loop.run_forever()
            
        except KeyboardInterrupt:
            print("\n🛑 ᴋᴇʏʙᴏᴀʀᴅ ɪɴᴛᴇʀʀᴜᴘᴛ ʀᴇᴄᴇɪᴠᴇᴅ")
            
        except Exception as e:
            print(f"❌ ʙᴏᴛ ᴄʀᴀsʜᴇᴅ: {e}")
            
        finally:
            try:
                if loop and not loop.is_closed():
                    if self.is_running:
                        loop.run_until_complete(self.stop())
                    loop.close()
                print("✅ ᴄʟᴇᴀɴᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇᴅ")
            except Exception as e:
                print(f"❌ ᴇʀʀᴏʀ ᴅᴜʀɪɴɢ ᴄʟᴇᴀɴᴜᴘ: {e}")

    async def _send_startup_notification(self):
        try:
            startup_message = f"» <b>ᴠɪᴅxᴛʀᴀᴄᴛᴏʀ sᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n⏰ <i>sᴛᴀʀᴛᴇᴅ:</i> {self.uptime.strftime('%Y-%m-%d %H:%M:%S IST')}\n\n😴 <i>ᴅɪᴅ ɴᴏᴛ sʟᴇᴇᴘ ᴛɪʟʟ ɴᴏᴡ...</i>"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("» ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ", url="https://t.me/nyxgenie"),
                 InlineKeyboardButton("» ᴜᴘᴅᴀᴛᴇs", url="https://t.me/bhookibhabhi")]
            ])
            
            if Config.ADMIN_USERS:
                await self.send_photo(
                    chat_id=Config.ADMIN_USERS[0],
                    photo=Config.FORCE_PIC,
                    caption=startup_message,
                    reply_markup=keyboard
                )
                print("✅ sᴛᴀʀᴛᴜᴘ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ sᴇɴᴛ")
                
        except Exception as e:
            print(f"❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ sᴛᴀʀᴛᴜᴘ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ: {e}")

def main():
    print("🚀 ɪɴɪᴛɪᴀʟɪᴢɪɴɢ ᴠɪᴅxᴛʀᴀᴄᴛᴏʀ ʙᴏᴛ...")
    print("=" * 50)
    
    Config.print_config()
    print("=" * 50)
    
    config_errors = Config.validate_config()
    if config_errors:
        print("❌ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ ᴇʀʀᴏʀs ғᴏᴜɴᴅ:")
        for error in config_errors:
            print(f"   - {error}")
        sys.exit(1)
    
    print("✅ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ ᴠᴀʟɪᴅᴀᴛᴇᴅ")
    
    keep_alive()
    
    bot = Bot()
    bot.run()

if __name__ == "__main__":
    main()
