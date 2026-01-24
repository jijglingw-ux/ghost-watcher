import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# --- 配置区 (从环境变量读取) ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

# 初始化 Supabase (必须使用 service_role key 以便注销用户)
supabase = create_client(url, key)

# 网站地址
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
        print(f"❌ 邮件发送失败: {e}")

def parse_time(time_str):
    if not time_str: return None
    clean_str = time_str.replace('Z', '+00:00')
    try:
        return datetime.datetime.fromisoformat(clean_str)
    except ValueError:
        try:
            # 处理部分数据库返回的特殊精度格式
            return datetime.datetime.fromisoformat(clean_str.split('.')[0] + "+00:00")
        except: return None

def check_vaults():
    # ----------------------------------------------------
    # 任务 1: 监测活跃者 (status = active)
    # ----------------------------------------------------
    try:
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
        
        # A. 唤醒提醒阶段
        start_warn_time = deadline - (max_warns * interval)
        if diff >= start_warn_time and diff < deadline:
            expected_warns = int((diff - start_warn_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 正在唤醒用户 {user_id} ({current_warns}/{max_warns})")
                
                body = f"遗物系统检测到您已失联。\n遗言将于约 {mins_left} 分钟后正式发出。\n若您平安，请立即登录：{SITE_URL}"
                send_email(warn_email, f"🚨 最终唤醒通知 ({current_warns}/{max_warns})", body)
                
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1)

        # B. 确认失联 -> 执行移交并“斩杀”原账号
        if diff >= deadline:
            print(f"🔴 用户 {user_id} 确认失联。正在移交遗物...")
            
            # 生成受益人专用提取码
            relic_token = f"RELIC::{user_id}"
            
            # 准备给受益人的邮件 (强调身份锁死解密)
            ben_body = f"""
            【遗物 | 数字资产交接】

            您好。
            原持有者已确认失联。根据其失联前的设定，现将托管的加密遗言移交给您。

            ----------------------------------------
            遗物提取码：
            {relic_token}
            ----------------------------------------

            【解密必读：如何提取？】
            1. 访问官网：{SITE_URL}
            2. 【关键】请务必使用本接收邮箱 ({ben_email}) 进行注册或登录。
               （警告：由于身份锁死技术，使用其他邮箱登录将无法解密密文）
            3. 登录后，在底部“发掘”区域粘贴上方的提取码。
            4. 点击“提取并解读”，真相将自动显现。

            【阅后即焚说明】
            解密成功后，系统将开启30分钟倒计时，随后数据将永久物理销毁。
            """
            
            send_email(ben_email, "🔒 【遗物】待提取通知（身份锁死加密）", ben_body)
            
            # 逻辑斩杀：状态设为 pending，原主人将无法再次登录查看
            supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq("id", user_id).execute()

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
            # (可选) 同时注销 Auth 账号，彻底清理痕迹
            try:
                supabase.auth.admin.delete_user(user_id)
            except: pass

if __name__ == "__main__":
    print("🚀 遗物监测系统 V11.2 (受益人解密增强版) 启动...")
    while True:
        check_vaults()
        time.sleep(60)
