# -*- coding: utf-8 -*-
"""
SLAVE 通用启动程序

功能:
1. 自动检测本地所有 SLAVE 设备
2. 智能选择未被占用的串口连接
3. 连接成功后打印串口名称
4. 收到 MASTER 的探测请求后回复自身 ID
5. 支持双向通信 (收发消息)

用法:
  python slave/slave.py              自动检测并连接可用串口
  python slave/slave.py -p /dev/xxx  指定端口
  python slave/slave.py -h           显示帮助
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serial
import serial.tools.list_ports
import threading
import time
import datetime
from typing import Optional, Tuple, List

from common.nlink import (
    Role, UserFrame1,
    build_user_frame1, parse_user_frame1, find_and_parse_frame,
    FRAME_HEADER_USER_FRAME1
)


BAUD = 921600
PING_PAYLOAD = b'\x50\x49'
PONG_PREFIX = b'\x52\x53'
LOCK_FILE = '/tmp/uwb_slave_ports.lock'


def get_locked_ports() -> set:
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                return set(line.strip() for line in f if line.strip())
        except:
            return set()
    return set()


def lock_port(port: str):
    locked = get_locked_ports()
    locked.add(port)
    with open(LOCK_FILE, 'w') as f:
        for p in locked:
            f.write(p + '\n')


def unlock_port(port: str):
    locked = get_locked_ports()
    locked.discard(port)
    with open(LOCK_FILE, 'w') as f:
        for p in locked:
            f.write(p + '\n')


def detect_all_slave_ports() -> List[Tuple[str, int]]:
    print('正在扫描串口...')
    
    ports = serial.tools.list_ports.comports()
    
    valid_ports = []
    for p in ports:
        device = (p.device or '').lower()
        hwid = (p.hwid or '').lower()
        desc = (p.description or '').lower()
        if 'wchusbserial' in device or 'usb' in hwid or 'usb' in desc or 'com' in device:
            valid_ports.append(p)
    
    if not valid_ports:
        print('未找到有效的 USB 串口设备')
        print(f'可用串口: {[p.device for p in ports]}')
        return []
    
    print(f'找到 {len(valid_ports)} 个串口，正在识别...')
    
    slave_ports = []
    for port_info in valid_ports:
        port = port_info.device
        result = identify_port(port)
        if result:
            role, device_id = result
            if role == Role.SLAVE:
                print(f'  ✓ 发现 SLAVE {device_id}: {port}')
                slave_ports.append((port, device_id))
            else:
                role_name = {Role.MASTER: 'MASTER', Role.ANCHOR: 'ANCHOR', 
                            Role.TAG: 'TAG', Role.NODE: 'NODE'}.get(role, f'Role:{role}')
                print(f'  - {port}: {role_name} (跳过)')
    
    return slave_ports


def identify_port(port: str, timeout: float = 0.3) -> Optional[Tuple[int, int]]:
    READ_FRAME = bytes([
        0x52, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x4B
    ])
    
    try:
        ser = serial.Serial(port, BAUD, timeout=timeout, bytesize=8, parity='N', stopbits=1)
        ser.reset_input_buffer()
        ser.write(READ_FRAME)
        
        buffer = bytearray()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            data = ser.read(64)
            if data:
                buffer.extend(data)
                if len(buffer) >= 24 and buffer[0] == 0x52 and buffer[1] == 0x00:
                    role = buffer[22]
                    device_id = buffer[23]
                    ser.close()
                    return role, device_id
        
        ser.close()
        return None
        
    except Exception:
        return None


def select_available_port(slave_ports: List[Tuple[str, int]]) -> Optional[Tuple[str, int]]:
    if not slave_ports:
        return None
    
    locked = get_locked_ports()
    
    for port, slave_id in slave_ports:
        if port not in locked:
            return port, slave_id
    
    print('\n所有 SLAVE 设备串口已被占用')
    print('如果这是错误的，请删除锁文件: rm /tmp/uwb_slave_ports.lock')
    return None


class SlaveTerminal:
    def __init__(self, port: str, slave_id: int, baud: int = BAUD):
        self.port = port
        self.slave_id = slave_id
        self.baud = baud
        self.ser = None
        self.running = False
        self.rx_thread = None
        self.rx_buffer = bytearray()
        self.link_established = False
    
    def start(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.1, bytesize=8, parity='N', stopbits=1)
        self.ser.reset_input_buffer()
        self.running = True
        
        lock_port(self.port)
        
        self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.rx_thread.start()
        
        print(f'\n{"="*50}')
        print(f'SLAVE {self.slave_id} 终端已启动')
        print(f'串口: {self.port}')
        print(f'波特率: {self.baud}')
        print(f'{"="*50}')
        print('等待 MASTER 连接...\n')
        self._print_help()
    
    def stop(self):
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1)
        if self.ser:
            self.ser.close()
        unlock_port(self.port)
        print('\n终端已停止')
    
    def _print_help(self):
        print('命令:')
        print('  <消息>        向 MASTER 发送消息')
        print('  /h            显示帮助')
        print('  /q            退出')
        print('  /status       显示状态\n')
    
    def _receive_loop(self):
        while self.running:
            try:
                data = self.ser.read(4096)
                if data:
                    self._handle_data(data)
            except Exception as e:
                if self.running:
                    print(f'\r[接收错误] {e}')
                    print('> ', end='', flush=True)
    
    def _handle_data(self, data: bytes):
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        
        if not self.link_established:
            self.link_established = True
            print(f'\r[{now}] ★ 已与 MASTER 建立双向连接')
        
        if data.startswith(FRAME_HEADER_USER_FRAME1):
            self._handle_frame(data, now)
        else:
            self._handle_raw(data, now)
    
    def _handle_frame(self, data: bytes, now: str):
        buffer = bytearray(data)
        offset = 0
        
        while offset < len(buffer):
            frame, consumed = find_and_parse_frame(buffer[offset:])
            if frame is None:
                break
            offset += consumed
            
            if frame.payload == PING_PAYLOAD:
                self._respond_ping()
            elif frame.payload:
                self._print_message(frame.payload, now, is_frame=True)
    
    def _handle_raw(self, data: bytes, now: str):
        if data == PING_PAYLOAD:
            self._respond_ping()
        else:
            self._print_message(data, now, is_frame=False)
    
    def _respond_ping(self):
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        payload = PONG_PREFIX + bytes([self.slave_id])
        self.ser.write(payload)
        print(f'\r[{now}] ← 探测请求，回复 ID: {self.slave_id}')
        print('> ', end='', flush=True)
    
    def _print_message(self, data: bytes, now: str, is_frame: bool = False):
        try:
            text = data.decode('utf-8')
            print(f'\r[{now}] ← MASTER: "{text}"')
        except UnicodeDecodeError:
            hex_str = data.hex(' ').upper()
            print(f'\r[{now}] ← MASTER (HEX): {hex_str}')
        print('> ', end='', flush=True)
    
    def send(self, data: bytes):
        self.ser.write(data)
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        
        try:
            text = data.decode('utf-8')
            print(f'[{now}] → MASTER: "{text}"')
        except UnicodeDecodeError:
            print(f'[{now}] → MASTER (HEX): {data.hex(" ").upper()}')
        print('> ', end='', flush=True)
    
    def run_interactive(self):
        self.start()
        try:
            while self.running:
                try:
                    line = input('> ').strip()
                    if not line:
                        continue
                    
                    if line == '/q':
                        break
                    elif line == '/h':
                        self._print_help()
                    elif line == '/status':
                        status = '已连接' if self.link_established else '等待连接'
                        print(f'状态: SLAVE {self.slave_id} @ {self.port} - {status}')
                    elif line.startswith('/'):
                        print(f'未知命令: {line}')
                        self._print_help()
                    else:
                        self.send(line.encode('utf-8'))
                except EOFError:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    port = None
    slave_id = None
    
    args = sys.argv[1:]
    
    if '-h' in args or '--help' in args:
        print(__doc__)
        print('\n选项:')
        print('  -p, --port <端口>  指定串口')
        print('  -i, --id <ID>      指定 SLAVE ID (0-255)')
        print('  -h, --help         显示帮助')
        return
    
    i = 0
    while i < len(args):
        if args[i] in ('-p', '--port') and i + 1 < len(args):
            port = args[i + 1]
            i += 2
        elif args[i] in ('-i', '--id') and i + 1 < len(args):
            slave_id = int(args[i + 1])
            i += 2
        else:
            i += 1
    
    if not port:
        slave_ports = detect_all_slave_ports()
        if not slave_ports:
            print('\n错误: 未找到 SLAVE 设备')
            print('请确保设备已连接，或使用 -p 参数指定端口')
            sys.exit(1)
        
        result = select_available_port(slave_ports)
        if not result:
            sys.exit(1)
        
        port, detected_id = result
        if slave_id is None:
            slave_id = detected_id
    
    if slave_id is None:
        print('警告: 无法确定 SLAVE ID，使用默认值 0')
        slave_id = 0
    
    terminal = SlaveTerminal(port, slave_id)
    terminal.run_interactive()


if __name__ == '__main__':
    main()
