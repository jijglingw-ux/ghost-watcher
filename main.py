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
        if not last_checkin: continue

        try:
            deadline = int(row.get('timeout_minutes') or 60)
            max_warns = int(row.get('max_warnings') or 3)
            interval = int(row.get('warning_interval') or 5)
            current_warns = int(row.get('current_warnings') or 0)
        except: continue
            
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
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
            
            # --- 邮件文案更新：强调解密后才销毁 ---
            ben_body = f"""
            【遗物 | 最终交付】

            您好。
            原持有者已确认失联。
            根据其失联前设定，系统已生成唯一的【遗物提取码】。

            ----------------------------------------
            提取码：
            {relic_token}
            ----------------------------------------

            【重要提示】
            1. 此提取码目前永久有效，您可以随时提取。
            2. 【警告】一旦您在网站上输入提取码并成功“提取并解读”，系统将启动【30分钟自毁程序】。
            3. 解密 30分钟后，数据将执行物理销毁，再次输入提取码将无效。

            请在准备好阅读真相时，访问：{SITE_URL}
            (务必使用本邮箱 {ben_email} 登录)
            """
            
            send_email(ben_email, "🔒 【遗物】资产移交 - 解密后即刻销毁", ben_body)
            
            # 状态设为 triggered (等待受益人操作)，不更新时间，不删除
            supabase.table("vaults").update({
                "status": "triggered"
            }).eq("id", user_id).execute()

    # ====================================================
    # 任务 B: 检查已解锁用户 (status = unlocked) -> 30分钟后销毁
    # ====================================================
    try:
        # 只检查那些已经被受益人打开过的遗物
        res = supabase.table("vaults").select("*").eq("status", "unlocked").execute()
        unlocked_vaults = res.data
    except: unlocked_vaults = []

    for row in unlocked_vaults:
        user_id = row.get('id')
        unlock_time_str = row.get('last_checkin_at') # 这里的 last_checkin_at 记录的是“解锁时间”
        
        if unlock_time_str:
            unlock_time = datetime.datetime.fromisoformat(unlock_time_str.replace('Z', '+00:00'))
            now = datetime.datetime.now(datetime.timezone.utc)
            diff_mins = (now - unlock_time).total_seconds() / 60
            
            if diff_mins >= 30: # 解锁超过30分钟，删！
                print(f"💀 阅后即焚时间到：删除 {user_id}")
                supabase.table("vaults").delete().eq("id", user_id).execute()
            else:
                print(f"⏳ {user_id} 正在阅读中: 剩余 {int(30 - diff_mins)} 分钟存活")

if __name__ == "__main__":
    print("🚀 遗物系统 V10.0 (阅后即焚版) 启动...")
    while True:
        check_vaults()
        print("💤 ...")
        time.sleep(60)
