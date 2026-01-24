import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# --- 配置区 ---
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

# --- 核心修复：更强壮的时间解析函数 ---
def parse_time(time_str):
    if not time_str: return None
    # 1. 统一把 Z 换成 +00:00
    clean_str = time_str.replace('Z', '+00:00')
    try:
        # 2. 尝试直接解析
        return datetime.datetime.fromisoformat(clean_str)
    except ValueError:
        # 3. 如果报错 (例如 .36+00:00 这种精度问题)
        # 直接截断小数点后的部分，保留到秒，强制加上 UTC 时区
        try:
            base_time = clean_str.split('.')[0] # 拿到 2026-01-24T04:09:26
            return datetime.datetime.fromisoformat(base_time + "+00:00")
        except Exception as e:
            print(f"❌ 时间格式解析严重错误: {time_str} -> {e}")
            return None

def check_vaults():
    # ====================================================
    # 任务 A: 检查活跃用户 (status = active)
    # ====================================================
    try:
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
        active_vaults = res.data
    except: active_vaults = []

    for row in active_vaults:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        
        # 使用新的解析函数
        last_time = parse_time(last_checkin)
        if not last_time: continue

        try:
            deadline = int(row.get('timeout_minutes') or 60)
            max_warns = int(row.get('max_warnings') or 3)
            interval = int(row.get('warning_interval') or 5)
            current_warns = int(row.get('current_warnings') or 0)
        except: continue
            
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        # 1. 预警 (唤醒)
        start_warn_time = deadline - (max_warns * interval)
        if start_warn_time < 0: start_warn_time = deadline - interval

        if diff >= start_warn_time and diff < deadline:
            expected_warns = int((diff - start_warn_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 发送唤醒 {user_id} ({current_warns}/{max_warns})")
                
                body = f"遗物系统检测到您已失联。\n距离遗言发出还剩 {mins_left} 分钟。\n请立即登录续期：{SITE_URL}"
                send_email(warn_email, f"🚨 唤醒警告 ({current_warns}/{max_warns})", body)
                
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1)

        # 2. 死亡判定 (发送提取码，状态转为 Triggered)
        if diff >= deadline:
            print(f"🔴 确认失联 {user_id} -> 发送提取码")
            
            relic_token = f"RELIC::{user_id}"
            
            ben_body = f"""
            【遗物 | 最终交付】

            您好。
            原持有者已确认失联。
            根据其失联前设定，系统已生成唯一的【遗物提取码】。

            ----------------------------------------
            提取码：
            {relic_token}
            ----------------------------------------

            【紧急注意】
            1. 此提取码有效期仅为 30分钟。
            2. 30分钟后，系统将执行物理销毁，此码将永久失效。
            3. 请立即前往官网：{SITE_URL}
            4. 必须使用本邮箱 ({ben_email}) 登录。
            5. 在底部“发掘”处粘贴提取码。

            (倒计时已开始...)
            """
            
            send_email(ben_email, "⏳ 【遗物】30分钟后销毁 - 请立即提取", ben_body)
            
            # 更新状态为 triggered
            supabase.table("vaults").update({
                "status": "triggered"
            }).eq("id", user_id).execute()

    # ====================================================
    # 任务 B: 检查已解锁用户 (status = unlocked) -> 30分钟后销毁
    # ====================================================
    try:
        res = supabase.table("vaults").select("*").eq("status", "unlocked").execute()
        unlocked_vaults = res.data
    except: unlocked_vaults = []

    for row in unlocked_vaults:
        user_id = row.get('id')
        unlock_time_str = row.get('last_checkin_at') 
        
        # 使用新的解析函数
        unlock_time = parse_time(unlock_time_str)
        if not unlock_time: continue

        now = datetime.datetime.now(datetime.timezone.utc)
        diff_mins = (now - unlock_time).total_seconds() / 60
        
        if diff_mins >= 30: 
            print(f"💀 阅后即焚时间到：删除 {user_id}")
            supabase.table("vaults").delete().eq("id", user_id).execute()
        else:
            print(f"⏳ {user_id} 正在阅读中: 剩余 {int(30 - diff_mins)} 分钟存活")

if __name__ == "__main__":
    print("🚀 遗物系统 V10.2 (时间格式修复版) 启动...")
    while True:
        check_vaults()
        print("💤 ...")
        time.sleep(60)
