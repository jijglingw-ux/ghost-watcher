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
# 注意：必须使用 service_role key 才能有权限查询 auth.users
supabase = create_client(url, key)

# 你的网站地址 (如果有变动，请修改这里)
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
                
                # 【乐观锁】防止重复发送
                update_res = supabase.table("vaults").update({
                    "current_warnings": target_warn_level
                }).eq("id", user_id).eq("current_warnings", current_warns).execute()

                if update_res.data and len(update_res.data) > 0:
                    mins_left = int(deadline - diff)
                    print(f"⚠️ [唤醒] 正在呼叫持有者 {user_id} (第 {target_warn_level} 次)")
                    
                    # --- 唤醒邮件文案 (已更新为 Relic 风格) ---
                    body = f"""
【一级状态警报】遗物托管协议即将触发

用户 ID: {warn_email}
检测到您的数字活跃度已消失。

根据预设协议，系统将在约 {mins_left} 分钟后，认定您已“离线”。
届时，您托管的加密信物将自动发送给指定的受益人。

------------------------------------
如果您还活着，请立即终止此程序！
------------------------------------

>>> 点击此处续命/重置倒计时：
{SITE_URL}

（此为系统自动发送，若不操作将执行盲交付程序）
"""
                    send_email(warn_email, f"🚨 [最终唤醒] 离线倒计时: {mins_left}分钟", body)
                    
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
                print(f"🔴 [移交] 用户 {user_id} 确认失联。正在查询注册信息...")
                
                relic_token = f"RELIC::{user_id}"
                
                # --- 查询注册邮箱 (Auth Email) ---
                owner_identity = "未知用户"
                try:
                    user_data = supabase.auth.admin.get_user_by_id(user_id)
                    if user_data and user_data.user and user_data.user.email:
                        owner_identity = user_data.user.email
                        print(f"✅ 已获取真实注册身份: {owner_identity}")
                    else:
                        owner_identity = row.get('warning_email', '未知用户')
                except Exception as e:
                    print(f"⚠️ 获取注册信息失败: {e}，将使用备用邮箱身份。")
                    owner_identity = row.get('warning_email', '未知用户')

                print(f"📧 正在发送给受益人 {ben_email}...")
                
                # --- 最终交付邮件文案 (已更新为 Relic 风格) ---
                ben_subject = f"【重要】来自 [{owner_identity}] 的数字信物交付 (Relic Protocol)"
                ben_body = f"""
{ben_email}，您好。

这是一份迟到的、但至关重要的托付。
请不要惊慌，也不要删除这封邮件。

您收到这封信，是因为您的朋友/亲人：
【 {owner_identity} 】
生前（或失联前）在“遗物 (Relic)”分布式托管系统中设定了自动执行协议。

系统监测显示，该账号已长期处于“离线”状态。根据委托人预设的《数字信物盲交付规则》，系统已自动触发最终指令：
**您被指定为这份加密信物的唯一继承人。**

委托人为您留下了一段私密信息（可能包含资产密钥、真相、或未公开的嘱托）。
为了确保隐私，该内容在服务器端已加密，只有您手中的钥匙能解开。

=========================================
您的专属提取码 (Access Token)：
{relic_token}
=========================================

【如何提取信物？】
请务必严格按照以下步骤操作，否则无法解密：

1. 访问官方终端：
   {SITE_URL}

2. 验证身份（关键）：
   您必须使用【收到这封信的邮箱地址】在网站上注册并登录。
   (系统锁定了收信人身份，使用其他邮箱登录将无法解密)

3. 提取信物：
   登录后，在页面底部的“发掘/解密”框中，完整粘贴上面的提取码。

-----------------------------------------
⚠️ 阅后即焚警告 (Self-Destruct Protocol)：
为了绝对保护委托人的隐私，本信物设定了最高级别的销毁策略。
一旦您解密成功，30分钟倒计时将立即启动。
倒计时结束后，系统将执行物理粉碎，永久删除该信物的所有数据。
请在确保环境安全、情绪平稳的情况下开启。
-----------------------------------------

此致，

遗物 (Relic)
—— 未被遗忘的，即为永恒
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
    print("🚀 [GitHub Action] 遗物 (Relic) 巡查任务开始...")
    
    # 执行一次检查
    check_vaults()
    
    print("✅ 巡查结束。脚本自动退出。")
