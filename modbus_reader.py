import struct
import socket
import time
import logging

logger = logging.getLogger(__name__)

class ModbusTCPClient:
    def __init__(self, host, port=502, unit_id=1, timeout=5):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.transaction_id = 0

    def _build_read_request(self, start_address, count):
        self.transaction_id = (self.transaction_id + 1) % 65536
        tid = self.transaction_id
        protocol_id = 0
        length = 6
        func_code = 3  # FC3 - Read Holding Registers

        header = struct.pack('>HHHBB', tid, protocol_id, length, self.unit_id, func_code)
        data = struct.pack('>HH', start_address, count)
        return header + data

    def read_registers(self, start_address, count):
        request = self._build_read_request(start_address, count)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            sock.send(request)
            response = sock.recv(1024)
            sock.close()

            if len(response) < 9:
                logger.error("Response too short")
                return None

            byte_count = response[8]
            values = []
            for i in range(count):
                offset = 9 + i * 2
                if offset + 2 <= len(response):
                    val = struct.unpack('>H', response[offset:offset+2])[0]
                    values.append(val)
            return values
        except Exception as e:
            logger.error(f"Modbus read error: {e}")
            return None


def parse_value(raw, factor=10.0):
    """Convert raw register to float with scaling factor."""
    if raw is None:
        return None
    # Handle signed 16-bit
    if raw > 32767:
        raw -= 65536
    return round(raw / factor, 3)


def read_all_data(host, port=502, unit_id=1):
    client = ModbusTCPClient(host, port, unit_id)
    # Read registers 2..14 (13 registers, start_address=2, count=13)
    regs = client.read_registers(2, 13)

    if regs is None or len(regs) < 13:
        return None

    data = {
        "corrente_L1":         parse_value(regs[0],  10.0),
        "corrente_L2":         parse_value(regs[1],  10.0),
        "corrente_L3":         parse_value(regs[2],  10.0),
        "tensao_L1":           parse_value(regs[3],  10.0),
        "tensao_L2":           parse_value(regs[4],  10.0),
        "tensao_L3":           parse_value(regs[5],  10.0),
        "potencia_ativa":      parse_value(regs[6],  10.0),
        "potencia_reativa":    parse_value(regs[7],  10.0),
        "potencia_aparente":   parse_value(regs[8],  10.0),
        "frequencia":          parse_value(regs[9],  10.0),
        "fp_L1":               parse_value(regs[10], 1000.0),
        "fp_L2":               parse_value(regs[11], 1000.0),
        "fp_L3":               parse_value(regs[12], 1000.0),
        "timestamp":           time.time()
    }
    return data
