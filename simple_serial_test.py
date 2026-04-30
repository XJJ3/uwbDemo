# -*- coding: utf-8 -*-
"""
交互式串口测试工具
类似 NAssistant 串口助手，但带精确时间戳
"""

import serial
import time
import datetime
import sys


def get_timestamp_ms() -> float:
    return time.time() * 1000


def main():
    print(f'\n{"="*60}')
    print(f'交互式串口测试工具')
    print(f'{"="*60}\n')
    
    # 输入串口
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = input("输入串口路径: ").strip()
    
    baud = 921600
    
    try:
        ser = serial.Serial(port, baud, timeout=0.05, bytesize=8, parity='N', stopbits=1)
    except Exception as e:
        print(f"无法打开串口: {e}")
        sys.exit(1)
    
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    print(f"\n已连接 {port} @ {baud}")
    print(f"按 Ctrl+C 退出\n")
    print(f"命令:")
    print(f"  <hex数据>   发送十六进制数据 (如: 54F1FFFFFFFF050003001111016C)")
    print(f"  test        自动测试 10 次 (发送 USER_FRAME1)")
    print(f"  monitor     监控模式 (持续显示收到的数据)")
    print(f"  clear       清空接收缓冲区")
    print(f"")
    
    # DT_MODE0 MASTER 发送给 SLAVE 0 的测试帧
    test_frame = bytes.fromhex("54F1FFFFFFFF050003001111016C")
    
    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            
            # 自动测试
            if line == 'test':
                print(f"\n自动测试 10 次...")
                print(f"帧内容: {test_frame.hex().upper()}\n")
                
                for i in range(10):
                    ser.reset_input_buffer()
                    
                    ts_send = get_timestamp_ms()
                    ser.write(test_frame)
                    ser.flush()
                    
                    time.sleep(0.02)
                    
                    resp = ser.read(4096)
                    ts_recv = get_timestamp_ms()
                    
                    now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    delay = ts_recv - ts_send
                    
                    if resp:
                        print(f"[{now}] #{i:02d} 发送 {len(test_frame)}B → 收到 {len(resp)}B | 延迟: {delay:6.2f}ms | {resp.hex().upper()[:40]}...")
                    else:
                        print(f"[{now}] #{i:02d} 发送 {len(test_frame)}B → 无响应 | 超时")
                    
                    time.sleep(0.2)
                print()
                continue
            
            # 监控模式
            if line == 'monitor':
                print(f"\n监控模式 (按 Ctrl+C 退出)\n")
                count = 0
                while True:
                    data = ser.read(4096)
                    if data:
                        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"[{now}] #{count:04d} 收到 {len(data)}B | {data.hex().upper()[:60]}...")
                        count += 1
                    time.sleep(0.01)
            
            # 清空缓冲区
            if line == 'clear':
                ser.reset_input_buffer()
                print("已清空接收缓冲区\n")
                continue
            
            # 发送十六进制数据
            try:
                hex_str = line.replace(" ", "").replace("-", "")
                data = bytes.fromhex(hex_str)
                
                ts_send = get_timestamp_ms()
                ser.write(data)
                ser.flush()
                
                # 等待响应
                resp = ser.read(4096)
                ts_recv = get_timestamp_ms()
                
                now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                delay = ts_recv - ts_send
                
                print(f"[{now}] 发送 {len(data)}B: {data.hex().upper()}")
                if resp:
                    print(f"[{now}] 收到 {len(resp)}B: {resp.hex().upper()}")
                    print(f"延迟: {delay:.2f}ms")
                else:
                    print(f"[{now}] 无响应 (超时 100ms)")
                print()
                
            except ValueError as e:
                print(f"错误: 无效的十六进制数据 - {e}\n")
    
    except KeyboardInterrupt:
        print("\n\n退出")
    
    ser.close()


if __name__ == '__main__':
    main()
