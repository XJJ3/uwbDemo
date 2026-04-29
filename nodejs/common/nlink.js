/**
 * NLink 协议工具
 * LinkTrack DT_MODE0 模式下的协议封装与解析
 *
 * DT_MODE0 USER_FRAME1 帧格式 (MASTER 发送):
 *   54 F1 FF FF FF FF <remote_role> <remote_id> <data_len LE> <data> <checksum>
 *
 *   remote_role: 0x05 = SLAVE (单播), 0x00 = NODE (广播)
 *   remote_id:   SLAVE 的 ID (单播), 0xFF (广播)
 *   checksum:    sum(所有字节) & 0xFF
 *
 * SLAVE 接收/发送:
 *   - SLAVE 接收来自 MASTER 的数据是透明数据（无协议帧封装）
 *   - SLAVE 发送数据给 MASTER 也是直接发送透明数据
 */

// 帧头常量
const FRAME_HEADER_USER_FRAME1 = Buffer.from([0x54, 0xF1]);  // MASTER 发送帧头
const FRAME_HEADER_RESERVED = Buffer.from([0xFF, 0xFF, 0xFF, 0xFF]);

/**
 * 角色常量 (对应 NLink 协议 Role Table)
 */
const Role = {
  NODE: 0x00,    // 节点 (广播时使用)
  ANCHOR: 0x01,  // 基站
  TAG: 0x02,     // 标签
  CONSOLE: 0x03, // 控制台
  MASTER: 0x04,  // 主机
  SLAVE: 0x05    // 从机
};

/**
 * 角色名称映射
 */
const RoleNames = {
  [Role.NODE]: 'NODE',
  [Role.ANCHOR]: 'ANCHOR',
  [Role.TAG]: 'TAG',
  [Role.CONSOLE]: 'CONSOLE',
  [Role.MASTER]: 'MASTER',
  [Role.SLAVE]: 'SLAVE'
};

/**
 * USER_FRAME1 帧结构
 */
class UserFrame1 {
  /**
   * @param {number} remoteRole - 目标角色
   * @param {number} remoteId - 目标 ID
   * @param {Buffer} payload - 数据载荷
   */
  constructor(remoteRole, remoteId, payload) {
    this.remoteRole = remoteRole;
    this.remoteId = remoteId;
    this.payload = payload;
  }

  /**
   * 是否为广播帧
   */
  isBroadcast() {
    return this.remoteRole === Role.NODE;
  }

  /**
   * 字符串表示
   */
  toString() {
    const roleName = RoleNames[this.remoteRole] || `0x${this.remoteRole.toString(16).toUpperCase().padStart(2, '0')}`;
    if (this.isBroadcast()) {
      return `UserFrame1(广播, ${this.payload.length}B: ${this.payload.toString()})`;
    }
    return `UserFrame1(→${roleName}[${this.remoteId}], ${this.payload.length}B: ${this.payload.toString()})`;
  }
}

/**
 * 计算单字节校验和 (sum mod 256)
 * @param {Buffer} data - 数据
 * @returns {number} 校验和
 */
function checksum(data) {
  let sum = 0;
  for (const byte of data) {
    sum += byte;
  }
  return sum & 0xFF;
}

/**
 * 验证校验和是否正确
 * @param {Buffer} data - 完整帧数据
 * @returns {boolean}
 */
function verifyChecksum(data) {
  if (data.length < 2) return false;
  const expectedChecksum = checksum(data.slice(0, -1));
  return expectedChecksum === data[data.length - 1];
}

/**
 * 构建 DT_MODE0 MASTER 输入帧 (USER_FRAME1)
 *
 * @param {number} remoteRole - 目标角色 (Role.SLAVE 或 Role.NODE)
 * @param {number} remoteId - 目标 ID (SLAVE ID, 广播时为 0xFF)
 * @param {Buffer} payload - 要发送的数据
 * @returns {Buffer} 完整的 NLink 协议帧
 */
function buildUserFrame1(remoteRole, remoteId, payload) {
  const dataLen = payload.length;

  // 构建帧 (不含校验和)
  const header = Buffer.concat([
    FRAME_HEADER_USER_FRAME1,
    FRAME_HEADER_RESERVED,
    Buffer.from([remoteRole, remoteId, dataLen & 0xFF, (dataLen >> 8) & 0xFF]),
    payload
  ]);

  // 添加校验和
  const checksumByte = checksum(header);
  return Buffer.concat([header, Buffer.from([checksumByte])]);
}

/**
 * 向指定 SLAVE 发送数据 (单播)
 *
 * @param {number} slaveId - 目标 SLAVE 的 ID (0-254)
 * @param {Buffer} data - 要发送的数据
 * @returns {Buffer} 完整的协议帧
 */
function sendToSlave(slaveId, data) {
  return buildUserFrame1(Role.SLAVE, slaveId, data);
}

/**
 * 向所有 SLAVE 广播数据
 *
 * @param {Buffer} data - 要广播的数据
 * @returns {Buffer} 完整的协议帧
 */
function broadcast(data) {
  return buildUserFrame1(Role.NODE, 0xFF, data);
}

/**
 * 建立与 SLAVE 的双向连接 (发送 0 字节数据)
 * SLAVE 无数据输出，但建立了联系，SLAVE 可以向 MASTER 发送数据
 *
 * @param {number} slaveId - 目标 SLAVE 的 ID
 * @returns {Buffer} 完整的协议帧
 */
