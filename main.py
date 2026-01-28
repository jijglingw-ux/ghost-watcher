import os
import smtplib
import json
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

# ================= 配置区 =================
# 如果是在本地运行，可以直接把 os.environ.get 替换为真实字符串
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/"  # 请替换为你的实际部署域名

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_time_safe(time_str):
    if not time_str: return None
    try:
        clean_str = time_str.replace('Z', '+00:00')
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except:
        return None

def rsa_decrypt(encrypted_b64, private_key_pem):
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        try:
            return json.loads(decrypted_bytes.decode('utf-8'))
        except:
            return {'k': decrypted_bytes.decode('utf-8'), 't': None}
    except Exception as e:
        print(f"❌ 解密错误: {e}")
        return None

def send_email(to_email, subject, html_content):
    if not to_email or "None" in str(to_email): return False
    msg = MIMEMultipart('alternative')
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server_host = "smtp.qq.com" if "qq.com" in SENDER_EMAIL else "smtp.gmail.com"
        port = 465 if "qq.com" in SENDER_EMAIL else 587
        if port == 465:
            server = smtplib.SMTP_SSL(server_host, 465)
        else:
            server = smtplib.SMTP(server_host, port)
            server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 发信失败: {e}")
        return False

def send_warning(to_email, remaining_sec):
    """ 发送唤醒邮件 """
    print(f"⏰ 发送唤醒 -> {to_email}")
    time_str = str(timedelta(seconds=int(remaining_sec)))
    html = f"""
    <div style="border:2px solid #ffcc00; padding:20px; color:#333; font-family: sans-serif;">
        <h2 style="color:#e6b800;">⚠ 凤凰协议：心跳即将停止</h2>
        <p>您的死手开关倒计时仅剩：<strong>{time_str}</strong></p>
        <p>这是系统发出的存在性确认请求。</p>
        <p>如果您还安全，请立即点击下方按钮重置系统：</p>
        <a href="{BASE_URL}" style="background:#ffcc00; color:#000; padding:15px 30px; text-decoration:none; font-weight:bold; display:inline-block; margin-top:10px; border-radius: 4px;">我是本人，立即签到</a>
        <p style="font-size:12px; color:#666; margin-top:20px;">(若不操作，系统将按计划发送遗嘱)</p>
    </div>
    """
    return send_email(to_email, "【警报】请确认您的安全状态", html)

def send_final(to_email, key, uid):
    """ 发送最终遗嘱 """
    print(f"🚀 发送遗嘱 -> {to_email}")
    html = f"""
    <div style="border-left:5px solid #ff3333; padding:20px; font-family: monospace; background: #f9f9f9;">
        <h2>PHOENIX PROTOCOL | 资产提取通知</h2>
        <p>委托人设定的信托已激活。请在电脑端访问：<br>
        <a href="{BASE_URL}" style="color: #ff3333;">{BASE_URL}</a></p>
        <div style="background:#000; color: #0f0; padding:15px; margin:15px 0; border-radius: 4px;">
            <strong>Vault ID:</strong> {uid}<br>
            <strong>AES Key:</strong> {key}
        </div>
        <p style="color:red; font-size:12px;">此为最终通信。数据将在解密后销毁。</p>
    </div>
    """
    return send_email(to_email, "【绝密】数字资产提取通知", html)

def watchdog():
    print("🦅 凤凰看门狗 V15.9 (唤醒者) 正在扫描...")
    db = get_db()
    # 只处理状态为 active 的
    response = db.table("vaults").select("*").eq("status", "active").execute()
    users = response.data
    now = datetime.now(timezone.utc)

    for row in users:
        uid = row['id']
        last_check = parse_time_safe(row['last_checkin_at'])
        if not last_check: continue

        # 1. 计算时间 (全部按秒)
        elapsed = (now - last_check).total_seconds()
        timeout = row.get('timeout_seconds', 0)
        remaining = timeout - elapsed

        # 预警配置
        warn_start = row.get('warn_start_seconds', 0)    # 剩多少秒开始叫
        warn_interval = row.get('warn_interval_seconds', 3600) # 叫的间隔
        warn_max = row.get('warn_max_count', 0)          # 叫几次
        warn_sent = row.get('warn_sent_count', 0)        # 已叫几次
        last_warn = parse_time_safe(row.get('last_warn_at'))
        owner_email = row.get('owner_email')

        print(f"🔍 [{uid[:4]}] 剩余: {int(remaining)}s | 预警线: {warn_start}s | 已发预警: {warn_sent}/{warn_max}")

        # --- 阶段 A: 最终触发 ---
        if remaining <= 0:
            print("⚡ 倒计时归零，执行发射...")
            payload = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            if payload and payload.get('t'):
                if send_final(payload['t'], payload['k'], uid):
                    # 标记为已分发，并销毁私钥记录，防止二次读取
                    db.table("vaults").update({"status": "dispatched", "key_storage": "BURNED"}).eq("id", uid).execute()
                    print("🔥 发射完成")
            else:
                print("❌ 解密失败或数据不全")

        # --- 阶段 B: 智能唤醒 (剩余时间进入预警区) ---
        elif remaining <= warn_start and warn_sent < warn_max and owner_email:
            # 检查间隔 (如果没有上次发送时间，或者距离上次已超过间隔)
            time_since_last_warn = (now - last_warn).total_seconds() if last_warn else 999999999
            
            if time_since_last_warn >= warn_interval:
                if send_warning(owner_email, remaining):
                    db.table("vaults").update({
                        "warn_sent_count": warn_sent + 1,
                        "last_warn_at": datetime.now().isoformat()
                    }).eq("id", uid).execute()
                    print(f"✅ 唤醒邮件已发送 ({warn_sent+1}/{warn_max})")
            else:
                print(f"⏳ 预警冷却中 (再等 {int(warn_interval - time_since_last_warn)}s)")

if __name__ == "__main__":
    # 本地测试时，如果环境变量没设，这里会报错。请确保环境配置正确。
    if RSA_PRIVATE_KEY_PEM: 
        while True:
            watchdog()
            time.sleep(60) # 60秒轮询一次，节省资源
    else: 
        print("❌ 错误：未配置 RSA 私钥 (RSA_PRIVATE_KEY)")
