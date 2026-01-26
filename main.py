import os
from supabase import create_client
import datetime
import smtplib
import time
from email.mime.text import MIMEText

# --- 环境变量配置 ---
# 必须使用 service_role key，因为只有它有权限读取 key_storage 字段
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
sender_email = os.environ.get("SENDER_EMAIL")
sender_password = os.environ.get("SENDER_PASSWORD")

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

def check_vaults():
    print("正在巡查 Relic 信托库...")
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
        
        # --- 触发移交协议 (Handover Protocol) ---
        if diff_mins >= timeout_mins:
            print(f"⚠️ 用户 {user_id} 时限已到。正在启动移交程序...")
            
            # 1. 尝试锁定状态 (防止并发重复发送)
            lock = supabase.table("vaults").update({
                "status": "pending",
                "last_checkin_at": now.isoformat()
            }).eq("id", user_id).eq("status", "active").execute()

            if lock.data:
                # 2. 只有抢到锁的进程，才有资格读取 Master Key
                # 重新获取该行数据以拿到 Key (之前的 select 结果可能已过期)
                secure_data = supabase.table("vaults").select("key_storage, beneficiary_email").eq("id", user_id).single().execute()
                
                master_key = secure_data.data.get('key_storage')
                ben_email = secure_data.data.get('beneficiary_email')
                
                if master_key and ben_email:
                    # 3. 构造 "Magic Link" (锚点隔离技术)
                    # 格式: site.com/#id=UUID&key=MASTER_KEY
                    # 密钥藏在 # 后面，黑客网络拦截也看不到 Key
                    magic_link = f"{SITE_URL}/#id={user_id}&key={master_key}"
                    
                    # --- 中文邮件文案 ---
                    body = f"""
【Relic | 遗物信托】数字信物安全移交通知

您好。

这是一封自动系统通知。
您已被指定为一份加密数据信托的受益人。
托管人 (ID: {user_id}) 已停止活动，系统触发了自动交付协议。

根据预设规则，解密密钥现移交给您。

>>> 点击下方链接提取信物:
{magic_link}

【安全须知】
1. 点击上方链接后，您的浏览器将在本地自动解密数据。
2. 密钥已嵌入在链接中 (锚点部分)，请勿将此链接分享给他人。
3. 一旦您成功访问，由于“阅后即焚”策略，数据将在 30 分钟后从服务器永久销毁。
"""
                    # 4. 发送邮件
                    if send_email(ben_email, "【Relic】加密数字信物移交", body):
                        # 5. 【关键步骤：零信任闭环】密钥自毁 (Key Wipe)
                        # 邮件发出后，立即从数据库物理删除 key_storage
                        # 此时，只有受益人的邮件里有 Key，数据库里再也没有了
                        supabase.table("vaults").update({
                            "key_storage": None 
                        }).eq("id", user_id).execute()
                        print(f"🔥 用户 {user_id} 的密钥已擦除。平台现已不掌握任何密钥。")
                    else:
                        print("邮件发送失败。保留密钥以便重试。")
                        # 回滚状态以便下次重试
                        supabase.table("vaults").update({"status": "active"}).eq("id", user_id).execute()

    # --- 监测自毁 (Self-Destruct) ---
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
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if (now - unlock_time).total_seconds() / 60 >= 30:
            print(f"💀 销毁时间到：彻底删除记录 {user_id}")
            # 1. 删除信托记录
            supabase.table("vaults").delete().eq("id", user_id).execute()
            # 2. 尝试注销 Auth 账号 (可选，彻底清除痕迹)
            try:
                supabase.auth.admin.delete_user(user_id)
            except: pass

if __name__ == "__main__":
    check_vaults()
    # 注意：在 GitHub Actions 中不需要死循环，执行一次即可
