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
        
        # CSV replay parameters
        self.mode = 'realtime' # 'realtime' or 'csv' or 'idle'
        self.csv_file = None
        self.csv_paused = False
        self.csv_playback_speed = CSV_REPLAY_SPEED
        self.csv_data = []  # store CSV data
        self.csv_index = 0  # current replay index
        self.csv_start_time = None  # replay start time (real time)
        self.csv_base_timestamp = None  # csv base timestamp
        self.csv_file_version = 0 # csv file version for detecting changes (incremented on each file selection)
        self.csv_jumped = False # flag to indicate if a jump command was received or if we just switched to a new file (trigger time re-anchoring in the replay loop)

        self.command_handler = {
            'request_csv_list': 'handle_request_csv_list',
            'select_csv': 'handle_select_csv',
            'switch_realtime': 'handle_switch_realtime',
            'csv_pause': 'handle_csv_pause',
            'csv_jump_percentage': 'handle_csv_jump_percentage',
            'csv_jump_time': 'handle_csv_jump_time',
            'csv_set_speed': 'handle_csv_set_speed',
            'csv_restart': 'handle_csv_restart'
        }
        
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
    
    def init_can_bus(self, channel_name, bus_name):
        # initialize a CAN bus
        try:
            can_kwargs = dict(channel=channel_name)
            if version.parse(can.__version__) >= version.parse('4.2.0'):
                can_kwargs['interface'] = 'socketcan'
            else:
                can_kwargs['bustype'] = 'socketcan'
            return can.interface.Bus(**can_kwargs)
        except Exception as e:
            print(f"Warning: Could not initialize {bus_name} bus: {e}")
            return None
    
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
    
    async def read_can_bus(self, bus_id):
        # read CAN messages from the specified bus
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                # read CAN messages only in realtime mode (continue reading even if connection lost)
                if self.mode == 'realtime' and getattr(self, f'bus{bus_id}'):
                    # use thread pool to execute blocking recv call
                    message = await loop.run_in_executor(
                        None,  # use default thread pool
                        lambda: getattr(self, f'bus{bus_id}').recv(timeout=0.01)
                    )
                    if message:
                        # send_can_message will check the connection status internally
                        await self.send_can_message(
                            message.arbitration_id,
                            message.data,
                            bus_id=bus_id
                        )
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error reading CAN{bus_id}: {e}")
                await asyncio.sleep(0.1)
    
    async def csv_manager(self):
        last_version_processed = -1
        
        while self.running:
            try:
                # state check
                # if not in CSV mode, or already finished the current version, just wait
                if self.mode != 'csv' or self.csv_file_version == last_version_processed:
                    await asyncio.sleep(0.2) 
                    continue

                # load the new CSV file for replay
                print(f"🎬 Starting CSV replay from: {self.csv_file}")
               
                self.csv_data = self.parse_csv_file(self.csv_file)
            
                print(f"🕐 CSV時間範圍: {self.csv_data[0]['timestamp']} - {self.csv_data[-1]['timestamp']}")
                print(f"⏱️ 預計回放時長: {(self.csv_data[-1]['timestamp'] - self.csv_data[0]['timestamp']) / 1000000:.2f} 秒")
                
                if not self.csv_data:
                    print("⚠️ Failed to load CSV or file empty. Switching to idle.")
                    self.mode = 'idle'
                    last_version_processed = self.csv_file_version # Mark as "attempted"
                    continue

                last_version_processed = self.csv_file_version
                total_rows = len(self.csv_data)
    
                # 3. THE replay LOOP
                # This loop "cancels" itself if mode changes OR a new file version is requested
                # 3. THE replay LOOP
                while (self.running and 
                    self.mode == 'csv' and 
                    self.csv_file_version == last_version_processed):
                    
                    # --- JUMP HANDLING ---
                    if self.csv_jumped:
                        self.csv_base_timestamp = None  # Force timing re-anchor
                        self.csv_jumped = False         # CLEAR the flag so we don't loop here
                        # Optional: yield slightly to let state settle
                        await asyncio.sleep(0) 

                    if self.csv_index >= total_rows:
                        await self.notify_completion(total_rows)
                        self.mode = 'idle'
                        await self.websocket.send(json.dumps({
                            'type': 'mode_changed',
                            'mode': 'idle',
                            'filename': self.csv_file
                        }))
                        break

                    if self.csv_paused:
                        self.csv_base_timestamp = None 
                        await asyncio.sleep(0.1)
                        continue

                    # --- TIMING LOGIC ---
                    now = time.time()
                    
                    # If we just jumped or unpaused, this will be None
                    if self.csv_base_timestamp is None:
                        self.csv_base_timestamp = now
                        # Re-anchor to the CSV timestamp of the NEW current index
                        self._current_csv_anchor_ts = self.csv_data[min(self.csv_index, total_rows-1)]['timestamp']

                    # Calculate how much "CSV time" has passed since we anchored
                    elapsed_seconds = (now - self.csv_base_timestamp) * self.csv_playback_speed
                    target_ts = self._current_csv_anchor_ts + (elapsed_seconds * 1000000)

                    # --- BATCH SEND ---
                    while (self.csv_index < total_rows and 
                        self.csv_data[self.csv_index]['timestamp'] <= target_ts):
                        
                        if self.mode != 'csv' or self.csv_jumped: # Break batch if another jump happens
                            break 
                            
                        msg = self.csv_data[self.csv_index]
                        await self.send_can_message(msg['can_id'], msg['data'], msg['bus_id'])
                        
                        self.csv_index += 1

                    # Periodic progress update to UI (every ~0.5s)
                    if time.time() - getattr(self, 'last_progress_update', 0) > 0.5:
                        self.last_progress_update = time.time()
                        await self.send_progress_update(self.csv_data, self.csv_index)

                    await asyncio.sleep(0.001) # Yield to other tasks (heartbeat, command_receiver)

                print(f"ℹ️ CSV Manager exited replay loop (Mode: {self.mode})")

            except Exception as e:
                print(f"❌ Error in CSV manager: {e}")
                await asyncio.sleep(1)

        print("🛑 CSV Manager shut down.")

    def parse_csv_file(self, file_path):
        # parse the CSV file and return a list of messages with timestamp, can_id, bus_id, and data bytes
        csv_data = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Flexible header detection
                        ts = int(row.get('Time Stamp', row.get('timestamp', 0)))
                        can_id = int(row.get('ID', row.get('id', row.get('can_id', '0'))), 16)
                        bus_id = int(row.get('bus', row.get('bus_id', 0)))

                        # Extract D1 through D12
                        data_bytes = []
                        for i in range(1, 13):
                            val = row.get(f'D{i}')
                            # Check if the value exists and isn't just whitespace
                            if val and val.strip():
                                try:
                                    # Convert hex string to integer
                                    data_bytes.append(int(val.strip(), 16))
                                except ValueError:
                                    # If there's "garbage" (e.g., 'GG'), treat it as the end of the data
                                    print(f"⚠️ Warning: Invalid hex data '{val}' at D{i}. Stopping payload here.")
                                    break
                            else:
                                # End of data payload (empty cell or missing key)
                                break
                        
                        csv_data.append({
                            'timestamp': ts,
                            'can_id': can_id,
                            'bus_id': bus_id,
                            'data': bytes(data_bytes)
                        })
                    except (ValueError, TypeError):
                        continue # Skip malformed rows
            return csv_data
        except Exception as e:
            print(f"❌ File Load Error: {e}")
            return None
        
    async def send_progress_update(self, csv_data, index):
        # sends replay progress to the server
        total = len(csv_data)
        # clamp index to valid range
        safe_idx = min(index, total - 1)
        
        current_ts = csv_data[safe_idx]['timestamp']
        start_ts = csv_data[0]['timestamp']
        total_ts = csv_data[-1]['timestamp']

        await self.websocket.send(json.dumps({
            'type': 'csv_progress',
            'percentage': round((index / total) * 100, 2),
            'current_time': round((current_ts - start_ts) / 1000000, 2),
            'total_time': round((total_ts - start_ts) / 1000000, 2),
            'current_index': index,
            'total_count': total
        }))

    async def notify_completion(self, total_rows):
        # inform the server that CSV replay has completed
        if self.websocket:
            await self.websocket.send(json.dumps({
                'type': 'csv_status',
                'status': 'completed',
                'message': f'CSV replay completed: {total_rows} rows.',
                'row_count': total_rows
            }))
        print("⏸️ CSV replay finished. Waiting for next command...")

    async def command_receiver(self):
        # receive and process commands from the server
        while self.running:
            try:
                if not self.websocket:
                    await asyncio.sleep(0.1)
                    continue
                
                message = await self.websocket.recv()
                data = json.loads(message)
                
                cmd_type = data.get('type')
                print(f"📥 Received command: {cmd_type}")
                handler_name = self.command_handler.get(cmd_type)
                handler = getattr(self, handler_name)

                if handler:
                    await handler(data)
                else: 
                    print(f"⚠️ Unknown command type: {cmd_type}")
            except websockets.exceptions.ConnectionClosed:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in command receiver: {e}")
                await asyncio.sleep(0.1)
    
    async def handle_request_csv_list(self, data):
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

    async def handle_select_csv(self, data):
        # select csv file for replay
        filename = data.get('filename')
        print(f"Received CSV selection: {filename}")
        new_path = os.path.join(LOGS_DIR, filename)

        if os.path.exists(new_path):
            # switch to idle first to make sure the queue is cleared 
            self.mode = 'idle'
            # clear the message queue
            self.flush_message_queue() 
            
            # small sleep to let any 'in-thread' executions finish
            await asyncio.sleep(0.05) 

            # reset all replay state
            self.csv_file = new_path
            self.csv_data = []      # clear old file data from memory
            self.csv_index = 0      # reset pointer to start
            self.csv_jumped = True   # set jumped flag to re-anchor timing on next loop
            self.csv_paused = False
            self.csv_file_version += 1
            self.mode = 'csv'           # switch back to csv mode
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

    async def handle_switch_realtime(self, data):
        # swith to realtime mode
        print("Switching back to realtime mode")
        self.mode = 'realtime'
        self.csv_file = None
        self.csv_paused = False

        # clear the message queue
        self.flush_message_queue() 
        
        # small sleep to let any 'in-thread' executions finish
        await asyncio.sleep(0.05) 
        
        await self.websocket.send(json.dumps({
            'type': 'mode_changed',
            'mode': 'realtime',
        }))

    async def handle_csv_pause(self, data):
        # pause/resume csv replay 
        self.csv_paused = not self.csv_paused
        print(f"CSV replay {'paused' if self.csv_paused else 'resumed'}")

    async def handle_csv_jump_percentage(self, data):
        # jump to a specific percentage in the CSV file
        percentage = data.get('percentage', 0)
        if self.csv_data:
            percentage = max(0, min(100, percentage))
            target_index = int(len(self.csv_data) * percentage / 100)
            self.csv_index = target_index
            self.csv_jumped = True
            print(f"Jumped to {percentage:.2f}% ({self.csv_index}/{len(self.csv_data)})")
            
            await self.websocket.send(json.dumps({
                'type': 'csv_status',
                'status': 'jumped',
                'percentage': percentage,
                'index': self.csv_index
            }))

    async def handle_csv_jump_time(self, data):
        seconds = data.get('seconds', 0)
        if self.csv_data: 
            # use current index timestamp or last available timestamp
            idx = min(self.csv_index, len(self.csv_data) - 1)
            current_timestamp = self.csv_data[idx]['timestamp']
            target_timestamp = current_timestamp + (seconds * 1000000)
            
            # clamp the target_index within valid bounds
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

            # clamp csv_index to valid range
            self.csv_index = min(max(0, target_index), len(self.csv_data) - 1)
            self.csv_jumped = True
            
            # calculate progress
            progress = (self.csv_index / len(self.csv_data)) * 100
            print(f"Jumped to {progress:.2f}% ({self.csv_index}/{len(self.csv_data)})")
            
            # send update to server
            await self.websocket.send(json.dumps({
                'type': 'csv_status',
                'status': 'jumped',
                'progress': round(progress, 2),
                'index': self.csv_index,
                'seconds': seconds
            }))

            await self.send_progress_update(self.csv_data, self.csv_index)

    async def handle_csv_set_speed(self, data):
        # set replay speed
        speed = data.get('speed', 1.0)
        if speed > 0:
            self.csv_playback_speed = speed
            print(f"replay speed set to {speed}x")
            
            await self.websocket.send(json.dumps({
                'type': 'csv_status',
                'status': 'speed_changed',
                'speed': speed
            }))

    async def handle_csv_restart(self, data):
        if self.mode == 'idle' and self.csv_file:
            # Wrap the path/filename in a dict so handle_select_csv can read it
            filename = os.path.basename(self.csv_file)
            await self.handle_select_csv({'filename': filename})
        
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
        self.bus0 = self.init_can_bus('can0', 'CAN0')
        self.bus1 = self.init_can_bus('can1', 'CAN1')
        
        while self.running:
            if await self.connect():
                try:
                    # use a TaskGroup (Python 3.11+)
                    async with asyncio.TaskGroup() as tg:
                        # start all workers
                        t1 = tg.create_task(self.read_can_bus(0))
                        t2 = tg.create_task(self.read_can_bus(1))
                        t3 = tg.create_task(self.batch_sender())
                        t4 = tg.create_task(self.heartbeat_loop())
                        t5 = tg.create_task(self.csv_manager())
                        
                        # if command_receiver returns (connection loss) or 
                        # one of the above tasks raises an exception, the TaskGroup will 
                        # automatically terminate all tasks and exit the block
                        await self.command_receiver()

                        for task in [t1, t2, t3, t4, t5]: 
                            task.cancel() # Ensure all tasks are cancelled if command_receiver exits

                except (websockets.exceptions.ConnectionClosed, Exception) as e:
                    print(f"📡 Connection lost or Error: {e}")
                finally:
                    if self.websocket:
                        try:
                            await self.websocket.close()
                        except Exception:
                            pass
                    self.websocket = None
                    self.flush_message_queue() 
                    
                print(f"🔄 Reconnecting in {RECONNECT_DELAY}s...")
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