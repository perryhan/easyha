/* EasyHA 易家 · 初始化向导（重写后的网页结构，移动优先）
 *
 * 数据全部来自本机门户 API（/api/*），HA 相关操作由门户经 Supervisor/HA 官方 API 完成。
 * 流程：欢迎 → 连WiFi（需要时）→ 创建账号 → 一键装机 → 进度 → 完成
 */
'use strict';

const $ = (sel, root) => (root || document).querySelector(sel);
const app = $('#app');

const H = (strings, ...vals) => strings.reduce((acc, s, i) => acc + s + (vals[i] ?? ''), '');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.body ? 'POST' : 'GET',
    headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `请求失败 (${res.status})`);
  return data;
}

let status = null;
let selectedWifi = null;

/* ---------------------------------------------------------------- 视图 */

function go(html) {
  app.innerHTML = H`${html}`;
  window.scrollTo(0, 0);
}

function hero(title, sub) {
  return H`<div class="hero">
    <div class="logo">🏠</div><h1>${esc(title)}</h1><p>${sub || ''}</p>
  </div>`;
}

function tip(kind, msg) {
  return H`<div class="tip ${kind}">${esc(msg)}</div>`;
}

function msg(kind, text) {
  const el = $('#msg');
  if (el) el.innerHTML = kind ? tip(kind, text) : '';
}

/* ---------------------------------------------------------------- 欢迎页 */

function screenWelcome() {
  const s = status;
  const needWifi = s.mode === 'ap' || s.mode === 'offline';
  const online = s.mode === 'wifi' || s.mode === 'ethernet';
  go(H`
    ${hero(s.home_name || '易家', '基于 Home Assistant · 家庭智能中心')}
    <div class="card">
      <h2>开始设置</h2>
      <p class="sub">整个过程约 3 分钟，完成后你的手机就能像米家一样控制全屋设备。</p>
      ${online ? tip('ok', `设备已联网（${s.mode === 'wifi' ? 'WiFi: ' + esc(s.wifi?.ssid || '') : '有线'}），可以直接完成初始化。`)
               : needWifi ? `<div class="tip">${s.mode === 'ap'
                 ? `请先用手机连接热点 <b>${esc(s.ap?.ssid || 'EasyHA-Setup')}</b>，然后选择家里的 WiFi。`
                 : '设备尚未联网，请先完成 WiFi 配置。'}</div>` : ''}
      <div id="msg"></div>
      ${needWifi
        ? `<button class="btn" id="toWifi">连接 WiFi</button>`
        : `<button class="btn" id="toAccount">开始初始化</button>`}
      ${online ? `<button class="btn plain" id="toWifi">重新配置 WiFi</button>` : ''}
    </div>
    <div class="footer">EasyHA · 让智能家居更简单</div>
  `);
  const goWifi = $('#toWifi');
  if (goWifi) goWifi.onclick = () => screenWifi();
  const toAcc = $('#toAccount');
  if (toAcc) toAcc.onclick = () => screenAccount();
}

/* ---------------------------------------------------------------- WiFi 配网 */

async function screenWifi() {
  go(H`
    ${hero('连接 WiFi', '选择家里的 WiFi 并输入密码')}
    <div class="card">
      <h2>附近的网络</h2>
      <div id="list"><span class="spin"></span> 正在扫描…</div>
      <div id="msg"></div>
    </div>
    <button class="btn plain" id="back">返回</button>
  `);
  $('#back').onclick = () => screenWelcome();
  try {
    const { list } = await api('/api/wifi/list');
    renderWifiList(list);
  } catch (e) {
    $('#list').textContent = '扫描失败：' + e.message;
  }
}

function signalBars(v) {
  return v >= 80 ? '███' : v >= 55 ? '██_' : '█__';
}

