import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# --- 配置区 (自动读取环境变量) ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

# 初始化 Supabase
supabase = create_client(url, key)

# 你的网站地址
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
        print(f"✅ 邮件已发送给: {to_email}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

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
    # ----------------------------------------------------
    # 任务 1: 监测活跃者 (status = active)
    # ----------------------------------------------------
    try:
        # 获取所有活跃用户
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
        active_vaults = res.data
    except Exception as e:
        print(f"数据库读取失败: {e}")
        active_vaults = []

    for row in active_vaults:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        last_time = parse_time(last_checkin)
        if not last_time: continue

        deadline = int(row.get('timeout_minutes') or 60)
        max_warns = int(row.get('max_warnings') or 3)
        interval = int(row.get('warning_interval') or 5)
        current_warns = int(row.get('current_warnings') or 0)
            
        # warning_email 通常是用户自己的邮箱（账号持有者）
        # beneficiary_email 是受益人的邮箱
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        # === A. 唤醒提醒阶段 (发给账号持有者本人) ===
        start_warn_time = deadline - (max_warns * interval)
        if start_warn_time < 0: start_warn_time = deadline - interval

        if diff >= start_warn_time and diff < deadline:
            expected_warns = int((diff - start_warn_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            while current_warns < expected_warns:
                target_warn_level = current_warns + 1
                
                # 【乐观锁】防止重复发送唤醒邮件
                update_res = supabase.table("vaults").update({
                    "current_warnings": target_warn_level
                }).eq("id", user_id).eq("current_warnings", current_warns).execute()

                if update_res.data and len(update_res.data) > 0:
                    mins_left = int(deadline - diff)
                    print(f"⚠️ [唤醒] 正在呼叫持有者 {user_id} (第 {target_warn_level} 次)")
                    
                    body = f"【警告】检测到您 ({warn_email}) 已失联。\n遗言将于约 {mins_left} 分钟后发给受益人。\n若您平安，请立即登录续期：{SITE_URL}"
                    send_email(warn_email, f"🚨 最终唤醒通知 ({target_warn_level}/{max_warns})", body)
                    
                    current_warns = target_warn_level 
                    time.sleep(1) 
                else:
                    current_warns = target_warn_level 
                    break 

        # === B. 确认失联 -> 执行移交 (发给受益人) ===
        if diff >= deadline:
            # 尝试将状态从 active 改为 pending
            lock_res = supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq("id", user_id).eq("status", "active").execute()

            # 只有抢到锁的进程，才发送最终遗物邮件
            if lock_res.data and len(lock_res.data) > 0:
                # owner_identity 这里指代“原账号持有者”，通常就是 warning_email
                owner_identity = row.get('warning_email', '未知用户')
                relic_token = f"RELIC::{user_id}"
                
                print(f"🔴 [移交] 用户 {owner_identity} 确认失联。正在发送给受益人 {ben_email}...")
                
                ben_subject = f"⏳ 【遗物交付】来自 [{owner_identity}] 的加密嘱托"
                ben_body = f"""
您好，

这是一封由【遗物 | Ghost Watcher】系统自动发出的通知。

系统监测显示，本平台注册用户（账号持有者）：
【 {owner_identity} 】
已超过预设时限未与系统进行任何交互，现已判定为“确认失联”状态。

根据该持有者生前的设定，您 ({ben_email}) 是其指定的唯一遗物受益人。

--------------------------------
🔑 您的专属提取码：
{relic_token}
--------------------------------

【如何接收遗物？】
请注意：您需要使用“您的身份”来提取这份遗物，而不是持有者的身份。

1. 访问数字墓碑官网：
   {SITE_URL}

2. 身份验证（注册/登录）：
   请使用您收到这封邮件的邮箱（即：{ben_email}）在网站上进行【注册或登录】。
   *系统已将解密权限绑定至您的邮箱，使用其他账号将无法通过验证。*

3. 提取：
   登录后，在页面底部的“发掘”输入框中，粘贴上方的提取码，点击“提取并解读”。

【⚠️ 阅后即焚警告】
为了保护持有者的隐私，遗物内容设定为绝对销毁模式。
一旦您解密成功，系统将启动 30分钟倒计时。倒计时结束后，数据将永久物理粉碎。

请在确保环境安全的情况下开启。

此致，

遗物守望者 (Ghost Watcher)
"""
                send_email(ben_email, ben_subject, ben_body)
            else:
                 print(f"🔒 [并发保护] 遗物移交程序已被其他进程启动，跳过。")


    # ----------------------------------------------------
    # 任务 2: 监测已开启的“阅后即焚” (status = reading)
    # ----------------------------------------------------
    try:
        res = supabase.table("vaults").select("*").eq("status", "reading").execute()
        reading_vaults = res.data
    except: reading_vaults = []

    for row in reading_vaults:
        user_id = row.get('id')
        unlock_time = parse_time(row.get('last_checkin_at'))
        if not unlock_time: continue

        now = datetime.datetime.now(datetime.timezone.utc)
        diff_mins = (now - unlock_time).total_seconds() / 60
        
        if diff_mins >= 30: 
            print(f"💀 自毁时间到：彻底删除记录 {user_id}")
            # 物理删除数据库记录
            supabase.table("vaults").delete().eq("id", user_id).execute()
            # 尝试注销 Auth 账号，彻底清理痕迹
            try:
                supabase.auth.admin.delete_user(user_id)
            except: pass

if __name__ == "__main__":
    print("🚀 遗物监测系统 V12.4 (逻辑修正版) 启动...")
    while True:
        check_vaults()
        time.sleep(60)
