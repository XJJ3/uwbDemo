# -*- coding: utf-8 -*-
"""
SLAVE 自动回复工具
收到数据后自动回复 ACK
"""

import serial
import time
import datetime
import sys
import struct


def main():
    print(f'\n{"="*60}')
    print(f'SLAVE 自动回复工具')
    print(f'{"="*60}\n')
    
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = input("输入串口路径: ").strip()
    
    baud = 921600
    
    try:
        ser = serial.Serial(port, baud, timeout=0.01, bytesize=8, parity='N', stopbits=1)
    except Exception as e:
        print(f"无法打开串口: {e}")
        sys.exit(1)
    
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    print(f"\n已连接 {port} @ {baud}")
    print(f"按 Ctrl+C 退出\n")
    print(f"收到数据后自动回复: ACK + 时间戳\n")
    
    count = 0
    
    try:
        while True:
            data = ser.read(4096)
            if data:
                ts_recv = time.time() * 1000
                
                ack = b'ACK' + struct.pack('<I', count) + struct.pack('<Q', int(ts_recv * 1000))
                
                ser.write(ack)
                ser.flush()
                ser.write(ack)
                ser.flush()
                
                ts_reply = time.time() * 1000
                process_time = ts_reply - ts_recv
                
                now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                print(f"[{now}] #{count:04d} 收到 {len(data):3d}B | {data[:20].hex().upper():<40} | 回复 {len(ack)}B | 处理 {process_time:.2f}ms")
                count += 1
    
    except KeyboardInterrupt:
        print(f"\n\n退出，共处理 {count} 条消息")
    
    ser.close()


if __name__ == '__main__':
    main()
