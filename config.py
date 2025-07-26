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
    
    # Validation
    @classmethod
    def validate(cls):
        if not cls.API_ID or not cls.API_HASH or not cls.BOT_TOKEN:
            raise ValueError("Missing required environment variables")
        
        if not os.path.exists(cls.TEMP_DIR):
            os.makedirs(cls.TEMP_DIR)