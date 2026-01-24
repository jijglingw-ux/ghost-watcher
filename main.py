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
            
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        # === A. 唤醒提醒阶段 (并发安全版) ===
        start_warn_time = deadline - (max_warns * interval)
        if start_warn_time < 0: start_warn_time = deadline - interval

        # 如果时间到了警告区间，且还没到最终死线
        if diff >= start_warn_time and diff < deadline:
            expected_warns = int((diff - start_warn_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            # 循环补发每一个漏掉的警告
            while current_warns < expected_warns:
                target_warn_level = current_warns + 1
                
                # 【乐观锁】尝试更新数据库
                update_res = supabase.table("vaults").update({
                    "current_warnings": target_warn_level
                }).eq("id", user_id).eq("current_warnings", current_warns).execute()

                if update_res.data and len(update_res.data) > 0:
                    # --- 抢锁成功，发送邮件 ---
                    mins_left = int(deadline - diff)
                    print(f"⚠️ [锁定成功] 正在唤醒用户 {user_id} (第 {target_warn_level} 次)")
                    
                    body = f"遗物系统检测到您已失联。\n遗言将于约 {mins_left} 分钟后正式发出。\n若您平安，请立即登录续期：{SITE_URL}"
                    send_email(warn_email, f"🚨 唤醒警告 ({target_warn_level}/{max_warns})", body)
                    
                    current_warns = target_warn_level 
                    time.sleep(1) 
                else:
                    # --- 抢锁失败 ---
                    print(f"🔒 [并发保护] 警告 ({target_warn_level}/{max_warns}) 已被其他进程处理，跳过。")
                    current_warns = target_warn_level 
                    break 

        # === B. 确认失联 -> 执行移交 (并发安全版) ===
        if diff >= deadline:
            # 尝试将状态从 active 改为 pending
            lock_res = supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq("id", user_id).eq("status", "active").execute()

            # 只有抢到状态更新锁的进程，才发遗书
            if lock_res.data and len(lock_res.data) > 0:
                print(f"🔴 [锁定成功] 用户 {user_id} 确认失联。正在移交遗物...")
                
                relic_token = f"RELIC::{user_id}"
                owner_identity = row.get('warning_email', '未知用户')
                
                # --- 新版详细邮件文案 ---
                ben_subject = f"⏳ 【遗物交付】来自 [{owner_identity}] 的最终留言（请在独处时开启）"
                ben_body = f"""
您好，

这是一封由【遗物 | Ghost Watcher】数字墓碑系统自动发出的特殊邮件。

收到这封邮件，意味着该账号的持有者 [{owner_identity}] 已经超过了预设的时限没有与系统进行任何交互（登录或续期）。
根据其生前/失联前签署的《数字资产托管协议》，系统判定其处于“确认失联”状态。

他/她在生前为您留下了一份加密的遗言（或重要信息），并指定您为唯一的接收人。

--------------------------------
🔑 您的专属提取码：
{relic_token}
--------------------------------

【📖 如何读取遗言？】
由于信息的私密性，您无法直接在邮件中查看。请严格按照以下步骤操作：

第一步：访问数字墓碑
点击链接进入系统：{SITE_URL}

第二步：身份验证（非常重要！）
您必须使用收到这封邮件的邮箱地址 ({ben_email}) 在网站上点击“注册（新建档案）”或直接登录。
*⚠️ 注意：系统已锁死此邮箱为唯一钥匙。使用其他邮箱账号登录将无法解密。*

第三步：发掘
登录后，滚动到页面底部的“发掘”区域，将上方的提取码粘贴进去，点击“提取并解读”。

【🚨 阅后即焚警告（请务必阅读）】
为了保护逝者的隐私，该遗言被设定为绝对销毁模式。

1. 一旦您点击“提取并解读”且解密成功，系统将立即启动 30分钟倒计时。
2. 倒计时结束后，数据将从服务器进行物理粉碎，永久消失，无法恢复。
3. 建议：请确保您现在处于安全、私密且时间充足的环境下，再进行提取操作。

此致，

遗物守望者 (Ghost Watcher)
我们守护未被遗忘的声音。
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
    print("🚀 遗物监测系统 V12.3 (详细指引版) 启动...")
    while True:
        check_vaults()
        time.sleep(60)
