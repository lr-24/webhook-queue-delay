"""Webhook queue delay.

Receives the "new transaction" webhook from Firefly III, waits a little, then asks Firefly III to run another webhook
(trigger-transaction) for that transaction, one call at a time.

Changes of 2026-10-10:
  * the queue is saved to a file (QUEUE_FILE) after every change, so a restart does not lose the pending transactions;
  * a failed call is tried again after 1 min, 5 min, 15 min, 1 h, 6 h (RETRY_DELAYS); after the last attempt the
    transaction is written to the "abbandonate" list of the queue file and logged as "Giving up";
  * the same transaction is never queued twice;
  * every call has a timeout, and the answer of Firefly III is checked (404 = transaction gone: no retry);
  * GET /health shows how many transactions wait, how old the oldest is and how many were given up.
"""
from flask import Flask, request, jsonify
import json
import os
import threading
import time
import logging
import requests
from logging.handlers import RotatingFileHandler


# Setup logging
def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_file = os.getenv('LOG_FILE', '/app/logs/app.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
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

# Environment variables
API_BASE_URL = os.getenv('API_BASE_URL', 'https://demo.firefly-iii.org')
FIREFLY_API_KEY = os.getenv('FIREFLY_API_KEY')
WEBHOOK_ID = os.getenv('WEBHOOK_ID', '1')
QUEUE_FILE = os.getenv('QUEUE_FILE', '/data/queue.json')
WAIT_BEFORE_PROCESSING = float(os.getenv('WAIT_BEFORE_PROCESSING', '30'))   # seconds before the first attempt
MIN_DELAY_BETWEEN_CALLS = float(os.getenv('MIN_DELAY_BETWEEN_CALLS', '29'))  # seconds between two calls to Firefly III
RETRY_DELAYS = [float(x) for x in os.getenv('RETRY_DELAYS', '60,300,900,3600,21600').split(',') if x.strip()]
REQUEST_TIMEOUT = float(os.getenv('REQUEST_TIMEOUT', '30'))
MAX_ABANDONED_KEPT = 200

logger.info(f"API_BASE_URL: {API_BASE_URL}")
logger.info(f"FIREFLY_API_KEY: {'*' * len(FIREFLY_API_KEY) if FIREFLY_API_KEY else 'Not Set'}")
logger.info(f"WEBHOOK_ID: {WEBHOOK_ID}")
logger.info(f"QUEUE_FILE: {QUEUE_FILE}; retry delays (s): {RETRY_DELAYS}")

if not all([API_BASE_URL, FIREFLY_API_KEY, WEBHOOK_ID]):
    logger.error("One or more required environment variables are not set.")

lock = threading.Lock()
# transaction id (str) -> {"id", "received", "next_try", "attempts", "last_error"}
pending = {}
# transactions that could not be processed after all the attempts (most recent last)
abandoned = []
started_at = time.time()
last_result = {"when": None, "transaction": None, "result": None}


def save_state():
    """Writes the queue to disk (atomically). Must be called with the lock held."""
    try:
        os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
        tmp = QUEUE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({"pending": list(pending.values()), "abandoned": abandoned[-MAX_ABANDONED_KEPT:]}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, QUEUE_FILE)
    except Exception as e:
        logger.error(f"Could not save the queue to {QUEUE_FILE}: {e}")


def load_state():
    """Reads the queue saved by a previous run."""
    global abandoned
    if not os.path.exists(QUEUE_FILE):
        return
    try:
        with open(QUEUE_FILE) as f:
            data = json.load(f)
        for item in data.get("pending", []):
            pending[str(item["id"])] = item
        abandoned = list(data.get("abandoned", []))
        logger.info(f"Loaded {len(pending)} pending transactions and {len(abandoned)} abandoned ones from {QUEUE_FILE}")
    except Exception as e:
        broken = f"{QUEUE_FILE}.corrupt-{int(time.time())}"
        logger.error(f"Queue file unreadable ({e}): moved to {broken}, starting with an empty queue")
        try:
            os.replace(QUEUE_FILE, broken)
        except Exception:
            pass


def call_firefly(transaction_id):
    """Asks Firefly III to run the webhook for the transaction. Returns ("ok" | "gone" | "retry", detail)."""
    api_url = f'{API_BASE_URL}/api/v1/webhooks/{WEBHOOK_ID}/trigger-transaction/{transaction_id}'
    headers = {
        'accept': '/',
        'Authorization': f'Bearer {FIREFLY_API_KEY}',
        'Content-Type': 'application/json'
    }
    try:
        logger.info(f"Sending API request for transaction ID: {transaction_id}")
        response = requests.post(api_url, headers=headers, json={}, timeout=REQUEST_TIMEOUT)
        logger.info(f'API response for transaction {transaction_id}: Status {response.status_code}')
        logger.debug(f'API response content: {response.text}')
    except requests.RequestException as e:
        logger.error(f"API request failed for transaction {transaction_id}: {str(e)}")
        return "retry", f"request failed: {e}"
    except Exception as e:
        logger.exception(f"Unexpected error processing transaction {transaction_id}: {str(e)}")
        return "retry", f"unexpected error: {e}"
    if 200 <= response.status_code < 300:
        return "ok", f"status {response.status_code}"
    if response.status_code == 404:
        return "gone", "status 404 (the transaction no longer exists)"
    return "retry", f"status {response.status_code}"


def worker():
    last_call_time = 0.0
    while True:
        with lock:
            due = min(pending.values(), key=lambda i: i["next_try"]) if pending else None
        if due is None or due["next_try"] > time.time():
            time.sleep(0.5)
            continue

        transaction_id = str(due["id"])
        logger.info(f"Processing transaction ID {transaction_id} (attempt {due['attempts'] + 1})")

        # Ensure a minimum time since the last API call
        wait_time = MIN_DELAY_BETWEEN_CALLS - (time.time() - last_call_time)
        if wait_time > 0:
            logger.info(f"Waiting additional {wait_time:.2f} seconds to ensure minimum delay between API calls")
            time.sleep(wait_time)

        result, detail = call_firefly(transaction_id)
        last_call_time = time.time()

        with lock:
            item = pending.get(transaction_id)
            if item is None:
                continue
            if result == "ok":
                del pending[transaction_id]
                logger.info(f"Finished processing transaction ID {transaction_id}")
            elif result == "gone":
                del pending[transaction_id]
                logger.warning(f"Transaction {transaction_id} no longer exists in Firefly III: removed from the queue")
            else:
                item["attempts"] += 1
                item["last_error"] = detail
                if item["attempts"] <= len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[item["attempts"] - 1]
                    item["next_try"] = time.time() + delay
                    logger.warning(f"Transaction {transaction_id} failed ({detail}); attempt {item['attempts']} of {len(RETRY_DELAYS) + 1}, trying again in {delay:.0f} seconds")
                else:
                    del pending[transaction_id]
                    abandoned.append({"id": transaction_id, "received": item["received"], "abandoned": time.time(),
                                      "attempts": item["attempts"], "last_error": detail})
                    logger.error(f"Giving up on transaction {transaction_id} after {item['attempts']} attempts ({detail})")
            last_result.update({"when": time.time(), "transaction": transaction_id, "result": result})
            save_state()


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        message = request.json
        logger.info(f"Received webhook message: {message}")

        # Extract the transaction ID and add it to the queue
        transaction_id = message.get('content', {}).get('id')
        if transaction_id:
            transaction_id = str(transaction_id)
            logger.info(f"Extracted transaction ID {transaction_id} from webhook message")
            with lock:
                if transaction_id in pending:
                    logger.info(f"Transaction ID {transaction_id} is already in the queue: ignored")
                    return jsonify({"status": "already_queued", "transaction_id": transaction_id}), 200
                now = time.time()
                pending[transaction_id] = {"id": transaction_id, "received": now, "next_try": now + WAIT_BEFORE_PROCESSING,
                                           "attempts": 0, "last_error": None}
                save_state()
            logger.info(f"Added transaction ID {transaction_id} to the processing queue")
            return jsonify({"status": "received", "transaction_id": transaction_id}), 200
        else:
            logger.error("No transaction ID found in the webhook message")
            return jsonify({"status": "error", "message": "No transaction ID found"}), 400
    except Exception as e:
        logger.exception(f"Error handling webhook request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    with lock:
        now = time.time()
        oldest = max((now - i["received"] for i in pending.values()), default=0)
        retrying = sum(1 for i in pending.values() if i["attempts"] > 0)
        return jsonify({
            "pending": len(pending),
            "oldest_pending_seconds": int(oldest),
            "pending_with_failed_attempts": retrying,
            "abandoned_total": len(abandoned),
            "last_abandoned": abandoned[-1] if abandoned else None,
            "last_result": dict(last_result),
            "up_seconds": int(now - started_at),
        }), 200


if __name__ == '__main__':
    logger.info("Starting Flask application and worker thread")
    with lock:
        load_state()
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    app.run(host='0.0.0.0', port=5000)
