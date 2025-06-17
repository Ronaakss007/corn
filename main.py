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
import signal

# Third-party imports
import pytz
from pyrogram import Client
from pyrogram.enums import ParseMode
from flask import Flask
import pyrogram.utils

# Local imports
from config import Config

# ═══════════════════════════════════════════════════════════════════════════════
#                                CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

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
    try:
        flask_app.run(
            host="0.0.0.0",
            port=FLASK_PORT,
            debug=False,
            use_reloader=False
        )
    except Exception as e:
        print(f"❌ Flask server error: {e}")

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
        self.is_running = False

    async def start(self):
        """
        Bot startup procedure
        - Setup directories
        - Get bot info
        - Send startup notification
        """
        try:
            await super().start()
            self.is_running = True
            
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
                await self.stop()
                return False
            
            # ═══════════════════════════════════════════════════════════════════════
            #                         FINAL CONFIGURATION
            # ═══════════════════════════════════════════════════════════════════════
            
            # Set default parse mode
            self.set_parse_mode(ParseMode.HTML)
            
            # Send startup notification to admin
            await self._send_startup_notification()
            
            print("🎉 Bot is now fully operational!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start bot: {e}")
            self.is_running = False
            return False

    async def stop(self, *args):
        """
        Bot shutdown procedure
        """
        if self.is_running:
            try:
                await super().stop()
                self.is_running = False
                print("🛑 Bot stopped gracefully")
            except Exception as e:
                print(f"❌ Error during bot shutdown: {e}")
        else:
            print("🛑 Bot is already stopped")

    def run(self):
        """
        Main bot execution method
        - Setup event loop
        - Handle graceful shutdown
        - Manage exceptions
        """
        loop = None
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Setup signal handlers for graceful shutdown
            def signal_handler(signum, frame):
                print(f"\n🛑 Received signal {signum}, shutting down...")
                if self.is_running:
                    loop.create_task(self.stop())
                loop.stop()
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Start the bot
            startup_success = loop.run_until_complete(self.start())
            
            if not startup_success:
                print("❌ Bot startup failed")
                return
                
            print("🔄 Bot event loop started")
            
            # Keep running until interrupted
            loop.run_forever()
            
        except KeyboardInterrupt:
            print("\n🛑 Keyboard interrupt received, shutting down...")
            
        except Exception as e:
            print(f"❌ Bot crashed: {e}")
            
        finally:
            # Ensure clean shutdown
            try:
                if loop and not loop.is_closed():
                    if self.is_running:
                        loop.run_until_complete(self.stop())
                    loop.close()
                print("✅ Cleanup completed")
            except Exception as e:
                print(f"❌ Error during cleanup: {e}")

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
                print("✅ Startup notification sent to admin")
                
        except Exception as e:
            print(f"❌ Failed to send startup notification: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
#                                MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main function to initialize and run the bot"""
    print("🚀 Initializing YT-DLP Leech Bot...")
    print("=" * 50)
    
    # Print configuration summary
    Config.print_config()
    print("=" * 50)
    
    # Validate configuration
    config_errors = Config.validate_config()
    if config_errors:
        print("❌ Configuration errors found:")
        for error in config_errors:
            print(f"   - {error}")
        sys.exit(1)
    
    print("✅ Configuration validated successfully")
    
    # Start keep-alive server
    keep_alive()
    
    # Initialize and run the bot
    bot = Bot()
    bot.run()

if __name__ == "__main__":
    main()
