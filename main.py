import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# === 从 Secrets 获取钥匙 ===
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
SMTP_SERVER = 'smtp.qq.com'
SMTP_PORT = 465

def send_email(to_email, subject, body):
    """通用邮件发送函数"""
    if not to_email:
        print("❌ 目标邮箱为空，跳过发送")
        return False
    
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        server.quit()
        print(f"✅ 邮件已发送至: {to_email}")
        return True
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        return False

def run_check():
    print("🛰️ GhostProtocol V2.0 扫描开始...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # 获取所有没“死透”的用户
        response = supabase.table('vaults').select("*").neq('status', 'triggered').execute()
        vaults = response.data
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    if not vaults:
        print("📭 当前没有活跃的监控任务。")
        return

    for vault in vaults:
        # 计算失联时间
        last_checkin = datetime.fromisoformat(vault['last_checkin_at'].replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        minutes_passed = (now - last_checkin).total_seconds() / 60
        
        # 获取用户设定的阈值 (没设则默认 1440 分钟)
        timeout = vault.get('timeout_minutes') or 1440
        
        print(f"用户 {vault['id']} | 失联: {int(minutes_passed)}分钟 | 阈值: {timeout}分钟")

        # 判断是否超时
        if minutes_passed > timeout:
            current_warns = vault.get('current_warnings', 0)
            max_warns = vault.get('max_warnings', 3)
            
            # === 分支 A: 发警告 ===
            if current_warns < max_warns:
                print(f"⚠️ 触发第 {current_warns + 1} 次警告...")
                subject = f"【红色警报】请立即签到 ({current_warns + 1}/{max_warns})"
                body = f"""
                警告！系统检测到心跳丢失。
                
                这是第 {current_warns + 1} 次提醒。
                如果你还活着，请立即访问终端点击“发送心跳”。
                
                如果达到 {max_warns} 次警告仍无反应，系统将判定为死亡并发送遗嘱。
                """
                if send_email(vault['warning_email'], subject, body):
                    # 计数 +1
                    supabase.table('vaults').update({
                        'current_warnings': current_warns + 1,
                        'status': 'warning'
                    }).eq('id', vault['id']).execute()

            # === 分支 B: 发遗嘱 ===
            else:
                print("💀 次数耗尽，确认死亡。执行最终协议...")
                subject = "【GHOST PROTOCOL】数字遗嘱交付通知"
                body = f"""
                系统已确认宿主离线（超过最大预警次数）。
                根据预设协议，现交付托管数据。
                
                [ 解密数据 ]:
                ----------------------------
                {vault['encrypted_data']}
                ----------------------------
                
                此流程已自动销毁。
                """
                if send_email(vault['beneficiary_email'], subject, body):
                    # 状态设为 triggered，彻底结束
                    supabase.table('vaults').update({'status': 'triggered'}).eq('id', vault['id']).execute()
                    print("✅ 遗嘱已发送，流程已销毁。")
        else:
            print("✅ 状态正常")

if __name__ == "__main__":
    run_check()
