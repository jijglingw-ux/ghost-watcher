import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

supabase = create_client(url, key)

def check_vaults():
    # 获取所有活跃用户
    try:
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return

    for row in res.data:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        if not last_checkin: continue

        # --- 修复核心：更强壮的数据读取 ---
        # 如果数据库里是 NULL (None)，就强制用默认值 (or 后面那个数)
        try:
            deadline = int(row.get('timeout_minutes') or 10)
            max_warns = int(row.get('max_warnings') or 2)
            interval = int(row.get('warning_interval') or 1)
            current_warns = int(row.get('current_warnings') or 0)
        except ValueError:
            print(f"用户 {user_id} 数据格式错误，跳过")
            continue
            
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        # 计算时间
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        print(f"\n[用户 {user_id}] 失联: {diff:.1f}分 / 设定: {deadline}分")

        # 1. 唤醒逻辑
        start_warning_time = deadline - (max_warns * interval)
        
        # 逻辑保护：如果计算出的开始时间比死线还晚（参数逻辑错误），就修正为死线前一刻
        if start_warning_time >= deadline: 
            start_warning_time = deadline - interval

        if diff >= start_warning_time and diff < deadline:
            expected_warns = int((diff - start_warning_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 发送预警 ({current_warns}/{max_warns})")
                send_email(warn_email, f"🚨 GhostProtocol 临终唤醒 ({current_warns}/{max_warns})", 
                           f"您已失联 {int(diff)} 分钟，距离数据移交并销毁还剩约 {mins_left} 分钟！")
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1)

        # 2. 死亡判定 & 销毁
        if diff >= deadline:
            print(f"🔴 确认死亡！正在执行数据移交与销毁程序...")
            content = row.get('encrypted_data', '')
            
            # 发送遗嘱
            send_email(ben_email, 
                       "🔒 GhostProtocol: 数字遗产移交", 
                       f"系统确认所有者已失联（超 {deadline} 分钟）。\n\n这是其托付的最后数据：\n\n{content}\n\n【系统提示】邮件发送完毕，该用户的所有云端数据已被永久擦除。")
            
            # 物理删除数据
            supabase.table("vaults").delete().eq("id", user_id).execute()
            print(f"✅ 用户数据已从数据库永久删除。")

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

if __name__ == "__main__":
    print("🚀 GhostProtocol V4.9 巡逻引擎启动...")
    check_vaults()
