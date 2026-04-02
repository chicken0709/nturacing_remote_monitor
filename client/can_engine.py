"""
CAN Engine for NTURT Remote Monitor
====================================
This module handles CAN bus message reading and processing.
"""

import can
import time
import struct
import asyncio
from packaging import version

SIMULATION_MODE = False # simulate CAN messages

class CANEngine:
    def __init__ (self, client):
        self.client = client

        self.bus0 = None
        self.bus1 = None

    def start(self):
        # initialize the engine by setting up CAN buses
        self.bus0 = self.init_can_bus('can0', 'CAN0')
        self.bus1 = self.init_can_bus('can1', 'CAN1')

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
        
    async def read_can_bus(self, bus_id):
        # read CAN messages from the specified bus
        loop = asyncio.get_event_loop()
        while self.client.running:
            try:
                # read CAN messages only in realtime mode (continue reading even if connection lost)
                if self.client.mode == 'realtime' and getattr(self, f'bus{bus_id}'):
                    # use thread pool to execute blocking recv call
                    message = await loop.run_in_executor(
                        None,  # use default thread pool
                        lambda: getattr(self, f'bus{bus_id}').recv(timeout=0.01)
                    )
                    if message:
                        # enqueue_can_message will check the connection status internally
                        await self.client.enqueue_can_message(
                            message.arbitration_id,
                            message.data,
                            bus_id=bus_id
                        )
                elif self.client.mode == 'realtime' and SIMULATION_MODE:
                    # simulate sending a CAN message on 0x421
                    now_utc = int(time.time())
                    data = struct.pack('<BI', 0x01, now_utc)
                    print(f"Simulating CAN message on bus {bus_id}: ID=0x421, Data={data.hex()}")
                    await self.client.enqueue_can_message(
                        0x421,
                        data,
                        bus_id=bus_id
                    )
                    await asyncio.sleep(1)  # delay between messages
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error reading CAN{bus_id}: {e}")
                await asyncio.sleep(0.1)
    
    def shutdown(self):
        # shutdown the engine by closing CAN buses
        if self.bus0:
            self.bus0.shutdown()
        if self.bus1:
            self.bus1.shutdown()