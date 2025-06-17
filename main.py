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
from pyrogram.errors import FloodWait, RPCError

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
    try:
        app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=False, use_reloader=False)
    except Exception as e:
        LOGGER.error(f"Flask server error: {e}")

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
                if self.is_connected:
                    await self.send_message(
                        Config.ADMIN_USERS[0], 
                        f"🛑 **{Config.BOT_NAME} Stopping...**\n\n"
                        f"Bot is shutting down.\n"
                        f"🕐 Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
            except Exception as e:
                LOGGER.warning(f"Could not send shutdown message to admin: {e}")
            
            if self.is_connected:
                await super().stop()
                LOGGER.info("✅ Bot stopped successfully")
            else:
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
                if hasattr(self, 'is_connected') and self.is_connected:
                    loop.run_until_complete(self.stop())
                else:
                    LOGGER.info("Bot was already disconnected")
            except Exception as e:
                LOGGER.error(f"Error during cleanup: {e}")
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

# Create bot instance
bot = YTDLBot()

# Basic command handlers
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    try:
        user_name = message.from_user.first_name or "User"
        user_id = message.from_user.id
        
        welcome_text = f"👋 **Welcome {user_name}!**\n\n"
        welcome_text += f"🤖 **{Config.BOT_NAME}**\n\n"
        welcome_text += "📥 I can download videos/audio from 1000+ websites!\n\n"
        welcome_text += "🚀 **Quick Start:**\n"
        welcome_text += "• Send any video URL to download\n"
        welcome_text += "• Send `/help` for more information\n\n"
        welcome_text += f"👤 **Your ID:** `{user_id}`"
        
        await message.reply_text(welcome_text)
        LOGGER.info(f"✅ START command processed for user {user_id}")
        
    except Exception as e:
        LOGGER.error(f"❌ Error in start command: {e}")
        await message.reply_text("❌ An error occurred!")

@bot.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    try:
        help_text = f"🆘 **{Config.BOT_NAME} - Help**\n\n"
        help_text += "📋 **Available Commands:**\n\n"
        help_text += "🔹 `/start` - Start the bot\n"
        help_text += "🔹 `/help` - Show this help message\n"
        help_text += "🔹 `/ping` - Test bot response\n\n"
        help_text += "📝 **How to use:**\n\n"
        help_text += "• Simply send any video URL from supported sites\n"
        help_text += "• The bot will automatically download and send the video\n\n"
        help_text += "🌐 **Supported sites:** YouTube, Instagram, TikTok, Facebook, Twitter, and 1000+ more!"
        
        await message.reply_text(help_text)
        
    except Exception as e:
        LOGGER.error(f"❌ Error in help command: {e}")
        await message.reply_text("❌ An error occurred!")

@bot.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    """Handle /ping command"""
    try:
        start_time = time.time()
        ping_msg = await message.reply_text("🏓 Pinging...")
        end_time = time.time()
        
        ping_time = round((end_time - start_time) * 1000, 2)
        
        ping_text = f"🏓 **Pong!**\n\n"
        ping_text += f"⚡ **Response Time:** {ping_time}ms\n"
        ping_text += f"✅ **Status:** Bot is alive and responding\n"
        ping_text += f"🤖 **Bot Name:** {Config.BOT_NAME}"
        
        await ping_msg.edit_text(ping_text)
        LOGGER.info(f"✅ PING command processed for user {message.from_user.id}")
        
    except Exception as e:
        LOGGER.error(f"❌ Error in ping command: {e}")

@bot.on_message(filters.private & ~filters.command(["start", "help", "ping"]))
async def handle_url_message(client: Client, message: Message):
    """Handle URL messages for download"""
    try:
        if not message.text:
            return
            
        url = message.text.strip()
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            await message.reply_text(
                "❌ **Invalid URL**\n\n"
                "Please send a valid URL starting with http:// or https://\n\n"
                "**Example:** https://youtube.com/watch?v=VIDEO_ID"
            )
            return
        
        user_id = message.from_user.id
        
        # Check if user already has active download
        if user_id in active_downloads:
            await message.reply_text(
                "❌ **Active Download**\n\n"
                "You already have an active download!\n"
                "Please wait for it to complete."
            )
            return
        
        # Send processing message
        status_msg = await message.reply_text(
            f"📥 **Processing Download**\n\n"
            f"🔗 **URL:** `{url}`\n"
            f"⏳ **Status:** Analyzing URL..."
        )
        
        # Mark user as having active download
        active_downloads[user_id] = {
            'url': url,
            'start_time': time.time(),
            'status_msg': status_msg
        }
        
        # Simulate download process (replace with actual download logic)
        await asyncio.sleep(2)
        
        await status_msg.edit_text(
            f"✅ **Download Complete!**\n\n"
            f"🔗 **URL:** `{url}`\n"
            f"📁 **Status:** Ready to send\n\n"
            f"⚠️ **Note:** Actual download functionality will be implemented soon!"
        )
        
        # Remove from active downloads
        if user_id in active_downloads:
            del active_downloads[user_id]
        
        LOGGER.info(f"✅ URL processed for user {user_id}: {url}")
        
    except Exception as e:
        LOGGER.error(f"❌ Error in handle_url_message: {e}")
        await message.reply_text(f"❌ **Error:** {str(e)}")
        # Remove from active downloads
        if message.from_user.id in active_downloads:
            del active_downloads[message.from_user.id]

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
