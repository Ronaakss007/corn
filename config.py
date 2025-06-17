import os

class Config:
    # Telegram Bot Configuration - Hardcoded
    API_ID = 21145186
    API_HASH = "daa53f4216112ad22b8a8f6299936a46"
    BOT_TOKEN = "7739933531:AAEyCzJ2XNOQEZ7o5cL9MScSlKwFij46Q_w"
    
    # Bot Settings
    BOT_NAME = "VɪᴅXᴛʀᴀᴄᴛᴏʀ"
    USER_SESSION = os.environ.get('USER_SESSION', 'BQGgvekAhGtAusgb66BX32jWE1XUescDL7s7WHqvH6cfRnf3SYD-IiNPjYhnZOMJkIgCSoklbnO_h0iQ_ad-jivTuQjw7Agop8Tx1GGFmQvBk38aARDevNLSruvp0ukAD3vrmpPHpw5siUgGRCYaOowF8z7w8fGAvgfC7godgPksgidWIaEZUOvEbxbcA2qMEDxEQ5UilBfm8SDvdXhJDzw4hPrsk5-4xPm_3Hc6KCLeOfin_uXiGuVhBwLuPdnbvcifa1u_WpFAduUw87nmmAzfIjEeAoUrhLqtqbdwaDF5ORtwoJ83f8kb04XEXbG13tURp_uf8Ll--PCc2QXfSlU_y117rgAAAAHCqoS-AA')
    BOT_USERNAME = "vidxtractorbot"
    
    # Download Configuration
    DOWNLOAD_DIR = "./downloads/"
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    PROGRESS_UPDATE_INTERVAL = 3  # seconds
    SESSION_TIMEOUT = 300  # 5 minutes
    
    # YT-DLP Configuration
    YT_DLP_QUALITY = "best"
    AUDIO_QUALITY = "192"  # kbps for MP3
    
    # Database Configuration
    DB_URL = "mongodb+srv://ronaksaini922:NbeuC9FX8baih72p@cluster0.z6bb3.mongodb.net/cornhub?retryWrites=true&w=majority"
    DB_NAME = "cornhub"
    DATABASE_NAME = "cornhub"  # Added this alias to fix the error
    
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
    
    @staticmethod
    def validate_config():
        """Validate configuration values"""
        errors = []
        
        if not Config.API_ID:
            errors.append("API_ID is required")
        if not Config.API_HASH:
            errors.append("API_HASH is required")
        if not Config.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        if not Config.DB_URL:
            errors.append("DB_URL is required")
        if not Config.ADMIN_USERS:
            errors.append("At least one ADMIN_USER is required")
            
        return errors
    
    @staticmethod
    def print_config():
        """Print configuration summary (without sensitive data)"""
        print("📋 Configuration Summary:")
        print(f"   Bot Name: {Config.BOT_NAME}")
        print(f"   Bot Username: @{Config.BOT_USERNAME}")
        print(f"   Download Dir: {Config.DOWNLOAD_DIR}")
        print(f"   Max File Size: {Config.MAX_FILE_SIZE / (1024*1024*1024):.1f} GB")
        print(f"   YT-DLP Quality: {Config.YT_DLP_QUALITY}")
        print(f"   Audio Quality: {Config.AUDIO_QUALITY} kbps")
        print(f"   Database: {Config.DB_NAME}")
        print(f"   Dump Channels: {len(Config.DUMP_CHAT_IDS)} channels")
        print(f"   Admin Users: {len(Config.ADMIN_USERS)} users")
        print(f"   Authorized Users: {'Public' if not Config.AUTHORIZED_USERS else len(Config.AUTHORIZED_USERS)}")
        print(f"   Flask Port: {Config.FLASK_PORT}")
        print(f"   Log Level: {Config.LOG_LEVEL}")
