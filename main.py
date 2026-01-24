// --- V12.0 阅后即焚逻辑修正 ---
async function handleDecrypt() {
    if (!sessionUser) return;
    let raw = document.getElementById('de_input').value.trim();
    if (!raw) return;

    if (raw.startsWith("RELIC::")) {
        const targetId = raw.replace("RELIC::", "").trim();
        
        // 1. 发起提取请求 (受益人视角)
        const { data, error } = await client.from('vaults').select('*').eq('id', targetId).maybeSingle();
        
        if (!data) {
            return Swal.fire({icon:'error', title:'已销毁或不存在', text:'无法找回此遗物。'});
        }

        // 2. 判定是否为“第一次开启”
        if (data.status === 'pending') {
            // 受益人成功触发解密，此时才拔掉拉环！
            const { error: upError } = await client.from('vaults').update({ 
                status: 'reading', 
                last_checkin_at: new Date().toISOString() 
            }).eq('id', targetId);
            
            if (!upError) {
                Swal.fire({
                    icon:'warning', title:'自毁倒计时启动',
                    text:'遗言已在您的屏幕显现。数据将在 30分钟 后物理注销。',
                    background:'#141414', color:'#d4c5a9'
                });
            }
        } else if (data.status === 'reading') {
            const left = Math.ceil(30 - (new Date() - new Date(data.last_checkin_at))/60000);
            if (left <= 0) return Swal.fire({icon:'error', title:'已过期销毁'});
        }

        raw = data.encrypted_data;
    }

    // 3. 身份锁死解密
    const result = decryptData(raw, sessionUser.email);
    if (result) {
        document.getElementById('de_output').innerText = result;
        document.getElementById('de_output').classList.remove('hidden');
    } else {
        Swal.fire({icon:'error', title:'身份不匹配', text:'登录账号无权解开此遗物。'});
    }
}