function renderWifiList(list) {
  const box = $('#list');
  if (!list.length) {
    box.innerHTML = '未发现 WiFi，请靠近设备后 <a href="javascript:location.reload()">重新扫描</a>';
    return;
  }
  box.innerHTML = H`${list.map((w) => H`
    <div class="wifi-row" data-ssid="${esc(w.ssid)}">
      <span class="name">${esc(w.ssid)}</span>
      ${w.security !== '开放' ? '<span class="lock">🔒</span>' : ''}
      <span class="sig">${signalBars(w.strength)} ${w.strength}%</span>
    </div>`).join('')}`;
  box.querySelectorAll('.wifi-row').forEach((row) => {
    row.onclick = () => {
      box.querySelectorAll('.wifi-row').forEach((r) => r.classList.remove('selected'));
      row.classList.add('selected');
      const w = list.find((x) => x.ssid === row.dataset.ssid);
      selectedWifi = w;
      screenWifiPassword(w);
    };
  });
}

function screenWifiPassword(w) {
  go(H`
    ${hero('输入密码', `连接到 <b>${esc(w.ssid)}</b>`)}
    <div class="card">
      <div class="field">
        <label>WiFi 密码${w.security === '开放' ? '（开放网络可留空）' : ''}</label>
        <input id="psk" type="password" placeholder="WiFi 密码" autocomplete="current-password">
      </div>
      <div id="msg"></div>
      <button class="btn" id="connect">连接</button>
      <button class="btn ghost" id="rescan">重新选择网络</button>
    </div>
  `);
  $('#rescan').onclick = () => screenWifi();
  $('#connect').onclick = async () => {
    const psk = $('#psk').value;
    try {
      msg(null);
      $('#connect').disabled = true;
      await api('/api/wifi/connect', { body: { ssid: w.ssid, psk } });
      screenConnecting(w.ssid);
    } catch (e) {
      msg('err', e.message);
      $('#connect').disabled = false;
    }
  };
}

function screenConnecting(ssid) {
  go(H`
    ${hero('正在连接', `正在让设备连上 ${esc(ssid)}…`)}
    <div class="card">
      <p><span class="spin"></span> <span id="hint">请保持手机在本页面，通常 10~30 秒。</span></p>
      <div id="msg"></div>
    </div>
  `);
  const timer = setInterval(async () => {
    try {
      const s = await api('/api/status');
      if (s.mode === 'wifi' || s.mode === 'ethernet') {
        clearInterval(timer);
        screenWifiDone(s);
      } else if (s.wifi_error && !s.connecting) {
        clearInterval(timer);
        go(H`
          ${hero('连接失败', '')}
          <div class="card">${tip('err', s.wifi_error)}
            <button class="btn" id="retry">重新输入密码</button>
          </div>`);
        $('#retry').onclick = () => screenWifi();
      }
    } catch (e) { /* 门户短暂不可达（网络切换）时继续等 */ }
  }, 2000);
}

