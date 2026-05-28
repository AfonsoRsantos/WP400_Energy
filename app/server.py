from flask import Flask, jsonify, render_template, request, send_file
import threading, time, os, logging, struct, socket, io
from collections import deque
from datetime import datetime
from modbus_reader import read_all_data
from database import init_db, insert_reading, get_date_range

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='/app/templates')

MODBUS_HOST    = os.environ.get('MODBUS_HOST', '192.168.1.100')
MODBUS_PORT    = int(os.environ.get('MODBUS_PORT', 502))
MODBUS_UNIT_ID = int(os.environ.get('MODBUS_UNIT_ID', 1))
POLL_INTERVAL  = float(os.environ.get('POLL_INTERVAL', 2.0))
MAX_HIST = 60

latest_energy = {}
latest_oee    = {}
freq_history  = deque(maxlen=MAX_HIST)
curr_history  = deque(maxlen=MAX_HIST)
oee_history   = deque(maxlen=MAX_HIST)
lock = threading.Lock()

init_db()

def modbus_read(host, port, unit_id, start_addr, count, timeout=5):
    try:
        req = struct.pack('>HHHBBHH', 1, 0, 6, unit_id, 3, start_addr, count)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.send(req)
        resp = s.recv(1024)
        s.close()
        if len(resp) < 9:
            return None
        values = []
        for i in range(count):
            off = 9 + i * 2
            if off + 2 <= len(resp):
                v = struct.unpack('>H', resp[off:off+2])[0]
                if v > 32767:
                    v -= 65536
                values.append(v)
        return values
    except Exception as e:
        logger.error(f"Modbus read error: {e}")
        return None

def read_oee_data():
    regs = modbus_read(MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT_ID, 18, 8)
    if not regs or len(regs) < 8:
        return None
    status_map = {1:'Em Producao', 2:'Em Manutencao', 3:'Parada', 4:'Em Emergencia'}
    turno_map  = {1:'1o Turno', 2:'2o Turno', 3:'3o Turno'}
    return {
        'disponibilidade': round(regs[0]/100, 1),
        'performance':     round(regs[1]/100, 1),
        'qualidade':       round(regs[2]/100, 1),
        'oee':             round(regs[3]/100, 1),
        'prod_produzidos': regs[4],
        'prod_rejeitados': regs[5],
        'turno_raw':       regs[6],
        'turno':           turno_map.get(regs[6], f'Turno {regs[6]}'),
        'status_raw':      regs[7],
        'status':          status_map.get(regs[7], 'Desconhecido'),
    }

db_counter = 0
def poller():
    global db_counter
    while True:
        try:
            data = read_all_data(MODBUS_HOST, MODBUS_PORT, MODBUS_UNIT_ID)
            if data:
                freq_val = round(data.get('frequencia', 0) / 10, 2)
                il1 = round(data.get('corrente_L1', 0) / 10, 1)
                il2 = round(data.get('corrente_L2', 0) / 10, 1)
                il3 = round(data.get('corrente_L3', 0) / 10, 1)
                with lock:
                    latest_energy.update(data)
                    freq_history.append(freq_val)
                    curr_history.append((il1, il2, il3))
                db_counter += 1
                if db_counter >= 5:
                    insert_reading(data)
                    db_counter = 0
                logger.info(f"Data OK - V_L1={round(data.get('tensao_L1',0)/10,1)}V I_L1={il1}A F={freq_val}Hz")
            oee = read_oee_data()
            if oee:
                with lock:
                    latest_oee.update(oee)
                    oee_history.append(oee['oee'])
        except Exception as e:
            logger.error(f"Poller error: {e}")
        time.sleep(POLL_INTERVAL)

@app.route('/')
def index():
    now = time.strftime('%d/%m/%Y %H:%M:%S')
    return render_template('energy.html', now=now)

@app.route('/oee')
def oee_page():
    with lock:
        oee   = dict(latest_oee) if latest_oee else None
        ohist = list(oee_history)
    now = time.strftime('%d/%m/%Y %H:%M:%S')
    return render_template('oee.html', oee=oee, now=now, oee_history=ohist)

@app.route('/report')
def report_page():
    ts_min, ts_max = get_date_range()
    date_min = datetime.fromtimestamp(ts_min).strftime('%Y-%m-%dT%H:%M') if ts_min else ''
    date_max = datetime.fromtimestamp(ts_max).strftime('%Y-%m-%dT%H:%M') if ts_max else ''
    now = time.strftime('%d/%m/%Y %H:%M:%S')
    return render_template('report.html', now=now, date_min=date_min, date_max=date_max)

@app.route('/api/report')
def api_report():
    try:
        from report_generator import generate_report
        start_str = request.args.get('start')
        end_str   = request.args.get('end')
        if not start_str or not end_str:
            return jsonify({'error': 'start e end sao obrigatorios'}), 400
        start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
        end_dt   = datetime.strptime(end_str,   '%Y-%m-%dT%H:%M')
        pdf_bytes = generate_report('/data/energy.db', start_dt, end_dt)
        filename = f"relatorio_{start_dt.strftime('%Y%m%d_%H%M')}_{end_dt.strftime('%Y%m%d_%H%M')}.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"Report error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data')
def api_data():
    with lock:
        data = dict(latest_energy) if latest_energy else None
    if not data:
        return jsonify({'error': 'no data'}), 503
    return jsonify({'data': data, 'status': {'connected': True}})

@app.route('/api/history')
def api_history():
    points = int(request.args.get('points', 60))
    with lock:
        fh = list(freq_history)[-points:]
        ch = list(curr_history)[-points:]
    combined = []
    for i in range(min(len(fh), len(ch))):
        combined.append({
            'frequencia':  round(fh[i] * 10),
            'corrente_L1': round(ch[i][0] * 10),
            'corrente_L2': round(ch[i][1] * 10),
            'corrente_L3': round(ch[i][2] * 10),
        })
    return jsonify({'history': combined})

if __name__ == '__main__':
    threading.Thread(target=poller, daemon=True).start()
    logger.info(f"Starting - Modbus: {MODBUS_HOST}:{MODBUS_PORT} Unit={MODBUS_UNIT_ID}")
    app.run(host='0.0.0.0', port=5000, debug=False)
