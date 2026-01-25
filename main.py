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
                    
                    # --- 文案更新：中性化的托管提醒 ---
                    body = f"""
【遗物 | Relic】托管状态通知

用户 ID: {warn_email}
系统检测到您的账号已长时间未登录。

根据您设定的托管协议，若您继续未进行任何操作，系统将在约 {mins_left} 分钟后，
自动将您托管的加密信物移交给指定的接收人。

------------------------------------
如果您只是忘记了登录，请点击下方链接重置时间：
------------------------------------

>>> 点击此处登录以保持持有权：
{SITE_URL}

（此为系统自动发送，若不操作将执行自动移交程序）
"""
                    send_email(warn_email, f"⏰ [待办] 您的托管数据即将移交 (剩余 {mins_left} 分钟)", body)
                    
                    current_warns = target_warn_level 
                    time.sleep(1) 
                else:
                    current_warns = target_warn_level 
                    break 

        # === B. 确认失联 -> 执行移交 (发给受益人) ===
        if diff >= deadline:
            # 尝试将状态从 active 改为 pending (移交中)
            lock_res = supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq("id", user_id).eq("status", "active").execute()

            # 只有抢到锁的进程，才发送最终邮件
            if lock_res.data and len(lock_res.data) > 0:
                print(f"🔴 [移交] 用户 {user_id} 确认失联。正在查询注册信息...")
                
                relic_token = f"RELIC::{user_id}"
                
                # --- 查询真实的注册邮箱 (作为发件人身份) ---
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
                
                # --- 文案更新：礼貌、清晰的信件转交 ---
                ben_subject = f"【遗物】您收到一份来自 [{owner_identity}] 的加密信物"
                ben_body = f"""
您好。

这是一封来自【遗物 | Relic】托管系统的自动通知。

您的朋友（或关联人）：
【 {owner_identity} 】
此前在我们的系统中托管了一份加密数据，并设定了自动交付规则。

由于该账号已长期未进行操作，根据协议，系统现将这份数据的提取权限移交给您。
**您已被指定为唯一的接收人。**

这份数据的内容已加密，只有您可以解开。

=========================================
您的专属提取码 (Access Key)：
{relic_token}
=========================================

【如何提取？】
请按照以下步骤操作：

1. 访问系统终端：
   {SITE_URL}

2. 验证身份：
   您必须使用【收到这封信的邮箱地址】在网站上注册并登录。
   (系统已绑定您的邮箱为唯一解密钥匙)

3. 提取信物：
   登录后，在页面底部的“发掘/解密”框中，粘贴上面的提取码。

-----------------------------------------
⚠️ 阅后即焚提示：
为了保护隐私，该信物设定了最高级别的安全策略。
解密成功后，内容将在 30分钟后 自动销毁。
请在方便的时候开启。
-----------------------------------------

此致，

遗物 (Relic)
—— 值得托付的数字信箱
"""
                send_email(ben_email, ben_subject, ben_body)
            else:
                 print(f"🔒 [并发保护] 移交程序已被其他进程启动，跳过。")


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
            print(f"💀 销毁时间到：彻底删除记录 {user_id}")
            # 物理删除数据库记录
            supabase.table("vaults").delete().eq("id", user_id).execute()
            # 尝试注销 Auth 账号，彻底清理痕迹
            try:
                supabase.auth.admin.delete_user(user_id)
            except: pass

if __name__ == "__main__":
    print("🚀 [Relic Backend] 托管巡查任务启动...")
    while True:
        check_vaults()
        time.sleep(60)
