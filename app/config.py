import os

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY')
    # if not SECRET_KEY:
        # raise ValueError("No SECRET_KEY set for Flask application")
    
    DEBUG = False
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    ENV = 'development'


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/test.log')


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    ENV = 'production'


# Config Map to Select Configuration Based on ENV Variable
config_map = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig
}

# Helper Function to Load Config
def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)
