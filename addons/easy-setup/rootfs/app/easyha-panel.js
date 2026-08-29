/* EasyHA 「易家」面板 —— 米家式日常控制首页
 *
 * 以 panel_custom 模块方式挂载在 Home Assistant 内（configuration.yaml）：
 *   panel_custom:
 *     - name: easyha
 *       module_url: /local/easyha/app.js
 * 同源运行，天然获得 hass 对象（认证、状态、服务调用全部来自 HA 官方前端能力）。
 * 本文件不依赖任何构建工具，也不自建后端。
 */
'use strict';

const STYLE = `
:host { display:block; }
.wrap { max-width: 640px; margin: 0 auto; padding: 16px 16px 32px; }
.head { display:flex; align-items:center; gap:10px; padding: 6px 4px 14px; }
.head .logo { width:38px;height:38px;border-radius:12px;background:var(--primary-color,#2f6bff);
  color:#fff;display:grid;place-items:center;font-size:20px; }
.head h1 { font-size:20px; margin:0; font-weight:700; flex:1; }
.head a.more { color:var(--primary-color,#2f6bff); text-decoration:none; font-size:13px; }
.rooms { display:flex; gap:8px; overflow-x:auto; padding: 2px 2px 12px; scrollbar-width:none; }
.rooms::-webkit-scrollbar { display:none; }
.chip { flex:none; padding:8px 16px; border-radius:999px; background:var(--card-bg-color,#fff);
  border:1px solid var(--divider-color,#e8eaee); font-size:14px; cursor:pointer; color:var(--primary-text-color,#1a1d21); }
.chip.on { background:var(--primary-color,#2f6bff); border-color:var(--primary-color,#2f6bff); color:#fff; }
.grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
@media (min-width: 560px) { .grid { grid-template-columns:repeat(3,1fr); } }
.tile { background:var(--card-bg-color,#fff); border-radius:16px; padding:14px;
  box-shadow:0 1px 3px rgba(0,0,0,.06); cursor:pointer; user-select:none;
  display:flex; flex-direction:column; gap:8px; min-height:96px; }
.tile .icon { width:36px;height:36px;border-radius:50%;display:grid;place-items:center;
  background:var(--secondary-background-color,#f2f3f5); color:var(--state-icon-color,#6b7280); }
.tile.on .icon { background:var(--primary-color,#2f6bff); color:#fff; }
.tile .name { font-size:14px; font-weight:600; line-height:1.35; }
.tile .state { font-size:12px; color:var(--secondary-text-color,#6b7280); }
.tile .ops { margin-top:auto; display:flex; gap:6px; }
.tile .ops button { flex:1; border:0; border-radius:10px; padding:7px 0; font-size:12px;
  background:var(--secondary-background-color,#f2f3f5); color:var(--primary-text-color,#1a1d21); cursor:pointer; }
.room-title { font-size:15px; font-weight:700; margin: 14px 4px 10px; }
.empty { text-align:center; color:var(--secondary-text-color,#6b7280); padding:48px 0; }
.loading { text-align:center; padding:48px 0; color:var(--secondary-text-color,#6b7280); }
`;

const DOMAIN_ICON = {
  light: 'mdi:lightbulb', switch: 'mdi:toggle-switch', fan: 'mdi:fan',
  climate: 'mdi:air-conditioner', cover: 'mdi:window-open-variant', humidifier: 'mdi:air-humidifier',
  media_player: 'mdi:speaker', vacuum: 'mdi:robot-vacuum', lock: 'mdi:lock',
  water_heater: 'mdi:kettle', camera: 'mdi:cctv', button: 'mdi:gesture-tap-button',
  sensor: 'mdi:gauge', binary_sensor: 'mdi:radar', number: 'mdi:tune', select: 'mdi:format-list-bulleted',
};

const ON_DOMAINS = new Set(['light', 'switch', 'fan', 'humidifier', 'media_player']);

const TOGGLABLE = new Set(['light', 'switch', 'fan', 'humidifier']);
const DISPLAY_DOMAINS = [
  'light', 'switch', 'fan', 'climate', 'cover', 'humidifier', 'media_player',
  'vacuum', 'lock', 'water_heater', 'camera', 'number', 'select', 'button',
  'sensor', 'binary_sensor',
];

function stateIsOn(stateObj) {
  if (!stateObj) return false;
  if (stateObj.entity_id.startsWith('lock.')) return stateObj.state === 'unlocked';
  if (stateObj.entity_id.startsWith('cover.')) return ['open', 'opening'].includes(stateObj.state);
  if (stateObj.entity_id.startsWith('climate.')) return stateObj.state !== 'off';
  return stateObj.state === 'on' || stateObj.state === 'playing' || stateObj.state === 'heat' || stateObj.state === 'cool';
}

