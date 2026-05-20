const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("appInfo", {
  appName: "Edu File Repository Desktop"
});

contextBridge.exposeInMainWorld("appControl", {
  closeApp: () => ipcRenderer.invoke("app:quit")
});
