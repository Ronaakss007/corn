import motor.motor_asyncio
import os
from datetime import datetime, timedelta
import logging
from config import Config

# Initialize MongoDB client
try:
    dbclient = motor.motor_asyncio.AsyncIOMotorClient(
        Config.DB_URL,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000
    )
    database = dbclient[Config.DATABASE_NAME]
    
    # Collections
    user_data = database['users']
    stats_data = database['stats']
    download_history = database['download_history']
    watermark_settings = database['watermark_settings']
    settings_data = database['settings']
    join_requests = database['join_requests']
    bot_settings = database['bot_settings']
    file_settings = database['file_settings']
    admin_states = database['admin_states']
    
    logging.info("✅ Database connection initialized")
    
except Exception as e:
    logging.error(f"❌ Database connection failed: {e}")
    user_data = None
    stats_data = None
    download_history = None
    watermark_settings = None

async def get_all_users():
    try:
        users = []
        async for user in user_data.find({}):
            users.append(user)
        return users
    except Exception as e:
        logging.error(f"Error getting all users: {e}")
        return []

# ==================== FILE SETTINGS FUNCTIONS ====================

async def get_file_settings():
    """Get file settings from database"""
    try:
        settings = await settings_data.find_one({'_id': 'file_settings'})
        if not settings:
            # Default settings
            default_settings = {
                '_id': 'file_settings',
                'protect_content': False,
                'show_caption': True,
                'auto_delete': False,
                'auto_delete_time': 300,
                'spoiler_enabled': True,
                'inline_buttons': True,
                'button_name': '📺 ᴍᴏʀᴇ ᴠɪᴅᴇᴏs',
                'button_url': 'https://t.me/bhookibhabhi',
                'created_at': datetime.now()
            }
            await settings_data.insert_one(default_settings)
            return default_settings
        return settings
    except Exception as e:
        print(f"❌ Error getting file settings: {e}")
        return {
            'protect_content': False,
            'show_caption': True,
            'auto_delete': False,
            'auto_delete_time': 300,
            'inline_buttons': True,
            'spoiler_enabled': True,
            'button_name': '📺 ᴍᴏʀᴇ ᴠɪᴅᴇᴏs',
            'button_url': 'https://t.me/bhookibhabhi'
        }

async def update_file_setting(key, value):
    """Update a single file setting"""
    try:
        await settings_data.update_one(
            {'_id': 'file_settings'},
            {'$set': {key: value, 'updated_at': datetime.now()}},
            upsert=True
        )
        print(f"✅ Updated file setting: {key} = {value}")
        return True
    except Exception as e:
        print(f"❌ Error updating file setting {key}: {e}")
        return False

# ==================== WATERMARK ====================

async def get_watermark_settings():
    """Get watermark settings from database"""
    try:
        settings = await watermark_settings.find_one({'_id': 'watermark_config'})
        if not settings:
            # Default watermark settings
            default_settings = {
                '_id': 'watermark_config',
                'enabled': True,
                'text': Config.BOT_NAME,
                'position': 'bottom-right',
                'font_size': 32,
                'color': 'white',
                'shadow_color': 'black',
                'box_color': 'black@0.3',
                'created_at': datetime.now()
            }
            await watermark_settings.insert_one(default_settings)
            return default_settings
        return settings
    except Exception as e:
        logging.error(f"Error getting watermark settings: {e}")
        return {
            'enabled': True,
            'text': Config.BOT_NAME,
            'position': 'bottom-right',
            'font_size': 32,
            'color': 'white',
            'shadow_color': 'black',
            'box_color': 'black@0.3'
        }

