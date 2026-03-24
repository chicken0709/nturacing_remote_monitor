"""
NTURT CAN Data Client - Vehicle Side
====================================
This script runs on the vehicle's Raspberry Pi.
It reads CAN data from can0 and can1 and sends it to the remote server.
"""

import os
import can
import csv
import json
import time
import glob
import asyncio
import websockets
from datetime import datetime
from packaging import version

# Configuration
# SERVER_URL = "ws://140.112.16.226:8889"  # modify this to your server's IP address or hostname
SERVER_URL = "ws://localhost:8889"
RECONNECT_DELAY = 5  # reconnection delay (second)
HEARTBEAT_INTERVAL = 1  # heartbeat interval (second)
BATCH_SIZE = 50  # batch size for sending messages (increase to improve efficiency)
BATCH_TIMEOUT = 0.05  # batch send timeout (second)
MAX_QUEUE_SIZE = 1000  # maximum queue size to prevent memory overflow
USE_BATCH_MODE = True  # batch sending mode
LOGS_DIR = "../LOGS"  # CSV file directory
CSV_REPLAY_SPEED = 1.0  # CSV replay speed multiplier

class CANDataClient:
    def __init__(self, server_url):
        self.server_url = server_url
        self.websocket = None
        self.running = True
        self.bus0 = None
        self.bus1 = None
        self.message_count = 0
        self.last_heartbeat = time.time()
        
        # batched message queue and statistics
        self.message_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.dropped_messages = 0
        self.sent_batches = 0
        self.last_send_report = time.time()
        
        # statistics for filtering duplicate messages
        self.total_can_received = 0  # total CAN messages received
        self.filtered_duplicates = 0  # number of filtered duplicate messages
        
        # latest message cache - for filtering duplication
        # key: (bus_id, can_id), value: message_data
        self.latest_messages = {}
        self.cache_lock = asyncio.Lock()
        
        # CSV playback parameters
        self.mode = 'realtime' # 'realtime' or 'csv' or 'idle'
        self.csv_file = None
        self.csv_paused = False
        self.csv_playback_speed = CSV_REPLAY_SPEED
        self.csv_data = []  # store CSV data
        self.csv_index = 0  # current playback index
        self.csv_start_time = None  # playback start time (real time)
        self.csv_base_timestamp = None  # csv base timestamp
        self.csv_file_version = 0 # csv file version for detecting changes (incremented on each file selection)
        
    async def connect(self):
        # connect to the server with reconnection logic
        while self.running:
            try:
                print(f"Connecting to server at {self.server_url}...")
                self.websocket = await websockets.connect(
                    self.server_url,
                    ping_interval=20,
                    ping_timeout=10
                )
                print("Connected to server successfully!")
                return True
            except Exception as e:
                print(f"Failed to connect to server: {e}")
                print(f"Retrying in {RECONNECT_DELAY} seconds...")
                await asyncio.sleep(RECONNECT_DELAY)
        return False
    
    def scan_csv_files(self):
        # scan csv files in LOGS_DIR and return a list of file info
        try:
            csv_files = []
            pattern = os.path.join(LOGS_DIR, '*.csv')
            
            for filepath in glob.glob(pattern):
                filename = os.path.basename(filepath)
                file_stat = os.stat(filepath)
                file_time = datetime.fromtimestamp(file_stat.st_mtime)
                file_size = file_stat.st_size
                
                csv_files.append({
                    'filename': filename,
                    'path': filepath,
                    'modified': file_time.isoformat(),
                    'size': file_size,
                    'size_mb': round(file_size / 1024 / 1024, 2)
                })
            
            # sort by modified time (newest first)
            csv_files.sort(key=lambda x: x['modified'], reverse=True)
            return csv_files
        except Exception as e:
            print(f"Error scanning CSV files: {e}")
            return []
    
    def init_can_buses(self):
        # initialize CAN buses
        try:
            # initialize can0
            can_kwargs = dict(channel='can0')
            if version.parse(can.__version__) >= version.parse('4.2.0'):
                can_kwargs['interface'] = 'socketcan'
            else:
                can_kwargs['bustype'] = 'socketcan'
            self.bus0 = can.interface.Bus(**can_kwargs)
            print("CAN0 initialized successfully")
        except Exception as e:
            print(f"Warning: Could not initialize CAN0 bus: {e}")
            self.bus0 = None
        
        try:
            # initialize can1
            can1_kwargs = dict(channel='can1')
            if version.parse(can.__version__) >= version.parse('4.2.0'):
                can1_kwargs['interface'] = 'socketcan'
            else:
                can1_kwargs['bustype'] = 'socketcan'
            self.bus1 = can.interface.Bus(**can1_kwargs)
            print("CAN1 initialized successfully")
        except Exception as e:
            print(f"Warning: Could not initialize CAN1 bus: {e}")
            self.bus1 = None
    
    async def send_can_message(self, can_id, data, bus_id):
        # enqueue CAN message with duplication filtering
        self.total_can_received += 1
        
        # discard data immediately if not connected, do not accumulate backlog
        if not self.websocket:
            return False
        
        message_key = (bus_id, can_id)
        data_list = list(data)
        message_data = {
            'bus_id': bus_id,
            'can_id': can_id,
            'data': data_list,
            'timestamp': time.time()
        }
        
        # under csv mode, skip duplication filtering and directly enqueue all messages
        if self.mode == 'csv':
            try:
                self.message_queue.put_nowait(message_data)
                return True
            except asyncio.QueueFull:
                self.dropped_messages += 1
                return False
        
        # single message mode for testing
        if not USE_BATCH_MODE:
            if self.websocket:
                try:
                    single_message = {
                        'type': 'can_message',
                        'bus_id': bus_id,
                        'can_id': can_id,
                        'data': data_list,
                        'timestamp': time.time()
                    }
                    await self.websocket.send(json.dumps(single_message))
                    self.message_count += 1
                    return True
                except Exception as e:
                    return False
            return False
        # batch mode with duplication filtering
        should_queue = False
        async with self.cache_lock:
            # duplication check
            if message_key in self.latest_messages:
                old_data = self.latest_messages[message_key]['data']
                # add to queue only if data changed, otherwise just update timestamp in cache
                if old_data != data_list:
                    should_queue = True
                    self.latest_messages[message_key] = message_data
                else:
                    self.filtered_duplicates += 1
                    self.latest_messages[message_key]['timestamp'] = message_data['timestamp']
            else:
                # new CAN ID, add to cache and queue
                should_queue = True
                self.latest_messages[message_key] = message_data
        
        if should_queue:
            try:
                # add full message data to the queue, not just the key
                self.message_queue.put_nowait(message_data)
                return True
            except asyncio.QueueFull:
                # dropped messages
                self.dropped_messages += 1
                if self.dropped_messages % 100 == 0:
                    print(f"Warning: Queue full ({self.message_queue.qsize()}), data cached. Delayed: {self.dropped_messages}")
                return False
        return True
    
    async def send_heartbeat(self):
        # send heartbeat message to the server
        if not self.websocket:
            return
        
        try:
            filter_rate = 0
            if self.total_can_received > 0:
                filter_rate = (self.filtered_duplicates / self.total_can_received) * 100
            
            heartbeat_data = {
                'type': 'heartbeat',
                'timestamp': time.time(),
                'message_count': self.message_count,
                'dropped_messages': self.dropped_messages,
                'queue_size': self.message_queue.qsize(),
                'total_received': self.total_can_received,
                'filtered': self.filtered_duplicates,
                'filter_rate': f"{filter_rate:.1f}%",
                'mode': self.mode,
                'csv_file': os.path.basename(self.csv_file) if self.csv_file else None,
                'csv_paused': self.csv_paused
            }
            await self.websocket.send(json.dumps(heartbeat_data))
            self.last_heartbeat = time.time()
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException):
            # Connection closed, stop trying to send
            pass
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
    
    async def batch_sender(self):
        # send batched messages to the server
        try:
            batch = []
            last_send_time = time.time()
            
            # wait for websocket connection to be established
            while self.running and not self.websocket:
                await asyncio.sleep(0.1)
            
            print("✅ Connected - Starting batch sender")
            
            # main loop for sending batches
            while self.running:
                try:
                    if not self.websocket:
                        await asyncio.sleep(0.1)
                        continue
                    
                    try:
                        # try to get messages from queue with a timeout of BATCH_TIMEOUT
                        timeout = max(0.001, BATCH_TIMEOUT - (time.time() - last_send_time))
                        message = await asyncio.wait_for(
                            self.message_queue.get(),
                            timeout=timeout
                        )
                        batch.append(message)
                        
                        # if batch size reached or timeout, send batch
                        current_time = time.time()
                        should_send = (
                            len(batch) >= BATCH_SIZE or
                            (batch and current_time - last_send_time >= BATCH_TIMEOUT)
                        )
                        
                        if should_send:
                            # send batch
                            batch_data = {
                                'type': 'can_batch',
                                'messages': batch,
                                'count': len(batch)
                            }
                            try:
                                await self.websocket.send(json.dumps(batch_data))
                                self.message_count += len(batch)
                                self.sent_batches += 1
                                
                                # print stastics periodically
                                if time.time() - self.last_send_report > 5:
                                    filter_rate = 0
                                    if self.total_can_received > 0:
                                        filter_rate = (self.filtered_duplicates / self.total_can_received) * 100
                                    print(f"📊 Sent: {self.message_count} msgs | Received: {self.total_can_received} | Filtered: {filter_rate:.1f}% | Queue: {self.message_queue.qsize()}")
                                    self.last_send_report = time.time()
                            except Exception as send_err:
                                print(f"Error sending batch: {send_err}")
                                raise
                            
                            batch = []
                            last_send_time = current_time
                            
                    except asyncio.TimeoutError:
                        # timeout, if batch is not empty, send it immediately
                        if batch:
                            batch_data = {
                                'type': 'can_batch',
                                'messages': batch,
                                'count': len(batch)
                            }
                            try:
                                await self.websocket.send(json.dumps(batch_data))
                                self.message_count += len(batch)
                                self.sent_batches += 1
                            except Exception as send_err:
                                print(f"Error sending batch (timeout): {send_err}")
                                raise
                            
                            batch = []
                            last_send_time = time.time()
                            
                except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException):
                    # connection closed, clear the batch and the entire queue
                    batch = []
                    queue_size = self.message_queue.qsize()
                    if queue_size > 0:
                        print(f"🗑️  Connection lost - Discarding {queue_size} queued messages")
                        # clear queue
                        while not self.message_queue.empty():
                            try:
                                self.message_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                    print("⚠️  Batch sender stopped - waiting for reconnection")
                    break
                except asyncio.CancelledError:
                    print("Batch sender: Task cancelled", flush=True)
                    break
                except Exception as e:
                    print(f"Error in batch sender: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(0.1)
        except Exception as outer_e:
            print(f"FATAL error in batch_sender: {outer_e}", flush=True)
            import traceback
            traceback.print_exc()
    
    async def read_can0(self):
        # read CAN messages from bus0
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                # read CAN messages only in realtime mode (continue reading even if connection lost)
                if self.mode == 'realtime' and self.bus0:
                    # use thread pool to execute blocking recv call
                    message = await loop.run_in_executor(
                        None,  # use default thread pool
                        lambda: self.bus0.recv(timeout=0.01)
                    )
                    if message:
                        # send_can_message will check the connection status internally
                        await self.send_can_message(
                            message.arbitration_id,
                            message.data,
                            bus_id=0
                        )
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error reading CAN0: {e}")
                await asyncio.sleep(0.1)
    
    async def csv_replayer(self):
        # replay CAN messages from CSV file according to their timestamps
        
        print(f"🎬 Starting CSV replay from: {self.csv_file}")
        
        try:
            # read and parse CSV file
            csv_data = []
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # read timestamp (microseconds)
                        timestamp = int(row.get('Time Stamp', row.get('timestamp', 0)))
                        # read CAN ID (hexadecimal)
                        can_id = int(row.get('ID', row.get('id', row.get('can_id', '0'))), 16)
                        # read bus ID (default 0)
                        bus_id = int(row.get('bus', row.get('bus_id', 0)))
                        
                        # decode data fields (D1-D12 format)
                        data = []
                        for i in range(1, 13):
                            data_key = f'D{i}'
                            if data_key in row and row[data_key] != '' and row[data_key] is not None:
                                try:
                                    data_value = str(row[data_key]).strip()
                                    if data_value:
                                        data.append(int(data_value, 16))
                                    else:
                                        break
                                except ValueError:
                                    break
                            else:
                                break
                        
                        csv_data.append({
                            'timestamp': timestamp,
                            'can_id': can_id,
                            'bus_id': bus_id,
                            'data': bytes(data)
                        })
                    except Exception as e:
                        continue
            
            if not csv_data:
                print("❌ No valid CSV data loaded")
                return
            
            print(f"📁 Loaded {len(csv_data)} CAN messages from CSV")
            
            self.csv_data = csv_data
            
            # initialize playback variables
            csv_index = self.csv_index
            csv_start_time = None
            csv_base_timestamp = csv_data[0]['timestamp']
            
            print(f"🕐 CSV時間範圍: {csv_base_timestamp} - {csv_data[-1]['timestamp']}")
            print(f"⏱️ 預計回放時長: {(csv_data[-1]['timestamp'] - csv_base_timestamp) / 1000000:.2f} 秒")
            
            # playback loop
            while self.running and self.mode == 'csv':
                # check if csv_index has been updated by command_receiver (e.g. jump or speed change)
                if self.csv_index != csv_index:
                    csv_index = self.csv_index
                    csv_start_time = None

                    if self.websocket and csv_data:
                        # Safety clamp for the progress calculation
                        safe_idx = min(csv_index, len(csv_data) - 1)
                        progress_pct = (csv_index / len(csv_data)) * 100
                        current_sec = (csv_data[safe_idx]['timestamp'] - csv_data[0]['timestamp']) / 1000000
                        total_sec = (csv_data[-1]['timestamp'] - csv_data[0]['timestamp']) / 1000000

                        await self.websocket.send(json.dumps({
                            'type': 'csv_progress', # Use the same type your progress bar listens to
                            'percentage': min(100, progress_pct),
                            'current_time': current_sec,
                            'total_time': total_sec,
                            'current_index': csv_index,
                            'total_count': len(csv_data)
                        }))

                # pause
                if self.csv_paused:
                    await asyncio.sleep(0.1)
                    # 暫停時重置時間基準
                    csv_start_time = None
                    continue
                
                # check if playback has reached the end of the CSV data
                if csv_index >= len(csv_data):
                    print(f"✅ CSV replay completed: {csv_index} rows processed")
                    break
                
                # intialize time base
                current_time = time.time()
                if csv_start_time is None:
                    csv_start_time = current_time
                    csv_base_timestamp = csv_data[csv_index]['timestamp']
                
                # calculate elapsed time in seconds using the instance variable for playback speed
                elapsed_time = (current_time - csv_start_time) * self.csv_playback_speed
                # covert to microseconds and calculate target timestamp
                target_timestamp = csv_base_timestamp + elapsed_time * 1000000
                
                # update instance variables to reflect the current state of playback
                self.csv_start_time = csv_start_time
                self.csv_base_timestamp = csv_base_timestamp
                
                # send all messages with timestamp <= target_timestamp
                updated = False
                while (csv_index < len(csv_data) and 
                       csv_data[csv_index]['timestamp'] <= target_timestamp):
                    msg = csv_data[csv_index]
                    await self.send_can_message(msg['can_id'], msg['data'], msg['bus_id'])
                    csv_index += 1
                    updated = True
                    self.csv_index = csv_index
                    
                    # print progress every 1000
                    if csv_index % 1000 == 0:
                        progress_pct = (csv_index / len(csv_data)) * 100
                        elapsed_sec = (csv_data[csv_index]['timestamp'] - csv_data[0]['timestamp']) / 1000000
                        print(f"📊 CSV replay: {csv_index}/{len(csv_data)} ({progress_pct:.1f}%) - {elapsed_sec:.2f}s")
                
                # send update to server every 0.5 seconds
                if updated and time.time() - getattr(self, '_last_progress_update', 0) > 0.5:
                    self._last_progress_update = time.time()
                    if self.websocket:
                        progress_pct = (csv_index / len(csv_data)) * 100
                        current_sec = (csv_data[csv_index]['timestamp'] - csv_data[0]['timestamp']) / 1000000
                        total_sec = (csv_data[-1]['timestamp'] - csv_data[0]['timestamp']) / 1000000
                        
                        await self.websocket.send(json.dumps({
                            'type': 'csv_progress',
                            'percentage': progress_pct,
                            'current_time': current_sec,
                            'total_time': total_sec,
                            'current_index': csv_index,
                            'total_count': len(csv_data)
                        }))
                
                # sleep to avoid busy loop
                await asyncio.sleep(0.001)
            
            # notify server that replay is completed
            if self.websocket:
                await self.websocket.send(json.dumps({
                    'type': 'csv_status',
                    'status': 'completed',
                    'message': f'CSV replay completed: {csv_index} rows',
                    'row_count': csv_index
                }))
            
            print("⏸️ CSV replay finished. Waiting for next command...")
                
        except FileNotFoundError:
            print(f"❌ CSV file not found: {self.csv_file}")
        except Exception as e:
            print(f"❌ Error in CSV replayer: {e}")
            import traceback
            traceback.print_exc()
    
    async def read_can1(self):
        # read CAN messages from bus1
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                # read CAN messages only in realtime mode (continue reading even if connection lost)
                if self.mode == 'realtime' and self.bus1:
                    # use thread pool to execute blocking recv call
                    message = await loop.run_in_executor(
                        None,  # use default thread pool
                        lambda: self.bus1.recv(timeout=0.01)
                    )
                    if message:
                        # send_can_message will check the connection status internally
                        await self.send_can_message(
                            message.arbitration_id,
                            message.data,
                            bus_id=1
                        )
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error reading CAN1: {e}")
                await asyncio.sleep(0.1)
    
    async def csv_monitor(self):
        # monitor CSV file changes and manage the csv replayer task
        csv_task = None
        last_file_attempted= None
        last_version_attempted = -1
        
        while self.running:
            try:
                # check if we need to start/restart the csv replayer
                if self.mode == 'csv':
                    # IF there is no task OR the file path changed
                    if csv_task is None or self.csv_file_version != last_version_attempted:
                        # 1. Kill the old task if it exists
                        if csv_task:
                            print(f"🛑 Killing replayer for {last_file_attempted}")
                            csv_task.cancel()
                            try:
                                await csv_task # Wait for it to actually stop
                            except asyncio.CancelledError:
                                pass
                        
                        # 2. Start the NEW task with the NEW file
                        print(f"📂 Loading new file: {self.csv_file}")
                        last_version_attempted = self.csv_file_version
                        last_file_attempted = self.csv_file
                        csv_task = asyncio.create_task(self.csv_replayer())
                
                # cancel csv task if switched back to realtime or idle mode
                elif (self.mode == 'realtime' or self.mode == 'idle') and csv_task is not None:
                    print(f"❌ Stopping CSV replayer task")
                    csv_task.cancel()
                    try:
                        await csv_task
                    except asyncio.CancelledError:
                        pass
                    csv_task = None
                
                # check if csv task is done
                if csv_task and csv_task.done():
                    print(f"✅ CSV replayer completed")
                    csv_task = None
                    self.mode = 'idle'
                
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                if csv_task:
                    csv_task.cancel()
                break
            except Exception as e:
                print(f"Error in CSV monitor: {e}")
                await asyncio.sleep(0.1)
    
    async def command_receiver(self):
        # receive and process commands from the server
        while self.running:
            try:
                if not self.websocket:
                    await asyncio.sleep(0.1)
                    continue
                
                # receive command from server
                message = await self.websocket.recv()
                data = json.loads(message)
                
                cmd_type = data.get('type')
                print(f"📥 Received command: {cmd_type}")
                
                if cmd_type == 'request_csv_list':
                    # server requests CSV file list
                    print("[DEBUG] Received request for CSV file list")
                    csv_files = self.scan_csv_files()
                    print(f"[DEBUG] Found {len(csv_files)} CSV files")
                    
                    response = {
                        'type': 'csv_list',
                        'files': csv_files,
                        'count': len(csv_files)
                    }
                    print(f"[DEBUG] Sending response with {len(csv_files)} files")
                    await self.websocket.send(json.dumps(response))
                    print(f"[DEBUG] Response sent successfully")
                
                elif cmd_type == 'select_csv':
                    # select csv file for replay
                    filename = data.get('filename')
                    print(f"Received CSV selection: {filename}")
                    new_path = os.path.join(LOGS_DIR, filename)

                    if os.path.exists(new_path):
                        self.mode = 'idle' # switch to idle mode while loading new file to prevent any CAN reading/sending

                        # 1. Clear the hardware/software buffers
                        self.flush_message_queue() 
                        
                        # 2. Small sleep to let any 'in-thread' executions finish
                        await asyncio.sleep(0.05) 

                        # 3. Reset all playback state
                        self.csv_file = new_path
                        self.csv_data = []      # Clear old file data from memory
                        self.csv_index = 0      # Reset pointer to start
                        self.csv_start_time = None
                        self.csv_paused = False
                        self.csv_file_version += 1
                        self.mode = 'csv'           # switch to csv mode
                        print(f"Switched to CSV mode: {self.csv_file}")
                        
                        # confirm switch
                        await self.websocket.send(json.dumps({
                            'type': 'mode_changed',
                            'mode': 'csv',
                            'file': filename
                        }))
                    else:
                        print(f"CSV file not found: {self.csv_file}")
                        await self.websocket.send(json.dumps({
                            'type': 'error',
                            'message': f'File not found: {filename}'
                        }))
                
                elif cmd_type == 'switch_realtime':
                    # swith to realtime mode
                    print("Switching back to realtime mode")
                    self.mode = 'realtime'
                    self.csv_file = None
                    self.csv_paused = False

                    # # 1. Clear the hardware/software buffers
                    self.flush_message_queue() 
                    
                    # 2. Small sleep to let any 'in-thread' executions finish
                    await asyncio.sleep(0.05) 
                    
                    await self.websocket.send(json.dumps({
                        'type': 'mode_changed',
                        'mode': 'realtime'
                    }))
                    # print("✅ Backlog purged and Server notified.")
                
                elif cmd_type == 'csv_pause':
                    # pause/resume csv playback 
                    self.csv_paused = not self.csv_paused
                    print(f"CSV replay {'paused' if self.csv_paused else 'resumed'}")
                
                elif cmd_type == 'csv_jump_percentage':
                    # jump to a specific percentage in the CSV file
                    percentage = data.get('percentage', 0)
                    if self.csv_data:
                        percentage = max(0, min(100, percentage))
                        target_index = int(len(self.csv_data) * percentage / 100)
                        self.csv_index = target_index
                        
                        # reset base timestamp
                        if self.csv_index < len(self.csv_data):
                            self.csv_start_time = time.time()
                            self.csv_base_timestamp = self.csv_data[self.csv_index]['timestamp']
                        
                        print(f"Jumped to {percentage}% ({self.csv_index}/{len(self.csv_data)})")
                        
                        await self.websocket.send(json.dumps({
                            'type': 'csv_status',
                            'status': 'jumped',
                            'percentage': percentage,
                            'index': self.csv_index
                        }))
                
                elif cmd_type == 'csv_jump_time':
                    seconds = data.get('seconds', 0)
                    if self.csv_data: # Removed check for csv_start_time so you can jump while paused
                        # Use current index timestamp or last available timestamp
                        idx = min(self.csv_index, len(self.csv_data) - 1)
                        current_timestamp = self.csv_data[idx]['timestamp']
                        target_timestamp = current_timestamp + (seconds * 1000000)
                        
                        # Optimized search: clamp the target_index within valid bounds
                        target_index = self.csv_index
                        if seconds > 0:
                            for i in range(self.csv_index, len(self.csv_data)):
                                target_index = i
                                if self.csv_data[i]['timestamp'] >= target_timestamp:
                                    break
                        else:
                            for i in range(self.csv_index, -1, -1):
                                target_index = i
                                if self.csv_data[i]['timestamp'] <= target_timestamp:
                                    break

                        # SAFETY CLAMP: Never let index equal len(data)
                        self.csv_index = min(max(0, target_index), len(self.csv_data) - 1)
                        
                        # RE-ANCHOR TIME
                        self.csv_start_time = time.time()
                        self.csv_base_timestamp = self.csv_data[self.csv_index]['timestamp']
                        
                        # CALCULATE PROGRESS
                        progress = (self.csv_index / len(self.csv_data)) * 100
                        
                        print(f"Jumped to index {self.csv_index} ({round(progress, 2)}%)")
                        
                        # SEND UPDATE (Including percentage for the progress bar!)
                        await self.websocket.send(json.dumps({
                            'type': 'csv_status',
                            'status': 'jumped',
                            'progress': round(progress, 2),
                            'index': self.csv_index,
                            'seconds': seconds
                        }))
                
                elif cmd_type == 'csv_set_speed':
                    # set playback speed
                    speed = data.get('speed', 1.0)
                    if speed > 0:
                        # adjust base timestamp to maintain continuity
                        if self.csv_start_time and not self.csv_paused and self.csv_data:
                            current_time = time.time()
                            elapsed_time = (current_time - self.csv_start_time) * self.csv_playback_speed
                            self.csv_start_time = current_time - (elapsed_time / speed)
                        
                        self.csv_playback_speed = speed
                        print(f"Playback speed set to {speed}x")
                        
                        await self.websocket.send(json.dumps({
                            'type': 'csv_status',
                            'status': 'speed_changed',
                            'speed': speed
                        }))
                    
            except websockets.exceptions.ConnectionClosed:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in command receiver: {e}")
                await asyncio.sleep(0.1)
    
    def flush_message_queue(self):
        """Purge the queue synchronously to avoid event loop naming conflicts"""
        flushed_count = 0
        # 1. Empty the queue
        try:
            while not self.message_queue.empty():
                self.message_queue.get_nowait()
                flushed_count += 1
        except Exception as e:
            print(f"Note: Queue empty during flush: {e}")

        # 2. Clear the cache (If you use a lock, you need a task)
        self.latest_messages.clear()
        print(f"🧹 Flushed {flushed_count} messages.")

    async def heartbeat_loop(self):
        # heartbeat loop
        while self.running:
            try:
                if self.websocket:
                    await self.send_heartbeat()
                else:
                    # Connection lost, exit loop
                    break
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
    
    async def run(self):
        # main run loop
        print("Starting CAN Data Client...")
        
        # initialize CAN buses
        self.init_can_buses()
        
        while self.running:
            # connect to server
            if await self.connect():
                try:
                    # create and run all tasks
                    tasks = [
                        asyncio.create_task(self.read_can0()),
                        asyncio.create_task(self.read_can1()),
                        asyncio.create_task(self.batch_sender()),
                        asyncio.create_task(self.heartbeat_loop()),
                        asyncio.create_task(self.command_receiver()),
                        asyncio.create_task(self.csv_monitor())
                    ]
                    
                    # wait for task to finish or connection to close
                    done, pending = await asyncio.wait(
                        tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # check if any finished task raised an exception
                    for task in done:
                        if task.exception():
                            print(f"Task failed with exception: {task.exception()}")
                    
                    # cancel remaining tasks
                    for task in pending:
                        task.cancel()
                    
                    # wait for task cleanup
                    await asyncio.gather(*pending, return_exceptions=True)
                    
                except websockets.exceptions.ConnectionClosed:
                    print("Connection to server closed")
                except Exception as e:
                    print(f"Error in main loop: {e}")
                finally:
                    # ensure all the tasks are cancelled
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    
                    # close websocket
                    if self.websocket:
                        try:
                            await self.websocket.close()
                        except Exception:
                            pass
                    self.websocket = None
                    
                    # empty queue to avoid sending stale data on reconnect
                    queue_size = self.message_queue.qsize()
                    if queue_size > 0:
                        print(f"🗑️  Clearing {queue_size} old messages before reconnect")
                        while not self.message_queue.empty():
                            try:
                                self.message_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                    
                    print(f"🔄 Reconnecting in {RECONNECT_DELAY} seconds...")
                    await asyncio.sleep(RECONNECT_DELAY)
    
    def shutdown(self):
        # shutdown client
        print("Shutting down client...")
        self.running = False
        
        if self.bus0:
            self.bus0.shutdown()
        if self.bus1:
            self.bus1.shutdown()

async def main():
    # main function
    client = CANDataClient(SERVER_URL)
    
    try:
        await client.run()
    except KeyboardInterrupt:
        print("\nReceived shutdown signal")
    finally:
        client.shutdown()
        print("Client stopped")

if __name__ == "__main__":
    print("=" * 60)
    print("NTURT CAN Data Client - Vehicle Side")
    print("=" * 60)
    print(f"Server URL: {SERVER_URL}")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    asyncio.run(main())