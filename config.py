import os
from typing import List, Optional

class Config:
    """
    Bot Configuration Class
    Centralized configuration management for the bot
    """
    
    # ═══════════════════════════════════════════════════════════════
    #                    TELEGRAM API CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    API_ID: int = 21145186
    API_HASH: str = "daa53f4216112ad22b8a8f6299936a46"
    BOT_TOKEN: str = "7739933531:AAEyCzJ2XNOQEZ7o5cL9MScSlKwFij46Q_w"
    BOT_USERNAME: str = "vidxtractorbot"
    BOT_NAME: str = "VɪᴅXᴛʀᴀᴄᴛᴏʀ"
    
    # User session for faster uploads (optional)
    USER_SESSION: Optional[str] = os.environ.get(
        'USER_SESSION', 
        'BQGgvekAhGtAusgb66BX32jWE1XUescDL7s7WHqvH6cfRnf3SYD-IiNPjYhnZOMJkIgCSoklbnO_h0iQ_ad-jivTuQjw7Agop8Tx1GGFmQvBk38aARDevNLSruvp0ukAD3vrmpPHpw5siUgGRCYaOowF8z7w8fGAvgfC7godgPksgidWIaEZUOvEbxbcA2qMEDxEQ5UilBfm8SDvdXhJDzw4hPrsk5-4xPm_3Hc6KCLeOfin_uXiGuVhBwLuPdnbvcifa1u_WpFAduUw87nmmAzfIjEeAoUrhLqtqbdwaDF5ORtwoJ83f8kb04XEXbG13tURp_uf8Ll--PCc2QXfSlU_y117rgAAAAHCqoS-AA'
    )
    
    # ═══════════════════════════════════════════════════════════════
    #                    DATABASE CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    DB_URL: str = "mongodb+srv://ronaksaini922:NbeuC9FX8baih72p@cluster0.z6bb3.mongodb.net/cornhub?retryWrites=true&w=majority"
    DB_NAME: str = "cornhub"
    DATABASE_NAME: str = "cornhub"  # Alias for compatibility
    
    # ═══════════════════════════════════════════════════════════════
    #                    ADMIN CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    OWNER_ID: int = int(os.environ.get("OWNER_ID", "7560922302"))
    OWNER_TAG: str = os.environ.get("OWNER_TAG", "shizukawachan")
    
    # Parse admin list from environment
    ADMIN_LIST: List[str] = os.environ.get("ADMINS", "").split()
    ADMINS: List[int] = [int(admin) for admin in ADMIN_LIST if admin.isdigit()]
    ADMINS.append(OWNER_ID)  # Always include owner
    
    ADMIN_USERS: List[int] = [7560922302]  # Primary admin users
    
    # ═══════════════════════════════════════════════════════════════
    #                    DOWNLOAD CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    DOWNLOAD_DIR: str = "./downloads/"
    MAX_FILE_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB in bytes
    PROGRESS_UPDATE_INTERVAL: int = 3  # seconds
    SESSION_TIMEOUT: int = 300  # 5 minutes
    
    # ═══════════════════════════════════════════════════════════════
    #                    YT-DLP CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    YT_DLP_QUALITY: str = "best"
    AUDIO_QUALITY: str = "192"  # kbps for MP3
    
    # ═══════════════════════════════════════════════════════════════
    #                    DUMP CHANNELS
    # ═══════════════════════════════════════════════════════════════
    
    DUMP_CHAT_IDS: List[int] = [-1002544745474, -1002720183106, -1002460893841, -1002664225966, -1002770588536, -1002663153052, -1002857709387, -1002877451208, -1002774996981, -1002677745677, -1002765057759, -1002642208423]
    
    # ═══════════════════════════════════════════════════════════════
    #                    AUTHORIZATION
    # ═══════════════════════════════════════════════════════════════
    
    AUTHORIZED_USERS: List[int] = []  # Empty = public bot
    
    # ═══════════════════════════════════════════════════════════════
    #                    SERVER CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    FLASK_HOST: str = "0.0.0.0"
    FLASK_PORT: int = 8087
    LOG_LEVEL: str = "INFO"
    FORCE_PIC = os.environ.get("FORCE_PIC", "https://ibb.co/WNSk3Q6x")
    
    # ═══════════════════════════════════════════════════════════════
    #                    UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def is_authorized(user_id: int) -> bool:
        """Check if user is authorized to use the bot"""
        if not Config.AUTHORIZED_USERS:
            return True  # Public bot
        return user_id in Config.AUTHORIZED_USERS or user_id in Config.ADMIN_USERS
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in Config.ADMIN_USERS or user_id in Config.ADMINS
    
    @staticmethod
    def validate_config() -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        required_configs = [
            ('API_ID', Config.API_ID),
            ('API_HASH', Config.API_HASH),
            ('BOT_TOKEN', Config.BOT_TOKEN),
            ('DB_URL', Config.DB_URL),
        ]
        
        for name, value in required_configs:
            if not value:
                errors.append(f"{name} is required")
        
        if not Config.ADMIN_USERS and not Config.ADMINS:
            errors.append("At least one admin user is required")
            
        return errors
    
    @staticmethod
    def print_config() -> None:
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
