import os
from supabase import create_client
import datetime
import smtplib
from email.mime.text import MIMEText

# 从 GitHub Secrets 读取配置
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

supabase = create_client(url, key)

def check_vaults():
    # 1. 从数据库获取所有保险箱记录
    res = supabase.table("vaults").select("*").execute()
    
    for row in res.data:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        # ⚠️ 关键修正：优先读取数据库里的 timeout_minutes，如果没有才默认 1440
        threshold = int(row.get('timeout_minutes', 1440))
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')
        current_warns = row.get('current_warnings', 0)
        max_warns = row.get('max_warnings', 3)
        status = row.get('status', 'active')

        if not last_checkin: continue

        # 2. 计算失联时间（分钟）
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        # 3. 打印实时日志（对应你截图里的输出）
        print(f"用户 {user_id} | 失联：{int(diff)}分钟 | 阈值：{threshold}分钟")

        # 4. 判定逻辑
        if diff > threshold and status == 'active':
            if current_warns < max_warns:
                # 触发预警邮件
                send_email(warn_email, "🚨 GhostProtocol 预警：检测到失联", f"您已超过 {threshold} 分钟未签到，请尽快登录控制台发送心跳。")
                # 更新警告次数
                supabase.table("vaults").update({"current_warnings": current_warns + 1}).eq("id", user_id).execute()
                print(f"⚠️ 已向预警邮箱发送通知 (第 {current_warns + 1} 次)")
            else:
                # 触发最终遗嘱
                content = row.get('encrypted_data', '无加密数据')
                send_email(ben_email, "🔒 GhostProtocol：数字遗产移交通知", f"由于所有者长期失联，以下是加密后的数字资产信息：\n\n{content}")
                # 标记为已触发
                supabase.table("vaults").update({"status": "triggered"}).eq("id", user_id).execute()
                print(f"🔴 已向受益人发送最终数据。")
        else:
            print("✅ 状态正常")

def send_email(to_email, subject, content):
    if not to_email: return
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email
        
        # 使用 QQ 邮箱服务器
        with smtplib.SMTP_SSL("smtp.qq.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    print("🚀 GhostProtocol V2.0 扫描开始...")
    check_vaults()
