import asyncio
import logging
import signal
import sys
import os
from pathlib import Path
from pyrogram.errors import FloodWait

# Setup logging for Docker environment
log_dir = os.getenv('LOG_DIR', '/app/logs')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{log_dir}/bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)

async def start_bot_with_retry():
    """Start bot with flood wait handling"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Import bot here to avoid import issues
            from bot import app
            
            logger.info(f"Starting bot (attempt {retry_count + 1}/{max_retries})")
            await app.start()
            logger.info("Bot started successfully")
            return app
            
        except FloodWait as e:
            logger.warning(f"Flood wait detected: {e.value} seconds")
            if retry_count < max_retries - 1:
                logger.info(f"Waiting {e.value} seconds before retry...")
                await asyncio.sleep(e.value)
                retry_count += 1
            else:
                logger.error("Max retries reached, giving up")
                raise
                
        except Exception as e:
            logger.error(f"Bot start failed: {e}")
            if retry_count < max_retries - 1:
                logger.info("Waiting 30 seconds before retry...")
                await asyncio.sleep(30)
                retry_count += 1
            else:
                raise
    
    raise Exception("Failed to start bot after maximum retries")

async def main():
    """Main entry point with proper error handling"""
    app = None
    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Create health check file
        Path('/tmp/bot_healthy').touch()
        
        # Start bot with retry logic
        app = await start_bot_with_retry()
        
        # Keep running
        logger.info("Bot is running... Press Ctrl+C to stop")
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except FloodWait as e:
        logger.error(f"Flood wait error: Need to wait {e.value} seconds")
        logger.info("Please wait before restarting the bot")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
    finally:
        if app:
            try:
                await app.stop()
                logger.info("Bot stopped gracefully")
            except:
                pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown completed")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)