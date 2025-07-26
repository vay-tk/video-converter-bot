
import asyncio
import logging
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import time

from config import Config
from utils.file_manager import FileManager
from utils.ffmpeg_converter import FFmpegConverter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize components
Config.validate()
app = Client("video_converter_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)
file_manager = FileManager(Config.TEMP_DIR)
converter = FFmpegConverter(Config.FFMPEG_PATH)

# User sessions to track conversion state
user_sessions = {}

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Welcome message"""
    welcome_text = (
        "🎬 **Video Converter Bot**\n\n"
        "Send me a video file and I'll convert it to:\n"
        "• MP4 (H.264 + AAC) - Standard format\n"
        "• MKV (H.265 + AAC, 480p, CRF 28) - Compressed format\n\n"
        "📁 **Supported**: Video files up to 2GB\n"
        "⚡ **Features**: Preserves audio/subtitles, fast conversion"
    )
    await message.reply_text(welcome_text)

@app.on_message(filters.video | (filters.document & filters.document.video))
async def handle_video(client: Client, message: Message):
    """Handle incoming video files"""
    try:
        # Check file size
        file_size = message.video.file_size if message.video else message.document.file_size
        
        if file_size > Config.MAX_FILE_SIZE:
            await message.reply_text(
                "❌ File too large! Maximum size is 2GB.\n"
                f"Your file: {file_size / (1024**3):.2f} GB"
            )
            return
        
        # Store session data
        user_sessions[message.from_user.id] = {
            'message': message,
            'file_size': file_size
        }
        
        # Show format selection
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎞 Convert to MP4 (H.264)", callback_data="convert_mp4")],
            [InlineKeyboardButton("🎬 Convert to MKV (H.265, 480p)", callback_data="convert_mkv")]
        ])
        
        file_name = message.video.file_name if message.video else message.document.file_name
        await message.reply_text(
            f"📹 **Video Received**: `{file_name}`\n"
            f"📦 **Size**: {file_size / (1024**2):.1f} MB\n\n"
            "Choose conversion format:",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Video handling error: {e}")
        await message.reply_text("❌ Error processing video. Please try again.")

@app.on_callback_query()
async def handle_conversion(client: Client, callback_query: CallbackQuery):
    """Handle format selection and start conversion"""
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions:
        await callback_query.answer("❌ Session expired. Please send video again.")
        return
    
    session = user_sessions[user_id]
    original_message = session['message']
    
    try:
        # Acknowledge callback
        await callback_query.answer("🔄 Starting conversion...")
        
        # Update message to show processing
        await callback_query.edit_message_text("⏳ **Processing your video...**")
        
        # Start conversion
        if callback_query.data == "convert_mp4":
            success = await process_conversion(client, callback_query, original_message, "mp4")
        elif callback_query.data == "convert_mkv":
            success = await process_conversion(client, callback_query, original_message, "mkv")
        else:
            await callback_query.edit_message_text("❌ Unknown conversion type.")
            return
        
        # Cleanup session
        if user_id in user_sessions:
            del user_sessions[user_id]
            
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await callback_query.edit_message_text("❌ Conversion failed. Please try again.")

async def process_conversion(client: Client, callback_query: CallbackQuery, message: Message, format_type: str):
    """Process video conversion"""
    progress_message = None
    input_file = None
    output_file = None
    
    try:
        # Download progress callback
        async def download_progress(current, total):
            nonlocal progress_message
            percent = (current * 100) / total
            if progress_message is None or percent % 10 < 1:  # Update every 10%
                text = f"📥 **Downloading**: {percent:.1f}%"
                if progress_message is None:
                    progress_message = await callback_query.edit_message_text(text)
                else:
                    await progress_message.edit_text(text)
        
        # Download file
        input_file = await file_manager.download_file(message, download_progress)
        if not input_file:
            await callback_query.edit_message_text("❌ Failed to download video.")
            return False
        
        # Prepare output file
        original_name = Path(input_file.name).stem
        output_file = file_manager.get_temp_path(f"{original_name}.{format_type}", "_output")
        
        # Get video duration for progress tracking
        duration = await converter.get_video_duration(input_file)
        
        # Conversion progress callback
        async def conversion_progress(current_seconds):
            if duration and current_seconds > 0:
                percent = min((current_seconds / duration) * 100, 100)
                text = f"🔄 **Converting to {format_type.upper()}**: {percent:.1f}%"
                try:
                    await progress_message.edit_text(text)
                except:
                    pass  # Ignore rate limit errors
        
        # Update status
        await progress_message.edit_text(f"🔄 **Converting to {format_type.upper()}**...")
        
        # Convert video
        if format_type == "mp4":
            success = await converter.convert_to_mp4(input_file, output_file, conversion_progress)
        else:  # mkv
            success = await converter.convert_to_mkv(input_file, output_file, conversion_progress)
        
        if not success:
            await progress_message.edit_text("❌ Conversion failed.")
            return False
        
        # Upload result
        await progress_message.edit_text("📤 **Uploading converted video...**")
        
        # Send converted file
        original_filename = message.video.file_name if message.video else message.document.file_name
        output_filename = f"{Path(original_filename).stem}.{format_type}"
        
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=str(output_file),
            caption=f"✅ **Conversion Complete**\n📁 **Format**: {format_type.upper()}\n📝 **Filename**: `{output_filename}`",
            reply_to_message_id=message.id
        )
        
        # Update final message
        await progress_message.edit_text("✅ **Video converted and sent successfully!**")
        
        return True
        
    except Exception as e:
        logger.error(f"Conversion process error: {e}")
        if progress_message:
            await progress_message.edit_text("❌ Conversion failed due to an error.")
        return False
    
    finally:
        # Cleanup files
        if input_file:
            file_manager.cleanup_file(input_file)
        if output_file:
            file_manager.cleanup_file(output_file)

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Help information"""
    help_text = (
        "🎬 **Video Converter Bot Help**\n\n"
        "**Supported Formats:**\n"
        "• MP4 - Standard H.264 + AAC format\n"
        "• MKV - Compressed H.265 + AAC (480p, CRF 28)\n\n"
        "**Features:**\n"
        "• Files up to 2GB\n"
        "• Preserves audio tracks\n"
        "• Preserves subtitle tracks\n"
        "• Original filename retained\n\n"
        "**Usage:**\n"
        "1. Send a video file\n"
        "2. Choose conversion format\n"
        "3. Wait for processing\n"
        "4. Receive converted video\n\n"
        "**Commands:**\n"
        "/start - Welcome message\n"
        "/help - This help message"
    )
    await message.reply_text(help_text)

if __name__ == "__main__":
    logger.info("Starting Video Converter Bot...")
    app.run()