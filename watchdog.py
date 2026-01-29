import os
import smtplib
import json
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from supabase import create_client
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

# === 环境变量 ===
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://your-username.github.io/phoenix/" # 请替换为实际地址

def get_db(): return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_time_safe(time_str):
    if not time_str: return None
    try:
        clean_str = time_str.replace('Z', '+00:00')
        if '.' in clean_str: clean_str = clean_str.split('.')[0] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except: return None

def rsa_decrypt(encrypted_b64, private_key_raw):
    print("  -> [Debug] 开始解密流程...")
    try:
        # 1. 自动修复 GitHub Secrets 可能导致的格式问题
        if not private_key_raw:
            print("  -> [Error] 私钥为空！")
            return None
            
        # 尝试修复换行符（关键修复）
        formatted_key = private_key_raw.replace('\\n', '\n')
        if "-----BEGIN" not in formatted_key:
            print("  -> [Error] 私钥格式错误 (缺少 Header)")
            return None

        print("  -> [Debug] 加载私钥 PEM...")
        private_key = serialization.load_pem_private_key(
            formatted_key.encode(), 
            password=None, 
            backend=default_backend()
        )
        
        print("  -> [Debug] 解码 Base64...")
        encrypted_bytes = base64.b64decode(encrypted_b64)
        
        print("  -> [Debug] 执行 RSA 解密...")
        decrypted_bytes = private_key.decrypt(
            encrypted_bytes, 
            padding.PKCS1v15()
        )
        
        print("  -> [Debug] 解析 JSON...")
        try: return json.loads(decrypted_bytes.decode('utf-8'))
        except: return {'k': decrypted_bytes.decode('utf-8'), 't': None}
        
    except Exception as e:
        print(f"  -> ❌ 解密崩溃: {str(e)}")
        return None

def send_email(to_email, subject, html_content):
    print(f"  -> [Debug] 准备连接 SMTP 服务器 (目标: {to_email})...")
    if not SENDER_EMAIL or not SENDER_PASSWORD: 
        print("  -> [Error] 缺少发件人配置")
        return False
        
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg.set_content(html_content, subtype='html', charset='utf-8')
    
    try:
        host = "smtp.qq.com" if "qq.com" in SENDER_EMAIL else "smtp.gmail.com"
        port = 465 if "qq.com" in SENDER_EMAIL else 587
        
        print(f"  -> [Debug] 连接 {host}:{port}...")
        if port == 465: 
            server = smtplib.SMTP_SSL(host, 465, timeout=30) # 增加超时设置
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
            
        print("  -> [Debug] 登录中...")
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        print("  -> [Debug] 发送指令...")
        server.send_message(msg)
        server.quit()
        print("  -> [Debug] 发送成功！")
        return True
    except Exception as e:
        print(f"  -> ❌ 邮件发送失败: {str(e)}")
        return False

def watchdog():
    print("🐕 Phoenix Watchdog V8.2 (Debug Mode) Running...")
    db = get_db()
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"⚠️ DB Error: {e}"); return

    if not users: print("💤 No active protocols."); return

    now = datetime.now(timezone.utc)

    for row in users:
        uid = row['id']
        last_check = parse_time_safe(row.get('last_checkin_at'))
        if not last_check: continue

        elapsed = (now - last_check).total_seconds()
        timeout = row.get('timeout_seconds', 86400)
        remaining = timeout - elapsed
        
        warn_start = row.get('warn_start_seconds', 300)
        warn_max = row.get('warn_max_count', 3)
        warn_sent = row.get('warn_sent_count', 0)
        owner = row.get('owner_email')

        print(f"🔍 [{uid[:4]}] Rem: {int(remaining)}s")

        if remaining <= 0:
            print("⚡ TIMEOUT. Decrypting payload...")
            
            # 使用带 Debug 的解密函数
            payload = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload and payload.get('t'):
                print(f"  -> [Debug] 解密成功，准备发送给: {payload['t']}")
                html = f"""
                <div style="border-left:5px solid #ff3333; padding:20px;">
                    <h2 style="color:#ff3333">凤凰协议 | 资产提取通知</h2>
                    <p>信托已激活。请访问：<a href="{BASE_URL}">{BASE_URL}</a></p>
                    <div style="background:#eee; padding:15px; font-family:monospace;">
                        Vault ID: {uid}<br>AES Key: {payload['k']}
                    </div>
                    <p style="color:red; font-size:12px">警告：一次性凭证，阅后即焚。</p>
                </div>
                """
                if send_email(payload['t'], "【绝密】资产提取通知", html):
                    # 只有发送成功才更新数据库
                    print("  -> [Debug] 更新数据库状态...")
                    try:
                        db.table("vaults").update({
                            "status": "dispatched", 
                            "dispatched_at": datetime.now().isoformat()
                        }).eq("id", uid).execute()
                        print("🔥 Dispatched & DB Updated.")
                    except Exception as db_err:
                        print(f"❌ 邮件已发但数据库更新失败: {db_err}")
            else:
                print("❌ Decrypt failed (Payload is empty or key error).")

        elif remaining <= warn_start and warn_sent < warn_max and owner:
            print("🔔 Triggering Warning...")
            html = f"""<div style="border:2px solid #fc0; padding:20px;"><h2>凤凰协议预警</h2><p>倒计时剩 {int(remaining)} 秒。</p><a href="{BASE_URL}">立即签到</a></div>"""
            if send_email(owner, "【警报】最后确认", html):
                db.table("vaults").update({"warn_sent_count": warn_sent+1, "last_warn_at": datetime.now().isoformat()}).eq("id", uid).execute()
                print("✅ Warning sent.")

if __name__ == "__main__":
    if RSA_PRIVATE_KEY_PEM: watchdog()
    else: print("❌ Missing Private Key")
