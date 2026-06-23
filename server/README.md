# 每日待办提醒 · 服务端部署

部署到 24h 运行的腾讯 DevCloud 服务器（21.214.67.158，Python 3.11.6）。

## 一、拿到 Server酱 微信密钥（一次性）
1. 微信扫码关注 Server³ 公众号：打开 https://sct.ftqq.com/ ，用微信扫码登录。
2. 登录后在「SendKey」页面复制你的密钥（形如 `SCTxxxxxxxx`）。
3. 在「消息通道」里把「方糖（微信）」打开并绑定，确保能收到测试消息。

## 二、把代码放到服务器
通过腾讯云控制台把整个 `每日待办提醒/server/` 目录上传到服务器，例如放到 `/root/todo/server/`。
（或在服务器上 `git clone` 本仓库后进入该目录。）

## 三、部署
```bash
cd /root/todo/server
bash deploy.sh         # 第一次会先安装依赖，然后生成 config.json 并提示你填写（这是正常的）
vi config.json         # 填 serverchan_sendkey 和 login_password（登录网页用的密码）
bash deploy.sh         # 填完后再跑一次，正式启动服务
```
> **提示：** 第一次跑 `deploy.sh` 会先安装 Python 依赖（pip install），安装完才提示你编辑 config.json，属于正常流程，按提示编辑好后再执行第二次即可。

## 三·五、开放服务器端口（首次部署需要）

> **为什么要这一步？** 即使在公司 VPN 下，如果云服务器的防火墙/安全组没有放行端口，浏览器打开网页也会"连接被拒绝"。

默认端口是 **5005**（如果 deploy.sh 输出或 `current_port.txt` 里显示的是别的端口，就用那个端口）。

**方式一：腾讯云控制台（推荐）**
1. 登录腾讯云控制台 → 找到这台云服务器 → 点击「安全组」（或「防火墙」）。
2. 进入「入站规则」→「添加规则」。
3. 填写：协议 **TCP**、端口 **5005**、来源填公司出口网段（不确定就先填 `0.0.0.0/0` 仅供自测，之后再收紧）。
4. 保存，稍等几秒生效。

**方式二：命令行（在服务器上执行）**
```bash
sudo firewall-cmd --add-port=5005/tcp --permanent && sudo firewall-cmd --reload
```

## 四、验证
- 脚本结尾会打印访问地址，如 `http://21.214.67.158:5005`。**在公司网络 / VPN 下**用浏览器打开，输入你设的登录密码。
- 测试微信推送：
  ```bash
  curl "https://sctapi.ftqq.com/<你的SendKey>.send" -d "title=测试&desp=待办提醒已上线"
  ```
  微信应收到一条消息。

## 五、常用运维
```bash
sudo systemctl status todo-reminder     # 状态
sudo systemctl restart todo-reminder    # 重启
tail -f service.log                      # 看日志
```

## 注意
- `config.json` 含密钥与密码，已被 `.gitignore` 忽略，不要提交。
- 网页仅在公司网络 / VPN 可访问；微信提醒不受此限制。
- Server酱 是第三方中转服务，待办标题请勿写敏感信息。
