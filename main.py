import os
import rsa
import base64
from supabase import create_client
import datetime
import smtplib
from email.mime.text import MIMEText

# --- 加载配置 ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

# 加载私钥
try:
    private_key_str = os.environ.get("RSA_PRIVATE_KEY")
    if private_key_str:
        pk = rsa.PrivateKey.load_pkcs1(private_key_str.encode('utf-8'))
    else:
        print("⚠️ 警告: 环境变量 RSA_PRIVATE_KEY 为空")
        pk = None
except Exception as e:
    print(f"❌ 私钥格式错误: {e}")
    exit(1)

supabase = create_client(url, key)
SITE_URL = "https://jijglingw-ux.github.io/ghost-watcher"

def send_email(to, content):
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = '【Relic】加密数字信物移交'
        msg['From'] = sender_email
        msg['To'] = to
        with smtplib.SMTP_SSL("smtp.qq.com", 465) as s:
            s.login(sender_email, sender_password)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ 邮件错误: {e}")
        return False

def watchdog():
    print("🐕 Phoenix Watchdog V4.5 Started...")
    try:
        # 获取活跃信托
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for row in res.data:
            uid = row['id']
            last_checkin = datetime.datetime.fromisoformat(row['last_checkin_at'].replace('Z', '+00:00'))
            timeout = int(row['timeout_minutes'])
            
            # 检查是否超时
            if (now - last_checkin).total_seconds() / 60 > timeout:
                print(f"⚠️ 用户 {uid} 已超时。准备解密...")
                
                # 锁定
                supabase.table("vaults").update({"status": "pending"}).eq("id", uid).execute()
                
                # 解密流程
                wrapped_key = row['key_storage']
                ben_email = row['beneficiary_email']
                
                if wrapped_key and ben_email and pk:
                    try:
                        # --- RSA 解密核心 ---
                        encrypted_bytes = base64.b64decode(wrapped_key)
                        aes_key = rsa.decrypt(encrypted_bytes, pk).decode('utf-8')
                        
                        link = f"{SITE_URL}/#id={uid}&key={aes_key}"
                        body = f"遗嘱触发。点击解密:\n{link}\n\n(此链接30分钟后失效)"
                        
                        if send_email(ben_email, body):
                            supabase.table("vaults").update({"key_storage": None}).eq("id", uid).execute()
                            print(f"✅ 邮件发送成功。密钥已擦除。")
                    except Exception as e:
                        print(f"解密失败: {e}")
    except Exception as e:
        print(f"数据库连接失败: {e}")

if __name__ == "__main__":
    watchdog()
