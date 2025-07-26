import asyncio
import logging
import signal
import sys
import os
from pathlib import Path

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

async def main():
    """Main entry point"""
    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Create health check file
        Path('/tmp/bot_healthy').touch()
        
        # Import and run bot
        from bot import app
        logger.info("Video Converter Bot started successfully")
        await app.start()
        await asyncio.Event().wait()  # Keep running
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
    finally:
        try:
            await app.stop()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())