import asyncio
import logging
import os
import sys
import time
import threading
from datetime import datetime
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import FloodWait, ConnectionError as PyrogramConnectionError

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)

# Global variables
active_downloads = {}

# Flask app for keep-alive
app = Flask(__name__)

@app.route('/')
def home():
    return f"✅ {Config.BOT_NAME} is running!"

@app.route('/health')
def health():
    return {"status": "healthy", "active_downloads": len(active_downloads)}

@app.route('/stats')
def stats():
    return {
        "bot_name": Config.BOT_NAME,
        "active_downloads": len(active_downloads),
        "uptime": time.time()
    }

def run_flask():
    """Run Flask app in a separate thread"""
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=False, use_reloader=False)

class YTDLBot(Client):
    def __init__(self):
        super().__init__(
            "ytdl_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workdir="./sessions"
        )
    
    async def start(self):
        """Start the bot"""
        try:
            await super().start()
            me = await self.get_me()
            LOGGER.info(f"✅ Bot started successfully: @{me.username}")
            LOGGER.info(f"Bot ID: {me.id}")
            LOGGER.info(f"Bot Name: {me.first_name}")
            
            # Send startup message to admin
            try:
                await self.send_message(
                    Config.ADMIN_USERS[0], 
                    f"🤖 **{Config.BOT_NAME} Started!**\n\n"
                    f"✅ Bot is now online and ready to use.\n"
                    f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                LOGGER.warning(f"Could not send startup message to admin: {e}")
                
        except Exception as e:
            LOGGER.error(f"Error starting bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot"""
        try:
            # Send shutdown message to admin
            try:
                await self.send_message(
                    Config.ADMIN_USERS[0], 
                    f"🛑 **{Config.BOT_NAME} Stopping...**\n\n"
                    f"Bot is shutting down.\n"
                    f"🕐 Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                LOGGER.warning(f"Could not send shutdown message to admin: {e}")
            
            await super().stop()
            LOGGER.info("✅ Bot stopped successfully")
            
        except PyrogramConnectionError:
            LOGGER.info("Bot was already disconnected")
        except Exception as e:
            LOGGER.error(f"Error stopping bot: {e}")
    
    def run(self):
        """Run the bot with proper error handling"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Start Flask server in background
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            LOGGER.info(f"✅ Keep-alive server started on port {Config.FLASK_PORT}")
            
            # Start the bot
            loop.run_until_complete(self.start())
            
            # Keep running
            LOGGER.info("🚀 Bot is running. Press Ctrl+C to stop.")
            loop.run_forever()
            
        except KeyboardInterrupt:
            LOGGER.info("🛑 Received stop signal")
        except Exception as e:
            LOGGER.error(f"❌ Bot crashed: {e}")
        finally:
            try:
                if not self.is_connected:
                    LOGGER.info("Bot was already disconnected")
                else:
                    loop.run_until_complete(self.stop())
            except Exception as e:
                LOGGER.error(f"Error during cleanup: {e}")
            finally:
                loop.close()

# Create bot instance
bot = YTDLBot()

# Import handlers after bot creation
try:
    from commands.basic import *
    from commands.download import *
    LOGGER.info("✅ All command handlers loaded successfully")
except Exception as e:
    LOGGER.error(f"❌ Error loading handlers: {e}")
    sys.exit(1)

if __name__ == "__main__":
    print("🚀 Initializing YT-DLP Leech Bot...")
    print("=" * 50)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        LOGGER.error(f"Fatal error: {e}")
    finally:
        print("👋 Goodbye!")
