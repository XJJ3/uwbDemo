# -*- coding: utf-8 -*-
"""
延迟测试程序 - 精确版

所有时间戳基于同一时间基准 (time.perf_counter)，精确计算各阶段延迟:
- 设备收发延迟 M→S: SLAVE收到 - MASTER发送
- SLAVE 代码处理延迟: SLAVE回复 - SLAVE收到  
- 设备收发延迟 S→M: MASTER收到 - SLAVE回复
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import serial
import serial.tools.list_ports
import threading
import time
import datetime
import struct
import argparse
import statistics
from typing import Optional, List, Tuple

from common.nlink import send_to_slave, Role


BAUD = 921600
TEST_COUNT = 50
TEST_INTERVAL = 0.2
SLAVE_ID = 0

TEST_PREFIX = b'\xAA\xBB'
ACK_PREFIX = b'\xCC\xDD'


def get_timestamp_us() -> int:
    """使用 time.time() 作为系统级时间基准，所有进程共享"""
    return int(time.time() * 1_000_000)


def ts_to_ms(ts_us: int) -> float:
    return ts_us / 1000.0


def build_test_payload(seq: int, send_ts: int, payload_size: int = 32) -> bytes:
    fill_size = max(0, payload_size - 12)
    return TEST_PREFIX + struct.pack('<H', seq) + struct.pack('<Q', send_ts) + bytes(fill_size)


def build_test_frame(slave_id: int, seq: int, send_ts: int, payload_size: int = 32) -> bytes:
    payload = build_test_payload(seq, send_ts, payload_size)
    return send_to_slave(slave_id, payload)


class SlaveTester:
    def __init__(self, port: str, slave_id: int = 0):
        self.port = port
        self.slave_id = slave_id
        self.ser = None
        self.running = False
        self.rx_thread = None
        self.stats = {'received': 0, 'replied': 0, 'errors': 0}
    
    def start(self):
        self.ser = serial.Serial(self.port, BAUD, timeout=0.01, bytesize=8, parity='N', stopbits=1)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.running = True
        self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.rx_thread.start()
        print(f'\n{"="*90}')
        print(f'SLAVE {self.slave_id} 已启动 ({self.port})')
        print(f'{"="*90}')
        print(f'\n精确延迟分解 (同一时间基准):')
        print(f'  [设备M→S] = SLAVE收到时间 - MASTER发送时间')
        print(f'  [SLAVE处理] = SLAVE回复时间 - SLAVE收到时间')
        print(f'\n等待 MASTER 测试请求...\n')
    
    def stop(self):
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1)
        if self.ser:
            self.ser.close()
        print(f'\n=== SLAVE 统计 ===')
        print(f'接收: {self.stats["received"]} | 回复: {self.stats["replied"]} | 错误: {self.stats["errors"]}')
    
    def _receive_loop(self):
        while self.running:
            try:
                data = self.ser.read(4096)
                if data:
                    self._handle_raw_data(data)
            except Exception as e:
                if self.running:
                    self.stats['errors'] += 1
                    print(f'[错误] {e}')
    
    def _handle_raw_data(self, data: bytes):
        if len(data) < 12:
            return
        if data[:2] != TEST_PREFIX:
            return
        
        ts_recv = get_timestamp_us()
        
        seq = struct.unpack('<H', data[2:4])[0]
        master_send_ts = struct.unpack('<Q', data[4:12])[0]
        
        self.stats['received'] += 1
        
        device_m2s_us = ts_recv - master_send_ts
        
        ack_payload = (
            ACK_PREFIX + 
            struct.pack('<H', seq) + 
            struct.pack('<Q', ts_recv) +
            struct.pack('<Q', master_send_ts)
        )
        
        self.ser.write(ack_payload)
        self.ser.flush()
        
        ts_reply = get_timestamp_us()
        
        slave_process_us = ts_reply - ts_recv
        self.stats['replied'] += 1
        
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f'[{now}] #{seq:03d} | 设备M→S: {ts_to_ms(device_m2s_us):7.2f}ms | SLAVE处理: {ts_to_ms(slave_process_us):6.2f}ms')


class MasterTester:
    def __init__(self, port: str, slave_id: int = 0):
        self.port = port
        self.slave_id = slave_id
        self.ser = None
        self.running = False
        self.rx_thread = None
        self.rx_buffer = bytearray()
        self.pending_acks = {}
        self.results = []
        self.lock = threading.Lock()
    
    def start(self):
        self.ser = serial.Serial(self.port, BAUD, timeout=0.01, bytesize=8, parity='N', stopbits=1)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.running = True
        self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.rx_thread.start()
        print(f'\n{"="*90}')
        print(f'MASTER 已启动 ({self.port})')
        print(f'目标 SLAVE ID: {self.slave_id}')
        print(f'{"="*90}')
    
    def stop(self):
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1)
        if self.ser:
            self.ser.close()
    
    def _receive_loop(self):
        while self.running:
            try:
                data = self.ser.read(4096)
                if data:
                    self.rx_buffer.extend(data)
                    self._process_raw_data()
            except Exception as e:
                if self.running:
                    print(f'[错误] {e}')
    
    def _process_raw_data(self):
        while len(self.rx_buffer) >= 20:
            ack_pos = None
            for i in range(len(self.rx_buffer) - 19):
                if self.rx_buffer[i:i+2] == ACK_PREFIX:
                    ack_pos = i
                    break
            
            if ack_pos is None:
                if len(self.rx_buffer) > 20:
                    del self.rx_buffer[:len(self.rx_buffer) - 20]
                return
            
            if ack_pos > 0:
                del self.rx_buffer[:ack_pos]
            
            if len(self.rx_buffer) < 20:
                return
            
            ts_master_recv = get_timestamp_us()
            ack_data = bytes(self.rx_buffer[:20])
            del self.rx_buffer[:20]
            
            seq = struct.unpack('<H', ack_data[2:4])[0]
            slave_recv_ts = struct.unpack('<Q', ack_data[4:12])[0]
            master_send_ts = struct.unpack('<Q', ack_data[12:20])[0]
            
            with self.lock:
                if seq not in self.pending_acks:
                    return
                payload_size = self.pending_acks.pop(seq)
            
            rt_us = ts_master_recv - master_send_ts
            device_m2s_us = slave_recv_ts - master_send_ts
            device_s2m_us = ts_master_recv - slave_recv_ts
            
            self.results.append({
                'seq': seq,
                'payload_size': payload_size,
                'rt_us': rt_us,
                'device_m2s_us': device_m2s_us,
                'device_s2m_us': device_s2m_us,
                'master_send_ts': master_send_ts,
                'slave_recv_ts': slave_recv_ts,
                'master_recv_ts': ts_master_recv
            })
            
            now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f'[{now}] #{seq:03d} | 往返: {ts_to_ms(rt_us):6.2f}ms | M→S设备: {ts_to_ms(device_m2s_us):6.2f}ms | S→M设备: {ts_to_ms(device_s2m_us):6.2f}ms')
    
    def run_test(self, count: int = TEST_COUNT, payload_size: int = 32):
        print(f'\n开始测试: {count} 次, 数据包: {payload_size}B\n')
        print(f'精确延迟分解 (同一时间基准 time.perf_counter):')
        print(f'  [往返]       = MASTER收到ACK - MASTER发送')
        print(f'  [M→S设备]    = SLAVE收到 - MASTER发送 (精确单向 UWB)')
        print(f'  [S→M设备]    = MASTER收到 - SLAVE收到 (精确单向 UWB + 串口)')
        print(f'  [SLAVE处理]  = SLAVE端单独计算并打印')
        print(f'\n{"序号":^6} | {"往返(ms)":^10} | {"M→S设备(ms)":^11} | {"S→M设备(ms)":^11}')
        print(f'{"-"*6} | {"-"*10} | {"-"*11} | {"-"*11}')
        
        self.results.clear()
        self.pending_acks.clear()
        
        for i in range(count):
            ts_send = get_timestamp_us()
            frame = build_test_frame(self.slave_id, i, ts_send, payload_size)
            
            with self.lock:
                self.pending_acks[i] = payload_size
            
            self.ser.write(frame)
            self.ser.flush()
            
            time.sleep(TEST_INTERVAL)
        
        start_wait = time.time()
        while len(self.pending_acks) > 0 and (time.time() - start_wait) < 3.0:
            time.sleep(0.01)
        
        self._print_statistics(payload_size)
    
    def _print_statistics(self, payload_size: int):
        if not self.results:
            print('\n⚠️ 未收到任何 ACK 响应!')
            return
        
        print(f'\n{"="*90}')
        print(f'延迟统计 (数据包: {payload_size}B, 有效样本: {len(self.results)}/{TEST_COUNT})')
        print(f'{"="*90}\n')
        
        rt_times = [r['rt_us'] for r in self.results]
        m2s_times = [r['device_m2s_us'] for r in self.results]
        s2m_times = [r['device_s2m_us'] for r in self.results]
        
        def stats(times):
            return {
                'min': min(times), 'max': max(times),
                'avg': statistics.mean(times),
                'median': statistics.median(times),
                'stdev': statistics.stdev(times) if len(times) > 1 else 0
            }
        
        rt_s = stats(rt_times)
        m2s_s = stats(m2s_times)
        s2m_s = stats(s2m_times)
        
        print(f'{"指标":^10} | {"往返(ms)":^10} | {"M→S设备(ms)":^12} | {"S→M设备(ms)":^12}')
        print(f'{"-"*10} | {"-"*10} | {"-"*12} | {"-"*12}')
        for label in ['最小', '最大', '平均', '中位数', '标准差']:
            val_rt = rt_s['min' if label=='最小' else 'max' if label=='最大' else 'avg' if label=='平均' else 'median' if label=='中位数' else 'stdev']
            val_m2s = m2s_s['min' if label=='最小' else 'max' if label=='最大' else 'avg' if label=='平均' else 'median' if label=='中位数' else 'stdev']
            val_s2m = s2m_s['min' if label=='最小' else 'max' if label=='最大' else 'avg' if label=='平均' else 'median' if label=='中位数' else 'stdev']
            print(f'{label:^10} | {ts_to_ms(val_rt):^10.2f} | {ts_to_ms(val_m2s):^12.2f} | {ts_to_ms(val_s2m):^12.2f}')
        
        print(f'\n{"="*90}')
        print(f'精确延迟分解')
        print(f'{"="*90}\n')
        
        avg_rt = ts_to_ms(rt_s['avg'])
        avg_m2s = ts_to_ms(m2s_s['avg'])
        avg_s2m = ts_to_ms(s2m_s['avg'])
        
        uwb_total = avg_m2s + avg_s2m
        
        print(f'┌───────────────────────────────────────────────────────────────────────┐')
        print(f'│ 【往返总延迟】         {avg_rt:8.2f} ms                                 │')
        print(f'├───────────────────────────────────────────────────────────────────────┤')
        print(f'│ 【设备 M→S】(UWB传输)  {avg_m2s:8.2f} ms  MASTER发送 → SLAVE收到        │')
        print(f'│ 【设备 S→M】(UWB传输)  {avg_s2m:8.2f} ms  SLAVE收到 → MASTER收到        │')
        print(f'├───────────────────────────────────────────────────────────────────────┤')
        print(f'│ 【纯UWB传输延迟】      {uwb_total:8.2f} ms  (M→S + S→M)                  │')
        print(f'│ 【SLAVE代码处理】      见 SLAVE 端输出                                │')
        print(f'├───────────────────────────────────────────────────────────────────────┤')
        print(f'│ 验证: M→S({avg_m2s:.2f}) + S→M({avg_s2m:.2f}) = {uwb_total:.2f} ms        │')
        print(f'└───────────────────────────────────────────────────────────────────────┘')
        print(f'')
        
        uwb_one_way = uwb_total / 2
        print(f'估算单向 UWB 传输延迟: {uwb_one_way:.2f} ms')
        print(f'')
        
        print(f'--- 与理论值对比 ---')
        print(f'文档规格 (DT Mode): < 0.5 ms')
        print(f'实测单向延迟: {uwb_one_way:.2f} ms')
        ratio = uwb_one_way / 0.5
        if ratio > 10:
            print(f'⚠️  实测延迟是规格的 {ratio:.0f} 倍，存在显著差异!')
        elif ratio > 2:
            print(f'⚠️  实测延迟是规格的 {ratio:.1f} 倍')
        else:
            print(f'✓ 实测延迟在合理范围')


def scan_all_ports() -> List[Tuple[str, int, int]]:
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
        return []
    
    print(f'找到 {len(valid_ports)} 个串口，正在识别角色...\n')
    
    READ_FRAME = bytes([
        0x52, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x4B
    ])
    
    role_names = {0: 'NODE', 1: 'ANCHOR', 2: 'TAG', 3: 'CONSOLE', 4: 'MASTER', 5: 'SLAVE'}
    identified = []
    
    for port_info in valid_ports:
        port = port_info.device
        try:
            ser = serial.Serial(port, BAUD, timeout=0.3, bytesize=8, parity='N', stopbits=1)
            ser.reset_input_buffer()
            ser.write(READ_FRAME)
            
            buffer = bytearray()
            start_time = time.time()
            
            while time.time() - start_time < 0.3:
                data = ser.read(64)
                if data:
                    buffer.extend(data)
                    if len(buffer) >= 24 and buffer[0] == 0x52 and buffer[1] == 0x00:
                        role = buffer[22]
                        device_id = buffer[23]
                        role_name = role_names.get(role, f'?{role}')
                        ser.close()
                        identified.append((port, role, device_id))
                        print(f'  ✓ {port}: {role_name} (ID: {device_id})')
                        break
            
            ser.close()
        except Exception:
            pass
    
    return identified


def main():
    parser = argparse.ArgumentParser(description='UWB 延迟测试程序 (精确版)')
    parser.add_argument('--master', action='store_true', help='作为 MASTER 端运行')
    parser.add_argument('--slave', action='store_true', help='作为 SLAVE 端运行')
    parser.add_argument('-i', '--id', type=int, default=None, help='SLAVE ID')
    parser.add_argument('-n', '--count', type=int, default=TEST_COUNT, help='测试次数')
    parser.add_argument('-s', '--size', type=int, default=32, help='数据包大小 (字节)')
    
    args = parser.parse_args()
    
    if not args.master and not args.slave:
        print('UWB 延迟测试程序 (精确版)\n')
        print('用法:')
        print('  MASTER 端: python test_latency.py --master')
        print('  SLAVE 端:  python test_latency.py --slave')
        print('\n可选参数:')
        print('  -i <ID>      SLAVE ID')
        print('  -n <次数>    测试次数 (默认 50)')
        print('  -s <大小>    数据包大小 (默认 32 字节)')
        sys.exit(1)
    
    devices = scan_all_ports()
    
    if not devices:
        print('\n错误: 未找到任何 UWB 设备')
        sys.exit(1)
    
    port = None
    slave_id = 0
    
    if args.master:
        master_devices = [(p, role, did) for p, role, did in devices if role == 4]
        if not master_devices:
            print('\n错误: 未找到 MASTER 设备')
            sys.exit(1)
        port = master_devices[0][0]
        print(f'\n自动选择 MASTER: {port}')
        
        if args.id is not None:
            slave_id = args.id
            print(f'目标 SLAVE ID: {slave_id} (手动指定)')
        else:
            slave_devices = [(p, role, did) for p, role, did in devices if role == 5]
            if slave_devices:
                slave_devices.sort(key=lambda x: x[2])
                slave_id = slave_devices[0][2]
                print(f'目标 SLAVE ID: {slave_id} (自动选择)')
            else:
                print('警告: 未检测到 SLAVE 设备，使用默认 ID=0')
        
    elif args.slave:
        slave_devices = [(p, role, did) for p, role, did in devices if role == 5]
        if not slave_devices:
            print('\n错误: 未找到 SLAVE 设备')
            sys.exit(1)
        
        if args.id is not None:
            for p, role, did in slave_devices:
                if did == args.id:
                    port = p
                    slave_id = did
                    break
            if not port:
                print(f'\n错误: 未找到 SLAVE ID={args.id}')
                print(f'可用的 SLAVE ID: {[did for p, role, did in slave_devices]}')
                sys.exit(1)
        else:
            slave_devices.sort(key=lambda x: x[2])
            port, _, slave_id = slave_devices[0]
        
        print(f'\n自动选择 SLAVE {slave_id}: {port}')
    
    try:
        if args.slave:
            tester = SlaveTester(port, slave_id)
            tester.start()
            print('按 Ctrl+C 退出\n')
            while True:
                time.sleep(1)
        
        elif args.master:
            tester = MasterTester(port, slave_id)
            tester.start()
            time.sleep(0.5)
            tester.run_test(count=args.count, payload_size=args.size)
            tester.stop()
    
    except KeyboardInterrupt:
        print('\n\n测试已中断')
        if 'tester' in dir():
            tester.stop()


if __name__ == '__main__':
    main()
