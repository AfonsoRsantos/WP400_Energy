from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import threading
import time
import os
import logging
from collections import deque
from modbus_reader import read_all_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='../static', template_folder='../templates')
CORS(app)

MODBUS_HOST = os.environ.get('MODBUS_HOST', '192.168.1.100')
MODBUS_PORT = int(os.environ.get('MODBUS_PORT', 502))
MODBUS_UNIT_ID = int(os.environ.get('MODBUS_UNIT_ID', 1))
POLL_INTERVAL = float(os.environ.get('POLL_INTERVAL', 2.0))

MAX_HISTORY = 300  # ~10 min at 2s interval

latest_data = {}
history = deque(maxlen=MAX_HISTORY)
lock = threading.Lock()
connection_status = {"connected": False, "last_error": "", "last_success": None}


def poller():
    while True:
        try:
            data = read_all_data(MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT_ID)
            if data:
                with lock:
                    latest_data.update(data)
                    history.append(dict(data))
                    connection_status["connected"] = True
                    connection_status["last_success"] = time.time()
                    connection_status["last_error"] = ""
                logger.info(f"Data read OK — V_L1={data.get('tensao_L1')}V I_L1={data.get('corrente_L1')}A")
            else:
                with lock:
                    connection_status["connected"] = False
                    connection_status["last_error"] = "No response from device"
                logger.warning("No data received from Modbus device")
        except Exception as e:
            with lock:
                connection_status["connected"] = False
                connection_status["last_error"] = str(e)
            logger.error(f"Poller error: {e}")
        time.sleep(POLL_INTERVAL)


@app.route('/')
def index():
    return render_template('index.html',
        modbus_host=MODBUS_HOST,
        modbus_port=MODBUS_PORT,
        unit_id=MODBUS_UNIT_ID,
        poll_interval=POLL_INTERVAL)


@app.route('/api/data')
def api_data():
    with lock:
        if not latest_data:
            return jsonify({"error": "No data yet", "status": connection_status}), 503
        return jsonify({"data": latest_data, "status": connection_status})


@app.route('/api/history')
def api_history():
    points = int(request.args.get('points', 60))
    with lock:
        data = list(history)[-points:]
    return jsonify({"history": data})


@app.route('/api/status')
def api_status():
    with lock:
        return jsonify(connection_status)


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT_ID, POLL_INTERVAL
    if request.method == 'POST':
        body = request.get_json(force=True) or {}
        if 'host' in body:
            MODBUS_HOST = body['host']
        if 'port' in body:
            MODBUS_PORT = int(body['port'])
        if 'unit_id' in body:
            MODBUS_UNIT_ID = int(body['unit_id'])
        if 'poll_interval' in body:
            POLL_INTERVAL = float(body['poll_interval'])
        return jsonify({"ok": True, "host": MODBUS_HOST, "port": MODBUS_PORT,
                        "unit_id": MODBUS_UNIT_ID, "poll_interval": POLL_INTERVAL})
    return jsonify({"host": MODBUS_HOST, "port": MODBUS_PORT,
                    "unit_id": MODBUS_UNIT_ID, "poll_interval": POLL_INTERVAL})


if __name__ == '__main__':
    t = threading.Thread(target=poller, daemon=True)
    t.start()
    logger.info(f"Starting server — Modbus target: {MODBUS_HOST}:{MODBUS_PORT} Unit={MODBUS_UNIT_ID}")
    app.run(host='0.0.0.0', port=5000, debug=False)
