const {defineConfig} = require('@playwright/test');
const python = process.platform==='win32'?'.venv\\Scripts\\python.exe':'.venv/bin/python';
module.exports = defineConfig({
  testDir:'./tests/web', timeout:45000, workers:1, fullyParallel:false,
  use:{baseURL:'http://127.0.0.1:8765',headless:true,viewport:{width:1440,height:1000},
    launchOptions:process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}},
  webServer:{command:`${python} scripts/run-web-tests.py`,url:'http://127.0.0.1:8765/api/health',reuseExistingServer:false,timeout:30000},
  reporter:'list',
});
