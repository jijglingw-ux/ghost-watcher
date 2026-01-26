import os
import rsa # 需要安装 pip install rsa
import base64
from supabase import create_client
import datetime
import smtplib
from email.mime.text import MIMEText

# --- 环境变量配置 ---
# 必须使用 service_role key，因为只有它有权限读取 key_storage 字段
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

# 【关键】加载私钥 (从 GitHub Secrets 读取)
# 格式必须是 PEM 格式
try:
    private_key_str = os.environ.get("RSA_PRIVATE_KEY")
    # 清理一下可能存在的格式问题
    if private_key_str:
        pk = rsa.PrivateKey.load_pkcs1(private_key_str.encode('utf-8'))
    else:
        print("⚠️ 警告: 未找到 RSA_PRIVATE_KEY 环境变量")
        pk = None
except Exception as e:
    print(f"❌ 私钥加载失败: {e}")
    exit(1)

supabase = create_client(url, key)

# 您的前端地址 (用于生成锚点链接)
SITE_URL = "https://jijglingw-ux.github.io/ghost-watcher"

def send_email(to_email, subject, content):
    if not to_email: return False
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email
        with smtplib.SMTP_SSL("smtp.qq.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"✅ 邮件已成功发送给: {to_email}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False

def watchdog():
    print("🐕 看门狗启动 (V4.5 RSA Enhanced)...")
    
    # --- 第一阶段: 检查超时遗嘱 (Dead Man's Switch) ---
    try:
        # 获取所有活跃的信托
        res = supabase.table("vaults").select("*").eq("status", "active").execute()
        vaults = res.data
    except Exception as e:
        print(f"数据库读取错误: {e}")
        return

    now = datetime.datetime.now(datetime.timezone.utc)

    for row in vaults:
        user_id = row.get('id')
        last_checkin = row.get('last_checkin_at')
        if not last_checkin: continue

        # 时间计算
        last_time = datetime.datetime.fromisoformat(last_checkin.replace('Z', '+00:00'))
        timeout_mins = int(row.get('timeout_minutes') or 1440)
        diff_mins = (now - last_time).total_seconds() / 60
        
        # --- 触发移交协议 ---
        if diff_mins >= timeout_mins:
            print(f"⚠️ 用户 {user_id} 时限已到。正在启动移交程序...")
            
            # 1. 尝试锁定状态 (防止并发)
            lock = supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": now.isoformat()
            }).eq("id", user_id).eq("status", "active").execute()

            if lock.data:
                # 2. 获取加密的密钥 (Wrapped Key)
                wrapped_key_b64 = row.get('key_storage') # 这是 RSA 加密后的 Base64 字符串
                ben_email = row.get('beneficiary_email')
                
                if wrapped_key_b64 and ben_email and pk:
                    try:
                        # 3. 【核心解密步骤】使用私钥还原 AES Key
                        # 只有这一步，AES Key 才会短暂地出现在内存中
                        encrypted_key_bytes = base64.b64decode(wrapped_key_b64)
                        aes_key = rsa.decrypt(encrypted_key_bytes, pk).decode('utf-8')
                        
                        # 4. 构造链接
                        magic_link = f"{SITE_URL}/#id={user_id}&key={aes_key}"
                        
                        body = f"""
【Relic | 遗物信托】数字信物安全移交通知

您好。这是一个自动触发的死手开关协议。
托管人 (ID: {user_id}) 已停止响应。

>>> 点击下方链接提取信物:
{magic_link}

【安全须知】
1. 密钥已嵌入在链接中，请勿转发。
2. 阅后即焚：数据将在被查看 30 分钟后物理销毁。
"""
                        # 5. 发送邮件
                        if send_email(ben_email, "【Relic】加密数字信物移交", body):
                            # 6. 物理擦除 (Key Wipe)
                            supabase.table("vaults").update({"key_storage": None}).eq("id", user_id).execute()
                            print(f"🔥 用户 {user_id} 的密钥已擦除。")
                        else:
                            # 失败回滚
                            print("邮件失败，回滚状态。")
                            supabase.table("vaults").update({"status": "active"}).eq("id", user_id).execute()
                            
                    except Exception as e:
                        print(f"❌ RSA解密或处理失败: {e}")
                else:
                    print("❌ 错误: 缺少密钥数据或私钥未加载")

    # --- 第二阶段: 监测自毁 (Self-Destruct) ---
    # 检查状态为 reading 的记录，超过 30 分钟则物理删除
    try:
        res = supabase.table("vaults").select("*").eq("status", "reading").execute()
        reading_vaults = res.data
    except: reading_vaults = []

    for row in reading_vaults:
        user_id = row.get('id')
        unlock_time_str = row.get('last_checkin_at')
        if not unlock_time_str: continue
        
        unlock_time = datetime.datetime.fromisoformat(unlock_time_str.replace('Z', '+00:00'))
        
        if (now - unlock_time).total_seconds() / 60 >= 30:
            print(f"💀 销毁时间到：彻底删除记录 {user_id}")
            # 1. 删除信托记录
            supabase.table("vaults").delete().eq("id", user_id).execute()
            # 2. 尝试注销 Auth 账号 (可选)
            try:
                supabase.auth.admin.delete_user(user_id)
            except: pass

if __name__ == "__main__":
    watchdog()
