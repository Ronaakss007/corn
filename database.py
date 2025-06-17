import motor.motor_asyncio
import os
from datetime import datetime
import logging
from config import Config


# Initialize MongoDB client with better error handling
try:
    dbclient = motor.motor_asyncio.AsyncIOMotorClient(
        Config.DB_URL,
        serverSelectionTimeoutMS=5000,  # 5 second timeout
        connectTimeoutMS=5000,
        socketTimeoutMS=5000
    )
    database = dbclient[Config.DATABASE_NAME]
    
    # Collections
    user_data = database['users']
    stats_data = database['stats']
    download_history = database['download_history']
    
    logging.info("✅ Database connection initialized")
    
except Exception as e:
    logging.error(f"❌ Database connection failed: {e}")
    # Create dummy functions for offline mode
    user_data = None
    stats_data = None
    download_history = None

# Collections
user_data = database['users']
stats_data = database['stats']
download_history = database['download_history']
# Add this collection
watermark_settings = database['watermark_settings']

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

# User functions
async def update_user_count():
    """Update total user count in stats"""
    try:
        total_users = await get_user_count()
        await update_stats({'total_users': total_users})
        return True
    except Exception as e:
        logging.error(f"Error updating user count: {e}")
        return False

async def get_user(user_id: int):
    try:
        user = await user_data.find_one({'_id': user_id})
        if not user:
            # Create new user
            user = new_user(user_id)
            await user_data.insert_one(user)
            
            # Update total user count in stats (only for new users)
            await increment_stats('total_users', 1)
            print(f"✅ New user created in DB: {user_id}")
            
        return user
    except Exception as e:
        logging.error(f"Error getting user {user_id}: {e}")
        return new_user(user_id)



async def update_user(user_id: int, update_data: dict):
    try:
        await user_data.update_one(
            {'_id': user_id},
            {'$set': update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating user {user_id}: {e}")
        return False

async def get_user_count():
    try:
        return await user_data.count_documents({})
    except Exception as e:
        logging.error(f"Error getting user count: {e}")
        return 0

async def get_all_users():
    try:
        users = []
        async for user in user_data.find({}):
            users.append(user)
        return users
    except Exception as e:
        logging.error(f"Error getting all users: {e}")
        return []

async def get_top_users(limit: int = 10):
    try:
        users = []
        async for user in user_data.find({}).sort('total_downloads', -1).limit(limit):
            users.append(user)
        return users
    except Exception as e:
        logging.error(f"Error getting top users: {e}")
        return []

async def get_user_rank(user_id: int):
    try:
        user = await get_user(user_id)
        user_downloads = user.get('total_downloads', 0)
        
        higher_users = await user_data.count_documents({
            'total_downloads': {'$gt': user_downloads}
        })
        
        return higher_users + 1
    except Exception as e:
        logging.error(f"Error getting user rank for {user_id}: {e}")
        return 0

async def get_premium_users():
    try:
        users = []
        async for user in user_data.find({'premium': True}):
            users.append(user)
        return users
    except Exception as e:
        logging.error(f"Error getting premium users: {e}")
        return []

# Download history functions
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

async def get_user_download_history(user_id: int, limit: int = 10):
    try:
        history = []
        async for entry in download_history.find({'user_id': user_id}).sort('download_time', -1).limit(limit):
            history.append(entry)
        return history
    except Exception as e:
        logging.error(f"Error getting download history for user {user_id}: {e}")
        return []

# Statistics functions
async def get_stats():
    try:
        stats = await stats_data.find_one({'_id': 'bot_stats'})
        if not stats:
            stats = {
                '_id': 'bot_stats',
                'total_downloads': 0,
                'sites': {},
                'file_types': {},
                'daily_stats': {},
                'created_at': datetime.now()
            }
            await stats_data.insert_one(stats)
        return stats
    except Exception as e:
        logging.error(f"Error getting stats: {e}")
        return {
            '_id': 'bot_stats',
            'total_downloads': 0,
            'sites': {},
            'file_types': {},
            'daily_stats': {}
        }

async def update_stats(update_data: dict):
    try:
        await stats_data.update_one(
            {'_id': 'bot_stats'},
            {'$set': update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating stats: {e}")
        return False

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

async def reset_all_stats():
    try:
        # Backup current stats
        current_stats = await get_stats()
        backup_entry = {
            '_id': f"backup_{int(datetime.now().timestamp())}",
            'backup_time': datetime.now(),
            'data': current_stats
        }
        await stats_data.insert_one(backup_entry)
        
        # Reset main stats
        new_stats = {
            '_id': 'bot_stats',
            'total_downloads': 0,
            'sites': {},
            'file_types': {},
            'daily_stats': {},
            'reset_time': datetime.now()
        }
        
        await stats_data.replace_one({'_id': 'bot_stats'}, new_stats, upsert=True)
        
        # Reset user stats
        await user_data.update_many({}, {
            '$set': {
                'total_downloads': 0,
                'total_size': 0,
                'favorite_sites': {}
            }
        })
        
        return True
    except Exception as e:
        logging.error(f"Error resetting stats: {e}")
        return False

# Update download statistics
async def update_download_stats(user_id: int, username: str, url: str, file_size: int, file_type: str):
    try:
        from urllib.parse import urlparse
        
        # Extract site name
        parsed = urlparse(url)
        site = parsed.netloc.lower().replace('www.', '')
        
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
                    'username': username,
                    'last_activity': datetime.now()
                }
            },
            upsert=True
        )
        
        # Update global stats
        await increment_stats('total_downloads', 1)
        await update_site_stats(site)
        await update_file_type_stats(file_type)
        await update_daily_stats()
        
        # Add to download history
        await add_download_history(user_id, url, "Downloaded File", file_size, file_type, site)
        
        return True
    except Exception as e:
        logging.error(f"Error updating download stats: {e}")
        return False

