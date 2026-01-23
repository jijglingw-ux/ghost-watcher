import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# 从 GitHub Secrets 获取环境配置
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

supabase = create_client(url, key)

def check_vaults():
    # 1. 抓取所有处于活跃状态的保险箱
    res = supabase.table("vaults").select("*").eq("status", "active").execute()
    
    for row in res.data:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        
        if not last_checkin: continue

        # --- 获取用户 V3.2 设定参数 ---
        deadline = int(row.get('timeout_minutes', 10))   # 最终判定时间
        max_warns = int(row.get('max_warnings', 2))      # 总唤醒次数
        interval = int(row.get('warning_interval', 1))   # 唤醒间隔
        current_warns = row.get('current_warnings', 0)
        
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        # --- 计算失联时长 ---
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        print(f"\n[检查用户: {user_id}]")
        print(f"已失联: {diff:.1f} 分钟 | 死亡终点: {deadline} 分钟")

        # --- V3.2 判定逻辑链 ---
        
        # A. 检查并补发唤醒邮件 (由远及近补齐所有漏发的警告)
        start_warning_time = deadline - (max_warns * interval)
        if diff >= start_warning_time and diff < deadline:
            # 计算当前时间点理论上应达到的警告次数
            expected_warns = int((diff - start_warning_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            # 如果记录的次数落后，开始补发
            while current_warns < expected_warns:
                current_warns += 1
                mins_left = int(deadline - diff)
                print(f"⚠️ 发送唤醒预警 ({current_warns}/{max_warns})，剩余寿命约 {mins_left} 分钟")
                send_email(warn_email, 
                           f"🚨 GhostProtocol 临终唤醒 ({current_warns}/{max_warns})", 
                           f"系统检测到您已失联 {int(diff)} 分钟，距离资产移交还剩约 {mins_left} 分钟，请尽快登录心跳！")
                
                # 同步更新数据库
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(1) # 避开 SMTP 频率限制

        # B. 终极判定：确认死亡
        if diff >= deadline:
            print(f"🔴 判定失联超限！正在向受益人发送解密数据...")
            content = row.get('encrypted_data', '无加密数据')
            
            # 发送遗嘱邮件
            send_email(ben_email, 
                       "🔒 GhostProtocol: 数字遗产移交通知", 
                       f"系统确认所有者已长期失联（超 {deadline} 分钟）。\n\n以下是其托付的加密资产数据，请前往控制台解密：\n\n{content}")
            
            # 标记为 triggered，相当于从“活跃监控名单”中移除
            supabase.table("vaults").update({"status": "triggered"}).eq("id", user_id).execute()
            print(f"✅ 该用户监控任务已结束。")
        else:
            print(f"🛡️ 账户状态正常，进度条运行中。")

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

if __name__ == "__main__":
    print("🚀 GhostProtocol V3.2 巡逻引擎启动...")
    check_vaults()
