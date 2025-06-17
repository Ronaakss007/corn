from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode 
from config import Config

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    try:
        user_name = message.from_user.first_name or "ᴜsᴇʀ"
        user_id = message.from_user.id
        
        welcome_text = (
            f"👋 <b>ʜᴇʏ {user_name}!</b>\n\n"
            f"🤖 <b>ɪ'ᴍ {Config.BOT_NAME}</b>\n\n"
            f"📥 <b>ɪ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ᴠɪᴅᴇᴏs ғʀᴏᴍ:</b>\n"
            f"• ʏᴏᴜᴛᴜʙᴇ, ɪɴsᴛᴀɢʀᴀᴍ, ᴛɪᴋᴛᴏᴋ\n"
            f"• ᴘᴏʀɴʜᴜʙ, xᴠɪᴅᴇᴏs, xɴxx\n"
            f"• ᴀɴᴅ 1000+ ᴏᴛʜᴇʀ sɪᴛᴇs!\n\n"
            f"🚀 <b>ᴊᴜsᴛ sᴇɴᴅ ᴍᴇ ᴀ ʟɪɴᴋ!</b>\n\n"
        )
        
        await message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
        print(f"✅ START: {user_id}")
        
    except Exception as e:
        print(f"❌ Error in start command: {e}")
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!</b>", parse_mode=ParseMode.HTML)



@Client.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    """Handle /ping command"""
    try:
        import time
        start_time = time.time()
        
        # Send initial message
        sent_message = await message.reply_text("🏓 ᴘɪɴɢɪɴɢ...")
        
        # Calculate response time
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Update with final response
        ping_text = (
            f"🏓 <b>ᴘᴏɴɢ!</b>\n\n"
            f"⚡ <b>ʀᴇsᴘᴏɴsᴇ ᴛɪᴍᴇ:</b> <code>{response_time:.2f}ᴍs</code>\n"
            f"🤖 <b>sᴛᴀᴛᴜs:</b> ᴏɴʟɪɴᴇ"
        )
        
        await sent_message.edit_text(ping_text, parse_mode=ParseMode.HTML)
        print(f"✅ PING: {message.from_user.id} - {response_time:.2f}ms")
        
    except Exception as e:
        print(f"❌ Error in ping command: {e}")
        await message.reply_text(
            "❌ <b>ᴇʀʀᴏʀ</b>", 
            parse_mode=ParseMode.HTML
        )



