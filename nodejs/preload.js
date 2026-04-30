const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  listPorts: () => ipcRenderer.invoke('list-ports'),

  connect: (options) => ipcRenderer.invoke('connect', options),
  disconnect: (options) => ipcRenderer.invoke('disconnect', options),
  send: (options) => ipcRenderer.invoke('send', options),
  scanSlaves: (options) => ipcRenderer.invoke('scan-slaves', options),

  onDataReceived: (callback) => {
    ipcRenderer.on('data-received', (event, data) => callback(data));
  },

  onDisconnected: (callback) => {
    ipcRenderer.on('disconnected', (event, data) => callback(data));
  },

  onSlaveFound: (callback) => {
    ipcRenderer.on('slave-found', (event, data) => callback(data));
  },

  onSlaveStatusUpdate: (callback) => {
    ipcRenderer.on('slave-status-update', (event, data) => callback(data));
  }
});
