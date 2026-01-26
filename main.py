import os
import rsa # 需要安装 pip install rsa
import base64
from supabase import create_client
import datetime
import smtplib
from email.mime.text import MIMEText

# --- 极客配置 ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

# 【关键】加载私钥 (从 GitHub Secrets 读取)
# 格式必须是 PEM 格式
try:
    private_key_str = os.environ.get("RSA_PRIVATE_KEY")
    # 清理一下可能存在的格式问题
    pk = rsa.PrivateKey.load_pkcs1(private_key_str.encode('utf-8'))
except Exception as e:
    print(f"❌ 私钥加载失败: {e}")
    exit(1)

supabase = create_client(url, key)
SITE_URL = "https://jijglingw-ux.github.io/ghost-watcher"

def send_email(to, content):
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = '【Relic V4.5】加密信物移交'
        msg['From'] = sender_email
        msg['To'] = to
        with smtplib.SMTP_SSL("smtp.qq.com", 465) as s:
            s.login(sender_email, sender_password)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"邮件发送错误: {e}")
        return False

def watchdog():
    print("🐕 看门狗启动 (V4.5 RSA Enhanced)...")
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # 获取所有活跃信托
    res = supabase.table("vaults").select("*").eq("status", "active").execute()
    
    for row in res.data:
        uid = row['id']
        last_checkin = datetime.datetime.fromisoformat(row['last_checkin_at'].replace('Z', '+00:00'))
        timeout = int(row['timeout_minutes'])
        
        # 检查是否超时
        if (now - last_checkin).total_seconds() / 60 > timeout:
            print(f"⚠️ 用户 {uid} 已失去响应。准备执行协议...")
            
            # 1. 锁定状态
            lock = supabase.table("vaults").update({"status": "pending"}).eq("id", uid).eq("status", "active").execute()
            if not lock.data: continue
            
            # 2. 获取加密的密钥 (Wrapped Key)
            wrapped_key_b64 = row['key_storage'] # 这是 RSA 加密后的 Base64 字符串
            ben_email = row['beneficiary_email']
            
            if wrapped_key_b64 and ben_email:
                try:
                    # 3. 【核心解密步骤】使用私钥还原 AES Key
                    # 只有这一步，AES Key 才会短暂地出现在内存中
                    encrypted_key_bytes = base64.b64decode(wrapped_key_b64)
                    aes_key = rsa.decrypt(encrypted_key_bytes, pk).decode('utf-8')
                    
                    # 4. 构造链接并发送
                    link = f"{SITE_URL}/#id={uid}&key={aes_key}"
                    body = f"遗嘱触发。点击解密:\n{link}\n\n(此链接阅后即焚)"
                    
                    if send_email(ben_email, body):
                        # 5. 物理擦除
                        supabase.table("vaults").update({"key_storage": None}).eq("id", uid).execute()
                        print(f"✅ 移交完成。密钥已从数据库物理擦除。")
                    else:
                        # 发送失败回滚
                        supabase.table("vaults").update({"status": "active"}).eq("id", uid).execute()
                        
                except Exception as e:
                    print(f"❌ 解密或处理失败: {e}")
                    # 可能是私钥不匹配，或者数据损坏

    # 处理自毁 (30分钟后删除)
    # (此处代码同 V4.0，省略以节省篇幅，逻辑不变)

if __name__ == "__main__":
    watchdog()
