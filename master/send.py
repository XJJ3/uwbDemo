# -*- coding: utf-8 -*-
"""
MASTER 端双向通信程序

功能:
  1. 向指定 SLAVE 发送数据 (单播)
  2. 向所有 SLAVE 广播数据
  3. 接收来自 SLAVE 的数据 (双向通信)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import serial
import threading
import time
import datetime
from common.nlink import (
    send_to_slave, broadcast, establish_link,
    Role, UserFrame1
)

PORT = '/dev/cu.wchusbserial585C0089431'  # MASTER 端口
BAUD = 921600
SLAVE_ID = 0


class MasterTerminal:
    """MASTER 终端，支持双向通信"""
    
    def __init__(self, port: str, baud: int, slave_id: int = 1):
        self.port = port
        self.baud = baud
        self.slave_id = slave_id
        self.ser = None
        self.running = False
        self.rx_thread = None
        self.link_established = False
    
    def start(self):
        """启动终端"""
        self.ser = serial.Serial(self.port, self.baud, timeout=0.1, bytesize=8, parity='N', stopbits=1)
        self.ser.reset_input_buffer()
        self.running = True
        
        # 启动接收线程
        self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.rx_thread.start()
        
        print(f'MASTER 终端已启动')
        print(f'  端口: {self.port}')
        print(f'  波特率: {self.baud}')
        print(f'  默认 SLAVE ID: {self.slave_id}')
        print()
        self._print_help()
    
    def stop(self):
        """停止终端"""
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1)
        if self.ser:
            self.ser.close()
        print('终端已停止')
    
    def _print_help(self):
        """打印帮助信息"""
        print('命令:')
        print('  <消息>           向 SLAVE 发送消息')
        print('  /b <消息>        广播到所有 SLAVE')
        print('  /l               建立双向连接')
        print('  /s <id>          切换目标 SLAVE ID')
        print('  /h               显示帮助')
        print('  /q               退出')
        print()
    
    def _receive_loop(self):
        """接收线程主循环"""
        while self.running:
            try:
                # SLAVE 发来的数据是透明数据，直接读取
                data = self.ser.read(4096)
                if data:
                    self._handle_receive(data)
            except Exception as e:
                if self.running:
                    print(f'[接收错误] {e}')
    
    def _handle_receive(self, data: bytes):
        """处理接收到的数据"""
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        try:
            text = data.decode('utf-8')
            print(f'\r[{now}] ← SLAVE: "{text}"')
        except UnicodeDecodeError:
            hex_str = data.hex(' ').upper()
            print(f'\r[{now}] ← SLAVE (HEX): {hex_str}')
        print('> ', end='', flush=True)
    
    def send_to_slave(self, data: bytes, slave_id: int = None):
        """向指定 SLAVE 发送数据"""
        sid = slave_id if slave_id is not None else self.slave_id
        frame = send_to_slave(sid, data)
        self.ser.write(frame)
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f'[{now}] → SLAVE{sid}: {data!r} ({len(data)}B)')
        self.link_established = True
    
    def broadcast(self, data: bytes):
        """向所有 SLAVE 广播数据"""
        frame = broadcast(data)
        self.ser.write(frame)
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f'[{now}] → 广播: {data!r} ({len(data)}B)')
    
    def establish_link(self, slave_id: int = None):
        """建立与 SLAVE 的双向连接"""
        sid = slave_id if slave_id is not None else self.slave_id
        frame = establish_link(sid)
        self.ser.write(frame)
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f'[{now}] → 建立连接 SLAVE{sid}')
        self.link_established = True
    
    def run_interactive(self):
        """交互式运行"""
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
                    elif line == '/l':
                        self.establish_link()
                    elif line.startswith('/s '):
                        try:
                            new_id = int(line[3:])
                            self.slave_id = new_id
                            print(f'目标 SLAVE ID 已切换为 {new_id}')
                        except ValueError:
                            print('错误: ID 必须是数字')
                    elif line.startswith('/b '):
                        msg = line[3:]
                        self.broadcast(msg.encode('utf-8'))
                    elif line.startswith('/'):
                        print(f'未知命令: {line}')
                        self._print_help()
                    else:
                        # 发送给默认 SLAVE
                        self.send_to_slave(line.encode('utf-8'))
                
                except EOFError:
                    break
        
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def send_once(self, data: bytes, slave_id: int = None):
        """单次发送模式"""
        self.start()
        self.send_to_slave(data, slave_id)
        time.sleep(0.1)
        self.stop()
    
    def broadcast_once(self, data: bytes):
        """单次广播模式"""
        self.start()
        self.broadcast(data)
        time.sleep(0.1)
        self.stop()


def main():
    terminal = MasterTerminal(PORT, BAUD, SLAVE_ID)
    
    if len(sys.argv) < 2:
        # 交互模式
        terminal.run_interactive()
    elif sys.argv[1] == '-b':
        # 广播模式
        msg = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else 'test'
        terminal.broadcast_once(msg.encode())
    elif sys.argv[1] == '-l':
        # 建立连接
        terminal.start()
        terminal.establish_link()
        print('连接已建立，按 Ctrl+C 退出')
        try:
            while terminal.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        terminal.stop()
    elif sys.argv[1] == '-h':
        print('用法:')
        print('  python master/send.py              交互模式')
        print('  python master/send.py <消息>       发送消息')
        print('  python master/send.py -b <消息>    广播')
        print('  python master/send.py -l           建立双向连接')
        print('  python master/send.py -h           显示帮助')
    else:
        # 单次发送
        msg = ' '.join(sys.argv[1:])
        terminal.send_once(msg.encode())


if __name__ == '__main__':
    main()
