const state = {
  master: { connected: false, port: null, target: null, scanning: false },
  slaves: new Map(),
  ports: []
};

const $ = (id) => document.getElementById(id);

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('zh-CN', { hour12: false }) + '.' + 
         date.getMilliseconds().toString().padStart(3, '0');
}

function hexToString(hex) {
  if (!hex) return '';
  const bytes = [];
  for (let i = 0; i < hex.length; i += 2) {
    bytes.push(parseInt(hex.substr(i, 2), 16));
  }
  try {
    return new TextDecoder('utf-8').decode(new Uint8Array(bytes));
  } catch {
    return hex.toUpperCase().match(/.{2}/g).join(' ');
  }
}

function stringToHex(str) {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(str);
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

function addMessage(direction, data, timestamp) {
  const list = $('messages-list');
  const item = document.createElement('div');
  item.className = `message-item ${direction.type}`;
  
  const headerDiv = document.createElement('div');
  headerDiv.className = 'msg-header';
  
  const timeSpan = document.createElement('span');
  timeSpan.className = 'time';
  timeSpan.textContent = formatTime(timestamp);
  
  const dirSpan = document.createElement('span');
  dirSpan.className = 'direction';
  dirSpan.textContent = direction.text;
  
  headerDiv.appendChild(timeSpan);
  headerDiv.appendChild(dirSpan);
  
  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content';
  contentDiv.textContent = hexToString(data);
  contentDiv.title = `HEX: ${data.toUpperCase()}`;
  
  item.appendChild(headerDiv);
  item.appendChild(contentDiv);
  
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;
}

function updateTargetDisplay() {
  const display = $('master-target-display');
  const broadcastBtn = $('master-broadcast');
  
  state.slaves.forEach((slaveData, slaveId) => {
    const card = slaveData.element;
    const btn = card.querySelector('.btn-set-target');
    
    if (btn) {
      if (state.master.target === slaveId) {
        card.classList.add('is-target');
        btn.classList.add('active');
        btn.textContent = '已选';
      } else {
        card.classList.remove('is-target');
        btn.classList.remove('active');
        btn.textContent = '设为目标';
      }
    }
  });
  
  if (state.master.target === 'broadcast') {
    display.textContent = '广播';
    display.classList.add('broadcast');
    broadcastBtn.classList.add('active');
  } else if (state.master.target !== null) {
    display.textContent = `SLAVE ${state.master.target}`;
    display.classList.remove('broadcast');
    broadcastBtn.classList.remove('active');
  } else {
    display.textContent = '未选择';
    display.classList.remove('broadcast');
    broadcastBtn.classList.remove('active');
  }
}

function setTarget(target) {
  state.master.target = target;
  updateTargetDisplay();
}

async function loadPorts() {
  try {
    state.ports = await window.electronAPI.listPorts();
    updatePortSelects();
  } catch (err) {
    console.error('获取串口列表失败:', err);
  }
}

function updatePortSelects() {
  const masterPortSelect = $('master-port');
  const currentMasterValue = masterPortSelect.value;
  masterPortSelect.innerHTML = '<option value="">选择串口</option>';
  
  const masterPorts = state.ports.filter(p => p.isMaster);
  
  masterPorts.forEach(port => {
    const option = document.createElement('option');
    option.value = port.path;
    option.textContent = port.label;
    masterPortSelect.appendChild(option);
  });
  
  if (currentMasterValue && masterPorts.find(p => p.path === currentMasterValue)) {
    masterPortSelect.value = currentMasterValue;
  } else if (masterPorts.length > 0) {
    masterPortSelect.value = masterPorts[0].path;
  }
  
  state.slaves.forEach((slaveData, slaveId) => {
    if (slaveData.isRemote) return;
    const portSelect = slaveData.element.querySelector('.slave-port');
    if (!portSelect) return;
    const currentValue = portSelect.value;
    portSelect.innerHTML = '<option value="">选择串口</option>';
    
    state.ports.forEach(port => {
      const option = document.createElement('option');
      option.value = port.path;
      option.textContent = port.label;
      portSelect.appendChild(option);
    });
    
    if (currentValue && state.ports.find(p => p.path === currentValue)) {
      portSelect.value = currentValue;
    }
  });
}

function createRemoteSlaveCard(slaveId) {
  if (state.slaves.has(slaveId)) return;
  
  const template = $('slave-template-remote');
  const clone = template.content.cloneNode(true);
  const card = clone.querySelector('.slave-card');
  
  card.dataset.slaveId = slaveId;
  card.querySelector('.slave-name').textContent = `SLAVE ${slaveId}`;
  
  state.slaves.set(slaveId, {
    connected: true,
    element: card,
    port: null,
    isRemote: true
  });
  
  card.querySelector('.btn-set-target').addEventListener('click', () => {
    if (state.master.target === slaveId) {
      setTarget(null);
    } else {
      setTarget(slaveId);
    }
  });
  
  card.querySelector('.btn-remove-slave').addEventListener('click', () => {
    card.remove();
    state.slaves.delete(slaveId);
    if (state.master.target === slaveId) {
      setTarget(null);
    }
  });
  
  $('slaves-list').appendChild(card);
}

function createLocalSlaveCard(slaveId, autoPort = null) {
  if (state.slaves.has(slaveId)) {
    const existing = state.slaves.get(slaveId);
    if (autoPort && !existing.port && !existing.isRemote) {
      const portSelect = existing.element.querySelector('.slave-port');
      if (portSelect) portSelect.value = autoPort;
      existing.port = autoPort;
    }
    return;
  }
  
  const template = $('slave-template-local');
  const clone = template.content.cloneNode(true);
  const card = clone.querySelector('.slave-card');
  
  card.dataset.slaveId = slaveId;
  card.querySelector('.slave-name').textContent = `SLAVE ${slaveId}`;
  
  state.slaves.set(slaveId, {
    connected: false,
    element: card,
    port: autoPort,
    isRemote: false
  });
  
  const slaveIdForAPI = `slave-${slaveId}`;
  
  card.querySelector('.btn-set-target').addEventListener('click', () => {
    if (state.master.target === slaveId) {
      setTarget(null);
    } else {
      setTarget(slaveId);
    }
  });
  
  card.querySelector('.slave-connect').addEventListener('click', async () => {
    const slaveData = state.slaves.get(slaveId);
    
    if (slaveData.connected) {
      await window.electronAPI.disconnect({ id: slaveIdForAPI });
      updateSlaveConnectionUI(slaveId, false);
    } else {
      const port = card.querySelector('.slave-port').value;
      if (!port) {
        alert('请选择串口');
        return;
      }
      
      try {
        await window.electronAPI.connect({
          id: slaveIdForAPI,
          port: port,
          baudRate: 921600
        });
        updateSlaveConnectionUI(slaveId, true);
        slaveData.port = port;
      } catch (err) {
        alert(`连接失败: ${err.message}`);
      }
    }
  });
  
  card.querySelector('.slave-send').addEventListener('click', async () => {
    const input = card.querySelector('.slave-input');
    const text = input.value.trim();
    if (!text) return;
    
    const hexData = stringToHex(text);
    
    try {
      await window.electronAPI.send({
        id: slaveIdForAPI,
        data: hexData,
        type: 'raw',
        slaveId: 0
      });
      addMessage(
        { type: 'to-master', text: `SLAVE ${slaveId} 发送 → MASTER` },
        hexData,
        Date.now()
      );
      input.value = '';
    } catch (err) {
      alert(`发送失败: ${err.message}`);
    }
  });
  
  card.querySelector('.slave-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      card.querySelector('.slave-send').click();
    }
  });
  
  card.querySelector('.btn-remove-slave').addEventListener('click', async () => {
    const slaveData = state.slaves.get(slaveId);
    if (slaveData && slaveData.connected) {
      await window.electronAPI.disconnect({ id: slaveIdForAPI });
    }
    card.remove();
    state.slaves.delete(slaveId);
    if (state.master.target === slaveId) {
      setTarget(null);
    }
  });
  
  $('slaves-list').appendChild(card);
  updatePortSelects();
  
  if (autoPort) {
    const portSelect = card.querySelector('.slave-port');
    portSelect.value = autoPort;
  }
}

