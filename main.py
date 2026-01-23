import os
from supabase import create_client
import datetime
import smtplib
from email.mime.text import MIMEText

# 环境配置
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

supabase = create_client(url, key)

def check_vaults():
    res = supabase.table("vaults").select("*").execute()
    
    for row in res.data:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        status = row.get('status', 'active')
        if not last_checkin or status != 'active': continue

        # --- 获取用户设置 ---
        deadline = int(row.get('timeout_minutes', 10))   # 死亡判定时间 (如10)
        max_warns = int(row.get('max_warnings', 2))      # 唤醒次数 (如2)
        interval = int(row.get('warning_interval', 1))   # 唤醒间隔 (如1)
        current_warns = row.get('current_warnings', 0)
        
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        # --- 计算时间差 ---
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        print(f"用户 {user_id} | 已失联：{diff:.1f}分 | 死亡终点：{deadline}分")

        # --- V3 倒计时逻辑 ---
        
        # 1. 判定是否到达“最终死亡终点”
        if diff >= deadline:
            print(f"🔴 确认死亡：失联时间已达终点 {deadline} 分钟。")
            content = row.get('encrypted_data', '无加密数据')
            send_email(ben_email, "🔒 数字遗产移交", f"由于所有者确认失联（超过{deadline}分钟），以下是托付数据：\n\n{content}")
            supabase.table("vaults").update({"status": "triggered"}).eq("id", user_id).execute()
            continue

        # 2. 判定是否进入“唤醒区间”
        # 起始唤醒时间 = 死亡时间 - (总唤醒次数 * 间隔)
        start_warning_time = deadline - (max_warns * interval)
        
        if diff >= start_warning_time:
            # 计算当前时间应该处于第几次唤醒
            # 公式：(当前失联时间 - 起始唤醒时间) / 间隔
            expected_warns = int((diff - start_warning_time) / interval) + 1
            
            # 限制最高警告次数
            if expected_warns > max_warns: expected_warns = max_warns

            # 如果当前已发次数少于理论应发次数，则补发
            if current_warns < expected_warns:
                mins_left = int(deadline - diff)
                send_email(warn_email, f"⚠️ 倒计时唤醒 ({expected_warns}/{max_warns})", 
                           f"检测到您已失联 {int(diff)} 分钟。距离系统判定死亡还剩约 {mins_left} 分钟！请尽快登录心跳。")
                
                supabase.table("vaults").update({"current_warnings": expected_warns}).eq("id", user_id).execute()
                print(f"⚠️ 已发送第 {expected_warns} 次提前唤醒邮件 (剩余约 {mins_left} 分钟)")
        else:
            print(f"✅ 状态安全 (尚未进入唤醒区间，距离预警还剩 {int(start_warning_time - diff)} 分钟)")

def send_email(to_email, subject, content):
    if not to_email: return
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email
        with smtplib.SMTP_SSL("smtp.qq.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    print("🚀 GhostProtocol V3.0 (倒计时版) 巡逻中...")
    check_vaults()
