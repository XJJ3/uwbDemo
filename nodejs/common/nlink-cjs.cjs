const FRAME_HEADER_USER_FRAME1 = Buffer.from([0x54, 0xF1]);
const FRAME_HEADER_RESERVED = Buffer.from([0xFF, 0xFF, 0xFF, 0xFF]);

const Role = {
  NODE: 0x00,
  ANCHOR: 0x01,
  TAG: 0x02,
  CONSOLE: 0x03,
  MASTER: 0x04,
  SLAVE: 0x05
};

const PING_PAYLOAD = Buffer.from([0x50, 0x49]);
const PONG_PREFIX = Buffer.from([0x52, 0x53]);

class UserFrame1 {
  constructor(remoteRole, remoteId, payload) {
    this.remoteRole = remoteRole;
    this.remoteId = remoteId;
    this.payload = payload;
  }

  isBroadcast() {
    return this.remoteRole === Role.NODE;
  }

  toString() {
    const roleName = this._getRoleName(this.remoteRole);
    if (this.isBroadcast()) {
      return `UserFrame1(广播, ${this.payload.length}B: ${this.payload.toString()})`;
    }
    return `UserFrame1(→${roleName}[${this.remoteId}], ${this.payload.length}B: ${this.payload.toString()})`;
  }

  _getRoleName(role) {
    const names = {
      [Role.NODE]: 'NODE',
      [Role.ANCHOR]: 'ANCHOR',
      [Role.TAG]: 'TAG',
      [Role.CONSOLE]: 'CONSOLE',
      [Role.MASTER]: 'MASTER',
      [Role.SLAVE]: 'SLAVE'
    };
    return names[role] || `0x${role.toString(16).toUpperCase().padStart(2, '0')}`;
  }
}

function checksum(data) {
  let sum = 0;
  for (const byte of data) {
    sum += byte;
  }
  return sum & 0xFF;
}

function verifyChecksum(data) {
  if (data.length < 2) return false;
  const expectedChecksum = checksum(data.slice(0, -1));
  return expectedChecksum === data[data.length - 1];
}

function buildUserFrame1(remoteRole, remoteId, payload) {
  const dataLen = payload.length;

  const header = Buffer.concat([
    FRAME_HEADER_USER_FRAME1,
    FRAME_HEADER_RESERVED,
    Buffer.from([remoteRole, remoteId, dataLen & 0xFF, (dataLen >> 8) & 0xFF]),
    payload
  ]);

  const checksumByte = checksum(header);
  return Buffer.concat([header, Buffer.from([checksumByte])]);
}

function sendToSlave(slaveId, data) {
  return buildUserFrame1(Role.SLAVE, slaveId, data);
}

function broadcast(data) {
  return buildUserFrame1(Role.NODE, 0xFF, data);
}

function establishLink(slaveId) {
  return buildUserFrame1(Role.SLAVE, slaveId, Buffer.alloc(0));
}

function buildPingFrame(slaveId) {
  return buildUserFrame1(Role.SLAVE, slaveId, PING_PAYLOAD);
}

function parsePongResponse(data) {
  if (data.length >= 3 && data[0] === 0x52 && data[1] === 0x53) {
    return data[2];
  }
  return null;
}

function parseUserFrame1(data) {
  if (data.length < 11) return null;

  if (!data.subarray(0, 2).equals(FRAME_HEADER_USER_FRAME1)) return null;
  if (!data.subarray(2, 6).equals(FRAME_HEADER_RESERVED)) return null;

  const remoteRole = data[6];
  const remoteId = data[7];
  const dataLen = data[8] | (data[9] << 8);

  const expectedLen = 10 + dataLen + 1;
  if (data.length < expectedLen) return null;

  const payload = data.subarray(10, 10 + dataLen);

  const frameData = data.subarray(0, expectedLen);
  if (!verifyChecksum(frameData)) return null;

  return new UserFrame1(remoteRole, remoteId, payload);
}

function findAndParseFrame(buffer) {
  const headerPos = buffer.indexOf(FRAME_HEADER_USER_FRAME1);
  if (headerPos === -1) {
    return [null, Math.max(0, buffer.length - 1)];
  }

  const remaining = buffer.length - headerPos;
  if (remaining < 11) {
    return [null, headerPos];
  }

  const dataLen = buffer[headerPos + 8] | (buffer[headerPos + 9] << 8);
  const frameLen = 10 + dataLen + 1;

  if (remaining < frameLen) {
    return [null, headerPos];
  }

  const frameData = buffer.subarray(headerPos, headerPos + frameLen);
  const result = parseUserFrame1(frameData);

  return [result, headerPos + frameLen];
}

const KNOWN_FRAMES = {
  manual_f1_s0: Buffer.from('54F1FFFFFFFF050003001111016C', 'hex'),
  manual_f3_s0: Buffer.from('54F1FFFFFFFF0500000046', 'hex'),
  manual_f5_bcast: Buffer.from('54F1FFFFFFFF00000300ABCDEFAB', 'hex')
};

module.exports = {
  Role,
  UserFrame1,
  FRAME_HEADER_USER_FRAME1,
  FRAME_HEADER_RESERVED,
  PING_PAYLOAD,
  PONG_PREFIX,
  checksum,
  verifyChecksum,
  buildUserFrame1,
  sendToSlave,
  broadcast,
  establishLink,
  buildPingFrame,
  parsePongResponse,
  parseUserFrame1,
  findAndParseFrame,
  KNOWN_FRAMES
};
