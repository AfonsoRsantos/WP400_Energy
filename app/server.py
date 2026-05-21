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
ENERGY_COST_PER_KWH = float(os.environ.get('ENERGY_COST_PER_KWH', 0.36))

MAX_HISTORY = 300

latest_data = {}
history = deque(maxlen=MAX_HISTORY)
daily_energy = {}  # date_str -> Wh accumulated
lock = threading.Lock()
connection_status = {"connected": False, "last_error": "", "last_success": None}


def poller():
    last_time = None
    while True:
        try:
            now = time.time()
            data = read_all_data(MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT_ID)
            if data:
                with lock:
                    if last_time is not None:
                        dt = now - last_time
                        power_w = latest_data.get('potencia_ativa') or 0
                        energy_wh = power_w * dt / 3600.0
                        day = time.strftime('%d.%m.%y', time.localtime(now))
                        daily_energy[day] = daily_energy.get(day, 0) + energy_wh
                    latest_data.update(data)
                    history.append(dict(data))
                    connection_status["connected"] = True
                    connection_status["last_success"] = now
                    connection_status["last_error"] = ""
                last_time = now
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
        poll_interval=POLL_INTERVAL,
        energy_cost=ENERGY_COST_PER_KWH)


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


@app.route('/api/daily')
def api_daily():
    with lock:
        cost = ENERGY_COST_PER_KWH
        result = []
        for day in sorted(daily_energy.keys(), reverse=True)[:7]:
            wh = daily_energy[day]
            result.append({
                'date': day,
                'wh': round(wh, 1),
                'cost': round((wh / 1000.0) * cost, 3)
            })
    return jsonify({'daily': result, 'cost_per_kwh': cost})


@app.route('/api/status')
def api_status():
    with lock:
        return jsonify(connection_status)


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT_ID, POLL_INTERVAL, ENERGY_COST_PER_KWH
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
        if 'cost_per_kwh' in body:
            ENERGY_COST_PER_KWH = float(body['cost_per_kwh'])
        return jsonify({"ok": True})
    return jsonify({
        "host": MODBUS_HOST, "port": MODBUS_PORT,
        "unit_id": MODBUS_UNIT_ID, "poll_interval": POLL_INTERVAL,
        "cost_per_kwh": ENERGY_COST_PER_KWH
    })


if __name__ == '__main__':
    t = threading.Thread(target=poller, daemon=True)
    t.start()
    logger.info(f"Starting server — Modbus target: {MODBUS_HOST}:{MODBUS_PORT} Unit={MODBUS_UNIT_ID}")
    app.run(host='0.0.0.0', port=5000, debug=False)
