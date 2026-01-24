import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# --- 配置 ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

supabase = create_client(url, key)
SITE_URL = "https://jijglingw-ux.github.io/ghost-watcher"

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
    except Exception as e:
        print(f"❌ 邮件错误: {e}")

def parse_time(time_str):
    if not time_str: return None
    clean_str = time_str.replace('Z', '+00:00')
    try:
        return datetime.datetime.fromisoformat(clean_str)
    except:
        try:
            return datetime.datetime.fromisoformat(clean_str.split('.')[0] + "+00:00")
        except: return None

def check_vaults():
    # A. 监测存活用户 (status = active)
    try:
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
        active_vaults = res.data
    except: active_vaults = []

    for row in active_vaults:
        user_id = row.get('id')
        last_time = parse_time(row.get('last_checkin_at'))
        if not last_time: continue

        deadline = int(row.get('timeout_minutes') or 60)
        max_warns = int(row.get('max_warnings') or 3)
        interval = int(row.get('warning_interval') or 5)
        current_warns = int(row.get('current_warnings') or 0)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        # 1. 发送唤醒邮件
        start_warn_time = deadline - (max_warns * interval)
        if start_warn_time < 0: start_warn_time = deadline - interval

        if diff >= start_warn_time and diff < deadline:
            expected_warns = int((diff - start_warn_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 唤醒 {user_id} ({current_warns}/{max_warns})")
                
                body = f"遗物系统检测到您已失联。\n遗言将于 {mins_left} 分钟后发出。\n请立即登录续期：{SITE_URL}"
                send_email(row.get('warning_email'), f"🚨 唤醒警告 ({current_warns}/{max_warns})", body)
                
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1)

        # 2. 确认失联 -> 进入待领取的“灵柩”状态 (永久存证起始点)
        if diff >= deadline:
            print(f"🔴 用户 {user_id} 确认失联 -> 数据封存入灵柩")
            relic_token = f"RELIC::{user_id}"
            
            # 发送永久有效的提取通知
            ben_body = f"""
            【遗物提取码】
            {relic_token}
            
            说明：
            1. 此码目前永久有效，数据已安全封存。
            2. 请访问官网 {SITE_URL} 使用本邮箱登录。
            3. 输入提取码并【成功解密】的瞬间，将启动30分钟自毁程序。
            """
            send_email(row.get('beneficiary_email'), "🔒 遗物已就绪 - 阅后即焚提醒", ben_body)
            
            # 状态设为 pending，账号自此注销，但数据保留
            supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq("id", user_id).execute()

    # B. 监测“阅后即焚”状态 (status = reading)
    # 只有当受益人在前端点击了解密，状态才会变成 reading
    try:
        res = supabase.table("vaults").select("*").eq("status", "reading").execute()
        reading_vaults = res.data
    except: reading_vaults = []

    for row in reading_vaults:
        user_id = row.get('id')
        unlock_time = parse_time(row.get('last_checkin_at')) # reading 状态下此字段记录解密时间
        
        if unlock_time:
            passed = (datetime.datetime.now(datetime.timezone.utc) - unlock_time).total_seconds() / 60
            if passed >= 30:
                print(f"💀 30分钟到，执行物理抹除: {user_id}")
                supabase.table("vaults").delete().eq("id", user_id).execute()
                try:
                    supabase.auth.admin.delete_user(user_id)
                except: pass

if __name__ == "__main__":
    print("🚀 遗物系统 V12.0 (Python修正版) 启动...")
    while True:
        check_vaults()
        time.sleep(60)
