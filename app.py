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
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)
    return logger

logger = setup_logging()

app = Flask(__name__)

# Queue to hold the transaction IDs
id_queue = Queue()

# Environment variables
API_BASE_URL = os.getenv('API_BASE_URL', 'https://demo.firefly-iii.org')
FIREFLY_API_KEY = os.getenv('FIREFLY_API_KEY')
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')

logger.info(f"API_BASE_URL: {API_BASE_URL}")
logger.info(f"FIREFLY_API_KEY: {'*' * len(FIREFLY_API_KEY) if FIREFLY_API_KEY else 'Not Set'}")
logger.info(f"WEBHOOK_ID: {WEBHOOK_ID}")

if not all([API_BASE_URL, FIREFLY_API_KEY, WEBHOOK_ID]):
    logger.error("One or more required environment variables are not set.")

WAIT_BEFORE_PROCESSING = 30  # 30 seconds
MIN_DELAY_BETWEEN_CALLS = 29  # 30 seconds (should not be necessary, but just as a precaution

def process_transaction(transaction_id):
    try:
        logger.info(f"Starting to process transaction ID: {transaction_id}")
        api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
        headers = {
            'accept': '/',
            'Authorization': f'Bearer {FIREFLY_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Sending API request for transaction ID: {transaction_id}")
        response = requests.post(api_url, headers=headers, json={})
        logger.info(f'API response for transaction {transaction_id}: Status {response.status_code}')
        logger.debug(f'API response content: {response.text}')
    except requests.RequestException as e:
        logger.error(f"API request failed for transaction {transaction_id}: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error processing transaction {transaction_id}: {str(e)}")

def worker():
    last_call_time = 0
    
    while True:
        transaction_id = id_queue.get()
        logger.info(f"Retrieved transaction ID {transaction_id} from queue")
        
        # Wait for 2 minutes before processing
        logger.info(f"Waiting for {WAIT_BEFORE_PROCESSING} seconds before processing transaction ID {transaction_id}")
        time.sleep(WAIT_BEFORE_PROCESSING)
        
        # Ensure at least 30 seconds have passed since the last API call
        time_since_last_call = time.time() - last_call_time
        if time_since_last_call < MIN_DELAY_BETWEEN_CALLS:
            wait_time = MIN_DELAY_BETWEEN_CALLS - time_since_last_call
            logger.info(f"Waiting additional {wait_time:.2f} seconds to ensure minimum delay between API calls")
            time.sleep(wait_time)
        
        process_transaction(transaction_id)
        last_call_time = time.time()
        
        logger.info(f"Finished processing transaction ID {transaction_id}")
        id_queue.task_done()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        message = request.json
        logger.info(f"Received webhook message: {message}")
        
        # Extract the transaction ID and add it to the queue
        transaction_id = message.get('content', {}).get('id')
        if transaction_id:
            logger.info(f"Extracted transaction ID {transaction_id} from webhook message")
            id_queue.put(transaction_id)
            logger.info(f"Added transaction ID {transaction_id} to the processing queue")
            return jsonify({"status": "received", "transaction_id": transaction_id}), 200
        else:
            logger.error("No transaction ID found in the webhook message")
            return jsonify({"status": "error", "message": "No transaction ID found"}), 400
    except Exception as e:
        logger.exception(f"Error handling webhook request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application and worker thread")
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    app.run(host='0.0.0.0', port=5000)
