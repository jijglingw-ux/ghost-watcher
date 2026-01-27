import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

# ================= 配置区 =================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def rsa_decrypt(encrypted_b64, private_key_pem):
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        decrypted_str = decrypted_bytes.decode('utf-8')
        try:
            return json.loads(decrypted_str)
        except json.JSONDecodeError:
            return {'k': decrypted_str, 't': None}
    except Exception as e:
        print(f"❌ 解密底层错误: {e}")
        return None

def send_email_via_smtp(to_email, aes_key, user_id):
    """ 修复版：强制类型转换 + 调试信息 """
    # 1. 强制转换为字符串 (防御性编程)
    to_email = str(to_email).strip()
    aes_key = str(aes_key).strip()
    sender = str(SENDER_EMAIL).strip()
    
    print(f"📧 正在尝试发信 -> 发件人: {sender} | 收件人: {to_email}")

    if not to_email or "None" in to_email:
        print("❌ 错误: 目标邮箱无效")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = "【Relic】数字信托移交 (V5.0)"

    link = f"https://jijglingw-ux.github.io/ghost-watcher/#id={user_id}&key={aes_key}"
    
    body = f"""
    尊敬的受益人：
    
    这是一封由自动化“死手开关”触发的信托移交邮件。
    委托人已长时间未签到，系统判断为“失联”。
    
    根据凤凰协议 V5.0，以下是解密密钥：
    --------------------------------
    {aes_key}
    --------------------------------
    
    请点击下方链接查看完整内容：
    {link}
    
    (本邮件由自动化程序发出，请勿回复)
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        # 自动识别 SMTP
        smtp_server = "smtp.qq.com" if "qq.com" in sender else "smtp.gmail.com"
        port = 465 if "qq.com" in sender else 587
        
        print(f"🔌 连接 SMTP 服务器: {smtp_server}:{port}")
        
        if port == 465:
            server = smtplib.SMTP_SSL(smtp_server, 465)
        else:
            server = smtplib.SMTP(smtp_server, port)
            server.starttls()
        
        server.login(sender, SENDER_PASSWORD)
        server.sendmail(sender, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败 (SMTP阶段): {e}")
        # 打印变量类型以供调试
        print(f"   Debug类型 -> Sender: {type(sender)}, To: {type(to_email)}, Pwd: {type(SENDER_PASSWORD)}")
        return False

def watchdog():
    print("🐕 凤凰看门狗 V5.0 (隐形版 - 调试增强) 启动...")
    db = get_db()
    
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    now = datetime.now(timezone.utc)
    
    for row in users:
        user_id = row['id']
        db_email = row.get('beneficiary_email')
        
        last_checkin = datetime.fromisoformat(row['last_checkin_at'].replace('Z', '+00:00'))
        timeout_minutes = row['timeout_minutes']
        time_diff = (now - last_checkin).total_seconds() / 60
        
        if time_diff > timeout_minutes:
            print(f"⚠️ 用户 {user_id[:8]}... 已超时 ({int(time_diff)}min > {timeout_minutes}min)。准备拆包...")
            
            payload_data = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload_data:
                aes_key = payload_data.get('k')
                target_email = payload_data.get('t') or db_email 
                
                if aes_key and target_email:
                    success = send_email_via_smtp(target_email, aes_key, user_id)
                    if success:
                        print(f"✅ 邮件发送成功！正在销毁钥匙...")
                        db.table("vaults").update({
                            "status": "dispatched",
                            "key_storage": "BURNED" 
                        }).eq("id", user_id).execute()
                        print("🔥 钥匙已销毁，任务完成。")
                else:
                    print(f"❌ 数据缺失: Key={bool(aes_key)}, Email={bool(target_email)}")
            else:
                print("❌ RSA解密失败")
        else:
            print(f"✅ 用户 {user_id[:8]}... 状态正常")

if __name__ == "__main__":
    if not RSA_PRIVATE_KEY_PEM:
        print("❌ 错误: 未检测到 RSA 私钥")
    elif not SENDER_EMAIL:
        print("❌ 错误: 未检测到发件人邮箱 (EMAIL_USER)")
    else:
        watchdog()
