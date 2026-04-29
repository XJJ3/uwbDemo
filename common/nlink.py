# -*- coding: utf-8 -*-
"""
NLink 协议工具
LinkTrack DT_MODE0 模式下的协议封装与解析

DT_MODE0 USER_FRAME1 帧格式 (MASTER 发送):
  54 F1 FF FF FF FF <remote_role> <remote_id> <data_len LE> <data> <checksum>
  
  remote_role: 0x05 = SLAVE (单播), 0x00 = NODE (广播)
  remote_id:   SLAVE 的 ID (单播), 0xFF (广播)
  checksum:    sum(所有字节) & 0xFF

SLAVE 接收/发送:
  - SLAVE 接收来自 MASTER 的数据是透明数据（无协议帧封装）
  - SLAVE 发送数据给 MASTER 也是直接发送透明数据
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from enum import IntEnum


# ============== 常量定义 ==============

# 帧头
FRAME_HEADER_USER_FRAME1 = b'\x54\xF1'  # MASTER 发送帧头
FRAME_HEADER_RESERVED = b'\xFF\xFF\xFF\xFF'

# 角色常量 (对应 NLink 协议 Role Table)
class Role(IntEnum):
    NODE    = 0x00  # 节点 (广播时使用)
    ANCHOR  = 0x01  # 基站
    TAG     = 0x02  # 标签
    CONSOLE = 0x03  # 控制台
    MASTER  = 0x04  # 主机
    SLAVE   = 0x05  # 从机


# ============== 数据类 ==============

@dataclass
class UserFrame1:
    """DT_MODE0 USER_FRAME1 帧结构"""
    remote_role: int      # 目标角色
    remote_id: int        # 目标 ID
    payload: bytes        # 数据载荷
    
    def is_broadcast(self) -> bool:
        """是否为广播帧"""
        return self.remote_role == Role.NODE
    
    def __str__(self) -> str:
        role_name = Role(self.remote_role).name if self.remote_role in Role._value2member_map_ else f"0x{self.remote_role:02X}"
        if self.is_broadcast():
            return f"UserFrame1(广播, {len(self.payload)}B: {self.payload!r})"
        return f"UserFrame1(→{role_name}[{self.remote_id}], {len(self.payload)}B: {self.payload!r})"


# ============== 帧构建函数 ==============

def checksum(data: bytes) -> int:
    """计算单字节校验和 (sum mod 256)"""
    return sum(data) & 0xFF


def verify_checksum(data: bytes) -> bool:
    """验证校验和是否正确"""
    if len(data) < 2:
        return False
    return (sum(data[:-1]) & 0xFF) == data[-1]


def build_user_frame1(remote_role: int, remote_id: int, payload: bytes) -> bytes:
    """
    构建 DT_MODE0 MASTER 输入帧 (USER_FRAME1)
    
    参数:
        remote_role: 目标角色 (Role.SLAVE 或 Role.NODE)
        remote_id:   目标 ID (SLAVE ID, 广播时为 0xFF)
        payload:     要发送的数据
    
    返回:
        完整的 NLink 协议帧字节
    """
    data_len = len(payload)
    frame = (FRAME_HEADER_USER_FRAME1 +
             FRAME_HEADER_RESERVED +
             bytes([remote_role, remote_id,
                    data_len & 0xFF, (data_len >> 8) & 0xFF]) +
             payload)
    frame += bytes([checksum(frame)])
    return frame


def send_to_slave(slave_id: int, data: bytes) -> bytes:
    """
    向指定 SLAVE 发送数据 (单播)
    
    参数:
        slave_id: 目标 SLAVE 的 ID (0-254)
        data:     要发送的数据
    
    返回:
        完整的协议帧
    """
    return build_user_frame1(Role.SLAVE, slave_id, data)


def broadcast(data: bytes) -> bytes:
    """
    向所有 SLAVE 广播数据
    
    参数:
        data: 要广播的数据
    
    返回:
        完整的协议帧
    """
    return build_user_frame1(Role.NODE, 0xFF, data)


def establish_link(slave_id: int) -> bytes:
    """
    建立与 SLAVE 的双向连接 (发送 0 字节数据)
    
    SLAVE 无数据输出，但建立了联系，SLAVE 可以向 MASTER 发送数据
    
    参数:
        slave_id: 目标 SLAVE 的 ID
    
    返回:
        完整的协议帧
    """
    return build_user_frame1(Role.SLAVE, slave_id, b'')


# ============== 帧解析函数 ==============

def parse_user_frame1(data: bytes) -> Optional[UserFrame1]:
    """
    解析 USER_FRAME1 帧
    
    参数:
        data: 原始帧数据
    
    返回:
        解析成功返回 UserFrame1 对象，失败返回 None
    """
    # 最小帧长: 帧头(2) + 保留(4) + role(1) + id(1) + len(2) + checksum(1) = 11
    if len(data) < 11:
        return None
    
    # 检查帧头
    if data[:2] != FRAME_HEADER_USER_FRAME1:
        return None
    
    # 检查保留字节
    if data[2:6] != FRAME_HEADER_RESERVED:
        return None
    
    # 提取字段
    remote_role = data[6]
    remote_id = data[7]
    data_len = data[8] | (data[9] << 8)
    
    # 检查长度
    expected_len = 10 + data_len + 1  # 头部10字节 + 数据 + 校验和1字节
    if len(data) < expected_len:
        return None
    
    # 提取载荷
    payload = data[10:10 + data_len]
    
    # 验证校验和
    frame_data = data[:expected_len]
    if not verify_checksum(frame_data):
        return None
    
    return UserFrame1(remote_role=remote_role, remote_id=remote_id, payload=payload)


def find_and_parse_frame(buffer: bytearray) -> Tuple[Optional[UserFrame1], int]:
    """
    在缓冲区中查找并解析帧
    
    参数:
        buffer: 接收缓冲区
    
    返回:
        (解析结果, 消耗的字节数)
        如果没有完整帧，返回 (None, 0)
    """
    # 查找帧头
    header_pos = buffer.find(FRAME_HEADER_USER_FRAME1)
    if header_pos == -1:
        # 没有找到帧头，丢弃所有数据（保留最后1字节防止帧头被截断）
        return None, max(0, len(buffer) - 1)
    
    # 帧头位置之后的剩余数据
    remaining = len(buffer) - header_pos
    if remaining < 11:
        # 数据不足最小帧长，等待更多数据
        return None, header_pos
    
    # 提取数据长度
    data_len = buffer[header_pos + 8] | (buffer[header_pos + 9] << 8)
    frame_len = 10 + data_len + 1
    
    if remaining < frame_len:
        # 数据不完整，等待更多数据
        return None, header_pos
    
    # 提取帧数据
    frame_data = bytes(buffer[header_pos:header_pos + frame_len])
    result = parse_user_frame1(frame_data)
    
    return result, header_pos + frame_len


# ============== 预定义帧 (用于调试/测试) ==============

KNOWN_FRAMES = {
    # 手册 Table 18 示例帧
    'manual_f1_s0': bytes.fromhex('54F1FFFFFFFF050003001111016C'),  # M→S0: "111101"
    'manual_f3_s0': bytes.fromhex('54F1FFFFFFFF0500000046'),        # M→S0: 0字节(建立连接)
    'manual_f5_bcast': bytes.fromhex('54F1FFFFFFFF00000300ABCDEFAB'),  # 广播: "ABCDEF"
}


# ============== 测试代码 ==============

if __name__ == '__main__':
    print("=" * 50)
    print("NLink 协议工具测试")
    print("=" * 50)
    
    # 测试帧构建
    print("\n[帧构建测试]")
    f = send_to_slave(1, b'Hello')
    print(f'向 SLAVE1 发送 "Hello": {f.hex(" ").upper()}')
    print(f'  校验和: 0x{f[-1]:02X}')
    
    f = broadcast(b'Test')
    print(f'广播 "Test":          {f.hex(" ").upper()}')
    
    f = establish_link(0)
    print(f'建立连接 SLAVE0:      {f.hex(" ").upper()}')
    
    # 测试帧解析
    print("\n[帧解析测试]")
    for name, frame in KNOWN_FRAMES.items():
        result = parse_user_frame1(frame)
        if result:
            print(f'{name}: {result}')
        else:
            print(f'{name}: 解析失败')
    
    # 验证手册示例帧
    print("\n[手册示例帧验证]")
    for name, frame in KNOWN_FRAMES.items():
        valid = verify_checksum(frame)
        print(f'{name}: 校验和 {"正确" if valid else "错误"}')
