const { SerialPort } = require('serialport');

const READ_FRAME = Buffer.from([
  0x52, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
  0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
]);

const checksum = READ_FRAME.slice(0, -1).reduce((sum, b) => sum + b, 0) & 0xFF;
READ_FRAME[READ_FRAME.length - 1] = checksum;

const RoleNames = {
  0: 'NODE',
  1: 'ANCHOR',
  2: 'TAG',
  3: 'CONSOLE',
  4: 'MASTER',
  5: 'SLAVE'
};

async function identifyPort(portPath) {
  return new Promise((resolve) => {
    const port = new SerialPort({
      path: portPath,
      baudRate: 921600,
      dataBits: 8,
      parity: 'none',
      stopBits: 1
    });

    let buffer = Buffer.alloc(0);
    let resolved = false;

    const cleanup = () => {
      if (!resolved) {
        resolved = true;
        if (port.isOpen) port.close();
        resolve(null);
      }
    };

    port.on('error', cleanup);

    port.on('open', () => {
      port.write(READ_FRAME);

      setTimeout(cleanup, 500);
    });

    port.on('data', (data) => {
      buffer = Buffer.concat([buffer, data]);

      if (buffer.length >= 32 && buffer[0] === 0x52 && buffer[1] === 0x00) {
        const role = buffer[22];
        const id = buffer[23];
        const roleName = RoleNames[role] || `UNKNOWN(${role})`;

        resolved = true;
        port.close();
        resolve({ role, id, roleName });
      }
    });
  });
}

async function main() {
  console.log('='.repeat(60));
  console.log('LinkTrack 设备自动识别测试');
  console.log('='.repeat(60));
  console.log();
  console.log('读取帧:', READ_FRAME.toString('hex').toUpperCase().match(/.{2}/g).join(' '));
  console.log();

  const ports = await SerialPort.list();
  const wchPorts = ports.filter(p => p.path.toLowerCase().includes('wchusbserial'));

  console.log(`发现 ${wchPorts.length} 个 WCH 串口设备:\n`);

  for (const p of wchPorts) {
    console.log(`检测 ${p.path}...`);
    const result = await identifyPort(p.path);

    if (result) {
      console.log(`  ✓ 角色: ${result.roleName}, ID: ${result.id}`);
    } else {
      console.log(`  ✗ 无响应或非 LinkTrack 设备`);
    }
    console.log();
  }
}

main().catch(console.error);
