const { app, BrowserWindow, ipcMain } = require('electron');
const { SerialPort } = require('serialport');
const path = require('path');
const { 
  sendToSlave, broadcast, establishLink, 
  buildPingFrame, parsePongResponse, PONG_PREFIX,
  buildAckFrame, parseAckResponse, ACK_PREFIX
} = require('./common/nlink-cjs.cjs');

// ==================== 配置项 ====================
const CONFIG = {
  POLLING_INTERVAL: 5000,      // 轮询间隔（毫秒）
  OFFLINE_THRESHOLD: 3,        // 连续超时次数判定离线
  PING_TIMEOUT: 150,           // PING 超时时间（毫秒）
  ACK_TIMEOUT: 500,            // ACK 超时时间（毫秒）
};
// ================================================

let mainWindow = null;
const connections = new Map();
let scanningMode = false;
let foundSlavesBuffer = [];
let currentScanSendTime = 0;
const pendingAckCallbacks = new Map();
const pendingPongCallbacks = new Map();
const slaveOnlineStatus = new Map();
let pollingTimer = null;

const READ_FRAME = Buffer.from([
  0x52, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF,
  0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x4B
]);

const RoleNames = {
  0: 'NODE',
  1: 'ANCHOR',
  2: 'TAG',
  3: 'CONSOLE',
  4: 'MASTER',
  5: 'SLAVE'
};

function identifyPort(portPath) {
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

    const cleanup = (result) => {
      if (!resolved) {
        resolved = true;
        if (port.isOpen) port.close();
        resolve(result);
      }
    };

    port.on('error', () => cleanup(null));

    port.on('open', () => {
      port.write(READ_FRAME);
      setTimeout(() => cleanup(null), 300);
    });

    port.on('data', (data) => {
      buffer = Buffer.concat([buffer, data]);

      if (buffer.length >= 24 && buffer[0] === 0x52 && buffer[1] === 0x00) {
        const role = buffer[22];
        const id = buffer[23];
        const roleName = RoleNames[role] || 'UNKNOWN';
        cleanup({ role, id, roleName });
      }
    });
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    title: 'UWB 通信演示'
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
    stopPolling();
    connections.forEach((conn) => {
      if (conn.port && conn.port.isOpen) {
        conn.port.close();
      }
    });
    connections.clear();
    slaveOnlineStatus.clear();
  });
}

function updateSlaveOnlineStatus(slaveId, isOnline) {
  const current = slaveOnlineStatus.get(slaveId) || { status: 'offline', timeoutCount: 0, lastSeen: 0 };
  
  if (isOnline) {
    current.status = 'online';
    current.timeoutCount = 0;
    current.lastSeen = Date.now();
  } else {
    current.timeoutCount++;
    if (current.timeoutCount >= CONFIG.OFFLINE_THRESHOLD) {
      current.status = 'offline';
    } else if (current.timeoutCount > 0) {
      current.status = 'maybe-offline';
    }
  }
  
  slaveOnlineStatus.set(slaveId, current);
  
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('slave-status-update', {
      slaveId,
      status: current.status,
      timeoutCount: current.timeoutCount,
      lastSeen: current.lastSeen
    });
  }
}

function startPolling() {
  if (pollingTimer) return;
  
  const doPoll = async () => {
    if (!connections.has('master') || scanningMode) {
      return;
    }
    
    const conn = connections.get('master');
    const slaveIds = Array.from(slaveOnlineStatus.keys());
    
    for (const slaveId of slaveIds) {
      const pingFrame = buildPingFrame(slaveId);
      const sendTime = Date.now();
      
      await new Promise((resolve) => {
        const timer = setTimeout(() => {
          pendingPongCallbacks.delete(slaveId);
          updateSlaveOnlineStatus(slaveId, false);
          console.log(`[轮询] SLAVE ${slaveId} 超时`);
          resolve();
        }, CONFIG.PING_TIMEOUT);
        
        pendingPongCallbacks.set(slaveId, (id, receiveTime) => {
          clearTimeout(timer);
          updateSlaveOnlineStatus(slaveId, true);
          console.log(`[轮询] SLAVE ${slaveId} 在线, 延迟: ${receiveTime - sendTime}ms`);
          resolve();
        });
        
        conn.port.write(pingFrame);
      });
      
      await new Promise(r => setTimeout(r, 50));
    }
  };
  
  pollingTimer = setInterval(doPoll, CONFIG.POLLING_INTERVAL);
  console.log('[轮询] 开始在线监测');
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
    console.log('[轮询] 停止在线监测');
  }
}

