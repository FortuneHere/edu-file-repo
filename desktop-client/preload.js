const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("appInfo", {
  appName: "Edu File Repository Desktop"
});
