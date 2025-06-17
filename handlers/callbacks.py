import logging
from pyrogram import Client
from pyrogram.types import CallbackQuery
from config import Config

LOGGER = logging.getLogger(__name__)

async def handle_quality_callback(client: Client, callback_query: CallbackQuery, active_downloads):
    """Handle quality selection callbacks"""
    try:
        data = callback_query.data
        await callback_query.answer()
        
        if data.startswith("yl_qual_"):
            # Extract gid and quality
            parts = data.split("_")
            gid = parts[2]
            quality = "_".join(parts[3:])
            
            # Find the download instance
            if gid in active_downloads:
                download_instance = active_downloads[gid]
                
                # Check if user is authorized
                if callback_query.from_user.id != download_instance.user_id:
                    await callback_query.answer("❌ You're not authorized to use this!", show_alert=True)
                    return
                
                # Edit message to show selection
                await callback_query.message.edit_text(
                    f"✅ **Quality Selected:** {quality}\n\n📥 Starting download..."
                )
                
                # Start download
                await download_instance.start_download(quality)
            else:
                await callback_query.message.edit_text("❌ Download session expired!")
                
        elif data.startswith("yl_cancel_"):
            # Cancel download
            gid = data.split("_")[2]
            
            if gid in active_downloads:
                download_instance = active_downloads[gid]
                
                # Check if user is authorized
                if callback_query.from_user.id != download_instance.user_id:
                    await callback_query.answer("❌ You're not authorized to use this!", show_alert=True)
                    return
                
                download_instance.cancel_download()
                await callback_query.message.edit_text("❌ **Download Cancelled!**")
            else:
                await callback_query.message.edit_text("❌ Download session expired!")
                
    except Exception as e:
        LOGGER.error(f"Error in callback handler: {e}")
        await callback_query.message.edit_text(f"❌ Error: {str(e)}")

async def handle_admin_callback(client: Client, callback_query: CallbackQuery):
    """Handle admin callbacks"""
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if not Config.is_admin(user_id):
            await callback_query.answer("❌ Admin access required!", show_alert=True)
            return
        
        await callback_query.answer()
        
        if data == "admin_stats":
            # Show bot statistics
            stats_text = "📊 **Bot Statistics**\n\n"
            stats_text += f"🔄 **Active Downloads:** {len(active_downloads)}\n"
            # Add more stats as needed
            
            await callback_query.message.edit_text(stats_text)
            
    except Exception as e:
        LOGGER.error(f"Error in admin callback handler: {e}")
