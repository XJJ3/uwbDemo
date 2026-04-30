# -*- coding: utf-8 -*-
"""
最小化 SLAVE 响应
不打印，只回复
"""

import serial
import time
import sys
import struct


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.wchusbserial5AB50010561"
    baud = 921600
    
    ser = serial.Serial(port, baud, timeout=0.001, bytesize=8, parity='N', stopbits=1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    count = 0
    
    print(f"\n最小化 SLAVE 响应 - {port}")
    print(f"不打印中间结果，只统计\n")
    
    start_time = time.time()
    
    while True:
        data = ser.read(64)
        if data:
            ts = time.time()
            ack = b'ACK' + struct.pack('<I', count) + struct.pack('<Q', int(ts * 1_000_000))
            ser.write(ack)
            count += 1
            
            if count % 100 == 0:
                elapsed = time.time() - start_time
                print(f"\r已处理: {count} | 速率: {count/elapsed:.1f}/s", end="", flush=True)
        
        if time.time() - start_time > 30:
            break
    
    ser.close()
    print(f"\n完成，共处理 {count} 条消息")


if __name__ == '__main__':
    main()
