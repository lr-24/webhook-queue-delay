from flask import Flask, request, jsonify
from celery import Celery
import time
import requests
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Celery configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

celery = Celery('tasks', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
celery.conf.update(app.config)

# Get the base URL, API key, and webhook ID from environment variables
API_BASE_URL = os.getenv('API_BASE_URL', 'https://demo.firefly-iii.org')
FIREFLY_API_KEY = os.getenv('FIREFLY_API_KEY')
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')  # Default to '1' if not set

logger.info(f"API_BASE_URL: {API_BASE_URL}")
logger.info(f"FIREFLY_API_KEY: {'*' * len(FIREFLY_API_KEY) if FIREFLY_API_KEY else 'Not Set'}")
logger.info(f"WEBHOOK_ID: {WEBHOOK_ID}")

if not all([API_BASE_URL, FIREFLY_API_KEY, WEBHOOK_ID]):
    logger.error("One or more required environment variables are not set.")

@celery.task(name='tasks.process_message')
def process_message(message):
    try:
        transaction_id = message['content']['id']
        logger.info(f"Processing transaction ID: {transaction_id}")
        
        time.sleep(120)
        
        api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {FIREFLY_API_KEY}',
            'Content-Type': 'application/json'
        }
        
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
        
        process_message.delay(message)
        
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.exception(f"Error handling webhook request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=5000)