function updateMasterConnectionUI(connected) {
  const statusDot = $('master-status-dot');
  const statusText = $('master-status-text');
  const connectBtn = $('master-connect');
  const sendSection = $('master-send-section');
  const portSelect = $('master-port');
  const scanBtn = $('scan-slaves-btn');
  
  state.master.connected = connected;
  
  if (connected) {
    statusDot.classList.add('connected');
    statusText.textContent = '已连接';
    statusText.classList.add('connected');
    connectBtn.textContent = '断开';
    connectBtn.classList.add('connected');
    sendSection.style.display = 'block';
    portSelect.disabled = true;
    if (scanBtn) scanBtn.disabled = false;
  } else {
    statusDot.classList.remove('connected');
    statusText.textContent = '未连接';
    statusText.classList.remove('connected');
    connectBtn.textContent = '连接 MASTER';
    connectBtn.classList.remove('connected');
    sendSection.style.display = 'none';
    portSelect.disabled = false;
    if (scanBtn) scanBtn.disabled = true;
  }
}

function updateSlaveConnectionUI(slaveId, connected) {
  const slaveData = state.slaves.get(slaveId);
  if (!slaveData || slaveData.isRemote) return;
  
  const card = slaveData.element;
  const statusDot = card.querySelector('.status-dot');
  const statusText = card.querySelector('.status-text');
  const connectBtn = card.querySelector('.slave-connect');
  const sendSection = card.querySelector('.slave-send-section');
  const portSelect = card.querySelector('.slave-port');
  
  slaveData.connected = connected;
  
  if (connected) {
    if (statusDot) statusDot.classList.add('connected');
    if (statusText) {
      statusText.textContent = '已连接';
      statusText.classList.add('connected');
    }
    if (connectBtn) {
      connectBtn.textContent = '断开';
      connectBtn.classList.add('connected');
    }
    if (sendSection) sendSection.style.display = 'block';
    if (portSelect) portSelect.disabled = true;
  } else {
    if (statusDot) statusDot.classList.remove('connected');
    if (statusText) {
      statusText.textContent = '未连接';
      statusText.classList.remove('connected');
    }
    if (connectBtn) {
      connectBtn.textContent = '连接';
      connectBtn.classList.remove('connected');
    }
    if (sendSection) sendSection.style.display = 'none';
    if (portSelect) portSelect.disabled = false;
  }
}

