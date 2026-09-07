# ad-agent

开心消消乐广告投放分析 Skills，可在 Codex 中直接提问并生成报告链接。

## 安装

cd到项目目录后执行：

```bash
curl -fsSL https://raw.githubusercontent.com/rayyang777/ad-agent/main/install.sh | bash -s -- --user 张三
```



## 支持的 Skills

- `ad-skills`：查看可用的广告分析能力
- `ad-dau`：分析广告投放对 DAU 的影响
- `ad-anomaly-attribution`：分析留存、ROI、LTV、付费率等异常

## MCP

MCP 是 Skills 调用外部能力的接口。本项目的 MCP 只负责原子操作：提交查询、查看进度、获取结果、渲染报告、上传文件；分析思路和报告内容由对应 Skill 负责。

## 配置

安装后编辑项目根目录的 `config.json`，补充下面字段：

```json
{
  "skills_scope": "default",
  "data_fortress_platform_user": "",
  "data_fortress_aes_key": "",
  "username": "张三",
  "feishu_drive": {
    "parent_node": ""
  },
  "feishu_app": {
    "app_id": "",
    "app_secret": ""
  }
}
```

- `skills_scope`：安装范围，默认是 `default`
- `username`：报告产出用户，可通过安装命令的 `--user` 设置
- `data_fortress_platform_user`：数据堡垒认证账号
- `data_fortress_aes_key`：数据堡垒 AES 秘钥
- `feishu_drive.parent_node`：飞书云盘文件夹 Token
- `feishu_app.app_id`：飞书应用 ID
- `feishu_app.app_secret`：飞书应用 Secret

## 更新

Skill 或报告模板有更新时，在业务项目根目录重新执行安装命令，然后重启 Codex 或新开任务：

```bash
bash /tmp/ad-agent-install.sh
```