async def update_watermark_settings(settings_data: dict):
    """Update watermark settings in database"""
    try:
        await watermark_settings.update_one(
            {'_id': 'watermark_config'},
            {'$set': settings_data},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating watermark settings: {e}")
        return False
    
# ==================== ADMIN STATE FUNCTIONS ====================


async def get_user_count():
    try:
        return await user_data.count_documents({})
    except Exception as e:
        logging.error(f"Error getting user count: {e}")
        return 0


async def store_admin_state(user_id, state, message_id=None, data=None):
    """Store admin state for input handling"""
    try:
        state_data = {
            'user_id': user_id,
            'state': state,
            'message_id': message_id,
            'data': data,
            'created_at': datetime.now()
        }
        
        await settings_data.update_one(
            {'_id': f'admin_state_{user_id}'},
            {'$set': state_data},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"❌ Error storing admin state: {e}")
        return False

async def get_admin_state(user_id):
    """Get admin state"""
    try:
        state = await settings_data.find_one({'_id': f'admin_state_{user_id}'})
        return state
    except Exception as e:
        print(f"❌ Error getting admin state: {e}")
        return None

async def clear_admin_state(user_id):
    """Clear admin state"""
    try:
        await settings_data.delete_one({'_id': f'admin_state_{user_id}'})
        return True
    except Exception as e:
        print(f"❌ Error clearing admin state: {e}")
        return False

async def is_premium_user(user_id):
    """Check if user is premium"""
    try:
        user = await get_user(user_id)
        return user.get('premium', False)
    except Exception as e:
        print(f"❌ Error checking premium status: {e}")
        return False


# ==================== USER FUNCTIONS ====================

def new_user(id):
    return {
        '_id': id,
        'username': "",
        'first_name': "",
        'total_downloads': 0,
        'total_size': 0,
        'favorite_sites': {},
        'join_date': datetime.now(),
        'last_activity': datetime.now(),
        'premium': False,
        'premium_expiry': 0
    }

async def get_user(user_id: int):
    try:
        user = await user_data.find_one({'_id': user_id})
        if not user:
            user = new_user(user_id)
            await user_data.insert_one(user)
            await increment_stats('total_users', 1)
            print(f"✅ New user created in DB: {user_id}")
        return user
    except Exception as e:
        logging.error(f"Error getting user {user_id}: {e}")
        return new_user(user_id)

async def register_new_user(user_id, username, first_name):
    """Register new user in database"""
    try:
        user = await get_user(user_id)
        await user_data.update_one(
            {'_id': user_id},
            {'$set': {'last_activity': datetime.now()}},
            upsert=True
        )
        print(f"✅ User {user_id} activity updated")
        return user
    except Exception as e:
        print(f"❌ Error updating user activity {user_id}: {e}")
        return await get_user(user_id)

async def is_premium_user(user_id):
    """Check if user is premium"""
    try:
        user = await user_data.find_one({'_id': user_id})
        if user:
            premium = user.get('premium', False)
            if premium:
                premium_expiry = user.get('premium_expiry', 0)
                if premium_expiry > 0:
                    import time
                    if time.time() > premium_expiry:
                        await user_data.update_one(
                            {'_id': user_id},
                            {'$set': {'premium': False, 'premium_expiry': 0}}
                        )
                        return False
                return True
        return False
    except Exception as e:
        logging.error(f"Error checking premium status for user {user_id}: {e}")
        return False

# ==================== STATS FUNCTIONS ====================

async def get_stats():
    try:
        stats = await stats_data.find_one({'_id': 'bot_stats'})
        if not stats:
            stats = {
                '_id': 'bot_stats',
                'total_downloads': 0,
                'total_users': 0,
                'sites': {},
                'file_types': {},
                'daily_stats': {},
                'created_at': datetime.now()
            }
            await stats_data.insert_one(stats)
        
        if 'sites' not in stats:
            stats['sites'] = {}
        elif not isinstance(stats['sites'], dict):
            stats['sites'] = {}
            
        return stats
    except Exception as e:
        logging.error(f"Error getting stats: {e}")
        return {
            '_id': 'bot_stats',
            'total_downloads': 0,
            'total_users': 0,
            'sites': {},
            'file_types': {},
            'daily_stats': {}
        }

async def increment_stats(field: str, value: int = 1):
    try:
        await stats_data.update_one(
            {'_id': 'bot_stats'},
            {'$inc': {field: value}},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error incrementing stats field {field}: {e}")
        return False

async def update_site_stats(site: str):
    try:
        await stats_data.update_one(
            {'_id': 'bot_stats'},
            {'$inc': {f'sites.{site}': 1}},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating site stats for {site}: {e}")
        return False

async def update_file_type_stats(file_type: str):
    try:
        await stats_data.update_one(
            {'_id': 'bot_stats'},
            {'$inc': {f'file_types.{file_type}': 1}},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating file type stats for {file_type}: {e}")
        return False

async def update_daily_stats():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        await stats_data.update_one(
            {'_id': 'bot_stats'},
            {'$inc': {f'daily_stats.{today}': 1}},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating daily stats: {e}")
        return False

# ==================== DOWNLOAD HISTORY ====================

async def add_download_history(user_id: int, url: str, file_name: str, file_size: int, file_type: str, site: str):
    try:
        history_entry = {
            'user_id': user_id,
            'url': url,
            'file_name': file_name,
            'file_size': file_size,
            'file_type': file_type,
            'site': site,
            'download_time': datetime.now(),
            'date': datetime.now().strftime("%Y-%m-%d")
        }
        await download_history.insert_one(history_entry)
        return True
    except Exception as e:
        logging.error(f"Error adding download history: {e}")
        return False

async def update_download_stats(user_id: int, username: str, url: str, file_size: int, file_type: str):
    """Update download statistics"""
    try:
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        site = parsed.netloc.lower().replace('www.', '')
        
        print(f"🔄 Updating stats for user {user_id}: site={site}, size={file_size}, type={file_type}")
        
        # Update user stats
        await user_data.update_one(
            {'_id': user_id},
            {
                '$inc': {
                    'total_downloads': 1,
                    'total_size': file_size,
                    f'favorite_sites.{site}': 1
                },
                '$set': {
                    'last_activity': datetime.now()
                }
            },
            upsert=True
        )
        
        # Update username if provided
        if username and username.strip():
            await user_data.update_one(
                {'_id': user_id},
                {'$set': {'username': username.strip()}},
                upsert=True
            )
        
        # Update global stats
        await increment_stats('total_downloads', 1)
        await update_site_stats(site)
        await update_file_type_stats(file_type)
        await update_daily_stats()
        
        # Add to download history
        await add_download_history(user_id, url, "Downloaded File", file_size, file_type, site)
        
        print(f"✅ Successfully updated stats for user {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating download stats for user {user_id}: {e}")
        return False

# ==================== FORCE SUB FUNCTIONS  ====================


async def get_settings():
    """Get bot settings from database"""
    try:
        settings = await settings_data.find_one({'_id': 'bot_settings'})
        if not settings:
            # Default settings
            default_settings = {
                '_id': 'bot_settings',
                'FORCE_SUB_CHANNELS': [],
                'REQUEST_SUB_CHANNELS': [],
                'created_at': datetime.now()
            }
            await settings_data.insert_one(default_settings)
            return default_settings
        return settings
    except Exception as e:
        logging.error(f"Error getting settings: {e}")
        return {
            'FORCE_SUB_CHANNELS': [],
            'REQUEST_SUB_CHANNELS': []
        }
    

async def remove_join_request(user_id: int, channel_id: int):
    """Remove join request when user joins"""
    try:
        await join_requests.delete_one({
            "user_id": user_id,
            "channel_id": channel_id
        })
        print(f"✅ Removed join request for user {user_id} in channel {channel_id}")
        return True
    except Exception as e:
        print(f"❌ Error removing join request: {e}")
        return False
    
async def store_join_request(user_id: int, channel_id: int):
    """Store a join request in the database"""
    try:
        request_data = {
            "user_id": user_id,
            "channel_id": channel_id,
            "status": "pending",
            "created_at": datetime.now()
        }
        
        # Use upsert to avoid duplicates
        await join_requests.update_one(
            {"user_id": user_id, "channel_id": channel_id},
            {"$set": request_data},
            upsert=True
        )
        print(f"✅ Stored join request for user {user_id} in channel {channel_id}")
        return True
    except Exception as e:
        print(f"❌ Error storing join request: {e}")
        return False

async def has_pending_request(user_id: int, channel_id: int) -> bool:
    """Check if a user has a pending join request for a channel in database"""
    try:
        # Convert channel_id to int if it's a string
        if isinstance(channel_id, str):
            channel_id = int(channel_id)
            
        request = await join_requests.find_one({
            "user_id": user_id, 
            "channel_id": channel_id,
            "status": "pending"
        })
        result = request is not None
        print(f"🔍 DB Check: Pending request for user {user_id} in channel {channel_id}: {result}")
        return result
    except Exception as e:
        print(f"❌ Error checking pending request in DB: {e}")
        return False
    
# ==================== UTILITY FUNCTIONS ====================

def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if bytes_value == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(bytes_value, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_value / p, 2)
    return f"{s} {size_names[i]}"

print("✅ Database functions loaded successfully")

