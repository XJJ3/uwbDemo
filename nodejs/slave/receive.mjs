import { SerialPort } from 'serialport';
import readline from 'readline';

const PORT = '/dev/cu.wchusbserial5AB50010561';
const BAUD = 921600;

class SlaveTerminal {
  constructor(port, baud) {
    this.port = port;
    this.baud = baud;
    this.serialPort = null;
    this.running = false;
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

    console.log(`SLAVE 终端已启动 (${this.port}, ${this.baud}bps)`);
    console.log('等待 MASTER 数据...\n');
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
    console.log('  <消息>        向 MASTER 发送消息');
    console.log('  /h            显示帮助');
    console.log('  /q            退出\n');
  }

  getTimestamp() {
    const now = new Date();
    return now.toTimeString().split(' ')[0] + '.' + now.getMilliseconds().toString().padStart(3, '0');
  }

  handleReceive(data) {
    const timestamp = this.getTimestamp();
    try {
      const text = data.toString('utf8');
      process.stdout.write(`\r[${timestamp}] ← MASTER: "${text}"\n> `);
    } catch {
      const hexStr = data.toString('hex').toUpperCase().match(/.{2}/g).join(' ');
      process.stdout.write(`\r[${timestamp}] ← MASTER (HEX): ${hexStr}\n> `);
    }
  }

  send(data) {
    this.serialPort.write(data);
    const timestamp = this.getTimestamp();
    console.log(`[${timestamp}] → MASTER: ${JSON.stringify(data.toString())} (${data.length}B)`);
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

        if (trimmed.startsWith('/')) {
          console.log(`未知命令: ${trimmed}`);
          this.printHelp();
          prompt();
          return;
        }

        this.send(Buffer.from(trimmed, 'utf8'));
        prompt();
      });
    };

    prompt();
  }

  async runReceiveOnly() {
    await this.start();
    console.log('纯接收模式，按 Ctrl+C 退出\n');

    await new Promise(resolve => {
      process.on('SIGINT', resolve);
    });

    this.stop();
  }
}

function printUsage() {
  console.log('用法:');
  console.log('  node slave/receive.js        交互模式');
  console.log('  node slave/receive.js -r     纯接收模式');
  console.log('  node slave/receive.js -h     显示帮助');
}

async function main() {
  const terminal = new SlaveTerminal(PORT, BAUD);
  const args = process.argv.slice(2);

  try {
    if (args.length === 0) {
      await terminal.runInteractive();
    } else if (args[0] === '-r') {
      await terminal.runReceiveOnly();
    } else if (args[0] === '-h') {
      printUsage();
    } else {
      const msg = args.join(' ');
      await terminal.start();
      terminal.send(Buffer.from(msg, 'utf8'));
      await new Promise(resolve => setTimeout(resolve, 100));
      terminal.stop();
    }
  } catch (err) {
    console.error(`错误: ${err.message}`);
    terminal.stop();
    process.exit(1);
  }
}

main();
