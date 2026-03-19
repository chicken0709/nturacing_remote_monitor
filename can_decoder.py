"""
CAN Message Decoders for NTURT Remote Monitor
==============================================
This module contains all CAN message decoding functions.
"""

import time
import struct
import logging
import cantools
from datetime import datetime

DBC_FILE = "dbc/NTUR_EP6_260307.dbc"

# CAN ID : (subsystem, handler_function_name, param_type)
# param_type: "raw" (data), "decoded" (decoded), "both" (data + decoded)
MESSAGE_HANDLERS = { 
    # error
    0x81 : ("error", "decode_error", "raw"),
    # timestamp
    0x100: ("timestamp", "decode_timestamp", "decoded"),
    # vcu
    0x181: ("vcu", "decode_vcu_cockpit", "decoded"),
    0x381: ("vcu", "decode_vcu_suspension", "decoded"),
    # gps
    0x400: ("gps", "decode_gps_basic", "decoded"),
    0x401: ("gps", "decode_gps_extended", "decoded"),
    # velocity
    0x402: ("velocity", "decode_velocity_x", "decoded"),
    0x403: ("velocity", "decode_velocity_y", "decoded"),
    0x404: ("velocity", "decode_velocity_z", "decoded"),
    0x405: ("velocity", "decode_angular_x", "decoded"),
    0x406: ("velocity", "decode_angular_y", "decoded"),
    0x407: ("velocity", "decode_angular_z", "decoded"),
    0x408: ("velocity", "decode_velocity_magnitude", "decoded"),
    0x440: ("distance", "decode_distance", "raw"),
    # accumulator
    0x601: ("accumulator", "decode_cell_voltage", "raw"),
    0x651: ("accumulator", "decode_accumulator_temperature", "raw"),
    0x710: ("accumulator", "decode_accumulator_heartbeat", "raw"),
    0x501: ("accumulator", "decode_accumulator_status", "raw"),
    0x511: ("accumulator", "decode_accumulator_state", "raw"),
    # inverter
    0x191: ("inverters", "decode_inverter_status", "both"),
    0x192: ("inverters", "decode_inverter_status", "both"),
    0x193: ("inverters", "decode_inverter_status", "both"),
    0x194: ("inverters", "decode_inverter_status", "both"),
    0x291: ("inverters", "decode_inverter_state", "decoded"),
    0x292: ("inverters", "decode_inverter_state", "decoded"),
    0x293: ("inverters", "decode_inverter_state", "decoded"),
    0x294: ("inverters", "decode_inverter_state", "decoded"),
    0x391: ("inverters", "decode_inverter_temperature", "decoded"),
    0x392: ("inverters", "decode_inverter_temperature", "decoded"),
    0x393: ("inverters", "decode_inverter_temperature", "decoded"),
    0x394: ("inverters", "decode_inverter_temperature", "decoded"),
    0x711: ("inverters", "decode_inverter_heartbeat", "raw"),
    0x712: ("inverters", "decode_inverter_heartbeat", "raw"),
    0x713: ("inverters", "decode_inverter_heartbeat", "raw"),
    0x714: ("inverters", "decode_inverter_heartbeat", "raw"),
    0x211: ("inverters", "decode_inverter_control", "raw"),
    0x212: ("inverters", "decode_inverter_control", "raw"),
    0x213: ("inverters", "decode_inverter_control", "raw"),
    0x214: ("inverters", "decode_inverter_control", "raw"),
    # imu
    0x185: ("imu", "decode_imu_accel_km6", "raw"),
    0x426: ("imu", "decode_imu_accel_km308", "decoded"),
    0x285: ("imu", "decode_imu_gyro", "raw"),
    0x385: ("imu", "decode_imu_euler", "raw"),
    0x429: ("imu", "decode_imu_mag", "decoded"),
    # imu2
    0x188: ("imu2", "decode_imu2_accel", "decoded"),
    0x288: ("imu2", "decode_imu2_gyro", "decoded"),
    0x488: ("imu2", "decode_imu2_quaternion", "decoded"),
}