function establishLink(slaveId) {
  return buildUserFrame1(Role.SLAVE, slaveId, Buffer.alloc(0));
}

/**
 * 解析 USER_FRAME1 帧
 *
 * @param {Buffer} data - 原始帧数据
 * @returns {UserFrame1|null} 解析成功返回 UserFrame1 对象，失败返回 null
 */
function parseUserFrame1(data) {
  // 最小帧长: 帧头(2) + 保留(4) + role(1) + id(1) + len(2) + checksum(1) = 11
  if (data.length < 11) return null;

  // 检查帧头
  if (!data.subarray(0, 2).equals(FRAME_HEADER_USER_FRAME1)) return null;

  // 检查保留字节
  if (!data.subarray(2, 6).equals(FRAME_HEADER_RESERVED)) return null;

  // 提取字段
  const remoteRole = data[6];
  const remoteId = data[7];
  const dataLen = data[8] | (data[9] << 8);

  // 检查长度
  const expectedLen = 10 + dataLen + 1;  // 头部10字节 + 数据 + 校验和1字节
  if (data.length < expectedLen) return null;

  // 提取载荷
  const payload = data.subarray(10, 10 + dataLen);

  // 验证校验和
  const frameData = data.subarray(0, expectedLen);
  if (!verifyChecksum(frameData)) return null;

  return new UserFrame1(remoteRole, remoteId, payload);
}

/**
 * 在缓冲区中查找并解析帧
 *
 * @param {Buffer} buffer - 接收缓冲区
 * @returns {[UserFrame1|null, number]} [解析结果, 消耗的字节数]
 *         如果没有完整帧，返回 [null, 0]
 */
function findAndParseFrame(buffer) {
  // 查找帧头
  const headerPos = buffer.indexOf(FRAME_HEADER_USER_FRAME1);
  if (headerPos === -1) {
    // 没有找到帧头，丢弃所有数据（保留最后1字节防止帧头被截断）
    return [null, Math.max(0, buffer.length - 1)];
  }

  // 帧头位置之后的剩余数据
  const remaining = buffer.length - headerPos;
  if (remaining < 11) {
    // 数据不足最小帧长，等待更多数据
    return [null, headerPos];
  }

  // 提取数据长度
  const dataLen = buffer[headerPos + 8] | (buffer[headerPos + 9] << 8);
  const frameLen = 10 + dataLen + 1;

  if (remaining < frameLen) {
    // 数据不完整，等待更多数据
    return [null, headerPos];
  }

  // 提取帧数据
  const frameData = buffer.subarray(headerPos, headerPos + frameLen);
  const result = parseUserFrame1(frameData);

  return [result, headerPos + frameLen];
}

/**
 * 预定义帧 (用于调试/测试)
 */
const KNOWN_FRAMES = {
  // 手册 Table 18 示例帧
  manual_f1_s0: Buffer.from('54F1FFFFFFFF050003001111016C', 'hex'),  // M→S0: "111101"
  manual_f3_s0: Buffer.from('54F1FFFFFFFF0500000046', 'hex'),        // M→S0: 0字节(建立连接)
  manual_f5_bcast: Buffer.from('54F1FFFFFFFF00000300ABCDEFAB', 'hex')  // 广播: "ABCDEF"
};

// 导出
export {
  Role,
  RoleNames,
  UserFrame1,
  FRAME_HEADER_USER_FRAME1,
  FRAME_HEADER_RESERVED,
  checksum,
  verifyChecksum,
  buildUserFrame1,
  sendToSlave,
  broadcast,
  establishLink,
  parseUserFrame1,
  findAndParseFrame,
  KNOWN_FRAMES
};

// 测试代码 (直接运行时执行)
if (import.meta.url === `file://${process.argv[1]}`) {
  console.log('='.repeat(50));
  console.log('NLink 协议工具测试');
  console.log('='.repeat(50));

  // 测试帧构建
  console.log('\n[帧构建测试]');
  let f = sendToSlave(1, Buffer.from('Hello'));
  console.log(`向 SLAVE1 发送 "Hello": ${f.toString('hex').toUpperCase().match(/.{2}/g).join(' ')}`);
  console.log(`  校验和: 0x${f[f.length - 1].toString(16).toUpperCase().padStart(2, '0')}`);

  f = broadcast(Buffer.from('Test'));
  console.log(`广播 "Test":          ${f.toString('hex').toUpperCase().match(/.{2}/g).join(' ')}`);

  f = establishLink(0);
  console.log(`建立连接 SLAVE0:      ${f.toString('hex').toUpperCase().match(/.{2}/g).join(' ')}`);

  // 测试帧解析
  console.log('\n[帧解析测试]');
  for (const [name, frame] of Object.entries(KNOWN_FRAMES)) {
    const result = parseUserFrame1(frame);
    if (result) {
      console.log(`${name}: ${result}`);
    } else {
      console.log(`${name}: 解析失败`);
    }
  }

  // 验证手册示例帧
  console.log('\n[手册示例帧验证]');
  for (const [name, frame] of Object.entries(KNOWN_FRAMES)) {
    const valid = verifyChecksum(frame);
    console.log(`${name}: 校验和 ${valid ? '正确' : '错误'}`);
  }
}