function registerSlave(slaveId) {
  if (!slaveOnlineStatus.has(slaveId)) {
    slaveOnlineStatus.set(slaveId, {
      status: 'online',
      timeoutCount: 0,
      lastSeen: Date.now()
    });
  }
  startPolling();
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

ipcMain.handle('list-ports', async () => {
  const ports = await SerialPort.list();

  const validPorts = ports.filter(p => {
    const pathLower = (p.path || '').toLowerCase();
    return pathLower.includes('wchusbserial');
  });

  const identifiedPorts = [];

  for (const p of validPorts) {
    const info = await identifyPort(p.path);

    let label = p.path;
    let isMaster = false;
    let isSlave = false;
    let slaveId = 0;

    if (info) {
      if (info.role === 4) {
        label += ` [MASTER]`;
        isMaster = true;
      } else if (info.role === 5) {
        label += ` [SLAVE ${info.id}]`;
        isSlave = true;
        slaveId = info.id;
      } else {
        label += ` [${info.roleName}]`;
      }
    }

    identifiedPorts.push({
      path: p.path,
      label: label,
      manufacturer: p.manufacturer || '',
      serialNumber: p.serialNumber || '',
      isMaster,
      isSlave,
      slaveId,
      identified: !!info,
      role: info ? info.role : null,
      id: info ? info.id : null
    });
  }

  return identifiedPorts;
});

ipcMain.handle('connect', async (event, { id, port, baudRate }) => {
  if (connections.has(id)) {
    const existing = connections.get(id);
    if (existing.port && existing.port.isOpen) {
      existing.port.close();
    }
  }

  return new Promise((resolve, reject) => {
    const serialPort = new SerialPort({
      path: port,
      baudRate: baudRate,
      dataBits: 8,
      parity: 'none',
      stopBits: 1
    });

    serialPort.on('open', () => {
      connections.set(id, { port: serialPort, mode: id });
      resolve({ success: true });
    });

    serialPort.on('error', (err) => {
      reject(new Error(err.message));
    });

    serialPort.on('data', (data) => {
      const receiveTime = Date.now();
      
      if (id === 'master') {
        // 处理 ACK 响应（消息确认）
        const ackSlaveId = parseAckResponse(data);
        if (ackSlaveId !== null && pendingAckCallbacks.has(ackSlaveId)) {
          const cb = pendingAckCallbacks.get(ackSlaveId);
          pendingAckCallbacks.delete(ackSlaveId);
          cb(ackSlaveId, receiveTime);
          return;
        }
        
        // 处理 PONG 响应（轮询/扫描）
        const pongSlaveId = parsePongResponse(data);
        if (pongSlaveId !== null) {
          // 优先处理轮询回调
          if (pendingPongCallbacks.has(pongSlaveId)) {
            const cb = pendingPongCallbacks.get(pongSlaveId);
            pendingPongCallbacks.delete(pongSlaveId);
            cb(pongSlaveId, receiveTime);
            return;
          }
          
          // 扫描模式下的处理
          if (scanningMode) {
            const elapsed = receiveTime - currentScanSendTime;
            console.log(`[扫描] ← 收到 SLAVE ${pongSlaveId} 响应, 延迟: ${elapsed}ms`);
            foundSlavesBuffer.push(pongSlaveId);
            registerSlave(pongSlaveId);
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('slave-found', { slaveId: pongSlaveId });
            }
            return;
          }
        }
      }
      
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('data-received', {
          id,
          data: data.toString('hex'),
          timestamp: Date.now()
        });
      }
    });

    serialPort.on('close', () => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('disconnected', { id });
      }
      connections.delete(id);
    });
  });
});