# suppress cantools warnings about overwriting messages when loading dbc
logging.getLogger("cantools").setLevel(logging.ERROR)

class CANDecoder:
    def __init__(self):
        # Data storage 
        self.data_store = self.create_empty_data_store()

        # load dbc file
        try:
            self.db = cantools.database.load_file(DBC_FILE)
            self.dbc_supported_can_id = set(msg.frame_id for msg in self.db.messages)
            print(f"Loaded DBC file: {DBC_FILE}")
            print(f"Messages count: {len(self.db.messages)}")
        except Exception as e:
            print(f"Error loading DBC file: {e}")

    def create_empty_data_store(self):
        return {
            'timestamp': {'time': None, 'last_update': None},
            'gps': {
                'lat': None, 'lon': None, 'alt': None, 'status': None,
                'last_update': None
            },
            'velocity': {
                'linear_x': None, 'linear_y': None, 'linear_z': None,
                'angular_x': None, 'angular_y': None, 'angular_z': None,
                'magnitude': None, 'speed_kmh': None,
                'last_update': None
            },
            'accumulator': {
                'soc': None, 'voltage': None, 'current': None, 'temperature': None,
                'status': None, 'heartbeat': None, 'capacity': None,
                'cell_voltages': [None] * 105, 'cell_temperatures': [None] * 224,
                'last_update': None
            },
            'inverters': {
                1: {'name': 'FL', 'status': None, 'torque': None, 'speed': None,
                    'control_word': None, 'target_torque': None,
                    'dc_voltage': None, 'dc_current': None,
                    'mos_temp': None, 'mcu_temp': None, 'motor_temp': None,
                    'heartbeat': None, 'last_update': None},
                2: {'name': 'FR', 'status': None, 'torque': None, 'speed': None,
                    'control_word': None, 'target_torque': None,
                    'dc_voltage': None, 'dc_current': None,
                    'mos_temp': None, 'mcu_temp': None, 'motor_temp': None,
                    'heartbeat': None, 'last_update': None},
                3: {'name': 'RL', 'status': None, 'torque': None, 'speed': None,
                    'control_word': None, 'target_torque': None,
                    'dc_voltage': None, 'dc_current': None,
                    'mos_temp': None, 'mcu_temp': None, 'motor_temp': None,
                    'heartbeat': None, 'last_update': None},
                4: {'name': 'RR', 'status': None, 'torque': None, 'speed': None,
                    'control_word': None, 'target_torque': None,
                    'dc_voltage': None, 'dc_current': None,
                    'mos_temp': None, 'mcu_temp': None, 'motor_temp': None,
                    'heartbeat': None, 'last_update': None}
            },
            'vcu': {
                'steer': None, 'accel': None, 'apps1': None,    
                'apps2': None, 'brake': None, 'bse1': None, 'bse2': None,
                'suspF': None, 'suspR': None,
                'last_update': None},
            'imu': {
                'accel_km6': {'x': None, 'y': None, 'z': None},
                'accel_km308': {'x': None, 'y': None, 'z': None},
                'gyro': {'x': None, 'y': None, 'z': None},
                'euler': {'roll': None, 'pitch': None, 'yaw': None},
                'mag': {'x': None, 'y': None, 'z': None},
                'last_update': None
            },
            'imu2': {
                'accel': {'x': None, 'y': None, 'z': None},
                'gyro': {'x': None, 'y': None, 'z': None},
                'quaternion': {'w': None, 'x': None, 'y': None, 'z': None},
                'last_update': None
            },
            'distance': {
                'trip_distance_km': None,
                'last_update': None
            },
            'error' : {
                'status': None,
                'active_errors': [],
                'last_update': None
            }
        }

    def decode_can_message(self, msg):
        can_id = msg.arbitration_id
        data = msg.data

        if can_id not in MESSAGE_HANDLERS:
            return
        
        subsystem, handler_name, param_type = MESSAGE_HANDLERS[can_id]
        handler = getattr(self, handler_name)

        if can_id in self.dbc_supported_can_id and subsystem != "accumulator":
            message = self.db.get_message_by_frame_id(can_id)
            if len(data) < message.length:
                return
            try:
                decoded = message.decode(data)
            except Exception as e:
                print(f"DBC decoding error for CAN ID 0x{can_id:03X}: {e}")
                return

        try: 
            # decode messages based on subsystem and param_type
            if subsystem == "inverters":
                inv_num = can_id & 0xF
                if param_type == "raw":
                    handler(data, inv_num)
                elif param_type == "decoded":
                    handler(decoded, inv_num)
                elif param_type == "both":
                    handler(data, decoded, inv_num)
            else:
                if param_type == "raw":
                    handler(data)
                elif param_type == "decoded":
                    handler(decoded)

            # update last_update time
            if subsystem is None:
                return
            if subsystem != 'inverters':
                self.data_store[subsystem]['last_update'] = time.time()
            else:
                inv_num = can_id & 0xF    
                self.data_store['inverters'][inv_num]['last_update'] = time.time()
        
        except Exception as e:
            print(f"Failed to decode CAN message ID 0x{can_id:03X}: {e}")

    # decode functions
    def decode_error(self, data):
        # check if the data is valid
        flag = struct.unpack('<B', data[2:3])[0]
        if flag < 0x30: return

        # get error status and code
        status = struct.unpack('<H', data[0:2])[0]
        error_code = struct.unpack('<I', data[3:7])[0]

        # update error status and active errors list
        if status == 0xff10:
            # error 
            self.data_store['error']['status'] = 1
            self.data_store['error']['active_errors'].append(error_code)
        elif status == 0x0: 
            # no error
            self.data_store['error']['status'] = 0
            self.data_store['error']['active_errors'].clear()
        else:
            print(f"Unknown error status: {status}")


    def decode_timestamp(self, decoded):
        ms_since_midnight = decoded.get('MillisecondsSinceMidnight')
        days_since_1984 = decoded.get('DaysSince1984')
            
        base_timestamp = 441763200
        total_seconds = base_timestamp + (days_since_1984 * 86400) + (ms_since_midnight / 1000.0)
        decoded_time = datetime.fromtimestamp(total_seconds)
        
        self.data_store['timestamp']['time'] = decoded_time

    def decode_vcu_cockpit(self, decoded):
        self.data_store['vcu']['steer'] = decoded.get('Steer') * 10000
        self.data_store['vcu']['accel'] = decoded.get('Accel')
        self.data_store['vcu']['apps1'] = decoded.get('APPS1')
        self.data_store['vcu']['apps2'] = decoded.get('APPS2')
        self.data_store['vcu']['brake'] = decoded.get('Brake')
        self.data_store['vcu']['bse1'] = decoded.get('BSE1')
        self.data_store['vcu']['bse2'] = decoded.get('BSE2')

    def decode_vcu_suspension(self, decoded):                    
        self.data_store['vcu']['suspF'] = decoded.get('SUSP_F') * 0.001 + 0.3
        self.data_store['vcu']['suspR'] = decoded.get('SUSP_R') * 0.001 + 0.3

    def decode_gps_basic(self, decoded):
        self.data_store['gps']['lat'] = decoded.get('Latitude') / 1e7
        self.data_store['gps']['lon'] = decoded.get('Logitude') / 1e7

    def decode_gps_extended(self, decoded):
        self.data_store['gps']['alt'] = decoded.get('Altitude')
        self.data_store['gps']['status'] = decoded.get('Status')

    def decode_velocity_x(self, decoded):
        self.data_store['velocity']['linear_x'] = decoded.get('Vx') / 1000.0

    def decode_velocity_y(self, decoded):
        self.data_store['velocity']['linear_y'] = decoded.get('Vy') / 1000.0

    def decode_velocity_z(self, decoded):
        self.data_store['velocity']['linear_z'] = decoded.get('Vz') / 1000.0

    def decode_angular_x(self, decoded):
        self.data_store['velocity']['angular_x'] = decoded.get('Gx') / 1000.0

    def decode_angular_y(self, decoded):
        self.data_store['velocity']['angular_y'] = decoded.get('Gy') / 1000.0

    def decode_angular_z(self, decoded):
        self.data_store['velocity']['angular_z'] = decoded.get('Gz') / 1000.0

    def decode_velocity_magnitude(self, decoded):
        self.data_store['velocity']['magnitude'] = decoded.get('Velocity') / 1000.0
        self.data_store['velocity']['speed_kmh'] = decoded.get('Velocity') / 1000.0 * 3.6

    def decode_distance(self, data):
        if len(data) >= 4:
            distance_mm = struct.unpack('<I', data[0:4])[0]
            self.data_store['distance']['trip_distance_km'] = distance_mm / 1000000.0

    def decode_cell_voltage(self, data):
        if len(data) >= 8:
            index = data[0]
            
            if index % 7 != 0 or index > 98:
                return
            
            voltages = []
            for i in range(1, min(8, len(data))):
                voltage = data[i] * 0.02
                voltages.append(voltage)
            
            for i, voltage in enumerate(voltages):
                array_index = index + i
                if array_index < 105:
                    self.data_store['accumulator']['cell_voltages'][array_index] = voltage
            
    def decode_accumulator_temperature(self, data):
        if len(data) >= 8:
            index = data[0]
            
            if index % 7 != 0 or index > 217:
                return
            
            temperatures = []
            for i in range(1, min(8, len(data))):
                temp = data[i] - 32  
                temperatures.append(temp)
            
            for i, temp in enumerate(temperatures):
                array_index = index + i
                if array_index < 224: 
                    self.data_store['accumulator']['cell_temperatures'][array_index] = temp

    def decode_accumulator_heartbeat(self, data):
        if len(data) >= 1:
            heartbeat = data[0] == 0x7F
            self.data_store['accumulator']['heartbeat'] = heartbeat

    def decode_accumulator_status(self, data):
        if len(data) >= 7:
            status = data[0]
            temperature_raw = struct.unpack('<h', data[1:3])[0]
            voltage_raw = struct.unpack('<I', data[3:7])[0] if len(data) >= 7 else 0
            
            self.data_store['accumulator']['status'] = status
            self.data_store['accumulator']['temperature'] = temperature_raw * 0.125
            self.data_store['accumulator']['voltage'] = voltage_raw / 1024.0

    def decode_accumulator_state(self, data):
        if len(data) >= 5:
            soc = data[0]
            current_raw = struct.unpack('<h', data[1:3])[0]
            capacity_raw = struct.unpack('<h', data[3:5])[0] if len(data) >= 5 else 0
            
            self.data_store['accumulator']['soc'] = soc
            self.data_store['accumulator']['current'] = current_raw * 0.01
            self.data_store['accumulator']['capacity'] = capacity_raw * 0.01

    def decode_inverter_status(self, data, decoded, inv_num):
        # status doesn't match with any dbc signal
        status_word1 = data[0]
        status_word2 = data[1]

        feedback_torque_raw = decoded.get('TorqueFeedback')
        speed_raw = decoded.get('Speed')

        feedback_torque = feedback_torque_raw / 100.0 * 20 * 4
        speed = speed_raw

        if inv_num == 3:
            feedback_torque *= -1
        
        self.data_store['inverters'][inv_num]['status'] = (status_word1, status_word2) 
        self.data_store['inverters'][inv_num]['torque'] = feedback_torque
        self.data_store['inverters'][inv_num]['speed'] = speed

    def decode_inverter_state(self, decoded, inv_num):
        self.data_store['inverters'][inv_num]['dc_voltage'] = decoded.get('DCvolt')
        self.data_store['inverters'][inv_num]['dc_current'] = decoded.get('DCcurrent')

    def decode_inverter_temperature(self, decoded, inv_num):
        self.data_store['inverters'][inv_num]['mos_temp'] = decoded.get('InvMOStemp')
        self.data_store['inverters'][inv_num]['mcu_temp'] = decoded.get('MCUtemp')
        self.data_store['inverters'][inv_num]['motor_temp'] = decoded.get('MOTORtemp')

    def decode_inverter_heartbeat(self, data, inv_num):
        if len(data) >= 1:
            heartbeat = data[0] == 0x05
            self.data_store['inverters'][inv_num]['heartbeat'] = heartbeat

    def decode_inverter_control(self, data, inv_num):
        if len(data) >= 4:
            control_word = struct.unpack('<H', data[0:2])[0]
            target_torque_raw = struct.unpack('<h', data[2:4])[0]
            target_torque = target_torque_raw / 1000.0 * 20

            if inv_num == 3:
                target_torque *= -1

            self.data_store['inverters'][inv_num]['control_word'] = control_word
            self.data_store['inverters'][inv_num]['target_torque'] = target_torque

    def decode_imu_accel_km6(self, data):
        if len(data) >= 6:
            x_raw = struct.unpack('<h', data[0:2])[0]
            y_raw = struct.unpack('<h', data[2:4])[0]
            z_raw = struct.unpack('<h', data[4:6])[0]
            
            self.data_store['imu']['accel_km6']['x'] = x_raw * 0.001
            self.data_store['imu']['accel_km6']['y'] = y_raw * 0.001
            self.data_store['imu']['accel_km6']['z'] = z_raw * 0.001

    def decode_imu_accel_km308(self, decoded):
        self.data_store['imu']['accel_km308']['x'] = decoded.get('a_x')
        self.data_store['imu']['accel_km308']['y'] = decoded.get('a_y')
        self.data_store['imu']['accel_km308']['z'] = decoded.get('a_z')

    def decode_imu_gyro(self, data):
        if len(data) >= 6:
            x_raw = struct.unpack('<h', data[0:2])[0]
            y_raw = struct.unpack('<h', data[2:4])[0]
            z_raw = struct.unpack('<h', data[4:6])[0]
            
            self.data_store['imu']['gyro']['x'] = x_raw * 0.1
            self.data_store['imu']['gyro']['y'] = y_raw * 0.1
            self.data_store['imu']['gyro']['z'] = z_raw * 0.1

    def decode_imu_euler(self, data):
        if len(data) >= 6:
            roll_raw = struct.unpack('<h', data[0:2])[0]
            pitch_raw = struct.unpack('<h', data[2:4])[0]
            yaw_raw = struct.unpack('<h', data[4:6])[0]
            
            self.data_store['imu']['euler']['roll'] = roll_raw * 0.01
            self.data_store['imu']['euler']['pitch'] = pitch_raw * 0.01
            self.data_store['imu']['euler']['yaw'] = yaw_raw * 0.01

    def decode_imu_mag(self, decoded):
        self.data_store['imu']['mag']['x'] = decoded.get('m_x') * 0.1
        self.data_store['imu']['mag']['y'] = decoded.get('m_y') * 0.1
        self.data_store['imu']['mag']['z'] = decoded.get('m_z') * 0.1

    def decode_imu2_accel(self, decoded):
        self.data_store['imu2']['accel']['x'] = decoded.get('a_x_1')
        self.data_store['imu2']['accel']['y'] = decoded.get('a_y_1')
        self.data_store['imu2']['accel']['z'] = decoded.get('a_z_1')

    def decode_imu2_gyro(self, decoded):
        self.data_store['imu2']['gyro']['x'] = decoded.get('g_x_1')
        self.data_store['imu2']['gyro']['y'] = decoded.get('g_y_1')
        self.data_store['imu2']['gyro']['z'] = decoded.get('g_z_1')

    def decode_imu2_quaternion(self, decoded):
        self.data_store['imu2']['quaternion']['w'] = decoded.get('q_w')
        self.data_store['imu2']['quaternion']['x'] = decoded.get('q_x')
        self.data_store['imu2']['quaternion']['y'] = decoded.get('q_y')
        self.data_store['imu2']['quaternion']['z'] = decoded.get('q_z')