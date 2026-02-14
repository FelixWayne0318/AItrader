// PM2 Ecosystem Configuration for AlgVex Web
// Usage: pm2 start ecosystem.config.js
//
// On the production server the repo is at /home/linuxuser/nautilus_AItrader.
// Override with AITRADER_PATH environment variable if deploying elsewhere.

const path = require('path');
const REPO_DIR = process.env.AITRADER_PATH || '/home/linuxuser/nautilus_AItrader';

module.exports = {
  apps: [
    {
      name: 'algvex-frontend',
      // IMPORTANT: Use absolute path to avoid cwd mismatch when PM2 restarts.
      cwd: path.join(REPO_DIR, 'web', 'frontend'),
      script: 'npm',
      args: 'start',
      env: {
        NODE_ENV: 'production',
        PORT: 3000
      },
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',

      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: '~/.pm2/logs/algvex-frontend-error.log',
      out_file: '~/.pm2/logs/algvex-frontend-out.log',
      merge_logs: true,

      exp_backoff_restart_delay: 100,
      max_restarts: 10,
      min_uptime: '10s'
    },
    {
      name: 'algvex-backend',
      cwd: path.join(REPO_DIR, 'web', 'backend'),
      // Use Python interpreter directly with -m uvicorn for reliable startup
      script: path.join(REPO_DIR, 'web', 'backend', 'venv', 'bin', 'python3'),
      args: '-m uvicorn main:app --host 0.0.0.0 --port 8000',
      interpreter: 'none',
      env: {
        PYTHONUNBUFFERED: '1',
        AITRADER_PATH: REPO_DIR
      },
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',

      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: '~/.pm2/logs/algvex-backend-error.log',
      out_file: '~/.pm2/logs/algvex-backend-out.log',
      merge_logs: true
    }
  ]
};
