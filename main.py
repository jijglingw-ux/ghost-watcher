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
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Service Role Key
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/" # 请替换你的真实部署域名

def get_db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ 环境变量缺失")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def rsa_decrypt(encrypted_b64):
    try:
        private_key = serialization.load_pem_private_key(
            RSA_PRIVATE_KEY_PEM.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception as e:
        print(f"❌ 解密失败: {e}")
        return None

def send_email(to_email, subject, html_content):
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_content, 'html'))
        
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
        print(f"❌ 邮件发送异常: {e}")
        return False

def watchdog():
    print("🦅 凤凰看门狗 V14.0 (纯净版) 正在扫描...")
    db = get_db()
    if not db: return

    # 只查询状态为 active 的包裹
    # V14 SQL触发器保证了每个用户只有一个 active，所以这里很安全
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        vaults = response.data
    except Exception as e:
        print(f"❌ DB读取失败: {e}")
        return

    now = datetime.now(timezone.utc)

    for row in vaults:
        uid = row.get('id')
        # 兼容处理时间格式
        last_check_str = row.get('last_checkin_at')
        if not last_check_str: continue
        
        try:
            last_check = datetime.fromisoformat(last_check_str.replace('Z', '+00:00'))
        except:
            continue

        elapsed = (now - last_check).total_seconds()
        timeout = row.get('timeout_seconds', 0)
        remaining = timeout - elapsed
        
        # 预警逻辑
        warn_start = row.get('warn_start_seconds', 0) or 0
        warn_interval = row.get('warn_interval_seconds', 300) or 300
        last_warn_str = row.get('last_warn_at')
        
        print(f"🔍 [ID:{uid[:4]}] 剩余: {int(remaining)}s")

        # === 触发逻辑 ===
        if remaining <= 0:
            print(f"⚡ [ID:{uid[:4]}] 触发！正在解密...")
            payload = rsa_decrypt(row.get('key_storage'))
            
            if payload and payload.get('t') and payload.get('k'):
                # 发送给受益人 (payload['t']) 或者是 owner_email，取决于你的业务逻辑
                # V14 默认逻辑：payload['t'] 里面存的是受益人邮箱
                target_email = payload['t'] 
                
                html = f"""
                <div style="background:#000; color:#0f0; padding:20px; font-family:monospace;">
                    <h1>PHOENIX PROTOCOL // DISPATCH</h1>
                    <p>预设的死手开关已被触发。</p>
                    <hr style="border:1px solid #333;">
                    <p><strong>Vault ID:</strong> {uid}</p>
                    <p><strong>AES Key:</strong> {payload['k']}</p>
                    <p><a href="{BASE_URL}" style="color:#0f0; text-decoration:underline;">前往终端解密 >></a></p>
                </div>
                """
                
                if send_email(target_email, "【绝密】数字资产提取凭证", html):
                    # 标记为已发送，防止重复触发
                    db.table("vaults").update({
                        "status": "dispatched", 
                        "key_storage": "BURNED" # 销毁私钥记录
                    }).eq("id", uid).execute()
                    print(f"🔥 [ID:{uid[:4]}] 发送成功，已销毁。")
            else:
                print("❌ 解密失败，跳过。")

        # === 预警逻辑 ===
        elif 0 < remaining <= warn_start:
            # 检查是否冷却中
            should_warn = True
            if last_warn_str:
                last_warn = datetime.fromisoformat(last_warn_str.replace('Z', '+00:00'))
                if (now - last_warn).total_seconds() < warn_interval:
                    should_warn = False
            
            if should_warn:
                # 预警发给 owner_email
                owner = row.get('owner_email')
                if owner:
                    html_warn = f"""
                    <div style="background:#fff; border-left:4px solid #ffcc00; padding:15px;">
                        <h3>⚠️ 凤凰协议预警</h3>
                        <p>死手开关将在 <strong>{int(remaining/60)}分钟</strong> 后触发。</p>
                        <a href="{BASE_URL}">立即签到重置</a>
                    </div>
                    """
                    if send_email(owner, "【警告】请确认生存状态", html_warn):
                        db.table("vaults").update({"last_warn_at": now.isoformat()}).eq("id", uid).execute()
                        print(f"⚠️ [ID:{uid[:4]}] 预警已发送")

if __name__ == "__main__":
    if RSA_PRIVATE_KEY_PEM: 
        watchdog()
    else: 
        print("❌ 缺私钥")
