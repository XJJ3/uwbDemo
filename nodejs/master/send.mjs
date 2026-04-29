import { SerialPort } from 'serialport';
import readline from 'readline';
import { sendToSlave, broadcast, establishLink } from '../common/nlink.js';

const PORT = '/dev/cu.wchusbserial585C0089431';
const BAUD = 921600;
const SLAVE_ID = 0;

class MasterTerminal {
  constructor(port, baud, slaveId = 1) {
    this.port = port;
    this.baud = baud;
    this.slaveId = slaveId;
    this.serialPort = null;
    this.running = false;
    this.linkEstablished = false;
    this.rl = null;
  }

  async start() {
    this.serialPort = new SerialPort({
      path: this.port,
      baudRate: this.baud,
      dataBits: 8,
      parity: 'none',
      stopBits: 1
    });

    await new Promise((resolve, reject) => {
      this.serialPort.on('open', resolve);
      this.serialPort.on('error', reject);
    });

    this.serialPort.on('data', (data) => this.handleReceive(data));
    this.serialPort.on('error', (err) => {
      if (this.running) console.log(`\n[接收错误] ${err.message}`);
    });

    this.running = true;

    console.log('MASTER 终端已启动');
    console.log(`  端口: ${this.port}`);
    console.log(`  波特率: ${this.baud}`);
    console.log(`  默认 SLAVE ID: ${this.slaveId}`);
    console.log();
    this.printHelp();
  }

  stop() {
    this.running = false;
    if (this.rl) {
      this.rl.close();
    }
    if (this.serialPort && this.serialPort.isOpen) {
      this.serialPort.close();
    }
    console.log('终端已停止');
  }

  printHelp() {
    console.log('命令:');
    console.log('  <消息>           向 SLAVE 发送消息');
    console.log('  /b <消息>        广播到所有 SLAVE');
    console.log('  /l               建立双向连接');
    console.log('  /s <id>          切换目标 SLAVE ID');
    console.log('  /h               显示帮助');
    console.log('  /q               退出');
    console.log();
  }

  getTimestamp() {
    const now = new Date();
    return now.toTimeString().split(' ')[0] + '.' + now.getMilliseconds().toString().padStart(3, '0');
  }

  handleReceive(data) {
    const timestamp = this.getTimestamp();
    try {
      const text = data.toString('utf8');
      process.stdout.write(`\r[${timestamp}] ← SLAVE: "${text}"\n> `);
    } catch {
      const hexStr = data.toString('hex').toUpperCase().match(/.{2}/g).join(' ');
      process.stdout.write(`\r[${timestamp}] ← SLAVE (HEX): ${hexStr}\n> `);
    }
  }

  sendToSlave(data, slaveId = null) {
    const sid = slaveId !== null ? slaveId : this.slaveId;
    const frame = sendToSlave(sid, data);
    this.serialPort.write(frame);
    const timestamp = this.getTimestamp();
    console.log(`[${timestamp}] → SLAVE${sid}: ${JSON.stringify(data.toString())} (${data.length}B)`);
    this.linkEstablished = true;
  }

  broadcastData(data) {
    const frame = broadcast(data);
    this.serialPort.write(frame);
    const timestamp = this.getTimestamp();
    console.log(`[${timestamp}] → 广播: ${JSON.stringify(data.toString())} (${data.length}B)`);
  }

  establishLinkToSlave(slaveId = null) {
    const sid = slaveId !== null ? slaveId : this.slaveId;
    const frame = establishLink(sid);
    this.serialPort.write(frame);
    const timestamp = this.getTimestamp();
    console.log(`[${timestamp}] → 建立连接 SLAVE${sid}`);
    this.linkEstablished = true;
  }

  async runInteractive() {
    await this.start();

    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    const prompt = () => {
      this.rl.question('> ', (line) => {
        if (!this.running) return;

        const trimmed = line.trim();
        if (!trimmed) {
          prompt();
          return;
        }

        if (trimmed === '/q') {
          this.stop();
          return;
        }

        if (trimmed === '/h') {
          this.printHelp();
          prompt();
          return;
        }

        if (trimmed === '/l') {
          this.establishLinkToSlave();
          prompt();
          return;
        }

        if (trimmed.startsWith('/s ')) {
          const newId = parseInt(trimmed.slice(3), 10);
          if (isNaN(newId)) {
            console.log('错误: ID 必须是数字');
          } else {
            this.slaveId = newId;
            console.log(`目标 SLAVE ID 已切换为 ${newId}`);
          }
          prompt();
          return;
        }

        if (trimmed.startsWith('/b ')) {
          const msg = trimmed.slice(3);
          this.broadcastData(Buffer.from(msg, 'utf8'));
          prompt();
          return;
        }

        if (trimmed.startsWith('/')) {
          console.log(`未知命令: ${trimmed}`);
          this.printHelp();
          prompt();
          return;
        }

        this.sendToSlave(Buffer.from(trimmed, 'utf8'));
        prompt();
      });
    };

    prompt();
  }

  async sendOnce(data, slaveId = null) {
    await this.start();
    this.sendToSlave(data, slaveId);
    await new Promise(resolve => setTimeout(resolve, 100));
    this.stop();
  }

  async broadcastOnce(data) {
    await this.start();
    this.broadcastData(data);
    await new Promise(resolve => setTimeout(resolve, 100));
    this.stop();
  }
}

function printUsage() {
  console.log('用法:');
  console.log('  node master/send.js              交互模式');
  console.log('  node master/send.js <消息>       发送消息');
  console.log('  node master/send.js -b <消息>    广播');
  console.log('  node master/send.js -l           建立双向连接');
  console.log('  node master/send.js -h           显示帮助');
}

async function main() {
  const terminal = new MasterTerminal(PORT, BAUD, SLAVE_ID);
  const args = process.argv.slice(2);

  try {
    if (args.length === 0) {
      await terminal.runInteractive();
    } else if (args[0] === '-b') {
      const msg = args.slice(1).join(' ') || 'test';
      await terminal.broadcastOnce(Buffer.from(msg, 'utf8'));
    } else if (args[0] === '-l') {
      await terminal.start();
      terminal.establishLinkToSlave();
      console.log('连接已建立，按 Ctrl+C 退出');
      await new Promise(resolve => {
        process.on('SIGINT', resolve);
      });
      terminal.stop();
    } else if (args[0] === '-h') {
      printUsage();
    } else {
      const msg = args.join(' ');
      await terminal.sendOnce(Buffer.from(msg, 'utf8'));
    }
  } catch (err) {
    console.error(`错误: ${err.message}`);
    terminal.stop();
    process.exit(1);
  }
}

main();
