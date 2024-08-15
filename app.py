from flask import Flask, request, jsonify
import threading
import time
import requests
from queue import Queue
import os
import logging
from logging.handlers import RotatingFileHandler

# Setup logging
def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_file = '/app/logs/app.log'
    log_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 100, backupCount=20)
    log_handler.setFormatter(log_formatter)
    log_handler.setLevel(logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)
    # Add a stream handler to also log to console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)
    return logger

logger = setup_logging()

app = Flask(__name__)

# Queue to hold the webhook messages
message_queue = Queue()

# Get the base URL, API key, and webhook ID from environment variables
API_BASE_URL = os.getenv('API_BASE_URL', 'https://demo.firefly-iii.org')
FIREFLY_API_KEY = os.getenv('FIREFLY_API_KEY')
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')

# Default to '1' if not set
# Log the environment variables for debugging
logger.info(f"API_BASE_URL: {API_BASE_URL}")
logger.info(f"FIREFLY_API_KEY: {'*' * len(FIREFLY_API_KEY) if FIREFLY_API_KEY else 'Not Set'}")
logger.info(f"WEBHOOK_ID: {WEBHOOK_ID}")

if not all([API_BASE_URL, FIREFLY_API_KEY, WEBHOOK_ID]):
    logger.error("One or more required environment variables are not set.")

# Configurable delays
INITIAL_DELAY = 120  # seconds before processing any input
DELAY_BETWEEN_REQUESTS = 30  # seconds between successive API calls

def process_message(message):
    try:
        transaction_id = message['content']['id']
        logger.info(f"Processing transaction ID: {transaction_id}")
        
        api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
        headers = {
            'accept': '/',
            'Authorization': f'Bearer {FIREFLY_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Send an empty JSON object as data
        response = requests.post(api_url, headers=headers, json={})
        logger.info(f'API response for transaction {transaction_id}: Status {response.status_code}')
        logger.debug(f'API response content: {response.text}')
    except KeyError:
        logger.error(f"Failed to extract transaction ID from message: {message}")
    except requests.RequestException as e:
        logger.error(f"API request failed for transaction {transaction_id}: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error processing message: {str(e)}")

def worker():
    # Initial delay before starting the processing
    logger.info(f"Worker will start processing after {INITIAL_DELAY} seconds.")
    time.sleep(INITIAL_DELAY)
    
    last_request_time = time.time()
    
    while True:
        message = message_queue.get()
        
        # Ensure a delay between successive API calls
        current_time = time.time()
        elapsed_time = current_time - last_request_time
        
        if elapsed_time < DELAY_BETWEEN_REQUESTS:
            sleep_time = DELAY_BETWEEN_REQUESTS - elapsed_time
            logger.info(f"Sleeping for {sleep_time} seconds to maintain delay between API calls.")
            time.sleep(sleep_time)
        
        process_message(message)
        message_queue.task_done()
        
        # Update the last request time
        last_request_time = time.time()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        message = request.json
        logger.info(f"Received webhook message: {message}")
        
        # Add the message to the queue
        message_queue.put(message)
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.exception(f"Error handling webhook request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application")
    # Start the worker thread
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    app.run(host='0.0.0.0', port=5000)
