import os
import time
from datetime import datetime, timezone
from supabase import create_client

# === 环境变量配置 ===
# 确保你的 GitHub Secrets 或本地环境变量里有这两个值
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ 错误: 缺少 SUPABASE_URL 或 SUPABASE_KEY 环境变量")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def financial_audit():
    print("📊 PLUVO 财务审计系统启动...")
    db = get_db()
    if not db: return

    try:
        # 1. 从 transactions 表拉取所有数据
        # 注意：这里改成了正确的表名 'transactions'
        response = db.table("transactions").select("*").execute()
        logs = response.data
    except Exception as e:
        print(f"⚠️ 数据库读取失败: {e}")
        return

    if not logs:
        print("💤 暂无交易记录")
        return

    # 2. 核心财务计算
    total_mint = 0.0  # 总发行量 (负债)
    total_burn = 0.0  # 总核销量的绝对值 (收入确认)
    revenue = 0.0     # 实际法币营收预估

    print(f"\n🔍 正在审计 {len(logs)} 条流水...")

    for log in logs:
        amount = float(log['amount'])
        t_type = log['type']
        
        if t_type == 'mint':
            total_mint += amount
        elif t_type == 'burn':
            # Burn 记录通常是负数，我们需要它的绝对值
            burn_val = abs(amount)
            total_burn += burn_val
            # 假设核销 1个币 = 确认 1元营收 (根据你的模型调整)
            revenue += burn_val * 1.0 

    # 3. 计算当前流通总量 (Outstanding Supply)
    current_supply = total_mint - total_burn

    # 4. 输出财务报表
    print("-" * 40)
    print(f"📅 审计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)
    print(f"🟢 累计发行 (Mint):  {total_mint:,.2f} CP")
    print(f"🔴 累计核销 (Burn):  {total_burn:,.2f} CP")
    print("-" * 40)
    print(f"💎 当前流通总量:     {current_supply:,.2f} CP")
    print(f"💰 预估核销营收:     ¥ {revenue:,.2f}")
    print("-" * 40)

    # 5. (可选) 风控预警
    # 如果流通量异常大，可以发邮件报警（这里仅打印）
    if current_supply > 10000:
        print("⚠️ 警告: 资产池水位过高，请检查是否有刷单行为！")

if __name__ == "__main__":
    # 如果是在 GitHub Actions 里跑，运行一次就退出
    financial_audit()
    
    # 如果是本地跑，可以开启循环监控
    # while True:
    #     financial_audit()
    #     time.sleep(60) # 每分钟查一次
