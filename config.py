import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Telegram Bot Configuration
    API_ID = int(os.getenv("API_ID", "21145186"))
    API_HASH = os.getenv("API_HASH", "daa53f4216112ad22b8a8f6299936a46")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "7806754713:AAE9kpSexdgBeIBlwy-3sJ4Bxu6IJn5CETs")
    # DUMP_CHAT_IDS=-1002519738807 -1002460893841 -1002664225966
    
    # Bot Settings
    BOT_NAME = "YT-DLP Leech Bot"
    BOT_USERNAME = "ytdl_leech_bot"
    
    # Download Configuration
    DOWNLOAD_DIR = "./downloads/"
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    SESSION_TIMEOUT = 300  # 5 minutes
    
    # Admin Users
    ADMIN_USERS = [7560922302]
    
    # Logging
    LOG_LEVEL = "INFO"
    
    @staticmethod
    def is_admin(user_id):
        """Check if user is admin"""
        return user_id in Config.ADMIN_USERS

# Test configuration when imported
if __name__ == "__main__":
    print("=== CONFIG TEST ===")
    print(f"API_ID: {Config.API_ID}")
    print(f"API_HASH: {Config.API_HASH}")
    print(f"BOT_TOKEN: {Config.BOT_TOKEN}")
    print(f"BOT_NAME: {Config.BOT_NAME}")
