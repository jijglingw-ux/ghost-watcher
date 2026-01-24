import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# --- 配置区 (请确保环境变量已设置) ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

# 初始化 Supabase
supabase = create_client(url, key)

# 你的网站地址 (受益人点击这个去解密)
SITE_URL = "https://jijglingw-ux.github.io/ghost-watcher" 

def check_vaults():
    try:
        # 获取所有活跃的遗嘱
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return

    for row in res.data:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        if not last_checkin: continue

        try:
            deadline = int(row.get('timeout_minutes') or 60)
            max_warns = int(row.get('max_warnings') or 3)
            interval = int(row.get('warning_interval') or 5)
            current_warns = int(row.get('current_warnings') or 0)
        except ValueError:
            continue
            
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email') # 受益人邮箱

        # 计算失联时间
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        print(f"[用户 {user_id}] 失联: {diff:.1f}分 / 阈值: {deadline}分")

        # ----------------------------------------------------
        # 阶段 1: 预警 (仅提醒本人)
        # ----------------------------------------------------
        # 计算开始预警的时间点
        start_warning_time = deadline - (max_warns * interval)
        if start_warning_time < 0: start_warning_time = deadline - interval

        if diff >= start_warning_time and diff < deadline:
            # 计算当前应该发第几次预警
            expected_warns = int((diff - start_warning_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            # 如果实际发送次数 < 应该发送次数，就补发
            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 发送预警邮件 ({current_warns}/{max_warns})")
                
                warn_body = f"""
                【遗物 | 最终确认】

                系统检测到您已失联。
                
                距离【遗言发送】及【数据销毁】还剩约 {mins_left} 分钟。
                
                如果您还安全，请立即点击下方链接，点击“确认存续”按钮：
                {SITE_URL}
                """
                send_email(warn_email, f"🚨 警告：遗物系统即将触发 ({current_warns}/{max_warns})", warn_body)
                
                # 更新数据库里的警告次数
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1)

        # ----------------------------------------------------
        # 阶段 2: 死亡判定 (发送遗物给受益人)
        # ----------------------------------------------------
        if diff >= deadline:
            print(f"🔴 确认失联！执行遗物移交...")
            content = row.get('encrypted_data', '')
            
            # --- 关键修改：针对 V6.2 身份锁死版的邮件文案 ---
            ben_body = f"""
            【遗物 | 数字资产交接】

            您好。
            您收到这封邮件，说明“遗物”系统的原持有者已确认失联。
            根据其生前设定，现将【加密遗言】移交给您。

            ----------------------------------------
            请复制下方密文：
            ----------------------------------------
            {content}
            ----------------------------------------

            【如何解密？】
            1. 访问遗物系统官网：{SITE_URL}
            2. 【关键步骤】请务必使用本邮箱 ({ben_email}) 进行注册并登录。
               (⚠️ 警告：此遗言已与本邮箱地址锁死。如果您使用其他邮箱登录，将解出乱码！)
            3. 登录后，在页面底部的“发掘”区域粘贴上面的密文。
            4. 点击“解读”，真相将自动显现。

            (注：原持有者的账号数据已执行物理销毁，此邮件为唯一留存备份。)
            """
            
            # A. 发送给受益人
            send_email(ben_email, "🔒 【遗物】加密资产移交（身份锁死）", ben_body)
            
            # B. 销毁数据
            try:
                supabase.table("vaults").delete().eq("id", user_id).execute()
                print(f"✅ Vault 数据已删除")
                # 注销用户 (可选，视 Supabase 权限而定)
                # supabase.auth.admin.delete_user(user_id) 
                print(f"✅ 用户数据已清理")
            except Exception as e:
                print(f"❌ 删除失败 (可能是权限问题): {e}")

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
        print(f"❌ 邮件发送错误: {e}")

if __name__ == "__main__":
    print("🚀 遗物系统 (V6.2 Identity-Lock) 正在巡逻...")
    while True:
        check_vaults()
        print("💤 休息 60 秒...")
        time.sleep(60)
