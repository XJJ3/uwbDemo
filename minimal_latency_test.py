# -*- coding: utf-8 -*-
"""
最小化延迟测试
排除打印、sleep、超时等待的影响
"""

import serial
import time
import sys


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.wchusbserial585C0089431"
    baud = 921600
    
    ser = serial.Serial(port, baud, timeout=0.001, bytesize=8, parity='N', stopbits=1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    test_frame = bytes.fromhex("54F1FFFFFFFF050003001111016C")
    
    print(f"\n最小化延迟测试 - {port}")
    print(f"发送帧: {test_frame.hex().upper()}")
    print(f"测试 50 次，不打印中间结果\n")
    
    delays = []
    
    for i in range(50):
        ser.reset_input_buffer()
        
        t1 = time.perf_counter()
        ser.write(test_frame)
        
        resp = b''
        start = time.perf_counter()
        while (time.perf_counter() - start) < 0.05:
            if ser.in_waiting > 0:
                resp += ser.read(ser.in_waiting)
                if len(resp) >= 15:
                    break
        t2 = time.perf_counter()
        
        delay_ms = (t2 - t1) * 1000
        if resp:
            delays.append(delay_ms)
    
    ser.close()
    
    if delays:
        print(f"成功: {len(delays)}/50")
        print(f"最小: {min(delays):.2f}ms")
        print(f"最大: {max(delays):.2f}ms")
        print(f"平均: {sum(delays)/len(delays):.2f}ms")
        print(f"中位数: {sorted(delays)[len(delays)//2]:.2f}ms")
    else:
        print("全部失败，无响应")


if __name__ == '__main__':
    main()
