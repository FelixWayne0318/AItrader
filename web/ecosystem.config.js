// PM2 Ecosystem Configuration for AlgVex Web
// 使用方法: pm2 start ecosystem.config.js

module.exports = {
  apps: [
    {
      name: 'algvex-frontend',
      // IMPORTANT: Use absolute path to avoid cwd mismatch when PM2 restarts.
      // Relative paths depend on where PM2 was first started from.
      cwd: '/home/linuxuser/nautilus_AItrader/web/frontend',
      script: 'npm',
      args: 'start',
      env: {
        NODE_ENV: 'production',
        PORT: 3000
      },
      // 自动重启配置
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',

      // 日志配置
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: '~/.pm2/logs/algvex-frontend-error.log',
      out_file: '~/.pm2/logs/algvex-frontend-out.log',
      merge_logs: true,

      // 重启策略
      exp_backoff_restart_delay: 100,
      max_restarts: 10,
      min_uptime: '10s'
    },
    {
      name: 'algvex-backend',
      cwd: '/home/linuxuser/nautilus_AItrader/web/backend',
      script: 'uvicorn',
      args: 'main:app --host 0.0.0.0 --port 8000',
      interpreter: 'python3',
      env: {
        PYTHONUNBUFFERED: '1'
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
