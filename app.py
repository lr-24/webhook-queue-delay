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
API_BASE_URL = os.getenv('API_BASE_URL')
FIREFLY_API_KEY = os.getenv('FIREFLY_API_KEY')
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')  # Default to '123' if not set

def process_message(message):
    # Extract 'id' from the message
    transaction_id = message['content']['id']
    
    # Wait for 2 minutes (120 seconds)
    time.sleep(120)
    
    # Perform the API request
    api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
    headers = {
        'accept': '*/*',
        'Authorization': f'Bearer {FIREFLY_API_KEY}'
    }
    response = requests.post(api_url, headers=headers, data={})
    
    # Optional: Log the response or handle it
    print(f'API response: {response.status_code}, {response.text}')

@app.route('/webhook', methods=['POST'])
def webhook():
    message = request.json
    
    # Add the message to the queue
    message_queue.put(message)
    
    # Start a new thread to process the message
    threading.Thread(target=process_message, args=(message,)).start()
    
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
