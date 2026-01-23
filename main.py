import os
from supabase import create_client
import datetime
import smtplib
from email.mime.text import MIMEText

# 环境配置
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

supabase = create_client(url, key)

def check_vaults():
    res = supabase.table("vaults").select("*").execute()
    
    for row in res.data:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        # V3 核心参数读取
        timeout = int(row.get('timeout_minutes', 60))
        max_warns = int(row.get('max_warnings', 2))
        interval = int(row.get('warning_interval', 10))
        
        current_warns = row.get('current_warnings', 0)
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')
        status = row.get('status', 'active')

        if not last_checkin or status != 'active': continue

        # 计算失联总时间
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        total_diff = (now - last_time).total_seconds() / 60
        
        print(f"用户 {user_id} | 总失联：{int(total_diff)}分 | 初始阈值：{timeout}分 | 阶梯间隔：{interval}分")

        # --- V3 阶梯判定逻辑 ---
        # 1. 判定是否已经超过初始阈值
        if total_diff > timeout:
            # 计算理论上应该处于第几次唤醒 (公式：超过阈值后的时长 / 间隔时间)
            expected_warns = int((total_diff - timeout) / interval) + 1
            
            # 限制最高警告次数，不能超过用户设定的 max_warns
            if expected_warns > max_warns:
                expected_warns = max_warns

            # 2. 如果当前警告次数落后于理论次数，则触发补发邮件
            if current_warns < expected_warns:
                send_email(warn_email, f"🚨 唤醒提醒 ({expected_warns}/{max_warns})", 
                           f"您已超过 {timeout} 分钟未打卡。这是第 {expected_warns} 次提醒，请尽快登录心跳。")
                
                # 更新数据库中的警告计数
                supabase.table("vaults").update({"current_warnings": expected_warns}).eq("id", user_id).execute()
                print(f"⚠️ 已发送第 {expected_warns} 次唤醒邮件")

            # 3. 终极判定：当警告次数已满，且时间超过了最后一次宽限期
            # 判定公式：总失联时间 > 初始阈值 + (最大次数 * 间隔时间)
            final_deadline = timeout + (max_warns * interval)
            if total_diff > final_deadline and current_warnings >= max_warns:
                print(f"🔴 确认死亡：失联 {int(total_diff)} 分钟已超过极限 ({final_deadline}分)")
                content = row.get('encrypted_data', '无加密数据')
                send_email(ben_email, "🔒 数字遗产移交", f"所有者确认长期失联，以下是托付数据：\n\n{content}")
                # 封印保险箱
                supabase.table("vaults").update({"status": "triggered"}).eq("id", user_id).execute()
        else:
            print("✅ 状态正常：仍在初始宽限期内")

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
    except Exception as e: print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    print("🚀 GhostProtocol V3.0 巡逻中...")
    check_vaults()
