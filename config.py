import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # File handling
    TEMP_DIR = os.getenv("TEMP_DIR", "./temp")
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "2147483648"))  # 2GB
    
    # FFmpeg
    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
    FFMPEG_THREAD_QUEUE_SIZE = int(os.getenv("FFMPEG_THREAD_QUEUE_SIZE", "512"))
    
    # Progress update intervals
    PROGRESS_UPDATE_INTERVAL = 10  # seconds - reduce frequency for long conversions
    PROGRESS_CHECK_INTERVAL = 30  # Check progress every 30 seconds
    ETA_CALCULATION_THRESHOLD = 60  # Start ETA calculation after 60 seconds
    
    # Session management
    SESSION_STRING_NAME = os.getenv("SESSION_STRING_NAME", "video_converter_session")
    FLOOD_WAIT_HANDLE = os.getenv("FLOOD_WAIT_HANDLE", "true").lower() == "true"
    
    # Validation
    @classmethod
    def validate(cls):
        if not cls.API_ID or not cls.API_HASH or not cls.BOT_TOKEN:
            raise ValueError("Missing required environment variables")
        
        if not os.path.exists(cls.TEMP_DIR):
            os.makedirs(cls.TEMP_DIR, exist_ok=True)