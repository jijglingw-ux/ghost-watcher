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

# 注意：这里的 key 必须是 service_role key，否则无法删除 Auth 用户
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

        # 读取数据 (防崩溃处理)
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
        if start_warning_time >= deadline: start_warning_time = deadline - interval

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

        # 2. 死亡判定 & 彻底销毁
        if diff >= deadline:
            print(f"🔴 确认死亡！正在执行【账号级】物理抹除...")
            content = row.get('encrypted_data', '')
            
            # A. 发送遗嘱
            send_email(ben_email, 
                       "🔒 GhostProtocol: 数字遗产移交", 
                       f"系统确认所有者已失联（超 {deadline} 分钟）。\n\n这是其托付的最后数据：\n\n{content}\n\n【系统提示】邮件发送完毕，该账号及所有数据已被永久注销。")
            
            # B. 物理删除数据 (Vault)
            try:
                supabase.table("vaults").delete().eq("id", user_id).execute()
                print(f"✅ 用户数据表记录已删除。")
            except Exception as e:
                print(f"❌ 数据表删除异常 (可能已级联删除): {e}")

            # C. 物理删除账号 (Auth User) - 新增功能
            try:
                # 使用 admin 接口直接从 Auth 系统中移除用户
                supabase.auth.admin.delete_user(user_id)
                print(f"✅ Supabase Auth 账号已永久注销。")
            except Exception as e:
                print(f"❌ 账号注销失败 (请检查是否使用了 service_role key): {e}")

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
    print("🚀 GhostProtocol V5.0 终极销毁引擎启动...")
    check_vaults()
