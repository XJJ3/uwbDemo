# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import serial
import threading
import time
import datetime

PORT = '/dev/tty.usbserial-5AB31140701'  # SLAVE1 端口
BAUD = 921600


class SlaveTerminal:
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.ser = None
        self.running = False
        self.rx_thread = None
    
    def start(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
        self.ser.reset_input_buffer()
        self.running = True
        
        self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.rx_thread.start()
        
        print(f'SLAVE 终端已启动 ({self.port}, {self.baud}bps)')
        print('等待 MASTER 数据...\n')
        self._print_help()
    
    def stop(self):
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1)
        if self.ser:
            self.ser.close()
        print('终端已停止')
    
    def _print_help(self):
        print('命令:')
        print('  <消息>        向 MASTER 发送消息')
        print('  /h            显示帮助')
        print('  /q            退出\n')
    
    def _receive_loop(self):
        while self.running:
            try:
                data = self.ser.read(4096)
                if data:
                    self._handle_receive(data)
            except Exception as e:
                if self.running:
                    print(f'[接收错误] {e}')
    
    def _handle_receive(self, data: bytes):
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        try:
            text = data.decode('utf-8')
            print(f'\r[{now}] ← MASTER: "{text}"')
        except UnicodeDecodeError:
            print(f'\r[{now}] ← MASTER (HEX): {data.hex(" ").upper()}')
        print('> ', end='', flush=True)
    
    def send(self, data: bytes):
        self.ser.write(data)
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f'[{now}] → MASTER: {data!r} ({len(data)}B)')
    
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
    
    def run_receive_only(self):
        self.start()
        print('纯接收模式，按 Ctrl+C 退出\n')
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        self.stop()


def main():
    terminal = SlaveTerminal(PORT, BAUD)
    
    if len(sys.argv) < 2:
        terminal.run_interactive()
    elif sys.argv[1] == '-r':
        terminal.run_receive_only()
    elif sys.argv[1] == '-h':
        print('用法:')
        print('  python slave/receive.py        交互模式')
        print('  python slave/receive.py -r     纯接收模式')
        print('  python slave/receive.py -h     显示帮助')
    else:
        msg = ' '.join(sys.argv[1:])
        terminal.start()
        terminal.send(msg.encode())
        time.sleep(0.1)
        terminal.stop()


if __name__ == '__main__':
    main()
