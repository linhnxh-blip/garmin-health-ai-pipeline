/**
 * ==============================================================================
 * PM2 ECOSYSTEM CONFIGURATION CHO ASUS ROG ALLY X (WINDOWS 11 LOCAL SERVER)
 * ==============================================================================
 * Hướng dẫn chạy:
 *   npm install -g pm2 pm2-windows-startup
 *   pm2 start ecosystem.config.js
 *   pm2 save
 *   pm2-startup install
 */

const path = require("path");
const fs = require("fs");

// Tự động phát hiện đường dẫn Python trong Virtualenv trên Windows
const projectRoot = __dirname;
const venvPythonWin = path.join(projectRoot, "venv", "Scripts", "python.exe");
const dotVenvPythonWin = path.join(projectRoot, ".venv", "Scripts", "python.exe");

let pythonInterpreter = "python";
if (fs.existsSync(venvPythonWin)) {
  pythonInterpreter = venvPythonWin;
} else if (fs.existsSync(dotVenvPythonWin)) {
  pythonInterpreter = dotVenvPythonWin;
}

module.exports = {
  apps: [
    {
      name: "garmin-web-dashboard",
      script: "main.py",
      args: "web --host 0.0.0.0 --port 8000",
      interpreter: pythonInterpreter,
      cwd: projectRoot,
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
        WEB_HOST: "0.0.0.0",
        WEB_PORT: "8000"
      },
      out_file: path.join(projectRoot, "logs", "pm2_web_out.log"),
      error_file: path.join(projectRoot, "logs", "pm2_web_err.log"),
      merge_logs: true,
      time: true
    },
    {
      name: "garmin-telegram-bot",
      script: "main.py",
      args: "bot",
      interpreter: pythonInterpreter,
      cwd: projectRoot,
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      out_file: path.join(projectRoot, "logs", "pm2_bot_out.log"),
      error_file: path.join(projectRoot, "logs", "pm2_bot_err.log"),
      merge_logs: true,
      time: true
    }
  ]
};

