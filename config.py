import os
from dotenv import load_dotenv

class Config:
    # Telegram Bot Configuration - Hardcoded
    API_ID = 21145186
    API_HASH = "daa53f4216112ad22b8a8f6299936a46"
    BOT_TOKEN = "7806754713:AAE9kpSexdgBeIBlwy-3sJ4Bxu6IJn5CETs"
    
    # Bot Settings
    BOT_NAME = "YT-DLP Leech Bot"
    BOT_USERNAME = "ytdl_leech_bot"
    
    # Download Configuration
    DOWNLOAD_DIR = "./downloads/"
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    PROGRESS_UPDATE_INTERVAL = 3  # seconds
    SESSION_TIMEOUT = 300  # 5 minutes
    
    # YT-DLP Configuration
    YT_DLP_QUALITY = "best"
    AUDIO_QUALITY = "192"  # kbps for MP3
    
    # Database Configuration - Fixed connection string
    DB_URL = "mongodb+srv://ronaksaini922:NbeuC9FX8baih72p@cluster0.z6bb3.mongodb.net/cornhub?retryWrites=true&w=majority"
    DB_NAME = "cornhub"
    
    # Dump Channels - Fixed format (integers, not strings)
    DUMP_CHAT_IDS = [-1002519738807, -1002460893841, -1002664225966]
    
    # Authorized Users (optional - leave empty for public bot)
    AUTHORIZED_USERS = []  # Add user IDs: [123456789, 987654321]
    
    # Admin Users
    ADMIN_USERS = [7560922302]
    
    # Logging
    LOG_LEVEL = "INFO"
    
    # Flask Keep-alive settings
    FLASK_HOST = "0.0.0.0"
    FLASK_PORT = 8087
    
    @staticmethod
    def is_authorized(user_id):
        """Check if user is authorized to use the bot"""
        if not Config.AUTHORIZED_USERS:
            return True  # Public bot
        return user_id in Config.AUTHORIZED_USERS or user_id in Config.ADMIN_USERS
    
    @staticmethod
    def is_admin(user_id):
        """Check if user is admin"""
        return user_id in Config.ADMIN_USERS