function screenWifiDone(s) {
  const ip = s.wifi?.ip || s.network?.eth_ip || '';
  go(H`
    ${hero('连接成功 🎉', `设备已连上 <b>${esc(s.wifi?.ssid || 'WiFi')}</b>`)}
    <div class="card">
      <div class="tip ok">设备已断开热点。请把<b>手机也切回家里同一个 WiFi</b>，然后扫描/打开下方地址继续设置。</div>
      <div class="qrbox">
        <img id="qr" alt="二维码" src="/api/qr?text=${encodeURIComponent('http://easyha.local')}">
        <div class="url">http://easyha.local</div>
        <p class="sub">扫码或手动访问${ip ? `，也可直接打开 <b>http://${esc(ip)}</b>` : ''}</p>
      </div>
      <div class="tip">本页面会自动检测：手机回到同一网络后点击下方按钮继续。</div>
      <button class="btn" id="check">我已切回 WiFi，继续</button>
    </div>
  `);
  $('#check').onclick = async () => {
    try {
      const s2 = await api('/api/status');
      if (s2.mode === 'ap' || s2.mode === 'offline') {
        msg('err', '还没有检测到连接，请确认手机与设备在同一 WiFi 后重试');
        return;
      }
      status = s2;
      screenAccount();
    } catch (e) {
      msg('err', '暂时无法访问设备：' + e.message);
    }
  };
}

/* ---------------------------------------------------------------- 创建账号 */

function screenAccount() {
  go(H`
    ${hero('创建管理员', '这是你控制全家设备的账号')}
    <div class="card">
      <div class="field"><label>称呼（家庭里显示）</label>
        <input id="name" type="text" value="管理员" placeholder="如：爸爸"></div>
      <div class="field"><label>账号（用户名）</label>
        <input id="username" type="text" placeholder="如：admin" autocapitalize="off"></div>
      <div class="field"><label>密码（至少 4 位）</label>
        <input id="password" type="password" placeholder="设置密码"></div>
      <div id="msg"></div>
      <button class="btn" id="create">创建并继续</button>
    </div>
    <button class="btn plain" id="skip">已有账号？跳过</button>
  `);
  $('#skip').onclick = () => screenOptions();
  $('#create').onclick = async () => {
    const name = $('#name').value.trim();
    const username = $('#username').value.trim();
    const password = $('#password').value;
    if (!username || password.length < 4) { msg('err', '请填写账号和至少 4 位密码'); return; }
    try {
      $('#create').disabled = true;
      await api('/api/wizard/account', { body: { name, username, password } });
      screenOptions({ username });
    } catch (e) {
      msg('err', e.message);
      $('#create').disabled = false;
    }
  };
}

/* ---------------------------------------------------------------- 一键装机 */

function screenOptions(opts = {}) {
  go(H`
    ${hero('一键配置', '自动安装主流插件并识别设备')}
    <div class="card">
      <div class="field"><label>家庭名称</label>
        <input id="home" type="text" value="${esc(status.home_name || '易家')}"></div>
      <label class="checkline">
        <input id="trusted" type="checkbox" checked>
        <span>家庭 WiFi 免登录<small>连上家里 WiFi 打开控制台即可自动登录（推荐家用开启）</small></span>
      </label>
      <label class="checkline">
        <input id="xiaomi" type="checkbox" checked>
        <span>绑定小米账号<small>自动接入米家设备（台灯、传感器、扫地机等），需要小米账号密码</small></span>
      </label>
      <div id="xiaomiFields">
        <div class="field"><label>小米账号（手机号/邮箱）</label>
          <input id="xu" type="text" autocapitalize="off" placeholder="小米账号"></div>
        <div class="field"><label>小米账号密码</label>
          <input id="xp" type="password" placeholder="小米账号密码"></div>
      </div>
      ${tip('', '将自动完成：安装小米 Miot 集成、HACS、文件编辑器、Samba、终端，开启设备发现，重启生效。')}
      <div id="msg"></div>
      <button class="btn" id="apply">开始自动配置</button>
    </div>
  `);
  $('#xiaomi').onchange = (e) => { $('#xiaomiFields').style.display = e.target.checked ? '' : 'none'; };
  $('#apply').onclick = async () => {
    const body = {
      home_name: $('#home').value.trim() || '易家',
      trusted_lan: $('#trusted').checked,
      xiaomi_user: $('#xiaomi').checked ? $('#xu').value.trim() : '',
      xiaomi_pass: $('#xiaomi').checked ? $('#xp').value : '',
    };
    if ($('#xiaomi').checked && (!body.xiaomi_user || !body.xiaomi_pass)) {
      msg('err', '请填写小米账号与密码，或取消勾选');
      return;
    }
    try {
      $('#apply').disabled = true;
      await api('/api/wizard/apply', { body });
      screenProgress();
    } catch (e) {
      msg('err', e.message);
      $('#apply').disabled = false;
    }
  };
}

/* ---------------------------------------------------------------- 进度 */

const STEP_NAMES = {
  components: '安装主流集成（小米 Miot / HACS）',
  panel: '写入「易家」面板与配置',
  addons: '安装常用插件（编辑器/Samba/终端）',
  restart: '重启 Home Assistant',
  discovery: '识别设备并完成收尾',
};

function screenProgress() {
  go(H`
    ${hero('正在自动配置', '一般 1~3 分钟，可以放着不管')}
    <div class="card">
      <ul class="steps" id="steps"></ul>
      <div class="logbox" id="logs"></div>
      <div id="msg"></div>
    </div>
  `);
  const timer = setInterval(async () => {
    try {
      const p = await api('/api/wizard/progress');
      $('#steps').innerHTML = H`${Object.keys(STEP_NAMES).map((id) => {
        const st = (p.steps || {})[id] || { status: 'pending' };
        return H`<li class="${st.status}">
          <span class="dot"></span><span>${STEP_NAMES[id]}</span>
          <span class="st">${st.status === 'done' ? '完成' : st.status === 'running' ? '进行中' : st.status === 'error' ? '失败' : '等待'}</span>
        </li>`;
      }).join('')}`;
      const logs = $('#logs');
      if (logs) { logs.textContent = (p.log || []).join('\n'); logs.scrollTop = logs.scrollHeight; }
      if (p.done) {
        clearInterval(timer);
        screenDone();
      } else {
        const failed = Object.values(p.steps || {}).some((s) => s.status === 'error');
        if (failed) {
          clearInterval(timer);
          msg('err', '部分步骤失败（详见日志）。常用功能一般仍可用，可稍后在插件里重试，或继续进入面板。');
          const btn = document.createElement('button');
          btn.className = 'btn ghost';
          btn.textContent = '仍然继续';
          btn.onclick = () => screenDone();
          $('#msg').appendChild(btn);
        }
      }
    } catch (e) { /* 重启 HA 期间门户仍在，忽略瞬时错误 */ }
  }, 2000);
}

/* ---------------------------------------------------------------- 完成 / 落地页 */

function screenDone() {
  go(H`
    ${hero('一切就绪 🎉', '开始体验你的智能家居')}
    <div class="card">
      <a class="biglink" href="${esc(status?.ha_url || 'http://easyha.local:8123')}" target="_blank">
        🏠 打开易家控制台<small>建议「添加到主屏幕」，体验如 App</small><span class="arrow">›</span>
      </a>
      <div class="qrbox">
        <img alt="控制台二维码" src="/api/qr?text=${encodeURIComponent(status?.ha_url || 'http://easyha.local:8123')}">
        <div class="url">${esc(status?.ha_url || 'http://easyha.local:8123')}</div>
      </div>
      <div id="xiaomiSlot"></div>
      ${tip('', '提示：打开控制台后用你刚创建的账号登录；若开启了「免登录」，家里 WiFi 下会直接进入。')}
      <button class="btn ghost" id="bindXiaomi">绑定小米账号 / 配置集成</button>
    </div>
  `);
  $('#bindXiaomi').onclick = () => bindFlow('xiaomi_miot', $('#xiaomiSlot'));
}

async function screenLanding() {
  go(H`
    ${hero(status.home_name || '易家', '设备已配置完成')}
    <div class="card">
      <a class="biglink" href="${esc(status.ha_url)}" target="_blank">
        🏠 打开易家控制台<small>http://easyha.local:8123</small><span class="arrow">›</span>
      </a>
      <div class="qrbox">
        <img alt="控制台二维码" src="/api/qr?text=${encodeURIComponent(status.ha_url)}">
        <div class="url">${esc(status.ha_url)}</div>
      </div>
      <div id="xiaomiSlot"></div>
      <button class="btn ghost" id="bindXiaomi">绑定小米账号 / 配置集成</button>
      <button class="btn plain" id="redo">重新运行向导</button>
    </div>
    <div class="footer">EasyHA v${esc(status.version)}</div>
  `);
  $('#bindXiaomi').onclick = () => bindFlow('xiaomi_miot', $('#xiaomiSlot'));
  $('#redo').onclick = () => { status.setup_done = false; screenWelcome(); };
}

/* ---------------------------------------------------------------- 通用配置流渲染器（绑定小米账号等） */

async function bindFlow(handler, slot) {
  slot.innerHTML = H`<div class="tip"><span class="spin"></span> 正在发起配置…</div>`;
  let flow;
  try {
    flow = await api('/api/ha/config/config_entries/flow', { body: { handler } });
  } catch (e) { slot.innerHTML = tip('err', '发起配置失败：' + e.message); return; }
  renderFlowStep(flow, slot);
}

function renderFlowStep(flow, slot) {
  if (flow.type === 'create_entry') {
    slot.innerHTML = tip('ok', '✅ 配置成功！设备已加入。');
    return;
  }
  if (flow.type === 'abort') {
    slot.innerHTML = tip('err', '配置中止：' + esc(flow.reason || '未知原因'));
    return;
  }
  const schema = (flow.step && flow.step.data_schema) || [];
  slot.innerHTML = H`
    <div class="card">
      <h2>${esc(flow.title || '配置')}</h2>
      ${schema.map((f) => renderField(f)).join('')}
      <div id="flowMsg"></div>
      <button class="btn" id="flowSubmit">提交</button>
    </div>`;
  $('#flowSubmit', slot).onclick = async () => {
    const data = {};
    schema.forEach((f) => {
      const input = $(`#f_${f.name}`, slot);
      if (!input) return;
      if (f.__bool) data[f.name] = input.checked;
      else if (f.__int) { if (input.value !== '') data[f.name] = Number(input.value); }
      else data[f.name] = input.value;
    });
    try {
      $('#flowMsg').innerHTML = '';
      $('#flowSubmit').disabled = true;
      const next = await api(`/api/ha/config/config_entries/flow/${flow.flow_id}`, { body: data });
      renderFlowStep(next, slot);
    } catch (e) {
      $('#flowMsg').innerHTML = tip('err', e.message);
      $('#flowSubmit').disabled = false;
    }
  };
}

