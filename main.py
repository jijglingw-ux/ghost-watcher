<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>凤凰协议 V5.0 | 隐形信托</title>
    <script src="https://unpkg.com/@supabase/supabase-js@2"></script>
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.1.1/crypto-js.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jsencrypt/3.3.2/jsencrypt.min.js"></script>
    <style>
        /* 保持赛博朋克风格 */
        :root { --matrix-green: #00ff41; --panel-bg: rgba(13, 17, 23, 0.95); --glow: 0 0 10px rgba(0, 255, 65, 0.3); }
        * { box-sizing: border-box; }
        body { background-color: #000; color: var(--matrix-green); font-family: 'Microsoft YaHei', sans-serif; margin: 0; height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; background-image: radial-gradient(circle, #1a1a1a 0%, #000 100%); }
        .scanlines { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0,0,0,0.1) 50%, rgba(0,0,0,0.1)); background-size: 100% 4px; pointer-events: none; z-index: 999; }
        .container { width: 100%; max-width: 500px; padding: 30px; border: 1px solid var(--matrix-green); box-shadow: var(--glow); background: var(--panel-bg); position: relative; z-index: 10; }
        h2 { text-align: center; letter-spacing: 5px; text-shadow: var(--glow); border-bottom: 1px solid var(--matrix-green); padding-bottom: 15px; margin-bottom: 30px; }
        input, textarea { width: 100%; background: #000; border: 1px solid #333; color: var(--matrix-green); padding: 15px; margin-bottom: 15px; font-family: inherit; outline: none; transition: 0.3s; }
        input:focus { border-color: var(--matrix-green); box-shadow: var(--glow); }
        .btn-group { display: flex; gap: 10px; }
        button { flex: 1; padding: 15px; background: transparent; border: 1px solid var(--matrix-green); color: var(--matrix-green); font-weight: bold; cursor: pointer; transition: 0.3s; }
        button:hover { background: var(--matrix-green); color: #000; box-shadow: 0 0 20px var(--matrix-green); }
        button.secondary { border-color: #888; color: #888; }
        .status-badge { display: inline-block; padding: 5px 10px; border: 1px solid var(--matrix-green); font-size: 0.8rem; margin-bottom: 20px; }
        .hidden { display: none !important; }
        #decrypt { margin-top: 20px; padding: 15px; border: 1px dashed var(--matrix-green); background: rgba(0, 50, 0, 0.2); line-height: 1.6; word-break: break-all; }
    </style>
</head>
<body>
    <div class="scanlines"></div>
    <div class="container">
        <h2>凤凰协议 <span style="font-size:0.6em;">V5.0 幽灵版</span></h2>
        
        <div id="login-section">
            <div class="status-badge">[ 终端已锁定 ]</div>
            <input type="email" id="email" placeholder="身份账号 (电子邮箱)">
            <input type="password" id="password" placeholder="通行密码">
            <div class="btn-group">
                <button onclick="login()">准入登录</button>
                <button class="secondary" onclick="signup()">初始化身份</button>
            </div>
        </div>

        <div id="dash" class="hidden">
            <div class="status-badge" style="color:#00ff41">[ 隐形信道已建立 ]</div>
            <textarea id="secret" rows="5" placeholder="输入绝密内容 (内容将在本地加密)"></textarea>
            
            <label style="font-size:0.8rem; opacity:0.7;">受益人邮箱 (将不存储在数据库，仅封装进RSA包)</label>
            <input type="email" id="ben" placeholder="接收人地址">
            
            <label style="font-size:0.8rem; opacity:0.7;">静默触发时长 (分钟)</label>
            <input type="number" id="time" value="1" min="1">
            
            <button onclick="deploy()">执行：隐形武装协议</button>
        </div>

        <div id="decrypt" class="hidden"></div>
    </div>

<script>
    // ==========================================
    // 配置区域
    const DB_URL = 'https://uudlauufdnrdcztlesvr.supabase.co'; 
    const DB_KEY = 'sb_publishable_KtfqCfLqUd_AtLj0Nb2WKQ_aPbsHjus'; 

    // 这是你的前端公钥 (锁)
    const WATCHDOG_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAviA23JxW181JM9cbwClQ
x7+KP+rmhFJ2RF30z1OAjvWngczIYYRT4EGjx74OLqP3leYXME+4ZKZIqt6v8jf1
trELXELa5khEOwWHj2EbOnhPdbk7aJ3Du/RmkZAu/gSVKHiWAeVPdmZuEDRP8wV1
gIYQsnXW+gNTt0SPKdheSkWTiksSImiJlzV3HC9AS/ucx/GfAhxnLLQ67ZhRE+Ub
ytBiBV+RfQX9P0oWbsESOD+FtiJfvKO74jA9naWsmG7hMmhotH1O1oC3YWFYvpNi
RYytkgByTOHBmtFqUVa1jIAJGdAZ8g1jMhZOOte5NfjJ4fJQhmqzdHBlH2xU/14A
pQIDAQAB
-----END PUBLIC KEY-----`;
    // ==========================================

    const client = window.supabase.createClient(DB_URL, DB_KEY);
    
    // 自动解密逻辑
    window.onload = async () => {
        if(location.hash.includes("key=")){
            document.getElementById("login-section").classList.add("hidden");
            document.querySelector("h2").innerText = "遗物解密中";
            const key = location.hash.split("key=")[1].split("&")[0];
            const id = location.hash.split("id=")[1].split("&")[0];
            
            Swal.fire({ title: '身份验证通过', text: '正在本地重组数据...', background: '#000', color: '#0f0', showConfirmButton: false, didOpen: () => { Swal.showLoading() } });

            try {
                // 即使数据库记录已删，如果受益人已拿到key和密文缓存，理论上可解
                // 但为了演示完整性，通常此时记录已被脚本删除。
                // 这里的逻辑假设用户点击链接时，数据可能已被脚本读后即焚。
                // *注：如果是V5.0，脚本发信后会删除记录。受益人若想看，必须脚本不删或者另存。
                // 为了能让受益人看到，我们这里假设脚本采取“只发信不删”或“延时删除”。
                // 如果是“阅后即焚”模式，受益人必须在邮件里直接看到内容，或者Supabase里保留密文A。
                // 这里我们保持原逻辑：去Supabase取密文A。这意味着脚本在发信后 *不能* 立即删密文A，只能删key_storage。
                
                const {data, error} = await client.from("vaults").select("encrypted_data").eq("id", id).single();
                
                if(error || !data) throw new Error("信托记录已被销毁或不存在");

                const bytes = CryptoJS.AES.decrypt(data.encrypted_data, key);
                const text = bytes.toString(CryptoJS.enc.Utf8);
                
                if(!text) throw new Error("密钥错误");

                Swal.close();
                const decryptBox = document.getElementById("decrypt");
                decryptBox.classList.remove("hidden");
                decryptBox.innerHTML = "<strong>>> 绝密内容还原：</strong><br><br>" + text;
            } catch(e){ 
                Swal.fire({icon:'error', title:'提取失败', text: '数据已物理销毁或链接失效', background:'#000', color:'#f00', confirmButtonText: '关闭'});
            }
        }
    };

    // 登录
    async function login() {
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        const {error} = await client.auth.signInWithPassword({email, password});
        if(error) return Swal.fire({icon:'error', title:'准入失败', text:'账号或密码错误', background:'#000', color:'#f00', confirmButtonText: '重试'});
        document.getElementById("login-section").classList.add("hidden");
        document.getElementById("dash").classList.remove("hidden");
    }

    // 注册
    async function signup() {
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        if(!email || password.length < 6) return Swal.fire({text:'密码需至少6位', background:'#000', color:'#f00', confirmButtonText: '修正'});
        const {error} = await client.auth.signUp({email, password});
        if(error) {
            let msg = error.message.includes("already registered") ? "身份已存在，请直接登录" : "网络异常";
            return Swal.fire({icon:'error', title:'初始化中断', text: msg, background:'#000', color:'#f00', confirmButtonText: '确定'});
        }
        Swal.fire({icon:'success', title:'身份预置成功', text:'激活邮件已发送，请查收', background:'#000', color:'#0f0', confirmButtonText: '了解'});
    }

    // V5.0 核心部署逻辑
    async function deploy() {
        const secret = document.getElementById("secret").value;
        const ben = document.getElementById("ben").value;
        const time = document.getElementById("time").value;

        if(!secret || !ben) return Swal.fire({text:'数据不完整', background:'#000', color:'#f00'});

        // 1. 生成 AES 密钥
        const aesKey = Array.from(crypto.getRandomValues(new Uint8Array(32)), b=>b.toString(16).padStart(2,'0')).join('');
        
        // 2. 加密秘密 (密文A)
        const encryptedData = CryptoJS.AES.encrypt(secret, aesKey).toString();
        
        // 3. 【核心升级】打包 AES 密钥 + 受益人邮箱 -> JSON
        const payload = JSON.stringify({
            k: aesKey,
            t: ben
        });

        // 4. 用 RSA 公钥加密整个 JSON 包 (生成 key_storage)
        const encryptor = new JSEncrypt();
        encryptor.setPublicKey(WATCHDOG_PUBLIC_KEY);
        const wrappedPayload = encryptor.encrypt(payload); // 限制：JSEncrypt处理长文本能力有限，但JSON很短，没问题

        if(!wrappedPayload) return Swal.fire({text:'加密环境异常', background:'#000', color:'#f00'});

        const user = (await client.auth.getUser()).data.user;
        
        // 5. 上传 (注意：不再上传 beneficiary_email)
        const {error} = await client.from("vaults").upsert({
            id: user.id,
            encrypted_data: encryptedData,
            key_storage: wrappedPayload, // 这里面现在包含了隐形邮箱
            timeout_minutes: time,
            status: 'active',
            last_checkin_at: new Date()
        });

        if(error) {
            Swal.fire({icon:'error', title:'部署受阻', text: error.message, background:'#000', color:'#f00'});
        } else {
            Swal.fire({
                icon: 'success', 
                title: '幽灵协议已激活', 
                text: '受益人信息已隐身，数据库仅留密文', 
                background: '#000', 
                color: '#0f0', 
                confirmButtonText: '锁定终端'
            });
        }
    }
</script>
</body>
</html>