ipcMain.handle('disconnect', async (event, { id }) => {
  if (connections.has(id)) {
    const conn = connections.get(id);
    if (conn.port && conn.port.isOpen) {
      conn.port.close();
    }
    connections.delete(id);
  }
  
  if (id === 'master') {
    stopPolling();
    slaveOnlineStatus.clear();
  }
  
  return { success: true };
});

ipcMain.handle('send', async (event, { id, data, type, slaveId }) => {
  if (!connections.has(id)) {
    throw new Error('未连接');
  }

  const conn = connections.get(id);
  const buffer = Buffer.from(data, 'hex');
  
  const sendStart = Date.now();

  if (id === 'master') {
    let frame;
    let needsAck = false;
    
    if (type === 'broadcast') {
      frame = broadcast(buffer);
    } else if (type === 'link') {
      frame = establishLink(slaveId);
    } else if (type === 'ping') {
      frame = buildPingFrame(slaveId);
    } else {
      frame = sendToSlave(slaveId, buffer);
      needsAck = true;
    }
    
    conn.port.write(frame);
    await new Promise(resolve => conn.port.drain(resolve));
    
    if (needsAck) {
      const ackPromise = new Promise((resolve) => {
        pendingAckCallbacks.set(slaveId, (ackSlaveId, receiveTime) => {
          const roundTrip = receiveTime - sendStart;
          console.log(`[发送] → SLAVE ${slaveId}, 往返耗时: ${roundTrip}ms (单向约 ${Math.round(roundTrip / 2)}ms)`);
          updateSlaveOnlineStatus(slaveId, true);
          resolve();
        });
        
        setTimeout(() => {
          if (pendingAckCallbacks.has(slaveId)) {
            console.log(`[发送] → SLAVE ${slaveId}, 未收到 ACK (超时)`);
            pendingAckCallbacks.delete(slaveId);
            updateSlaveOnlineStatus(slaveId, false);
            resolve();
          }
        }, CONFIG.ACK_TIMEOUT);
      });
      
      await ackPromise;
    } else {
      const sendEnd = Date.now();
      console.log(`[发送] → SLAVE ${slaveId || 'ALL'}, 发送完成: ${sendEnd - sendStart}ms`);
    }
  } else {
    conn.port.write(buffer);
    await new Promise(resolve => conn.port.drain(resolve));
    const sendEnd = Date.now();
    console.log(`[发送] → ${id}, 发送完成: ${sendEnd - sendStart}ms`);
  }

  return { success: true };
});

ipcMain.handle('scan-slaves', async (event, { startId, endId, timeout }) => {
  if (!connections.has('master')) {
    throw new Error('MASTER 未连接');
  }

  const conn = connections.get('master');
  const start = startId || 0;
  const end = endId !== undefined ? endId : 15;
  const timeoutMs = timeout || CONFIG.PING_TIMEOUT;

  scanningMode = true;
  foundSlavesBuffer = [];
  console.log(`[扫描] 开始扫描 SLAVE ${start}-${end}, 超时 ${timeoutMs}ms/ID`);

  return new Promise((resolve) => {
    let currentId = start;
    let responseTimer = null;
    let scanTimer = null;

    const cleanup = () => {
      if (responseTimer) clearTimeout(responseTimer);
      if (scanTimer) clearTimeout(scanTimer);
      scanningMode = false;
      console.log('[扫描] 结束, 发现:', foundSlavesBuffer);
    };

    const probeNext = () => {
      if (currentId > end) {
        cleanup();
        resolve({ slaves: foundSlavesBuffer });
        return;
      }

      const pingFrame = buildPingFrame(currentId);
      currentScanSendTime = Date.now();
      conn.port.write(pingFrame);
      console.log(`[扫描] 探测 SLAVE ${currentId}, 发送时间: ${currentScanSendTime}`);

      responseTimer = setTimeout(() => {
        const elapsed = Date.now() - currentScanSendTime;
        if (elapsed > timeoutMs - 10) {
          console.log(`[扫描] SLAVE ${currentId} 超时 (${elapsed}ms)`);
        }
        currentId++;
        probeNext();
      }, timeoutMs);
    };

    scanTimer = setTimeout(() => {
      cleanup();
      resolve({ slaves: foundSlavesBuffer, timeout: true });
    }, (end - start + 1) * timeoutMs + 2000);

    probeNext();
  });
});
