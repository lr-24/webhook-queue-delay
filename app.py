from flask import Flask, request, jsonify
import threading
import time
import requests
from queue import Queue

app = Flask(__name__)

# Queue to hold the webhook messages
message_queue = Queue()

def process_message(message):
    # Extract 'id' from the message
    transaction_id = message['content']['id']
    
    # Wait for 2 minutes (120 seconds)
    time.sleep(120)
    
    # Perform the API request
    api_url = f'https://demo.firefly-iii.org/api/v1/webhooks/123/trigger-transaction/{transaction_id}'
    response = requests.post(api_url, headers={'accept': '*/*'}, data={})
    
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
