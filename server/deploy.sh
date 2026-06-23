#!/usr/bin/env bash
# 在云服务器上、本脚本所在目录执行：bash deploy.sh
set -euo pipefail

APPDIR="$(cd "$(dirname "$0")" && pwd)"
echo "应用目录：$APPDIR"

echo "[1/5] 安装依赖…"
python3 -m pip install -r "$APPDIR/requirements.txt"

echo "[2/5] 准备配置文件…"
if [ ! -f "$APPDIR/config.json" ]; then
  cp "$APPDIR/config.example.json" "$APPDIR/config.json"
  echo ">>> 已生成 config.json，请编辑它填入 serverchan_sendkey 和 login_password 后重跑本脚本。"
  echo ">>> 编辑命令：vi $APPDIR/config.json"
  exit 0
fi

echo "[3/5] 安装 systemd 服务…"
sed "s#__APPDIR__#$APPDIR#g" "$APPDIR/todo-reminder.service" | sudo tee /etc/systemd/system/todo-reminder.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable todo-reminder
sudo systemctl restart todo-reminder

echo "[4/5] 等待启动…"
sleep 3
sudo systemctl --no-pager status todo-reminder | head -n 8 || true

echo "[5/5] 访问地址："
PORT="$(cat "$APPDIR/current_port.txt" 2>/dev/null || echo 5005)"
IP="$(hostname -I | awk '{print $1}')"
echo ">>> 在公司网络/VPN 下打开： http://$IP:$PORT"
echo ">>> 查看日志： tail -f $APPDIR/service.log"
