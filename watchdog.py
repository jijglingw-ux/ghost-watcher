import os
import smtplib
import json
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from supabase import create_client

# ================= 配置区 =================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/" # 请替换为你的实际网址

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

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
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("❌ 配置错误: 缺少发件人信息")
        return False
    
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg.set_content(html_content, subtype='html', charset='utf-8')
    
    try:
        server_host = "smtp.qq.com" if "qq.com" in SENDER_EMAIL else "smtp.gmail.com"
        port = 465 if "qq.com" in SENDER_EMAIL else 587
        
        if port == 465:
            server = smtplib.SMTP_SSL(server_host, 465)
        else:
            server = smtplib.SMTP(server_host, port)
            server.starttls()
            
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 发信失败: {e}")
        return False

def send_warning(to_email, remaining_sec):
    time_str = str(timedelta(seconds=int(remaining_sec)))
    html = f"""
    <div style="border:2px solid #ffcc00; padding:20px; color:#333; font-family:sans-serif;">
        <h2 style="color:#e6b800;">⚠ 凤凰协议：心跳即将停止</h2>
        <p>您的死手开关倒计时仅剩：<strong>{time_str}</strong></p>
        <p>如果您还安全，请立即点击下方按钮重置系统：</p>
        <a href="{BASE_URL}" style="background:#ffcc00; color:#000; padding:15px 30px; text-decoration:none; font-weight:bold; display:inline-block; border-radius:4px;">我是本人，立即签到</a>
    </div>
    """
    return send_email(to_email, "【警报】请确认您的安全状态", html)

def send_final(to_email, key, uid):
    # 强制类型转换，防止隐形错误
    safe_uid = str(uid)
    safe_key = str(key)
    
    html = f"""
    <div style="border-left:5px solid #ff3333; padding:20px; font-family:sans-serif;">
        <h2 style="color:#ff3333;">凤凰协议 | 资产提取通知</h2>
        <p>委托人设定的信托已激活。请在电脑端访问：<br>
        <a href="{BASE_URL}">{BASE_URL}</a></p>
        <div style="background:#f4f4f4; padding:15px; margin:15px 0; font-family:monospace; border-radius:4px;">
            <strong>Vault ID:</strong> {safe_uid}<br>
            <strong>AES Key:</strong> {safe_key}
        </div>
        <p style="color:red; font-size:12px;">警告：该凭证为一次性提取。解密后数据将立即从服务器彻底销毁。</p>
    </div>
    """
    return send_email(to_email, "【绝密】数字资产提取通知", html)

def watchdog():
    print("🐕 凤凰看门狗 V7.5 (阅后即焚版) 启动...")
    db = get_db()
    
    # 仅获取 active 状态，过滤掉 burned 和 dispatched
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"⚠️ DB连接失败: {e}")
        return

    if not users:
        print("💤 无活跃协议")
        return

    now = datetime.now(timezone.utc)

    for row in users:
        uid = row['id']
        last_check = parse_time_safe(row['last_checkin_at'])
        if not last_check: continue

        elapsed = (now - last_check).total_seconds()
        timeout = row.get('timeout_seconds', 0)
        remaining = timeout - elapsed
        
        warn_start = row.get('warn_start_seconds', 300)
        warn_interval = row.get('warn_interval_seconds', 3600)
        warn_max = row.get('warn_max_count', 3)
        warn_sent = row.get('warn_sent_count', 0)
        last_warn = parse_time_safe(row.get('last_warn_at'))
        owner_email = row.get('owner_email')

        print(f"🔍 [{uid[:4]}] 剩: {int(remaining)}s")

        # --- 阶段 A: 最终触发 ---
        if remaining <= 0:
            print("⚡ 倒计时归零，执行发射...")
            payload = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload and payload.get('t'):
                if send_final(payload['t'], payload['k'], uid):
                    # 更新状态为 dispatched 并记录时间
                    db.table("vaults").update({
                        "status": "dispatched", 
                        "dispatched_at": datetime.now().isoformat()
                    }).eq("id", uid).execute()
                    print("🔥 发射完成，等待受益人一次性提取")
                else:
                    print("❌ 邮件发送失败")
            else:
                print("❌ 私钥解密失败")

        # --- 阶段 B: 智能唤醒 ---
        elif remaining <= warn_start and warn_sent < warn_max and owner_email:
            time_since_last_warn = (now - last_warn).total_seconds() if last_warn else 999999
            
            if time_since_last_warn >= warn_interval:
                if send_warning(owner_email, remaining):
                    db.table("vaults").update({
                        "warn_sent_count": warn_sent + 1,
                        "last_warn_at": datetime.now().isoformat()
                    }).eq("id", uid).execute()
                    print(f"✅ 唤醒邮件已发 ({warn_sent+1}/{warn_max})")

if __name__ == "__main__":
    if RSA_PRIVATE_KEY_PEM: watchdog()
    else: print("❌ 缺私钥 RSA_PRIVATE_KEY")
