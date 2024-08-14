from flask import Flask, request, jsonify
import threading
import time
import requests
from queue import Queue
import os

app = Flask(__name__)

# Queue to hold the webhook messages
message_queue = Queue()

# Get the base URL, API key, and webhook ID from environment variables
API_BASE_URL = os.getenv('API_BASE_URL', 'https://demo.firefly-iii.org')
FIREFLY_API_KEY = os.getenv('FIREFLY_API_KEY')
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')  # Default to '1' if not set

# Print the environment variables for debugging
print(f"API_BASE_URL: {API_BASE_URL}")
print(f"FIREFLY_API_KEY: {FIREFLY_API_KEY}")
print(f"WEBHOOK_ID: {WEBHOOK_ID}")

def process_message(message):
    try:
        # Extract 'id' from the message
        transaction_id = message['content']['id']
        print(f"Processing transaction ID: {transaction_id}")

        # Wait for 2 minutes (120 seconds)
        time.sleep(120)

        # Perform the API request
        api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {FIREFLY_API_KEY}'
        }
        response = requests.post(api_url, headers=headers, data={})

        # Log the response for debugging
        print(f'API response: {response.status_code}, {response.text}')
    except Exception as e:
        # Log any exceptions that occur
        print(f"Error processing message: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        message = request.json
        print(f"Received message: {message}")  # Log the received message

        # Add the message to the queue
        message_queue.put(message)

        # Start a new thread to process the message
        threading.Thread(target=process_message, args=(message,), daemon=True).start()

        return jsonify({"status": "received"}), 200
    except Exception as e:
        # Log any exceptions that occur
        print(f"Error handling webhook request: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    # Enable debug mode for Flask
    app.run(host='0.0.0.0', port=5000)
