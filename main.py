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

# 强壮的时间解析
def parse_time(time_str):
    if not time_str: return None
    clean_str = time_str.replace('Z', '+00:00')
    try:
        return datetime.datetime.fromisoformat(clean_str)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(clean_str.split('.')[0] + "+00:00")
        except: return None

def check_vaults():
    # ====================================================
    # 任务 A: 监测活人 (status = active)
    # ====================================================
    try:
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
        active_vaults = res.data
    except: active_vaults = []

    for row in active_vaults:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
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
        
        # 1. 唤醒阶段
        start_warn_time = deadline - (max_warns * interval)
        if start_warn_time < 0: start_warn_time = deadline - interval

        if diff >= start_warn_time and diff < deadline:
            expected_warns = int((diff - start_warn_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 唤醒 {user_id} ({current_warns}/{max_warns})")
                body = f"检测到失联迹象。\n遗言将于 {mins_left} 分钟后发出。\n请立即登录续期：{SITE_URL}"
                send_email(warn_email, f"🚨 唤醒警告 ({current_warns}/{max_warns})", body)
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1)

        # 2. 确认失联 -> 移入“数字灵柩” (Status: pending)
        if diff >= deadline:
            print(f"🔴 用户 {user_id} 失联 -> 账号停用，等待提取")
            
            relic_token = f"RELIC::{user_id}"
            
            ben_body = f"""
            【遗物 | 提取通知】

            您好。
            原持有者已确认失联。
            根据设定，其留下的加密遗言已进入【待提取】状态。

            ----------------------------------------
            提取码：
            {relic_token}
            ----------------------------------------

            【阅后即焚机制说明】
            1. 数据目前安全保存在“数字灵柩”中，无时间限制。
            2. 当您在网站输入提取码并【解密成功】的瞬间，将触发自毁程序。
            3. 解密后 30分钟，数据将永久物理销毁。

            请在准备好后，访问官网提取：
            {SITE_URL}
            (请使用本邮箱 {ben_email} 作为身份验证)
            """
            
            send_email(ben_email, "🔒 【遗物】待提取 - 包含阅后即焚数据", ben_body)
            
            # 关键：状态改为 pending，停止一切活动监测，静默等待
            supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": datetime.datetime.now(datetime.timezone.utc).isoformat() # 记录死亡时间
            }).eq("id", user_id).execute()

    # ====================================================
    # 任务 B: 监测“正在阅读”的遗物 (status = reading)
    # ====================================================
    try:
        # 只有受益人点击了解密，状态才会变成 reading
        res = supabase.table("vaults").select("*").eq("status", "reading").execute()
        reading_vaults = res.data
    except: reading_vaults = []

    for row in reading_vaults:
        user_id = row.get('id')
        start_read_time_str = row.get('last_checkin_at') # 这里记录的是“开始阅读时间”
        
        start_read_time = parse_time(start_read_time_str)
        if not start_read_time: continue

        now = datetime.datetime.now(datetime.timezone.utc)
        diff_mins = (now - start_read_time).total_seconds() / 60
        
        if diff_mins >= 30: 
            print(f"💀 阅读时间结束 ({diff_mins:.1f}m)：物理销毁 {user_id}")
            supabase.table("vaults").delete().eq("id", user_id).execute()
        else:
            print(f"⏳ {user_id} 正在阅读中: 剩余 {int(30 - diff_mins)} 分钟")

if __name__ == "__main__":
    print("🚀 遗物系统 V11.0 (阅后即焚终极版) 启动...")
    while True:
        check_vaults()
        print("💤 ...")
        time.sleep(60)