function friendly(stateObj) {
  return (stateObj && stateObj.attributes && stateObj.attributes.friendly_name) || stateObj.entity_id;
}

function stateText(stateObj) {
  if (!stateObj) return '不可用';
  const a = stateObj.attributes || {};
  switch (stateObj.entity_id.split('.')[0]) {
    case 'climate': {
      const hvac = { cool: '制冷', heat: '制热', auto: '自动', off: '关闭', dry: '除湿', fan_only: '送风', idle: '待机' };
      const target = a.temperature != null ? ` / 设 ${a.temperature}°C` : '';
      return `${a.current_temperature ?? '--'}°C${target} ${hvac[stateObj.state] || stateObj.state}`;
    }
    case 'cover': return { open: '已打开', opening: '打开中', closed: '已关闭', closing: '关闭中' }[stateObj.state] || stateObj.state;
    case 'media_player': return stateObj.state === 'playing' ? '播放中' : '未播放';
    case 'sensor': case 'binary_sensor': return `${a.device_class === 'temperature' && a.unit_of_measurement ? '' : ''}${stateObj.state}${a.unit_of_measurement ? ' ' + a.unit_of_measurement : ''}`;
    case 'vacuum': return stateObj.state === 'cleaning' ? '清扫中' : stateObj.state;
    default: return stateObj.state;
  }
}

class EasyhaPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._areas = null;
    this._room = '__all__';
    this._lastSig = '';
  }

  set hass(hass) { this._hass = hass; this._schedule(); }
  set panel(panel) { this._panel = panel; }
  set narrow(n) { this._narrow = n; }
  set route(r) { this._route = r; }

  get hass() { return this._hass; }

  connectedCallback() {
    const style = document.createElement('style');
    style.textContent = STYLE;
    this.shadowRoot.appendChild(style);
    this._root = document.createElement('div');
    this.shadowRoot.appendChild(this._root);
    this._root.innerHTML = '<div class="loading">正在载入易家…</div>';
    this._loadRegistry();
  }

  async _loadRegistry() {
    if (!this._hass) return; // hass 尚未注入；首次渲染时会再次触发
    if (this._areas) return;
    this._registryLoading = true;
    // 房间信息来自 HA 官方注册表 API（无则全部归入“全部”）
    try {
      const [areas, devices, entities] = await Promise.all([
        this._callWS({ type: 'config/area_registry/list' }),
        this._callWS({ type: 'config/device_registry/list' }),
        this._callWS({ type: 'config/entity_registry/list' }),
      ]);
      const areaName = {};
      areas.forEach((a) => { areaName[a.area_id] = a.name; });
      const entityArea = {};
      (entities || []).forEach((e) => { if (e.area_id) entityArea[e.entity_id] = e.area_id; });
      (devices || []).forEach((d) => {
        if (!d.area_id) return;
        (d.entities || []).forEach((eid) => { if (!entityArea[eid]) entityArea[eid] = d.area_id; });
      });
      this._areas = { areaName, entityArea };
    } catch (e) {
      this._areas = { areaName: {}, entityArea: {} };
    }
    this._registryLoading = false;
    this._schedule(true);
  }

  _callWS(msg) {
    return new Promise((resolve, reject) => {
      this._hass.connection.sendMessagePromise(msg).then(resolve, reject);
    });
  }

  _schedule(force) {
    if (force) this._lastSig = '';
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = null; this._render(); });
  }

  _entityArea(entityId) {
    if (!this._areas) return '__all__';
    return this._areas.entityArea[entityId] || '__none__';
  }

  _render() {
    const hass = this._hass;
    if (!hass || !this._root) return;
    if (!this._areas && !this._registryLoading) this._loadRegistry();
    const all = DISPLAY_DOMAINS
      .flatMap((d) => Object.keys(hass.states).filter((eid) => eid.startsWith(d + '.')))
      .map((eid) => hass.states[eid])
      .filter(Boolean)
      .filter((s) => s.state !== 'unavailable' && s.state !== 'unknown')
      .sort((a, b) => friendly(a).localeCompare(friendly(b), 'zh-Hans'));

    // 签名包含会显示在卡片上的属性（如空调目标温度），属性变化也要触发重渲染
    const sig = all.map((s) => {
      const a = s.attributes || {};
      return `${s.entity_id}:${s.state}:${a.temperature ?? ''}`;
    }).join('|') + '#' + this._room + '#' + (this._areas ? Object.keys(this._areas.entityArea).length : -1);
    if (sig === this._lastSig) return;
    this._lastSig = sig;

    // 房间清单
    const roomIds = [...new Set(all.map((s) => this._entityArea(s.entity_id)))];
    const rooms = [{ id: '__all__', name: '全部' },
      ...roomIds.filter((r) => r !== '__none__').map((r) => ({ id: r, name: (this._areas.areaName[r]) || r })),
      ...(roomIds.includes('__none__') ? [{ id: '__none__', name: '未分配' }] : [])];

    const shown = this._room === '__all__' ? all : all.filter((s) => this._entityArea(s.entity_id) === this._room);
    const home = hass.user && hass.user.name ? hass.user.name : '';

    this._root.innerHTML = `
      <div class="wrap">
        <div class="head">
          <div class="logo">🏠</div>
          <h1>${hass.config && hass.config.location_name ? hass.config.location_name : '易家'}</h1>
          <a class="more" href="/config">更多设置 ›</a>
        </div>
        <div class="rooms">${rooms.map((r) => `
          <span class="chip ${r.id === this._room ? 'on' : ''}" data-room="${r.id}">${r.name}</span>`).join('')}
        </div>
        ${shown.length ? `<div class="grid">${shown.map((s) => this._tile(s)).join('')}</div>`
          : `<div class="empty">还没有设备<br><br>到 <a href="/config/integrations">设备与服务</a> 添加，或在易家向导里绑定小米账号。</div>`}
      </div>`;

    this._root.querySelectorAll('.chip').forEach((chip) => {
      chip.onclick = () => { this._room = chip.dataset.room; this._lastSig = ''; this._render(); };
    });
    this._root.querySelectorAll('[data-entity]').forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.dataset.op) return;
        this._tap(el.dataset.entity);
      };
      el.querySelectorAll('button[data-op]').forEach((btn) => {
        btn.onclick = (ev) => { ev.stopPropagation(); this._op(el.dataset.entity, btn.dataset.op); };
      });
    });
  }

  _tile(s) {
    const domain = s.entity_id.split('.')[0];
    const on = stateIsOn(s);
    const icon = DOMAIN_ICON[domain] || 'mdi:chip';
    const ops = this._ops(domain, s);
    return `
      <div class="tile ${on ? 'on' : ''}" data-entity="${s.entity_id}">
        <div class="icon"><ha-icon icon="${icon}"></ha-icon></div>
        <div class="name">${friendly(s)}</div>
        <div class="state">${stateText(s)}</div>
        ${ops ? `<div class="ops">${ops}</div>` : ''}
      </div>`;
  }

  _ops(domain, s) {
    switch (domain) {
      case 'climate': return `<button data-op="temp-">－</button><button data-op="temp+">＋</button>`;
      case 'cover': return `<button data-op="open">打开</button><button data-op="close">关闭</button>`;
      case 'media_player': return `<button data-op="playpause">${stateIsOn(s) ? '暂停' : '播放'}</button>`;
      case 'vacuum': return `<button data-op="start">开始清扫</button><button data-op="home">回充</button>`;
      case 'lock': return `<button data-op="lock">${stateIsOn(s) ? '上锁' : '开锁'}</button>`;
      default: return '';
    }
  }

  _tap(entityId) {
    const domain = entityId.split('.')[0];
    if (TOGGLABLE.has(domain)) {
      this._hass.callService('homeassistant', 'toggle', { entity_id: entityId });
    } else if (domain === 'button') {
      this._hass.callService('button', 'press', { entity_id: entityId });
    } else if (domain === 'cover' || domain === 'climate' || domain === 'media_player'
      || domain === 'vacuum' || domain === 'lock') {
      // 带操作按钮的领域由按钮处理；点击卡片本身切换开/关
      if (domain === 'media_player') {
        this._hass.callService('media_player', 'media_play_pause', { entity_id: entityId });
      } else if (domain === 'climate') {
        this._hass.callService('homeassistant', 'toggle', { entity_id: entityId });
      }
    }
  }

  _op(entityId, op) {
    const domain = entityId.split('.')[0];
    const hass = this._hass;
    const stateObj = hass.states[entityId];
    switch (op) {
      case 'temp+': case 'temp-': {
        const step = 0.5;
        const cur = (stateObj && stateObj.attributes.temperature) || 23;
        hass.callService('climate', 'set_temperature', {
          entity_id: entityId, temperature: Number(cur) + (op === 'temp+' ? step : -step),
        });
        break;
      }
      case 'open': hass.callService('cover', 'open_cover', { entity_id: entityId }); break;
      case 'close': hass.callService('cover', 'close_cover', { entity_id: entityId }); break;
      case 'start': hass.callService('vacuum', 'start', { entity_id: entityId }); break;
      case 'home': hass.callService('vacuum', 'return_to_base', { entity_id: entityId }); break;
      case 'lock': hass.callService('lock', stateIsOn(stateObj) ? 'lock' : 'unlock', { entity_id: entityId }); break;
      default: break;
    }
  }
}

customElements.define('easyha-panel', EasyhaPanel);