function initMasterPanel() {
  $('master-refresh').addEventListener('click', loadPorts);
  
  $('master-connect').addEventListener('click', async () => {
    if (state.master.connected) {
      await window.electronAPI.disconnect({ id: 'master' });
      updateMasterConnectionUI(false);
    } else {
      const port = $('master-port').value;
      if (!port) {
        alert('请选择串口');
        return;
      }
      
      try {
        await window.electronAPI.connect({
          id: 'master',
          port: port,
          baudRate: 921600
        });
        updateMasterConnectionUI(true);
        state.master.port = port;
      } catch (err) {
        alert(`连接失败: ${err.message}`);
      }
    }
  });
  
  $('master-broadcast').addEventListener('click', () => {
    if (state.master.target === 'broadcast') {
      setTarget(null);
    } else {
      setTarget('broadcast');
    }
  });
  
  $('master-send').addEventListener('click', async () => {
    if (state.master.target === null) {
      alert('请先选择目标 SLAVE 或广播');
      return;
    }
    
    const input = $('master-input');
    const text = input.value.trim();
    if (!text) return;
    
    const hexData = stringToHex(text);
    
    try {
      if (state.master.target === 'broadcast') {
        await window.electronAPI.send({
          id: 'master',
          data: hexData,
          type: 'broadcast',
          slaveId: 0
        });
        addMessage(
          { type: 'broadcast', text: 'MASTER 广播 → 所有 SLAVE' },
          hexData,
          Date.now()
        );
      } else {
        await window.electronAPI.send({
          id: 'master',
          data: hexData,
          type: 'send',
          slaveId: state.master.target
        });
        addMessage(
          { type: 'from-master', text: `MASTER 发送 → SLAVE ${state.master.target}` },
          hexData,
          Date.now()
        );
      }
      input.value = '';
    } catch (err) {
      alert(`发送失败: ${err.message}`);
    }
  });
  
  $('master-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      $('master-send').click();
    }
  });
}

function initEventListeners() {
  window.electronAPI.onDataReceived((data) => {
    if (data.id === 'master') {
      addMessage(
        { type: 'to-master', text: 'MASTER 收到 ← SLAVE' },
        data.data,
        data.timestamp
      );
    } else if (data.id.startsWith('slave-')) {
      const slaveId = parseInt(data.id.replace('slave-', ''));
      addMessage(
        { type: 'to-master', text: `SLAVE ${slaveId} 收到 ← MASTER` },
        data.data,
        data.timestamp
      );
    }
  });
  
  window.electronAPI.onDisconnected((data) => {
    if (data.id === 'master') {
      updateMasterConnectionUI(false);
    } else if (data.id.startsWith('slave-')) {
      const slaveId = parseInt(data.id.replace('slave-', ''));
      updateSlaveConnectionUI(slaveId, false);
    }
  });
  
  $('refresh-slaves').addEventListener('click', loadPorts);
  
  $('scan-slaves-btn').addEventListener('click', () => {
    scanSlaves(0, 15);
  });
  
  $('clear-all-msgs').addEventListener('click', () => {
    $('messages-list').innerHTML = '';
  });
  
  window.electronAPI.onSlaveFound((data) => {
    createRemoteSlaveCard(data.slaveId);
  });
}

async function scanSlaves(startId = 0, endId = 255) {
  if (!state.master.connected) {
    alert('请先连接 MASTER');
    return;
  }
  
  if (state.master.scanning) {
    return;
  }
  
  state.master.scanning = true;
  const scanBtn = $('scan-slaves-btn');
  if (scanBtn) {
    scanBtn.textContent = '扫描中...';
    scanBtn.disabled = true;
  }
  
  addMessage(
    { type: 'broadcast', text: `开始扫描 SLAVE ${startId}-${endId}...` },
    '',
    Date.now()
  );
  
  try {
    const result = await window.electronAPI.scanSlaves({
      startId,
      endId,
      timeout: 150
    });
    
    if (result.slaves.length > 0) {
      addMessage(
        { type: 'to-master', text: `发现 ${result.slaves.length} 个 SLAVE: ${result.slaves.map(id => `S${id}`).join(', ')}` },
        '',
        Date.now()
      );
    } else {
      addMessage(
        { type: 'broadcast', text: '未发现在线 SLAVE' },
        '',
        Date.now()
      );
    }
  } catch (err) {
    alert(`扫描失败: ${err.message}`);
  } finally {
    state.master.scanning = false;
    if (scanBtn) {
      scanBtn.textContent = '扫描';
      scanBtn.disabled = false;
    }
  }
}

async function init() {
  initMasterPanel();
  initEventListeners();
  await loadPorts();
}

document.addEventListener('DOMContentLoaded', init);
