# watchdog.py - 真实连接 Supabase 的看门狗
import os
import time
from supabase import create_client, Client

# 从 GitHub Secrets 读取配置 (需在 GitHub 仓库设置里配置这些变量)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ 错误: 未找到数据库配置，看门狗无法启动")
    exit(1)

supabase: Client = create_client(url, key)

print("🐶 [Phoenix Watchdog] 正在连接云端数据库...")

# 1. 审计任务：检查总资产
response = supabase.table('assets').select("*").execute()
assets = response.data
print(f"✅ 系统健康 | 当前全网资产沉淀: {len(assets)} 条记录")

# 2. 审计任务：检查异常大额交易
abnormal = supabase.table('records').select("*").gt('amount', 500).execute()
if len(abnormal.data) > 0:
    print(f"⚠️ 警报: 检测到 {len(abnormal.data)} 笔大额异常交易！")
else:
    print("✅ 交易风控: 无异常")

print("🐕 看门狗巡检完毕")
