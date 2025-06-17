
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
    watermark_settings = database['watermark_settings']
    settings_data = database['settings']
    join_requests = database['join_requests']
    
    logging.info("✅ Database connection initialized")
    

    

except Exception as e:
    logging.error(f"❌ Database connection failed: {e}")
    # Create dummy functions for offline mode
    user_data = None
    stats_data = None
    download_history = None
    watermark_settings = None

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

async def update_download_stats(user_id: int, username: str, url: str, file_size: int, file_type: str):
    """Update download statistics"""
    try:
        from urllib.parse import urlparse
        
        # Extract site name
        parsed = urlparse(url)
        site = parsed.netloc.lower().replace('www.', '')
        
        print(f"🔄 Updating stats for user {user_id}: site={site}, size={file_size}, type={file_type}")
        
        # Update user stats - separate operations to avoid conflicts
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
        
        # Update username separately if provided
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
        import traceback
        traceback.print_exc()
        return False


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


async def update_settings(settings_dict: dict):
    """Update bot settings in database"""
    try:
        settings_dict['updated_at'] = datetime.now()
        await settings_data.update_one(
            {'_id': 'bot_settings'},
            {'$set': settings_dict},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating settings: {e}")
        return False

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
        
        # Ensure sites is always a dict with proper structure
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
            'total_file_size': 0,
            'sites': {},
            'file_types': {},
            'daily_stats': {},
            'top_users': {},
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

async def update_download_stats(user_id: int, username: str, url: str, file_size: int, file_type: str):
    """Update download statistics - Fixed version"""
    try:
        from urllib.parse import urlparse
        
        # Extract site name
        parsed = urlparse(url)
        site = parsed.netloc.lower().replace('www.', '')
        
        print(f"🔄 Starting stats update for user {user_id}")
        print(f"   Site: {site}")
        print(f"   File size: {file_size}")
        print(f"   File type: {file_type}")
        
        # Step 1: Ensure user exists
        existing_user = await user_data.find_one({'_id': user_id})
        if not existing_user:
            print(f"   Creating new user {user_id}")
            new_user = new_user(user_id)
            await user_data.insert_one(new_user)
        
        # Step 2: Update user stats with atomic operations
        print(f"   Updating user stats...")
        
        # Update total downloads and size
        result1 = await user_data.update_one(
            {'_id': user_id},
            {
                '$inc': {
                    'total_downloads': 1,
                    'total_size': file_size
                }
            }
        )
        print(f"   Downloads/Size update: matched={result1.matched_count}, modified={result1.modified_count}")
        
        # Update favorite sites separately
        result2 = await user_data.update_one(
            {'_id': user_id},
            {
                '$inc': {f'favorite_sites.{site}': 1},
                '$set': {'last_activity': datetime.now()}
            }
        )
        print(f"   Sites update: matched={result2.matched_count}, modified={result2.modified_count}")
        
        # Update username if provided (separate operation to avoid conflicts)
        if username and username.strip():
            await user_data.update_one(
                {'_id': user_id},
                {'$set': {'username': username.strip()}}
            )
        
        # Step 3: Add to download history
        print(f"   Adding to download history...")
        history_success = await add_download_history(user_id, url, f"Downloaded File", file_size, file_type, site)
        print(f"   History added: {history_success}")
        
        # Step 4: Update global stats
        print(f"   Updating global stats...")
        await increment_stats('total_downloads', 1)
        await update_site_stats(site)
        await update_file_type_stats(file_type)
        await update_daily_stats()
        
        # Step 5: Verify the update worked
        updated_user = await user_data.find_one({'_id': user_id})
        if updated_user:
            print(f"✅ Final user stats:")
            print(f"   Total downloads: {updated_user.get('total_downloads', 0)}")
            print(f"   Total size: {updated_user.get('total_size', 0)}")
            print(f"   Favorite sites: {updated_user.get('favorite_sites', {})}")
        else:
            print(f"❌ Could not find user after update!")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating download stats for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


# Helper function to format file sizes
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

# Function to get detailed stats for admin
async def get_detailed_stats():
    """Get detailed statistics for admin panel"""
    try:
        stats = await get_stats()
        user_count = await get_user_count()
        top_users = await get_top_users(5)
        
        return {
            'total_users': user_count,
            'total_downloads': stats.get('total_downloads', 0),
            'total_file_size': stats.get('total_file_size', 0),
            'top_sites': dict(sorted(stats.get('sites', {}).items(), key=lambda x: x[1], reverse=True)[:5]),
            'top_users': top_users,
            'file_types': stats.get('file_types', {}),
            'daily_stats': stats.get('daily_stats', {})
        }
    except Exception as e:
        logging.error(f"Error getting detailed stats: {e}")
        return {}
