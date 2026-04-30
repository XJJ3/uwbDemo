# -*- coding: utf-8 -*-
"""
串口回环测试程序

用于测试改装设备（收到什么就回复什么）的延迟
可以精确测量：
1. 串口写入延迟
2. 串口读取延迟
3. 往返延迟
"""

import serial
import time
import statistics
import datetime

PORT = '/dev/cu.wchusbserial56D00085001'
BAUD = 921600
TEST_COUNT = 100


def get_timestamp_us() -> int:
    return int(time.time() * 1_000_000)


def ts_to_ms(ts_us: int) -> float:
    return ts_us / 1000.0


def test_serial_loopback():
    print(f'\n{"="*70}')
    print(f'串口回环延迟测试')
    print(f'{"="*70}')
    print(f'\n设备: {PORT}')
    print(f'波特率: {BAUD}')
    print(f'测试次数: {TEST_COUNT}')
    print(f'\n设备特性: 收到什么数据就立即回复相同数据')
    print(f'')
    
    ser = serial.Serial(PORT, BAUD, timeout=0.1, bytesize=8, parity='N', stopbits=1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    results = []
    
    payload_sizes = [8, 32, 64, 128, 256]
    
    for payload_size in payload_sizes:
        print(f'\n--- 测试数据包大小: {payload_size} 字节 ---\n')
        print(f'{"序号":^6} | {"往返(ms)":^10} | {"写入(ms)":^10} | {"读取(ms)":^10}')
        print(f'{"-"*6} | {"-"*10} | {"-"*10} | {"-"*10}')
        
        test_data = bytes([i % 256 for i in range(payload_size)])
        roundtrip_times = []
        
        for i in range(TEST_COUNT):
            ts_before_write = get_timestamp_us()
            ser.write(test_data)
            ts_after_write = get_timestamp_us()
            
            response = ser.read(payload_size)
            ts_after_read = get_timestamp_us()
            
            if len(response) != payload_size:
                print(f'[{i:03d}] 错误: 收到 {len(response)}B, 期望 {payload_size}B')
                continue
            
            if response != test_data:
                print(f'[{i:03d}] 错误: 数据不匹配')
                continue
            
            write_time_us = ts_after_write - ts_before_write
            read_time_us = ts_after_read - ts_after_write
            roundtrip_us = ts_after_read - ts_before_write
            
            roundtrip_times.append(roundtrip_us)
            
            if i < 10 or i >= TEST_COUNT - 3:
                print(f'{i:^6} | {ts_to_ms(roundtrip_us):^10.2f} | {ts_to_ms(write_time_us):^10.2f} | {ts_to_ms(read_time_us):^10.2f}')
            elif i == 10:
                print(f'{"...":^6} | {"...":^10} | {"...":^10} | {"...":^10}')
        
        if roundtrip_times:
            avg = ts_to_ms(statistics.mean(roundtrip_times))
            min_val = ts_to_ms(min(roundtrip_times))
            max_val = ts_to_ms(max(roundtrip_times))
            median = ts_to_ms(statistics.median(roundtrip_times))
            stdev = ts_to_ms(statistics.stdev(roundtrip_times)) if len(roundtrip_times) > 1 else 0
            
            print(f'\n统计: 平均 {avg:.2f}ms | 最小 {min_val:.2f}ms | 最大 {max_val:.2f}ms | 中位数 {median:.2f}ms | 标准差 {stdev:.2f}ms')
            print(f'估算单向延迟: {avg/2:.2f}ms')
            
            results.append({
                'size': payload_size,
                'avg': avg,
                'min': min_val,
                'max': max_val,
                'median': median
            })
    
    ser.close()
    
    print(f'\n{"="*70}')
    print(f'汇总')
    print(f'{"="*70}\n')
    print(f'{"大小(B)":^8} | {"平均(ms)":^10} | {"最小(ms)":^10} | {"最大(ms)":^10} | {"单向(ms)":^10}')
    print(f'{"-"*8} | {"-"*10} | {"-"*10} | {"-"*10} | {"-"*10}')
    for r in results:
        print(f'{r["size"]:^8} | {r["avg"]:^10.2f} | {r["min"]:^10.2f} | {r["max"]:^10.2f} | {r["avg"]/2:^10.2f}')
    
    print(f'\n结论:')
    print(f'  - 这是纯串口收发延迟（不经过 UWB）')
    print(f'  - 主要包含: 系统调用开销 + USB 传输 + 设备处理')
    print(f'  - 可作为 UWB 测试的基准参考')


def test_raw_monitor():
    """实时监控模式"""
    print(f'\n{"="*70}')
    print(f'串口实时监控')
    print(f'{"="*70}')
    print(f'\n设备: {PORT}')
    print(f'波特率: {BAUD}')
    print(f'\n按 Ctrl+C 退出\n')
    
    ser = serial.Serial(PORT, BAUD, timeout=0.01, bytesize=8, parity='N', stopbits=1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    test_count = 0
    
    try:
        while True:
            test_data = b'\xAA\xBB\xCC\xDD' + struct.pack('<I', test_count)
            
            ts_send = get_timestamp_us()
            ser.write(test_data)
            
            response = ser.read(len(test_data))
            ts_recv = get_timestamp_us()
            
            if response:
                delay_us = ts_recv - ts_send
                now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                match = '✓' if response == test_data else '✗'
                print(f'[{now}] #{test_count:04d} | {ts_to_ms(delay_us):6.2f}ms | {match} | 发送: {test_data.hex().upper()} | 收到: {response.hex().upper()}')
                test_count += 1
            else:
                print(f'[{now}] #{test_count:04d} | 超时')
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print(f'\n\n测试结束，共发送 {test_count} 次')
    
    ser.close()


def interactive_mode():
    """交互模式"""
    import struct
    
    print(f'\n{"="*70}')
    print(f'串口交互测试')
    print(f'{"="*70}')
    print(f'\n设备: {PORT}')
    print(f'波特率: {BAUD}')
    print(f'\n命令:')
    print(f'  <hex数据>   发送十六进制数据 (如: AA BB CC)')
    print(f'  /test       自动测试 100 次')
    print(f'  /q          退出')
    print(f'')
    
    ser = serial.Serial(PORT, BAUD, timeout=0.5, bytesize=8, parity='N', stopbits=1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    try:
        while True:
            line = input('> ').strip()
            if not line:
                continue
            
            if line == '/q':
                break
            
            elif line == '/test':
                print('\n自动测试 100 次...\n')
                test_data = bytes([i % 256 for i in range(32)])
                times = []
                
                for i in range(100):
                    ts_send = get_timestamp_us()
                    ser.write(test_data)
                    ser.flush()
                    response = ser.read(len(test_data))
                    ts_recv = get_timestamp_us()
                    
                    if response == test_data:
                        times.append(ts_recv - ts_send)
                
                if times:
                    print(f'成功: {len(times)}/100')
                    print(f'平均: {ts_to_ms(statistics.mean(times)):.2f}ms')
                    print(f'最小: {ts_to_ms(min(times)):.2f}ms')
                    print(f'最大: {ts_to_ms(max(times)):.2f}ms')
                    print(f'单向估算: {ts_to_ms(statistics.mean(times)/2):.2f}ms')
                else:
                    print('全部失败!')
                print()
            
            else:
                try:
                    hex_str = line.replace(' ', '')
                    data = bytes.fromhex(hex_str)
                    
                    ts_send = get_timestamp_us()
                    ser.write(data)
                    ser.flush()
                    response = ser.read(4096)
                    ts_recv = get_timestamp_us()
                    
                    delay_us = ts_recv - ts_send
                    
                    print(f'发送: {data.hex(" ").upper()} ({len(data)}B)')
                    print(f'收到: {response.hex(" ").upper()} ({len(response)}B)')
                    print(f'延迟: {ts_to_ms(delay_us):.2f}ms')
                    print(f'匹配: {"✓" if response == data else "✗"}')
                    print()
                
                except ValueError as e:
                    print(f'错误: 无效的十六进制数据 - {e}')
    
    except KeyboardInterrupt:
        pass
    
    ser.close()
    print('已退出')


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--monitor':
        test_raw_monitor()
    elif len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        interactive_mode()
    else:
        test_serial_loopback()
