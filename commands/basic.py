from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    try:
        user_name = message.from_user.first_name or "User"
        user_id = message.from_user.id
        
        welcome_text = f"👋 **Welcome {user_name}!**\n\n"
        welcome_text += f"🤖 **{Config.BOT_NAME}**\n\n"
        welcome_text += "📥 I can download videos/audio from 1000+ websites!\n\n"
        welcome_text += "🚀 **Quick Start:**\n"
        welcome_text += "• Send `/test` to test the bot\n"
        welcome_text += "• Send `/help` for more information\n\n"
        welcome_text += f"👤 **Your ID:** `{user_id}`"
        
        await message.reply_text(welcome_text)
        print(f"✅ START command processed for user {user_id}")
        
    except Exception as e:
        print(f"❌ Error in start command: {e}")
        await message.reply_text("❌ An error occurred!")


@Client.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    """Handle /ping command"""
    try:
        ping_text = "🏓 **Pong!**\n\n"
        ping_text += "✅ Bot is alive and responding\n"
        ping_text += f"🤖 Bot Name: {Config.BOT_NAME}"
        
        await message.reply_text(ping_text)
        print(f"✅ PING command processed for user {message.from_user.id}")
        
    except Exception as e:
        print(f"❌ Error in ping command: {e}")



