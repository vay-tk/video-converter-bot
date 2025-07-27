import asyncio
import logging
import os
import time
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified

from config import Config
from utils.file_manager import FileManager
from utils.ffmpeg_converter import FFmpegConverter

# Configure logging for Docker
log_dir = os.getenv('LOG_DIR', '/app/logs')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{log_dir}/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize components
Config.validate()

# Use session name to persist sessions and avoid repeated auth
app = Client(
    Config.SESSION_STRING_NAME,
    api_id=Config.API_ID, 
    api_hash=Config.API_HASH, 
    bot_token=Config.BOT_TOKEN,
    workdir="/app"  # Store session files in app directory
)

file_manager = FileManager(Config.TEMP_DIR)
converter = FFmpegConverter(Config.FFMPEG_PATH)

# User sessions to track conversion state
user_sessions = {}

# Custom filter for video documents
def video_document_filter(_, __, message):
    return (message.document and 
            message.document.mime_type and 
            message.document.mime_type.startswith('video/'))

video_document = filters.create(video_document_filter)

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
    
    # Create health check file
    Path('/tmp/bot_healthy').touch()

@app.on_message(filters.video | video_document)
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
    """Process video conversion with proper progress tracking and rate limit handling"""
    progress_message = None
    input_file = None
    output_file = None
    last_progress_text = ""
    last_update_time = 0
    
    try:
        # Download progress callback with rate limiting
        async def download_progress(current, total):
            nonlocal progress_message, last_progress_text, last_update_time
            
            current_time = time.time()
            percent = (current * 100) / total
            
            # Only update every 10% or every 15 seconds to avoid rate limits
            should_update = (
                abs(percent - (float(last_progress_text.split(': ')[1].split('%')[0]) if ': ' in last_progress_text and '%' in last_progress_text else 0)) >= 10 or
                current_time - last_update_time >= 15
            )
            
            if should_update:
                text = f"📥 **Downloading**: {percent:.1f}%"
                
                try:
                    if progress_message is None:
                        progress_message = await callback_query.edit_message_text(text)
                    else:
                        await progress_message.edit_text(text)
                    
                    last_progress_text = text
                    last_update_time = current_time
                    logger.info(f"Download progress: {percent:.1f}%")
                    
                except FloodWait as e:
                    logger.warning(f"Download progress flood wait: {e.value}s")
                    # Don't wait, just skip this update
                    pass
                except MessageNotModified:
                    # Message content hasn't changed, ignore
                    pass
                except Exception as e:
                    logger.debug(f"Download progress update error: {e}")
        
        # Download file
        logger.info("Starting file download...")
        input_file = await file_manager.download_file(message, download_progress)
        if not input_file:
            await safe_edit_message(callback_query, "❌ Failed to download video.")
            return False
        
        # Prepare output file
        original_name = Path(input_file.name).stem
        output_file = file_manager.get_temp_path(f"{original_name}.{format_type}", "_output")
        
        # Conversion progress callback with better rate limiting
        async def conversion_progress(percent, current_seconds, eta_text):
            nonlocal last_progress_text, progress_message, last_update_time
            
            current_time = time.time()
            text = f"🔄 **Converting to {format_type.upper()}**: {percent:.1f}%{eta_text}"
            
            # More frequent console logging for debugging
            logger.info(f"CONVERSION PROGRESS: {percent:.1f}% - {text}")
            print(f"Bot Progress: {percent:.1f}%{eta_text}")  # Direct console output
            
            # Update Telegram message every 5% or every 20 seconds for conversion
            should_update = (
                abs(percent - (float(last_progress_text.split(': ')[1].split('%')[0]) if ': ' in last_progress_text and '%' in last_progress_text else 0)) >= 5 or
                current_time - last_update_time >= 20
            )
            
            if should_update and text != last_progress_text:
                try:
                    await progress_message.edit_text(text)
                    last_progress_text = text
                    last_update_time = current_time
                    logger.info(f"TELEGRAM MESSAGE UPDATED: {percent:.1f}%")
                    
                except FloodWait as e:
                    logger.warning(f"Conversion progress flood wait: {e.value}s")
                    # Don't wait, just skip this update
                    pass
                except MessageNotModified:
                    pass
                except Exception as e:
                    logger.error(f"Progress update failed: {e}")
        
        # Update initial conversion status with more detail
        initial_text = f"🔄 **Converting to {format_type.upper()}**... (Starting FFmpeg process)"
        await safe_edit_message(progress_message, initial_text)
        last_progress_text = initial_text
        last_update_time = time.time()
        
        logger.info(f"=== STARTING {format_type.upper()} CONVERSION ===")
        logger.info(f"INPUT FILE: {input_file}")
        logger.info(f"OUTPUT FILE: {output_file}")
        print(f"🎬 Starting {format_type.upper()} conversion...")
        print(f"📁 Input: {input_file.name}")
        print(f"📁 Output: {output_file.name}")
        
        # Convert video
        logger.info("CALLING CONVERTER WITH PROGRESS CALLBACK")
        if format_type == "mp4":
            success = await converter.convert_to_mp4(input_file, output_file, conversion_progress)
        else:  # mkv
            success = await converter.convert_to_mkv(input_file, output_file, conversion_progress)
        
        logger.info(f"CONVERSION COMPLETED: success={success}")
        
        if not success:
            await safe_edit_message(progress_message, "❌ Conversion failed.")
            return False
        
        # Upload result
        upload_text = "📤 **Uploading converted video...**"
        await safe_edit_message(progress_message, upload_text)
        
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
        await safe_edit_message(progress_message, "✅ **Video converted and sent successfully!**")
        
        return True
        
    except FloodWait as e:
        logger.error(f"Flood wait in conversion process: {e.value}s")
        if progress_message:
            try:
                # Wait for the flood wait period
                await asyncio.sleep(e.value)
                await progress_message.edit_text("⚠️ **Processing paused due to rate limits. Resuming...**")
            except:
                pass
        return False
        
    except Exception as e:
        logger.error(f"Conversion process error: {e}")
        if progress_message:
            try:
                await safe_edit_message(progress_message, "❌ Conversion failed due to an error.")
            except:
                pass
        return False
    
    finally:
        # Cleanup files
        if input_file:
            file_manager.cleanup_file(input_file)
        if output_file:
            file_manager.cleanup_file(output_file)

async def safe_edit_message(message_or_query, text: str, max_retries: int = 3):
    """Safely edit message with flood wait handling"""
    for attempt in range(max_retries):
        try:
            if hasattr(message_or_query, 'edit_message_text'):
                # It's a callback query
                return await message_or_query.edit_message_text(text)
            else:
                # It's a message
                return await message_or_query.edit_text(text)
                
        except FloodWait as e:
            if attempt < max_retries - 1:
                logger.warning(f"Flood wait on message edit (attempt {attempt + 1}): waiting {e.value}s")
                await asyncio.sleep(e.value)
            else:
                logger.error(f"Max retries reached for message edit after flood wait")
                raise
                
        except MessageNotModified:
            # Message content is the same, that's fine
            return message_or_query
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Message edit failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2)
            else:
                logger.error(f"Failed to edit message after {max_retries} attempts: {e}")
                raise

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