function renderField(f) {
  const name = esc(f.name);
  const req = f.required !== false;
  const sel = f.selector || {};
  if (sel.boolean) {
    f.__bool = true;
    return H`<label class="checkline"><input id="f_${name}" type="checkbox" ${f.default ? 'checked' : ''}>
      <span>${esc(f.name)}</span></label>`;
  }
  if (sel.select || f.type === 'select') {
    // 兼容两种形态：HA selector（selector.select.options）与顶层 options
    const opts = (sel.select && sel.select.options) || f.options || [];
    const norm = opts.map((o) => (Array.isArray(o) ? { value: o[0], label: o[1] } : o));
    return H`<div class="field"><label>${esc(f.name)}</label>
      <select id="f_${name}">${norm.map((o) => H`<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('')}</select></div>`;
  }
  const isSecret = (sel.text && sel.text.type === 'password') || f.type === 'password';
  if (sel.number || f.type === 'integer' || f.type === 'float') { f.__int = true; }
  return H`<div class="field"><label>${esc(f.name)}</label>
    <input id="f_${name}" type="${isSecret ? 'password' : 'text'}" ${req ? '' : ''} value="${esc(f.default ?? '')}"></div>`;
}

/* ---------------------------------------------------------------- 入口 */

async function boot() {
  try {
    status = await api('/api/status');
  } catch (e) {
    app.innerHTML = H`<div class="boot">无法连接设备（${esc(e.message)}）。<br>
      请确认手机已连接到热点 <b>EasyHA-Setup</b> 或与设备同一 WiFi。</div>`;
    return;
  }
  if (status.setup_done) { screenLanding(); return; }
  screenWelcome();
}

boot();
