import os
from supabase import create_client
import datetime
import smtplib
import time
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
        status = row.get('status', 'active')
        
        # 排除已处理或无记录的用户
        if not last_checkin or status != 'active': continue

        # --- 获取用户设置 ---
        deadline = int(row.get('timeout_minutes', 10))   
        max_warns = int(row.get('max_warnings', 2))      
        interval = int(row.get('warning_interval', 1))   
        current_warns = row.get('current_warnings', 0)
        
        warn_email = row.get('warning_email')
        ben_email = row.get('beneficiary_email')

        # --- 计算时间差 ---
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - last_time).total_seconds() / 60
        
        print(f"--- 巡逻日志: 用户 {user_id} ---")
        print(f"已失联：{diff:.1f} 分钟 | 设定终点：{deadline} 分钟")

        # --- 阶梯判定核心 (V3.1 穿透逻辑) ---
        
        # 1. 检查是否需要补发“唤醒邮件”
        start_warning_time = deadline - (max_warns * interval)
        if diff >= start_warning_time:
            # 计算当前失联时间段内，理论上应该发出的总警告次数
            # 如果失联很久，expected 可能会直接跳到 max_warns
            expected_warns = int((diff - start_warning_time) / interval) + 1
            if expected_warns > max_warns: expected_warns = max_warns

            # 循环补发：如果机器人漏掉了之前的唤醒点，现在一次性补齐
            while current_warns < expected_warns:
                current_warns += 1
                mins_left = max(0, int(deadline - (start_warning_time + (current_warns-1)*interval)))
                print(f"⚠️ 正在补发第 {current_warns} 次唤醒提醒...")
                send_email(warn_email, f"🚨 临界唤醒 ({current_warns}/{max_warns})", 
                           f"您已失联约 {int(diff)} 分钟。这是系统判定死亡前的最后提醒！")
                # 实时更新数据库，防止重复发送
                supabase.table("vaults").update({"current_warnings": current_warns}).eq("id", user_id).execute()
                time.sleep(2) # 稍微停顿，防止触发邮件系统垃圾过滤

        # 2. 判定是否达到“死亡终点”
        if diff >= deadline:
            print(f"🔴 确认死亡判定。正在发送遗言至受益人...")
            content = row.get('encrypted_data', '无加密数据')
            send_email(ben_email, "🔒 GhostProtocol: 数字遗产移交", 
                       f"系统确认所有者已失联超过 {deadline} 分钟。\n\n托付内容如下：\n{content}")
            # 彻底结束事件：修改状态为 triggered
            supabase.table("vaults").update({"status": "triggered"}).eq("id", user_id).execute()
            print(f"✅ 任务结束。")
        else:
            print(f"🛡️ 监控中：距离死亡终点还剩 {int(deadline - diff)} 分钟")

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
    print("🚀 GhostProtocol V3.1 (全覆盖扫描版) 启动...")
    check_vaults()
