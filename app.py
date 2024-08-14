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
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')  # Default to '1' if not set

# Log the environment variables for debugging
logger.info(f"API_BASE_URL: {API_BASE_URL}")
logger.info(f"FIREFLY_API_KEY: {'*' * len(FIREFLY_API_KEY) if FIREFLY_API_KEY else 'Not Set'}")
logger.info(f"WEBHOOK_ID: {WEBHOOK_ID}")

if not all([API_BASE_URL, FIREFLY_API_KEY, WEBHOOK_ID]):
    logger.error("One or more required environment variables are not set.")

def process_message(message):
    try:
        transaction_id = message['content']['id']
        logger.info(f"Processing transaction ID: {transaction_id}")
        
        time.sleep(120)
        
        api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {FIREFLY_API_KEY}',
            'Content-Type': 'application/json'  # Add this line
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

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        message = request.json
        logger.info(f"Received webhook message: {message}")
        
        # Add the message to the queue
        message_queue.put(message)
        
        # Start a new thread to process the message
        threading.Thread(target=process_message, args=(message,), daemon=True).start()
        
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.exception(f"Error handling webhook request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=5000)
