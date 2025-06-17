# ═══════════════════════════════════════════════════════════════════════════════
#                           YT-DLP LEECH BOT - MAIN FILE
# ═══════════════════════════════════════════════════════════════════════════════
# Author: Your Name
# Description: Advanced YT-DLP downloader bot
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
#                                   IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════

# Standard library imports
import os
import sys
import asyncio
from datetime import datetime
from threading import Thread

# Third-party imports
import pytz
from pyrogram import Client
from pyrogram.enums import ParseMode
from flask import Flask
from dotenv import load_dotenv
import pyrogram.utils

# Local imports
from config import Config

# ═══════════════════════════════════════════════════════════════════════════════
#                                CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Load environment variables
load_dotenv(".env")

# Configure Pyrogram settings
pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

# Server configuration
FLASK_PORT = 8087  # Flask keep-alive port

# ═══════════════════════════════════════════════════════════════════════════════
#                              FLASK KEEP-ALIVE SERVER
# ═══════════════════════════════════════════════════════════════════════════════

# Initialize Flask app for keep-alive functionality
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Health check endpoint for keep-alive service"""
    return "🤖 YT-DLP Leech Bot is running!"

@flask_app.route('/status')
def status():
    """Bot status endpoint"""
    return {
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "service": "YT-DLP Leech Bot"
    }

def run_flask():
    """Run Flask keep-alive server"""
    flask_app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=False,
        use_reloader=False
    )

def keep_alive():
    """Start Flask keep-alive server in separate thread"""
    thread = Thread(target=run_flask, daemon=True)
    thread.start()
    print(f"✅ Keep-alive server started on port {FLASK_PORT}")

# ═══════════════════════════════════════════════════════════════════════════════
#                                UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_indian_time():
    """
    Get current time in Indian Standard Time (IST)
    
    Returns:
        datetime: Current IST datetime object
    """
    ist_timezone = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist_timezone)

def setup_directories():
    """Setup required directories"""
    try:
        os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
        print(f"✅ Download directory created: {Config.DOWNLOAD_DIR}")
        return True
    except Exception as e:
        print(f"❌ Error creating directories: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
#                                  BOT CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class Bot(Client):
    """
    Main Bot class extending Pyrogram Client
    Handles bot initialization, startup, and shutdown procedures
    """
    
    def __init__(self):
        """Initialize the bot with configuration parameters"""
        super().__init__(
            name="ytdl_bot",
            api_hash=Config.API_HASH,
            api_id=Config.API_ID,
            plugins={"root": "commands"},  # Auto-load all command plugins
            bot_token=Config.BOT_TOKEN
        )

    async def start(self):
        """
        Bot startup procedure
        - Setup directories
        - Get bot info
        - Send startup notification
        """
        await super().start()
        
        # Get bot information
        bot_info = await self.get_me()
        self.username = bot_info.username
        self.uptime = get_indian_time()
        
        print(f"🚀 Starting {bot_info.first_name} (@{bot_info.username})")
        
        # ═══════════════════════════════════════════════════════════════════════
        #                        DIRECTORY SETUP
        # ═══════════════════════════════════════════════════════════════════════
        
        if not setup_directories():
            print("❌ Failed to setup directories")
            sys.exit(1)
        
        # ═══════════════════════════════════════════════════════════════════════
        #                         FINAL CONFIGURATION
        # ═══════════════════════════════════════════════════════════════════════
        
        # Set default parse mode
        self.set_parse_mode(ParseMode.HTML)
        
        # Send startup notification to admin
        await self._send_startup_notification()
        
        print("🎉 Bot is now fully operational!")

    async def stop(self, *args):
        """
        Bot shutdown procedure
        """
        await super().stop()
        print("🛑 Bot stopped gracefully")

    def run(self):
        """
        Main bot execution method
        - Setup event loop
        - Handle graceful shutdown
        - Manage exceptions
        """
        try:
            # Get or create event loop
            loop = asyncio.get_event_loop()
            
            # Start the bot
            loop.run_until_complete(self.start())
            print("🔄 Bot event loop started")
            
            # Keep running until interrupted
            loop.run_forever()
            
        except KeyboardInterrupt:
            print("\n🛑 Shutting down bot...")
            
        except Exception as e:
            print(f"❌ Bot crashed: {e}")
            
        finally:
            # Ensure clean shutdown
            if not loop.is_closed():
                loop.run_until_complete(self.stop())
            print("✅ Cleanup completed")

    # ═══════════════════════════════════════════════════════════════════════════
    #                            PRIVATE METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def _send_startup_notification(self):
        """Send startup notification to bot admin"""
        try:
            startup_message = (
                f"<b>"
                f"🤖 YT-DLP Bot Started Successfully...!\n\n"
                f"<blockquote>⏰ Started: {self.uptime.strftime('%Y-%m-%d %H:%M:%S IST')}\n"
                f"🆔 Bot ID: {(await self.get_me()).id}\n"
                f"👨‍💻 Bot Username: @{self.username}"
                f"</blockquote></b>"
            )
            
            # Send to first admin user
            if Config.ADMIN_USERS:
                await self.send_message(
                    chat_id=Config.ADMIN_USERS[0],
                    text=startup_message
                )
                
        except Exception as e:
            print(f"Failed to send startup notification: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
#                                MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🚀 Initializing YT-DLP Leech Bot...")
    print("=" * 50)
    
    # Start keep-alive server
    keep_alive()
    
    # Initialize and run the bot
    bot = Bot()
    bot.run()
