import logging

def setup_logging():
    """
    Sets up logging configuration for the application.
    This function configures the logging settings to output log messages to the console.
    It sets the logging level to INFO and formats the log messages to include the timestamp,
    logger name, log level, and the message.
    Returns:
        logging.Logger: Configured logger instance for the application.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create logger
    logger = logging.getLogger('bedrock-api')
    logger.setLevel(logging.INFO)
    
    # Create console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(ch)
    
    return logger

logger = setup_logging()