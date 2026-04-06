HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude History Viewer</title>
<style>
/* ── Variables ── */
:root {
  --bg: #f0f2f5;
  --sidebar-bg: #ffffff;
  --header-bg: #6366f1;
  --bubble-user: #6366f1;
  --bubble-user-text: #ffffff;
  --bubble-ai: #ffffff;
  --bubble-ai-text: #1a1a2e;
  --bubble-tool: #f0f4ff;
  --bubble-tool-text: #4b5563;
  --thinking-bg: #fef9c3;
  --thinking-text: #78350f;
  --border: #e5e7eb;
  --text: #1f2937;
  --text-muted: #6b7280;
  --accent: #6366f1;
  --accent-hover: #4f46e5;
  --tag-bg: #e0e7ff;
  --tag-text: #4338ca;
  --star-color: #f59e0b;
  --search-bg: #f9fafb;
  --chip-bg: #e5e7eb;
  --chip-text: #374151;
  --session-active: #ede9fe;
  --session-hover: #f5f3ff;
  --shadow: 0 1px 3px rgba(0,0,0,.1);
  --font-size: 14px;
  --radius: 18px;
  --font-family: 'Cascadia Code','Cascadia Mono',Consolas,'BIZ UDGothic','Noto Sans Mono',monospace;
}
[data-theme="dark"] {
  --bg: #0f1117;
  --sidebar-bg: #1a1d27;
  --header-bg: #312e81;
  --bubble-user: #4f46e5;
  --bubble-user-text: #ffffff;
  --bubble-ai: #1e2131;
  --bubble-ai-text: #e2e8f0;
  --bubble-tool: #1a2040;
  --bubble-tool-text: #94a3b8;
  --thinking-bg: #2d2208;
  --thinking-text: #fde68a;
  --border: #2d3148;
  --text: #e2e8f0;
  --text-muted: #9ca3af;
  --accent: #818cf8;
  --accent-hover: #6366f1;
  --tag-bg: #1e1b4b;
  --tag-text: #a5b4fc;
  --star-color: #fbbf24;
  --search-bg: #1a1d27;
  --chip-bg: #2d3148;
  --chip-text: #cbd5e1;
  --session-active: #1e1b4b;
  --session-hover: #1a1d35;
  --shadow: 0 1px 3px rgba(0,0,0,.4);
}
/* ── Reset ── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:var(--font-family);font-size:var(--font-size);background:var(--bg);color:var(--text)}
button{cursor:pointer;border:none;background:none;font:inherit;color:inherit}
input{font:inherit;color:inherit}
/* ── Layout ── */
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}
#header{background:var(--header-bg);color:#fff;display:flex;align-items:center;gap:8px;padding:0 16px;height:52px;flex-shrink:0}
#header h1{font-size:16px;font-weight:700;flex:1;white-space:nowrap}
.hbtn{padding:6px 10px;border-radius:8px;color:#fff;opacity:.85;transition:opacity .15s,background .15s;font-size:13px}
.hbtn:hover{opacity:1;background:rgba(255,255,255,.15)}
.hbtn.active{opacity:1;background:rgba(255,255,255,.25)}
#font-select{padding:5px 8px;border-radius:8px;border:none;background:rgba(255,255,255,.15);color:#fff;font-size:12px;cursor:pointer;opacity:.85}
#font-select:hover{opacity:1;background:rgba(255,255,255,.25)}
#font-select option{background:#312e81;color:#fff}
#main{display:flex;flex:1;overflow:hidden}
/* ── Sidebar ── */
#sidebar{width:280px;min-width:200px;max-width:380px;background:var(--sidebar-bg);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
#sidebar-header{padding:12px 14px 8px;border-bottom:1px solid var(--border);flex-shrink:0}
#sidebar-search{width:100%;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:13px;outline:none}
#sidebar-search:focus{border-color:var(--accent)}
#project-list{flex:1;overflow-y:auto;padding:6px 0}
.proj-header{display:flex;align-items:center;gap:6px;padding:9px 12px 9px 14px;cursor:pointer;user-select:none;border-bottom:1px solid var(--border);margin-top:2px}
.proj-header:first-child{margin-top:0}
.proj-header:hover{background:var(--session-hover)}
.proj-header.open{border-bottom-color:transparent}
.proj-caret{font-size:10px;transition:transform .15s;display:inline-block;color:var(--text-muted);flex-shrink:0}
.proj-header.open .proj-caret{transform:rotate(90deg)}
.proj-icon{font-size:13px;flex-shrink:0}
.proj-name{font-weight:700;font-size:12px;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:.01em;display:flex;align-items:center;gap:3px}
.proj-badge{font-size:10px;flex-shrink:0}
.proj-name-edit{font-weight:700;font-size:12px;flex:1;border:none;border-bottom:1px solid var(--accent);background:transparent;color:var(--text);outline:none;padding:0;min-width:0}
/* Context menu */
#ctx-menu,#sess-ctx-menu{position:fixed;z-index:500;background:var(--sidebar-bg);border:1px solid var(--border);border-radius:8px;padding:4px 0;box-shadow:0 4px 16px rgba(0,0,0,.2);min-width:160px;display:none}
#ctx-menu.open,#sess-ctx-menu.open{display:block}
.ctx-item{padding:7px 14px;font-size:13px;cursor:pointer;white-space:nowrap}
.ctx-item:hover{background:var(--session-hover)}
.ctx-sep{height:1px;background:var(--border);margin:3px 0}
.proj-hidden{opacity:.4}
.sess-hidden{opacity:.4}
#btn-show-hidden.active{color:var(--accent);opacity:1}
#help-modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5);display:none}
#help-modal.open{display:flex}
#help-box{background:var(--sidebar-bg);border-radius:12px;padding:20px 24px;min-width:320px;max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
#help-box h3{margin-bottom:14px;font-size:15px}
.help-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;font-size:13px;border-bottom:1px solid var(--border)}
.help-row:last-child{border-bottom:none}
.help-key{font-family:monospace;background:var(--chip-bg);padding:2px 7px;border-radius:5px;font-size:12px;color:var(--text-muted)}
.proj-open-btn{font-size:14px;font-weight:700;opacity:0;padding:2px 5px;border-radius:4px;color:var(--accent);transition:opacity .15s,background .15s;flex-shrink:0;cursor:alias;line-height:1}
.proj-header:hover .proj-open-btn{opacity:.8}
.proj-open-btn:hover{opacity:1!important;background:rgba(99,102,241,.15)}
.proj-count{font-size:10px;color:var(--text-muted);background:var(--chip-bg);padding:1px 6px;border-radius:8px;flex-shrink:0}
.session-list{display:none;padding:4px 8px 8px 20px;border-left:2px solid var(--border);margin:0 0 4px 18px}
.session-list.open{display:block}
.sess-item{padding:6px 8px;border-radius:6px;cursor:pointer;transition:background .1s;margin-bottom:1px}
.sess-item:hover{background:var(--session-hover)}
.sess-item.active{background:var(--session-active)}
.sess-title{font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sess-meta{display:flex;align-items:center;gap:6px;margin-top:2px}
.sess-date{font-size:11px;color:var(--text-muted)}
.sess-count{font-size:11px;color:var(--text-muted)}
.sess-star{color:var(--star-color);font-size:11px}
.sess-tags{display:flex;gap:3px;flex-wrap:wrap}
.tag-chip{font-size:10px;background:var(--tag-bg);color:var(--tag-text);padding:1px 6px;border-radius:10px}
/* ── Chat pane ── */
#chat-pane{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;position:relative}
#chat-header{padding:10px 16px;border-bottom:1px solid var(--border);background:var(--sidebar-bg);flex-shrink:0;display:flex;align-items:center;gap:8px}
.header-sep{width:1px;height:16px;background:var(--border);margin:0 2px;flex-shrink:0}
#session-title{font-weight:600;font-size:14px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#chat-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
/* ── Scroll jump buttons ── */
#scroll-btns{position:absolute;bottom:16px;right:20px;display:flex;flex-direction:column;gap:4px;z-index:10}
.scroll-btn{width:30px;height:30px;border-radius:50%;background:var(--chip-bg);color:var(--text-muted);font-size:14px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:.6;transition:opacity .15s}
.scroll-btn:hover{opacity:1;background:var(--session-hover)}
/* ── Code copy button ── */
.code-wrap{position:relative}
.code-copy-btn{position:absolute;top:6px;right:6px;padding:2px 8px;font-size:11px;border-radius:4px;background:rgba(128,128,128,.2);color:var(--text-muted);cursor:pointer;opacity:0;transition:opacity .15s}
.code-wrap:hover .code-copy-btn{opacity:1}
.code-copy-btn.copied{color:var(--accent);opacity:1}
#chat-empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px;text-align:center;flex-direction:column;gap:8px}
#chat-empty .icon{font-size:48px}
/* ── Compaction notice ── */
.compaction-notice{display:flex;align-items:center;justify-content:center;padding:6px 0 2px}
.compaction-notice span{font-size:12px;color:var(--text-muted);background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:3px 12px}
/* ── Plan block ── */
.plan-block{margin:4px 0;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;background:var(--sidebar-bg)}
.plan-block summary{display:flex;align-items:center;gap:6px;padding:8px 12px;cursor:pointer;font-size:12px;color:var(--text-muted);user-select:none;list-style:none}
.plan-block summary::marker{display:none}
.plan-block summary:hover{background:var(--session-hover)}
.plan-block-body{padding:10px 14px;border-top:1px solid var(--border);max-height:400px;overflow-y:auto}
.plan-block-body .bubble-text{font-size:13px}
/* ── Bubbles ── */
.msg-row{display:flex;flex-direction:column;gap:4px}
.msg-row.user{align-items:flex-end}
.msg-row.assistant{align-items:flex-start}
.msg-ts{font-size:11px;color:var(--text-muted);padding:0 4px}
.msg-ts.hidden{display:none}
.bubble{max-width:72%;padding:10px 14px;border-radius:var(--radius);word-break:break-word;position:relative}
.msg-row.user .bubble{background:var(--bubble-user);color:var(--bubble-user-text);border-bottom-right-radius:4px}
.msg-row.assistant .bubble{background:var(--bubble-ai);color:var(--bubble-ai-text);border-bottom-left-radius:4px;box-shadow:var(--shadow)}
.bubble-text{line-height:1.6;white-space:normal}
.bubble-text p{margin:0 0 .6em}
.bubble-text p:last-child{margin-bottom:0}
.bubble-text code{background:rgba(0,0,0,.1);padding:1px 4px;border-radius:4px;font-size:.9em;font-family:'Cascadia Code','Fira Code',monospace}
.msg-row.user .bubble-text code{background:rgba(255,255,255,.2)}
.bubble-text pre{background:rgba(0,0,0,.12);padding:8px 10px;border-radius:8px;overflow-x:auto;margin:.4em 0}
.msg-row.user .bubble-text pre{background:rgba(255,255,255,.15)}
.bubble-text pre code{background:none;padding:0}
.bubble-text h1{font-size:1.1em;font-weight:700;margin:.5em 0 .15em}.bubble-text h2{font-size:1.05em;font-weight:700;margin:.4em 0 .15em}.bubble-text h3{font-size:1em;font-weight:700;margin:.35em 0 .1em}.bubble-text h1:first-child,.bubble-text h2:first-child,.bubble-text h3:first-child{margin-top:.1em}
.bubble-text ul,.bubble-text ol{padding-left:1.4em;margin:.3em 0}
.bubble-text li{margin:.15em 0}
.bubble-text strong{font-weight:700}
.bubble-text em{font-style:italic}
.bubble-text a{color:inherit;opacity:.8;text-decoration:underline}
/* Tables */
.md-table-wrap{overflow-x:auto;margin:.5em 0;border-radius:6px}
.md-table{border-collapse:collapse;width:100%;font-size:.93em}
.md-table th,.md-table td{border:1px solid rgba(0,0,0,.15);padding:5px 10px;white-space:nowrap;line-height:1.4}
.md-table th{background:rgba(0,0,0,.06);font-weight:600}
.md-table tr:nth-child(even) td{background:rgba(0,0,0,.025)}
.msg-row.user .md-table th,.msg-row.user .md-table td{border-color:rgba(255,255,255,.3)}
.msg-row.user .md-table th{background:rgba(255,255,255,.18)}
.msg-row.user .md-table tr:nth-child(even) td{background:rgba(255,255,255,.08)}
[data-theme="dark"] .md-table th{background:rgba(255,255,255,.07)}
[data-theme="dark"] .md-table th,[data-theme="dark"] .md-table td{border-color:rgba(255,255,255,.1)}
/* Collapsed long messages */
.msg-collapse{margin-top:6px}
.msg-collapse summary{font-size:12px;color:var(--accent);cursor:pointer;user-select:none;list-style:none;padding:2px 0}
.msg-row.user .msg-collapse summary{color:rgba(255,255,255,.7)}
.msg-collapse summary::marker{display:none}
.msg-collapse[open]>summary{display:none}
.collapse-bottom-btn{margin-top:8px;font-size:12px;color:var(--accent);cursor:pointer;user-select:none;padding:2px 0}
.msg-row.user .collapse-bottom-btn{color:rgba(255,255,255,.7)}
/* Thinking */
.thinking-block{margin-top:6px;background:var(--thinking-bg);border-radius:10px;overflow:hidden}
.thinking-summary{padding:6px 10px;cursor:pointer;font-size:12px;color:var(--thinking-text);user-select:none;display:flex;align-items:center;gap:6px}
.thinking-summary::marker{display:none}
.thinking-content{padding:8px 10px;font-size:12px;color:var(--thinking-text);white-space:pre-wrap;max-height:300px;overflow-y:auto;border-top:1px solid rgba(0,0,0,.08)}
/* Tool chips */
.tool-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.tool-chip{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:3px 8px;border-radius:10px;background:var(--chip-bg);color:var(--chip-text);max-width:220px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.tool-icon{flex-shrink:0}
/* Images */
.msg-images{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.msg-images img{max-width:200px;max-height:150px;border-radius:8px;cursor:pointer;border:1px solid var(--border)}
/* Message toolbar */
.msg-toolbar{display:flex;gap:4px;margin-top:4px;visibility:hidden}
.msg-row:hover .msg-toolbar{visibility:visible}
.tbtn{font-size:14px;padding:2px 5px;border-radius:6px;opacity:.6;transition:opacity .1s}
.tbtn:hover{opacity:1;background:var(--chip-bg)}
.tbtn.active{opacity:1;color:var(--star-color)}
.tbtn:disabled{opacity:.25;cursor:default;pointer-events:none}
/* ── Search panel ── */
#search-panel{position:fixed;inset:0;z-index:100;display:flex;align-items:flex-start;justify-content:center;padding-top:60px;background:rgba(0,0,0,.4);display:none}
#search-panel.open{display:flex}
#search-box{background:var(--sidebar-bg);border-radius:12px;width:640px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.3)}
#search-input-row{display:flex;gap:8px;padding:12px 14px;border-bottom:1px solid var(--border);align-items:center}
#search-input{flex:1;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);font-size:14px;outline:none}
#search-input:focus{border-color:var(--accent)}
#search-type{padding:6px 8px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);font-size:13px;color:var(--text)}
#search-scope{padding:6px 8px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);font-size:13px;color:var(--text)}
#search-results{overflow-y:auto;flex:1;padding:8px}
.sr-empty{padding:20px;text-align:center;color:var(--text-muted);font-size:13px}
/* 階層構造 */
.sr-proj{margin-bottom:10px}
.sr-proj-header{font-size:11px;font-weight:700;color:var(--accent);padding:4px 6px;border-radius:6px;background:var(--chip-bg);margin-bottom:4px;display:flex;align-items:center;gap:5px}
.sr-sess{margin-left:10px;margin-bottom:6px;border-left:2px solid var(--border);padding-left:8px}
.sr-sess-header{font-size:11px;font-weight:600;color:var(--text-muted);padding:2px 0 4px;cursor:pointer}
.sr-sess-header:hover{color:var(--accent)}
.sr-item{padding:7px 10px;border-radius:6px;cursor:pointer;margin-bottom:2px}
.sr-item:hover{background:var(--session-hover)}
.sr-snippet{font-size:13px;color:var(--text);line-height:1.5}
.sr-role{font-size:10px;color:var(--text-muted);margin-top:2px}
/* ── Starred panel ── */
#starred-panel{position:fixed;inset:0;z-index:100;display:flex;align-items:flex-start;justify-content:center;padding-top:60px;background:rgba(0,0,0,.4);display:none}
#starred-panel.open{display:flex}
#starred-box{background:var(--sidebar-bg);border-radius:12px;width:600px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.panel-header{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);font-weight:600;font-size:15px}
.panel-header button{margin-left:auto;opacity:.6;font-size:18px}
.panel-header button:hover{opacity:1}
.panel-body{overflow-y:auto;flex:1;padding:10px}
.starred-section-title{font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;padding:6px 8px 4px}
.starred-item{padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:2px}
.starred-item:hover{background:var(--session-hover)}
.starred-item-title{font-size:13px;font-weight:500}
.starred-item-meta{font-size:11px;color:var(--text-muted);margin-top:2px}
.starred-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
/* ── Memo modal ── */
#memo-modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5);display:none}
#memo-modal.open{display:flex}
#memo-box{background:var(--sidebar-bg);border-radius:12px;width:400px;max-width:90vw;padding:16px;display:flex;flex-direction:column;gap:12px}
#memo-box h3{font-size:14px;font-weight:600}
#memo-textarea{padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:13px;resize:vertical;min-height:80px;outline:none}
#memo-textarea:focus{border-color:var(--accent)}
#tag-input{padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:13px;width:100%;outline:none}
#tag-input:focus{border-color:var(--accent)}
.memo-btns{display:flex;gap:8px;justify-content:flex-end}
.btn{padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:var(--accent-hover)}
.btn-ghost{background:var(--chip-bg);color:var(--text)}
/* ── Image lightbox ── */
#lightbox{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;cursor:zoom-out}
#lightbox.open{display:flex}
#lightbox img{max-width:90vw;max-height:90vh;border-radius:8px}
/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
/* ── Resize handle ── */
#resize-handle{width:4px;cursor:col-resize;background:transparent;flex-shrink:0}
#resize-handle:hover,#resize-handle.dragging{background:var(--accent)}
</style>
</head>
<body>
<div id="app">
  <!-- Header -->
  <div id="header">
    <h1>💬 Claude History Viewer</h1>
    <button class="hbtn" id="btn-search" title="検索 (Ctrl+K)">🔍 検索</button>
    <button class="hbtn" id="btn-starred" title="スター一覧">⭐ スター</button>
    <button class="hbtn" id="btn-ts" title="時刻表示切替">🕐 時刻</button>
    <button class="hbtn" id="btn-theme" title="ダーク/ライト切替">🌙</button>
    <button class="hbtn" id="btn-font-down" title="文字小">A-</button>
    <button class="hbtn" id="btn-font-up" title="文字大">A+</button>
    <select id="font-select" title="フォント選択">
      <option value="auto">Fnt: 自動</option>
      <option value="cascadia-code">Cascadia Code</option>
      <option value="cascadia-mono">Cascadia Mono</option>
      <option value="consolas">Consolas</option>
      <option value="biz-ud">BIZ UDゴシック</option>
      <option value="courier-new">Courier New</option>
      <option value="system">System UI</option>
    </select>
    <button class="hbtn" id="btn-help" title="キーボードショートカット (?)">?</button>
  </div>

  <div id="main">
    <!-- Sidebar -->
    <div id="sidebar">
      <div id="sidebar-header">
        <input id="sidebar-search" type="text" placeholder="セッション名・タグで絞り込み…" />
        <button class="tbtn" id="btn-show-hidden" title="非表示項目を表示" style="font-size:13px;margin-top:4px;width:100%;text-align:left;padding:3px 8px">👁 非表示を表示</button>
      </div>
      <div id="project-list"></div>
    </div>

    <div id="resize-handle"></div>

    <!-- Chat pane -->
    <div id="chat-pane">
      <div id="chat-header">
        <button class="tbtn" id="btn-prev-session" title="前のセッション" disabled style="font-size:16px">◀</button>
        <span id="session-title">プロジェクトを選択してください</span>
        <button class="tbtn" id="btn-next-session" title="次のセッション" disabled style="font-size:16px">▶</button>
        <span class="header-sep"></span>
        <button class="tbtn" id="btn-session-star" title="セッションをスター" style="font-size:16px">☆</button>
        <button class="tbtn" id="btn-session-memo" title="メモ・タグ編集" style="font-size:16px">📝</button>
        <span class="header-sep"></span>
        <select id="export-format" title="保存形式" style="padding:3px 6px;border-radius:6px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:12px">
          <option value="html">HTML</option>
          <option value="md">Markdown</option>
        </select>
        <button class="tbtn" id="btn-export" title="保存" style="font-size:16px">💾</button>
      </div>
      <div id="scroll-btns">
        <button class="scroll-btn" id="btn-scroll-top" title="先頭へ">↑</button>
        <button class="scroll-btn" id="btn-scroll-bottom" title="末尾へ">↓</button>
      </div>
      <div id="chat-messages">
        <div id="chat-empty">
          <div class="icon">💬</div>
          <div>左のサイドバーからセッションを選択してください</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Search panel -->
<div id="search-panel">
  <div id="search-box">
    <div id="search-input-row">
      <input id="search-input" type="text" placeholder="検索キーワードを入力…" />
      <select id="search-type">
        <option value="text">テキスト</option>
        <option value="file">ファイル名</option>
      </select>
      <select id="search-scope">
        <option value="">全プロジェクト</option>
      </select>
      <button class="tbtn" id="btn-search-close" style="font-size:18px">✕</button>
    </div>
    <div id="search-results"><div class="sr-empty">キーワードを入力して検索</div></div>
  </div>
</div>

<!-- Project context menu -->
<div id="ctx-menu">
  <div class="ctx-item" id="ctx-star">☆ スター</div>
  <div class="ctx-item" id="ctx-memo">📝 メモ・タグ</div>
  <div class="ctx-item" id="ctx-label">✏️ ラベルを編集</div>
  <div class="ctx-item" id="ctx-open-folder">⧉ フォルダを開く</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item" id="ctx-hide">🙈 非表示にする</div>
</div>

<!-- Session context menu -->
<div id="sess-ctx-menu">
  <div class="ctx-item" id="sess-ctx-hide">🙈 非表示にする</div>
</div>

<!-- Starred panel -->
<div id="starred-panel">
  <div id="starred-box">
    <div class="panel-header">
      ⭐ スター・タグ一覧
      <button id="btn-starred-close" style="font-size:18px">✕</button>
    </div>
    <div class="panel-body" id="starred-body"></div>
  </div>
</div>

<!-- Memo modal -->
<div id="memo-modal">
  <div id="memo-box">
    <h3>📝 メモ・タグ</h3>
    <textarea id="memo-textarea" placeholder="メモを入力…"></textarea>
    <input id="tag-input" type="text" placeholder="タグ (カンマ区切り、例: 重要, バグ修正)" />
    <div class="memo-btns">
      <button class="btn btn-ghost" id="btn-memo-cancel">キャンセル</button>
      <button class="btn btn-primary" id="btn-memo-save">保存</button>
    </div>
  </div>
</div>

<!-- Lightbox -->
<div id="lightbox"><img id="lightbox-img" src="" alt=""></div>

<!-- Help modal -->
<div id="help-modal">
  <div id="help-box">
    <h3>⌨️ キーボードショートカット</h3>
    <div class="help-row"><span>検索パネルを開く</span><span class="help-key">Ctrl + K</span></div>
    <div class="help-row"><span>前のセッションへ</span><span class="help-key">←</span></div>
    <div class="help-row"><span>次のセッションへ</span><span class="help-key">→</span></div>
    <div class="help-row"><span>パネルを閉じる</span><span class="help-key">Escape</span></div>
    <div class="help-row"><span>このヘルプを閉じる</span><span class="help-key">?</span></div>
    <div style="margin-top:14px;text-align:right"><button class="btn btn-ghost" id="btn-help-close">閉じる</button></div>
  </div>
</div>

<script>
// ── State ──
const S = {
  projects: [],
  currentProject: null,
  currentSession: null,
  messages: [],
  meta: { sessions: {}, messages: {} },
  showTs: localStorage.getItem('showTs') !== 'false',
  theme: localStorage.getItem('theme') || 'light',
  fontSize: parseInt(localStorage.getItem('fontSize') || '14'),
  fontKey: localStorage.getItem('fontKey') || 'auto',
  openProjects: new Set(JSON.parse(localStorage.getItem('openProjects') || '[]')),
  memoTarget: null, // { type: 'session'|'message', key, current }
  sidebarFilter: '',
  showHidden: false,
  cfg: { collapse_lines:15, collapse_chars:600, preview_chars:300, show_thinking:true, show_tool_chips:true },
};

// ── API ──
async function api(path) {
  const r = await fetch(path);
  return r.json();
}
async function post(path, data) {
  await fetch(path, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
}

// ── Init ──
async function init() {
  S.cfg = await api('/api/settings');
  applyTheme();
  applyFontSize();
  applyFont();
  applyTsBtn();

  S.projects = await api('/api/projects');
  S.meta = await api('/api/meta');
  renderProjects();
  populateSearchScope();

  // open状態のプロジェクトのセッションを並列ロードして描画
  await Promise.all([...S.openProjects].map(async projId => {
    const sl = document.getElementById('sl-' + projId);
    if (!sl) return;
    const sessions = await api(`/api/sessions?project=${encodeURIComponent(projId)}`);
    for (const s of sessions) {
      s.meta = (S.meta.sessions || {})[`${projId}/${s.id}`] || s.meta || {};
    }
    sl.dataset.loaded = '1';
    sl.dataset.sessions = JSON.stringify(sessions);
    renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
  }));

  // Restore last session
  const last = JSON.parse(localStorage.getItem('lastSession') || 'null');
  if (last) {
    await loadSession(last.project, last.session);
  }
}

// ── Theme / Font / TS ──
function applyTheme() {
  document.documentElement.setAttribute('data-theme', S.theme);
  document.getElementById('btn-theme').textContent = S.theme === 'dark' ? '☀️' : '🌙';
}
function applyFontSize() {
  document.documentElement.style.setProperty('--font-size', S.fontSize + 'px');
}
const FONT_STACKS = {
  'auto':         "'Cascadia Code','Cascadia Mono',Consolas,'BIZ UDGothic','Noto Sans Mono',monospace",
  'cascadia-code':"'Cascadia Code',monospace",
  'cascadia-mono':"'Cascadia Mono',monospace",
  'consolas':     "Consolas,monospace",
  'biz-ud':       "'BIZ UDGothic',monospace",
  'courier-new':  "'Courier New',monospace",
  'system':       "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
};
function applyFont() {
  const stack = FONT_STACKS[S.fontKey] || FONT_STACKS['auto'];
  document.documentElement.style.setProperty('--font-family', stack);
  const sel = document.getElementById('font-select');
  if (sel) sel.value = S.fontKey;
}
function applyTsBtn() {
  document.getElementById('btn-ts').classList.toggle('active', S.showTs);
  document.querySelectorAll('.msg-ts').forEach(el => el.classList.toggle('hidden', !S.showTs));
}

// ── Project/Session rendering ──
function renderProjects() {
  const filter = S.sidebarFilter.toLowerCase();
  const container = document.getElementById('project-list');
  if (!S.projects.length) {
    container.innerHTML = '<div style="padding:16px;color:var(--text-muted);font-size:13px">プロジェクトが見つかりません</div>';
    return;
  }
  container.innerHTML = '';
  for (const proj of S.projects) {
    const open = S.openProjects.has(proj.id);
    const projMeta = (S.meta.projects || {})[proj.id] || {};
    if (projMeta.hidden && !S.showHidden) continue;
    const label = projMeta.label || shortPath(proj.cwd);
    const ph = el('div', 'proj-header' + (open ? ' open' : '') + (projMeta.hidden ? ' proj-hidden' : ''));
    ph.dataset.projId = proj.id;
    // ヘッダー要素を個別に構築（innerHTML+= はイベントリスナーを破壊するため使わない）
    const caret = el('span', 'proj-caret'); caret.textContent = '▶';
    const icon  = el('span', 'proj-icon');  icon.textContent  = open ? '📂' : '📁';
    const nameSpan = el('span', 'proj-name');
    // ツールチップ：パス・メモ・日付範囲
    const firstDate = proj.first_activity ? fmtDate(proj.first_activity) : '?';
    const lastDate  = proj.last_activity  ? fmtDate(proj.last_activity)  : '?';
    const dateRange = firstDate === lastDate ? firstDate : `${firstDate} ～ ${lastDate}`;
    let titleLines = [proj.cwd, `📅 ${dateRange}`];
    if (projMeta.memo) titleLines.push(`📝 ${projMeta.memo}`);
    nameSpan.title = titleLines.join('\n');
    nameSpan.textContent = label;
    // スター・メモバッジ
    if (projMeta.starred) { const b = el('span','proj-badge'); b.textContent='⭐'; nameSpan.appendChild(b); }
    if (projMeta.memo)    { const b = el('span','proj-badge'); b.textContent='📝'; nameSpan.appendChild(b); }
    const count = el('span', 'proj-count'); count.textContent = proj.session_count;
    const openBtn = el('button', 'proj-open-btn');
    openBtn.textContent = '⧉';
    openBtn.title = `フォルダを開く\n${proj.cwd}`;
    openBtn.addEventListener('click', async e => {
      e.stopPropagation();
      await fetch(`/api/open-folder?path=${encodeURIComponent(proj.cwd)}`);
    });
    ph.appendChild(caret);
    ph.appendChild(icon);
    ph.appendChild(nameSpan);
    ph.appendChild(count);
    ph.appendChild(openBtn);
    ph.addEventListener('click', () => toggleProject(proj.id));
    // 右クリックでコンテキストメニュー
    ph.addEventListener('contextmenu', e => {
      e.preventDefault();
      openProjContextMenu(e, proj.id, proj.cwd, projMeta, nameSpan);
    });
    container.appendChild(ph);

    const sl = el('div', 'session-list' + (open ? ' open' : ''));
    sl.id = 'sl-' + proj.id;
    // セッションデータは init() 内で非同期ロード後に描画するためここでは行わない
    container.appendChild(sl);
  }
}

async function toggleProject(projId) {
  const sl = document.getElementById('sl-' + projId);
  const ph = sl.previousElementSibling;
  const iconEl = ph.querySelector('.proj-icon');
  if (S.openProjects.has(projId)) {
    S.openProjects.delete(projId);
    sl.classList.remove('open');
    ph.classList.remove('open');
    if (iconEl) iconEl.textContent = '📁';
  } else {
    S.openProjects.add(projId);
    sl.classList.add('open');
    ph.classList.add('open');
    if (iconEl) iconEl.textContent = '📂';
    // Load sessions if not yet loaded
    if (!sl.dataset.loaded) {
      const sessions = await api(`/api/sessions?project=${encodeURIComponent(projId)}`);
      // Merge meta
      for (const s of sessions) {
        const key = `${projId}/${s.id}`;
        s.meta = (S.meta.sessions || {})[key] || s.meta || {};
      }
      sl.dataset.loaded = '1';
      sl.dataset.sessions = JSON.stringify(sessions);
    }
    renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
  }
  localStorage.setItem('openProjects', JSON.stringify([...S.openProjects]));
}

function renderSessionList(sl, projId, filter) {
  const sessions = JSON.parse(sl.dataset.sessions || '[]');
  sl.innerHTML = '';
  const visible = S.showHidden ? sessions : sessions.filter(s => !(s.meta?.hidden));
  const filtered = filter ? visible.filter(s =>
    s.title.toLowerCase().includes(filter) ||
    (s.meta?.tags || []).some(t => t.toLowerCase().includes(filter))
  ) : visible;
  for (const sess of filtered) {
    const meta = sess.meta || {};
    const item = el('div', 'sess-item' + (S.currentSession === sess.id ? ' active' : '') + (meta.hidden ? ' sess-hidden' : ''));
    item.dataset.sid = sess.id;
    const tags = meta.tags || [];
    const tagsHtml = tags.map(t => `<span class="tag-chip">${esc(t)}</span>`).join('');
    item.innerHTML = `
      <div class="sess-title">${meta.starred ? '⭐ ' : ''}${esc(sess.title)}</div>
      <div class="sess-meta">
        <span class="sess-date">${fmtDate(sess.timestamp)}</span>
        <span class="sess-count">${sess.message_count}件</span>
      </div>
      ${tagsHtml ? `<div class="sess-tags">${tagsHtml}</div>` : ''}
      ${meta.memo ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📝 ${esc(meta.memo)}</div>` : ''}
    `;
    item.addEventListener('click', () => loadSession(projId, sess.id));
    item.addEventListener('contextmenu', e => {
      e.preventDefault();
      openSessContextMenu(e, projId, sess.id, meta);
    });
    sl.appendChild(item);
  }
  if (!filtered.length) {
    sl.innerHTML = '<div style="padding:6px 14px;font-size:12px;color:var(--text-muted)">一致なし</div>';
  }
}

async function loadSession(projId, sessionId) {
  S.currentProject = projId;
  S.currentSession = sessionId;
  localStorage.setItem('lastSession', JSON.stringify({project: projId, session: sessionId}));

  // プロジェクトが閉じていたら開く
  if (!S.openProjects.has(projId)) {
    await toggleProject(projId);
  }

  // Update sidebar active state
  document.querySelectorAll('.sess-item').forEach(el => el.classList.remove('active'));
  const activeEl = document.querySelector(`.sess-item[data-sid="${sessionId}"]`);
  if (activeEl) activeEl.classList.add('active');

  // Load messages
  const msgs = await api(`/api/messages?project=${encodeURIComponent(projId)}&session=${encodeURIComponent(sessionId)}`);
  S.messages = msgs;

  // Find session title
  let title = sessionId;
  for (const proj of S.projects) {
    if (proj.id === projId) {
      const sl = document.getElementById('sl-' + projId);
      if (sl) {
        const sessions = JSON.parse(sl.dataset.sessions || '[]');
        const s = sessions.find(x => x.id === sessionId);
        if (s) title = s.title;
      }
    }
  }
  document.getElementById('session-title').textContent = title;

  // Update session star button
  const sessKey = `${projId}/${sessionId}`;
  const sessMeta = (S.meta.sessions || {})[sessKey] || {};
  document.getElementById('btn-session-star').textContent = sessMeta.starred ? '⭐' : '☆';

  // Update prev/next buttons
  const sl = document.getElementById('sl-' + projId);
  const sessions = sl ? JSON.parse(sl.dataset.sessions || '[]') : [];
  const idx = sessions.findIndex(x => x.id === sessionId);
  document.getElementById('btn-prev-session').disabled = idx <= 0;
  document.getElementById('btn-next-session').disabled = idx < 0 || idx >= sessions.length - 1;

  renderMessages(msgs);
}

// ── Message rendering ──
function renderMessages(msgs) {
  const container = document.getElementById('chat-messages');
  container.innerHTML = '';
  if (!msgs.length) {
    container.innerHTML = '<div id="chat-empty"><div class="icon">🗒️</div><div>メッセージがありません</div></div>';
    return;
  }
  // If first non-plan message is from assistant, prior context was compacted
  const firstReal = msgs.find(m => !m.plan_content);
  if (firstReal && firstReal.role === 'assistant') {
    const notice = el('div', 'compaction-notice');
    notice.innerHTML = '<span>〔以前の会話は省略されています〕</span>';
    container.appendChild(notice);
  }
  for (const msg of msgs) {
    const row = renderMessage(msg);
    if (row) container.appendChild(row);
  }
  // 先頭から読めるようにトップへスクロール
  container.scrollTop = 0;
}

function renderMessage(msg) {
  // Plan-mode injection: display as collapsible plan document, not a chat bubble
  if (msg.plan_content) {
    const row = el('div', 'msg-row');
    row.dataset.uuid = msg.uuid;
    const ts = el('div', `msg-ts${S.showTs ? '' : ' hidden'}`);
    ts.textContent = fmtTime(msg.timestamp);
    const details = document.createElement('details');
    details.className = 'plan-block';
    details.innerHTML = `<summary>📋 実装計画 (クリックで展開)</summary>`;
    const body = el('div', 'plan-block-body');
    const bodyText = el('div', 'bubble-text');
    bodyText.innerHTML = renderMd(msg.plan_content);
    body.appendChild(bodyText);
    details.appendChild(body);
    row.appendChild(ts);
    row.appendChild(details);
    return row;
  }

  const row = el('div', `msg-row ${msg.role}`);
  row.dataset.uuid = msg.uuid;

  // Timestamp
  const ts = el('div', `msg-ts${S.showTs ? '' : ' hidden'}`);
  ts.textContent = fmtTime(msg.timestamp);

  // Bubble
  const bubble = el('div', 'bubble');

  // Main text
  if (msg.text) {
    const textEl = el('div', 'bubble-text');
    const collapseChars = S.cfg.collapse_chars ?? 600;
    const collapseLines = S.cfg.collapse_lines ?? 15;
    const previewChars  = S.cfg.preview_chars  ?? 300;
    const lineCount = (msg.text.match(/\n/g) || []).length;
    const shouldCollapse = msg.text.length > collapseChars || lineCount > collapseLines;
    if (shouldCollapse) {
      const preview = el('div', 'bubble-text');
      preview.innerHTML = renderMd(msg.text.slice(0, previewChars)) + '…';
      bubble.appendChild(preview);
      const details = document.createElement('details');
      details.className = 'msg-collapse';
      details.innerHTML = `<summary>▼ 続きを見る (${lineCount}行 / ${msg.text.length}文字)</summary>`;
      const full = el('div', 'bubble-text');
      full.innerHTML = renderMd(msg.text);
      details.appendChild(full);
      // 下部の「折りたたむ」ボタン
      const collapseBtn = el('div', 'collapse-bottom-btn');
      collapseBtn.textContent = '▲ 折りたたむ';
      collapseBtn.addEventListener('click', () => {
        details.open = false;
        bubble.scrollIntoView({ block: 'start' });
      });
      details.appendChild(collapseBtn);
      // 展開時はプレビューを隠してバブル先頭へ、閉じたら戻す
      details.addEventListener('toggle', () => {
        preview.style.display = details.open ? 'none' : '';
        if (details.open) bubble.scrollIntoView({ block: 'start' });
      });
      bubble.appendChild(details);
    } else {
      textEl.innerHTML = renderMd(msg.text);
      bubble.appendChild(textEl);
    }
  }

  // Thinking blocks
  if (S.cfg.show_thinking !== false) {
    for (const think of (msg.thinking || [])) {
      if (!think) continue;
      const d = document.createElement('details');
      d.className = 'thinking-block';
      d.innerHTML = `<summary class="thinking-summary">🤔 思考プロセス (${think.length}文字)</summary>`;
      const tc = el('div', 'thinking-content');
      tc.textContent = think;
      d.appendChild(tc);
      bubble.appendChild(d);
    }
  }

  // Tool chips
  if (S.cfg.show_tool_chips !== false && msg.tool_uses && msg.tool_uses.length) {
    const chips = el('div', 'tool-chips');
    for (const tu of msg.tool_uses) {
      const chip = el('div', 'tool-chip');
      chip.title = tu.description || tu.name;
      chip.innerHTML = `<span class="tool-icon">${toolIcon(tu.name)}</span>${esc(tu.description ? tu.description.slice(0,40) : tu.name)}`;
      chips.appendChild(chip);
    }
    bubble.appendChild(chips);
  }

  // Images
  if (msg.images && msg.images.length) {
    const imgRow = el('div', 'msg-images');
    for (const img of msg.images) {
      const im = document.createElement('img');
      im.src = `data:${img.media_type};base64,${img.data}`;
      im.alt = '画像';
      im.addEventListener('click', () => openLightbox(im.src));
      imgRow.appendChild(im);
    }
    bubble.appendChild(imgRow);
  }

  // バブルに表示する内容が何もなければ行ごとスキップ
  if (!bubble.hasChildNodes()) return null;

  // Toolbar (star / memo)
  const toolbar = el('div', 'msg-toolbar');
  const msgMeta = (S.meta.messages || {})[msg.uuid] || msg.meta || {};
  const starBtn = el('button', `tbtn${msgMeta.starred ? ' active' : ''}`);
  starBtn.textContent = msgMeta.starred ? '⭐' : '☆';
  starBtn.title = 'スター';
  starBtn.addEventListener('click', () => toggleMessageStar(msg.uuid, starBtn));
  const copyBtn = el('button', 'tbtn');
  copyBtn.textContent = '📋';
  copyBtn.title = 'テキストをコピー';
  copyBtn.addEventListener('click', async () => {
    const parts = [];
    if (msg.text) parts.push(msg.text);
    for (const t of (msg.thinking || [])) { if (t) parts.push(t); }
    for (const tu of (msg.tool_uses || [])) {
      const desc = tu.description || tu.name;
      parts.push(`[${tu.name}] ${desc}`);
    }
    const text = parts.join('\n\n');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
      document.body.appendChild(ta); ta.select(); document.execCommand('copy');
      document.body.removeChild(ta);
    }
    copyBtn.textContent = '✓';
    setTimeout(() => copyBtn.textContent = '📋', 1500);
  });
  const memoBtn = el('button', 'tbtn');
  memoBtn.textContent = '📝';
  memoBtn.title = 'メモ・タグ';
  memoBtn.addEventListener('click', () => openMemo('message', msg.uuid, msgMeta));
  toolbar.appendChild(copyBtn);
  toolbar.appendChild(starBtn);
  toolbar.appendChild(memoBtn);

  row.appendChild(ts);
  row.appendChild(bubble);
  row.appendChild(toolbar);
  return row;
}

function toolIcon(name) {
  const icons = { Read:'📖', Write:'💾', Edit:'✏️', Bash:'💻', Glob:'🗂️', Grep:'🔍',
    WebFetch:'🌐', WebSearch:'🌐', Agent:'🤖', TodoWrite:'📋', NotebookEdit:'📓',
    NotebookRead:'📓', TaskOutput:'📤' };
  return icons[name] || '🔧';
}

// ── Markdown renderer ──
function renderMd(text) {
  if (!text) return '';

  const saved = [];
  const save = html => { const i = saved.length; saved.push(html); return `\x00${i}\x00`; };
  const isSaved = s => /^\x00\d+\x00$/.test(s);

  // Normalize line endings (\r\n → \n)
  let s = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // ① テーブル・コードブロックを先に退避（内部の改行・HTMLを保護）
  const rawLines = s.split('\n');
  const out = [];
  let i = 0;
  while (i < rawLines.length) {
    // テーブル
    if (i + 1 < rawLines.length
        && /^\|.+\|/.test(rawLines[i])
        && /^\|[\s|:\-]+\|/.test(rawLines[i + 1])) {
      const tbl = [rawLines[i], rawLines[i + 1]]; i += 2;
      while (i < rawLines.length && /^\|.+\|/.test(rawLines[i])) tbl.push(rawLines[i++]);
      out.push(save(_renderTable(tbl)));
    } else {
      out.push(rawLines[i++]);
    }
  }
  s = out.join('\n');

  // ② コードブロックを退避（先にHTMLエスケープして \n を保護）
  s = s.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, c) => {
    const escaped = c.trimEnd().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return save(`<div class="code-wrap"><button class="code-copy-btn">コピー</button><pre><code>${escaped}</code></pre></div>`);
  });

  // ③ 残りをHTMLエスケープ（プレースホルダの \x00 は影響を受けない）
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // ④ インライン要素
  s = s.replace(/`([^`\n]+)`/g, (_, c) => `<code>${c}</code>`);
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

  // ⑤ 行単位でブロック要素を処理（見出し・リスト・段落を正しく分離）
  const parts = [];
  let paraLines = [];
  let listItems = [];
  let listOrdered = false;

  const flushPara = () => {
    const t = paraLines.join('<br>').trim();
    if (t) parts.push(`<p>${t}</p>`);
    paraLines = [];
  };
  const flushList = () => {
    if (!listItems.length) return;
    const tag = listOrdered ? 'ol' : 'ul';
    parts.push(`<${tag}>${listItems.join('')}</${tag}>`);
    listItems = [];
  };

  for (const line of s.split('\n')) {
    const t = line.trim();
    const h3 = t.match(/^### (.+)/), h2 = !h3 && t.match(/^## (.+)/), h1 = !h2 && !h3 && t.match(/^# (.+)/);
    const ul = t.match(/^[\*\-] (.+)/);
    const ol = t.match(/^\d+\. (.+)/);

    if (h3 || h2 || h1) {
      flushList(); flushPara();
      parts.push(h3 ? `<h3>${h3[1]}</h3>` : h2 ? `<h2>${h2[1]}</h2>` : `<h1>${h1[1]}</h1>`);
    } else if (isSaved(t)) {
      flushList(); flushPara();
      parts.push(t);
    } else if (ul) {
      flushPara();
      if (listOrdered) flushList();
      listOrdered = false;
      listItems.push(`<li>${ul[1]}</li>`);
    } else if (ol) {
      flushPara();
      if (!listOrdered) flushList();
      listOrdered = true;
      listItems.push(`<li>${ol[1]}</li>`);
    } else if (!t) {
      flushList(); flushPara();
    } else {
      flushList();
      paraLines.push(t);
    }
  }
  flushList();
  flushPara();

  // ⑥ プレースホルダ復元
  return parts.join('').replace(/\x00(\d+)\x00/g, (_, i) => saved[+i]);
}

function _renderTable(lines) {
  const parseRow = l => l.replace(/^\||\|$/g,'').split('|').map(c => c.trim());
  const header = parseRow(lines[0]);
  const sep    = parseRow(lines[1]);
  if (!sep.every(c => /^:?-+:?$/.test(c))) {
    // セパレータ行が不正なら plain text で返す
    return lines.map(l => l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')).join('<br>');
  }
  const aligns = sep.map(c =>
    (c.startsWith(':') && c.endsWith(':')) ? 'center' :
    c.endsWith(':') ? 'right' : 'left');
  // セル内テキストをエスケープ＋インラインマークアップだけ処理
  const ec = c => c
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g,'<em>$1</em>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
  let h = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
  header.forEach((c,i) => h += `<th style="text-align:${aligns[i]||'left'}">${ec(c)}</th>`);
  h += '</tr></thead><tbody>';
  lines.slice(2).forEach(l => {
    const cells = parseRow(l);
    if (!cells.length) return;
    h += '<tr>';
    header.forEach((_,i) => h += `<td style="text-align:${aligns[i]||'left'}">${ec(cells[i]||'')}</td>`);
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}

// ── Star / Memo ──
async function toggleMessageStar(uuid, btn) {
  const existing = (S.meta.messages || {})[uuid] || {};
  const meta = {
    ...existing,
    starred: !existing.starred,
    project_id: existing.project_id || S.currentProject,
    session_id: existing.session_id || S.currentSession,
  };
  await post('/api/meta/message', { uuid, meta });
  S.meta.messages = S.meta.messages || {};
  S.meta.messages[uuid] = meta;
  btn.textContent = meta.starred ? '⭐' : '☆';
  btn.classList.toggle('active', !!meta.starred);
}

function openMemo(type, key, currentMeta) {
  S.memoTarget = { type, key, currentMeta };
  document.getElementById('memo-textarea').value = currentMeta.memo || '';
  document.getElementById('tag-input').value = (currentMeta.tags || []).join(', ');
  document.getElementById('memo-modal').classList.add('open');
}

async function saveMemo() {
  const { type, key } = S.memoTarget;
  const memo = document.getElementById('memo-textarea').value.trim();
  const tagsRaw = document.getElementById('tag-input').value;
  const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);
  const existingMeta = type === 'session'
    ? (S.meta.sessions || {})[key] || {}
    : type === 'project'
    ? (S.meta.projects || {})[key] || {}
    : (S.meta.messages || {})[key] || {};
  const newMeta = { ...existingMeta, memo, tags };

  if (type === 'project') {
    await post('/api/meta/project', { project_id: key, meta: newMeta });
    S.meta.projects = S.meta.projects || {};
    S.meta.projects[key] = newMeta;
    renderProjects();
  } else if (type === 'session') {
    const [projId, sessId] = key.split('/', 2);
    // If key is already "projId/sessId" format:
    await post('/api/meta/session', { project_id: projId, session_id: sessId, meta: newMeta });
    S.meta.sessions = S.meta.sessions || {};
    S.meta.sessions[key] = newMeta;
    // Re-render session list
    refreshSessionMeta(key, newMeta);
  } else {
    const existingMsg = (S.meta.messages || {})[key] || {};
    const msgMeta = {
      ...newMeta,
      project_id: existingMsg.project_id || S.currentProject,
      session_id: existingMsg.session_id || S.currentSession,
    };
    await post('/api/meta/message', { uuid: key, meta: msgMeta });
    S.meta.messages = S.meta.messages || {};
    S.meta.messages[key] = msgMeta;
  }
  document.getElementById('memo-modal').classList.remove('open');
}

// ── Project context menu ──
let _ctxProjId = null, _ctxProjCwd = null, _ctxProjMeta = null, _ctxNameSpan = null;
function openProjContextMenu(e, projId, cwd, projMeta, nameSpan) {
  _ctxProjId = projId; _ctxProjCwd = cwd; _ctxProjMeta = projMeta; _ctxNameSpan = nameSpan;
  document.getElementById('ctx-star').textContent = projMeta.starred ? '⭐ スターを外す' : '☆ スター';
  document.getElementById('ctx-hide').textContent = projMeta.hidden ? '👁 再表示' : '🙈 非表示にする';
  const menu = document.getElementById('ctx-menu');
  menu.style.left = Math.min(e.clientX, window.innerWidth - 180) + 'px';
  menu.style.top  = Math.min(e.clientY, window.innerHeight - 80) + 'px';
  menu.classList.add('open');
}
function closeProjContextMenu() {
  document.getElementById('ctx-menu').classList.remove('open');
}
document.getElementById('ctx-star').addEventListener('click', async () => {
  closeProjContextMenu();
  const newMeta = { ..._ctxProjMeta, starred: !_ctxProjMeta.starred };
  await post('/api/meta/project', { project_id: _ctxProjId, meta: newMeta });
  S.meta.projects = S.meta.projects || {};
  S.meta.projects[_ctxProjId] = newMeta;
  renderProjects();
});
document.getElementById('ctx-memo').addEventListener('click', () => {
  closeProjContextMenu();
  openMemo('project', _ctxProjId, _ctxProjMeta);
});
document.getElementById('ctx-label').addEventListener('click', () => {
  closeProjContextMenu();
  const nameSpan = _ctxNameSpan;
  const projId = _ctxProjId, projMeta = _ctxProjMeta;
  const input = el('input', 'proj-name-edit');
  input.value = projMeta.label || shortPath(_ctxProjCwd);
  input.placeholder = shortPath(_ctxProjCwd);
  nameSpan.replaceWith(input);
  input.focus(); input.select();
  const commit = async () => {
    const newLabel = input.value.trim();
    const newMeta = { ...projMeta };
    if (newLabel) newMeta.label = newLabel; else delete newMeta.label;
    await post('/api/meta/project', { project_id: projId, meta: newMeta });
    S.meta.projects = S.meta.projects || {};
    S.meta.projects[projId] = newMeta;
    renderProjects();
  };
  input.addEventListener('blur', commit);
  input.addEventListener('keydown', ev => {
    if (ev.key === 'Enter')  { ev.preventDefault(); input.blur(); }
    if (ev.key === 'Escape') { input.removeEventListener('blur', commit); input.replaceWith(nameSpan); }
  });
});
document.getElementById('ctx-open-folder').addEventListener('click', async () => {
  closeProjContextMenu();
  await fetch(`/api/open-folder?path=${encodeURIComponent(_ctxProjCwd)}`);
});
document.getElementById('ctx-hide').addEventListener('click', async () => {
  closeProjContextMenu();
  const newMeta = { ..._ctxProjMeta, hidden: !_ctxProjMeta.hidden };
  await post('/api/meta/project', { project_id: _ctxProjId, meta: newMeta });
  S.meta.projects = S.meta.projects || {};
  S.meta.projects[_ctxProjId] = newMeta;
  renderProjects();
});
document.addEventListener('click', e => {
  if (!document.getElementById('ctx-menu').contains(e.target)) closeProjContextMenu();
  if (!document.getElementById('sess-ctx-menu').contains(e.target)) closeSessContextMenu();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeProjContextMenu(); closeSessContextMenu(); } });

// ── Session context menu ──
let _ctxSessProjId = null, _ctxSessId = null, _ctxSessMeta = null;
function openSessContextMenu(e, projId, sessId, meta) {
  _ctxSessProjId = projId; _ctxSessId = sessId; _ctxSessMeta = meta;
  document.getElementById('sess-ctx-hide').textContent = meta.hidden ? '👁 再表示' : '🙈 非表示にする';
  const menu = document.getElementById('sess-ctx-menu');
  menu.style.left = Math.min(e.clientX, window.innerWidth - 180) + 'px';
  menu.style.top  = Math.min(e.clientY, window.innerHeight - 60) + 'px';
  menu.classList.add('open');
}
function closeSessContextMenu() {
  document.getElementById('sess-ctx-menu').classList.remove('open');
}
document.getElementById('sess-ctx-hide').addEventListener('click', async () => {
  closeSessContextMenu();
  const key = `${_ctxSessProjId}/${_ctxSessId}`;
  const newMeta = { ..._ctxSessMeta, hidden: !_ctxSessMeta.hidden };
  await post('/api/meta/session', { project_id: _ctxSessProjId, session_id: _ctxSessId, meta: newMeta });
  S.meta.sessions = S.meta.sessions || {};
  S.meta.sessions[key] = newMeta;
  refreshSessionMeta(key, newMeta);
});

// ── Show hidden toggle ──
document.getElementById('btn-show-hidden').addEventListener('click', () => {
  S.showHidden = !S.showHidden;
  document.getElementById('btn-show-hidden').classList.toggle('active', S.showHidden);
  document.getElementById('btn-show-hidden').textContent = S.showHidden ? '👁 非表示を隠す' : '👁 非表示を表示';
  renderProjects();
  document.querySelectorAll('.session-list.open').forEach(sl => {
    renderSessionList(sl, sl.id.replace('sl-', ''), S.sidebarFilter.toLowerCase());
  });
});

function refreshSessionMeta(key, newMeta) {
  const [projId, sessId] = key.split('/', 2);
  const sl = document.getElementById('sl-' + projId);
  if (!sl) return;
  const sessions = JSON.parse(sl.dataset.sessions || '[]');
  for (const s of sessions) {
    if (s.id === sessId) { s.meta = newMeta; break; }
  }
  sl.dataset.sessions = JSON.stringify(sessions);
  renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
}

// ── Scroll jump ──
document.getElementById('btn-scroll-top').addEventListener('click', () => {
  document.getElementById('chat-messages').scrollTo({ top: 0, behavior: 'smooth' });
});
document.getElementById('btn-scroll-bottom').addEventListener('click', () => {
  const el = document.getElementById('chat-messages');
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
});

// ── Code copy (event delegation) ──
document.getElementById('chat-messages').addEventListener('click', e => {
  if (!e.target.classList.contains('code-copy-btn')) return;
  const code = e.target.nextElementSibling?.querySelector('code')?.textContent || '';
  navigator.clipboard.writeText(code);
  e.target.textContent = '✓';
  e.target.classList.add('copied');
  setTimeout(() => { e.target.textContent = 'コピー'; e.target.classList.remove('copied'); }, 1500);
});

// Session star
document.getElementById('btn-session-star').addEventListener('click', async () => {
  if (!S.currentSession) return;
  const key = `${S.currentProject}/${S.currentSession}`;
  const existing = (S.meta.sessions || {})[key] || {};
  const newMeta = { ...existing, starred: !existing.starred,
    title: document.getElementById('session-title').textContent };
  await post('/api/meta/session', { project_id: S.currentProject, session_id: S.currentSession, meta: newMeta });
  S.meta.sessions = S.meta.sessions || {};
  S.meta.sessions[key] = newMeta;
  document.getElementById('btn-session-star').textContent = newMeta.starred ? '⭐' : '☆';
  refreshSessionMeta(key, newMeta);
});

document.getElementById('btn-session-memo').addEventListener('click', () => {
  if (!S.currentSession) return;
  const key = `${S.currentProject}/${S.currentSession}`;
  const existing = (S.meta.sessions || {})[key] || {};
  openMemo('session', key, existing);
});
document.getElementById('btn-export').addEventListener('click', () => {
  const fmt = document.getElementById('export-format').value;
  if (fmt === 'md') exportMarkdown(); else exportHTML();
});

// ── Search ──
function populateSearchScope() {
  const sel = document.getElementById('search-scope');
  for (const proj of S.projects) {
    const opt = document.createElement('option');
    opt.value = proj.id;
    const projMeta = (S.meta.projects || {})[proj.id] || {};
    opt.textContent = projMeta.label || shortPath(proj.cwd);
    sel.appendChild(opt);
  }
}

let searchTimer = null;
document.getElementById('search-input').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 300);
});
document.getElementById('search-type').addEventListener('change', runSearch);
document.getElementById('search-scope').addEventListener('change', runSearch);

async function runSearch() {
  const q = document.getElementById('search-input').value.trim();
  const type = document.getElementById('search-type').value;
  const scope = document.getElementById('search-scope').value;
  const resultsEl = document.getElementById('search-results');
  if (!q) { resultsEl.innerHTML = '<div class="sr-empty">キーワードを入力して検索</div>'; return; }
  resultsEl.innerHTML = '<div class="sr-empty">検索中…</div>';
  const url = `/api/search?q=${encodeURIComponent(q)}&type=${type}${scope ? '&project=' + encodeURIComponent(scope) : ''}`;
  const results = await api(url);
  if (!results.length) {
    resultsEl.innerHTML = '<div class="sr-empty">一致するメッセージが見つかりませんでした</div>';
    return;
  }
  resultsEl.innerHTML = '';
  // プロジェクト → セッション → メッセージ の順に階層化
  const tree = {};
  for (const r of results) {
    const pk = r.project_id;
    const sk = r.session_id;
    if (!tree[pk]) tree[pk] = { sessions: {} };
    if (!tree[pk].sessions[sk]) tree[pk].sessions[sk] = { title: r.session_title || r.session_id, hits: [] };
    tree[pk].sessions[sk].hits.push(r);
  }
  for (const [projId, proj] of Object.entries(tree)) {
    const projMeta = (S.meta.projects || {})[projId] || {};
    const projLabel = projMeta.label || shortPath((S.projects.find(p => p.id === projId) || {}).cwd || projId);
    const sessCount = Object.keys(proj.sessions).length;
    const hitCount  = Object.values(proj.sessions).reduce((s, x) => s + x.hits.length, 0);
    const projDiv = el('div', 'sr-proj');
    const ph = el('div', 'sr-proj-header');
    ph.innerHTML = `📁 ${esc(projLabel)} <span style="opacity:.6;font-weight:400">${sessCount}セッション · ${hitCount}件</span>`;
    projDiv.appendChild(ph);
    for (const [sessId, sess] of Object.entries(proj.sessions)) {
      const sessDiv = el('div', 'sr-sess');
      const sh = el('div', 'sr-sess-header');
      const sessMeta = (S.meta.sessions || {})[`${projId}/${sessId}`] || {};
      const sessStarIcon = sessMeta.starred ? '⭐ ' : '';
      sh.textContent = `📄 ${sessStarIcon}${sess.title}  (${sess.hits.length}件)`;
      sh.addEventListener('click', async () => {
        document.getElementById('search-panel').classList.remove('open');
        await loadSession(projId, sessId);
      });
      sessDiv.appendChild(sh);
      for (const r of sess.hits) {
        const item = el('div', 'sr-item');
        item.innerHTML = `
          <div class="sr-snippet">${esc(r.snippet)}</div>
          <div class="sr-role">${r.role === 'user' ? '👤 あなた' : '🤖 Claude'} · ${fmtTime(r.timestamp)}</div>
        `;
        item.addEventListener('click', async () => {
          document.getElementById('search-panel').classList.remove('open');
          await loadSession(r.project_id, r.session_id);
          setTimeout(() => {
            const msgEl = document.querySelector(`.msg-row[data-uuid="${r.uuid}"]`);
            if (msgEl) { msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' }); msgEl.style.outline = '2px solid var(--accent)'; setTimeout(() => msgEl.style.outline = '', 2000); }
          }, 300);
        });
        sessDiv.appendChild(item);
      }
      projDiv.appendChild(sessDiv);
    }
    resultsEl.appendChild(projDiv);
  }
}

// ── Starred panel ──
async function openStarredPanel() {
  const starred = await api('/api/starred');
  const body = document.getElementById('starred-body');
  body.innerHTML = '';

  if (starred.sessions.length) {
    const h = el('div', 'starred-section-title'); h.textContent = 'スター付きセッション';
    body.appendChild(h);
    for (const s of starred.sessions) {
      const item = el('div', 'starred-item');
      const sessTitle = s.title || s.session_id;
      const projMeta = (S.meta.projects || {})[s.project_id] || {};
      const projLabel = projMeta.label || shortPath((S.projects.find(p => p.id === s.project_id) || {}).cwd || s.project_id);
      const tags = (s.tags || []).map(t => `<span class="tag-chip">${esc(t)}</span>`).join('');
      item.innerHTML = `
        <div class="starred-item-title">⭐ ${esc(sessTitle)}</div>
        <div class="starred-item-meta">📁 ${esc(projLabel)}</div>
        ${s.memo ? `<div class="starred-item-meta">📝 ${esc(s.memo)}</div>` : ''}
        ${tags ? `<div class="starred-tags">${tags}</div>` : ''}
      `;
      item.addEventListener('click', async () => {
        document.getElementById('starred-panel').classList.remove('open');
        await loadSession(s.project_id, s.session_id);
      });
      body.appendChild(item);
    }
  }
  if (starred.messages.length) {
    const h = el('div', 'starred-section-title'); h.textContent = 'スター付きメッセージ';
    body.appendChild(h);
    for (const m of starred.messages) {
      const item = el('div', 'starred-item');
      const canNav = m.project_id && m.session_id;
      item.innerHTML = `
        <div class="starred-item-title">⭐ ${esc(m.memo || m.uuid.slice(0,8) + '…')}</div>
        ${m.session_id ? `<div class="starred-item-meta">📁 ${esc(m.session_id.slice(0,8))}…</div>` : ''}
        ${!canNav ? '<div class="starred-item-meta" style="opacity:.6">※ 再スターで位置を記録できます</div>' : ''}
      `;
      if (canNav) {
        item.addEventListener('click', async () => {
          document.getElementById('starred-panel').classList.remove('open');
          await loadSession(m.project_id, m.session_id);
          setTimeout(() => {
            const target = document.querySelector(`[data-uuid="${m.uuid}"]`);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 100);
        });
      }
      body.appendChild(item);
    }
  }
  if (!starred.sessions.length && !starred.messages.length) {
    body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px">スター付きアイテムがありません</div>';
  }
  document.getElementById('starred-panel').classList.add('open');
}

// ── Prev / Next session ──
document.getElementById('btn-prev-session').addEventListener('click', () => {
  if (!S.currentProject) return;
  const sl = document.getElementById('sl-' + S.currentProject);
  if (!sl) return;
  const sessions = JSON.parse(sl.dataset.sessions || '[]');
  const idx = sessions.findIndex(x => x.id === S.currentSession);
  if (idx > 0) loadSession(S.currentProject, sessions[idx - 1].id);
});
document.getElementById('btn-next-session').addEventListener('click', () => {
  if (!S.currentProject) return;
  const sl = document.getElementById('sl-' + S.currentProject);
  if (!sl) return;
  const sessions = JSON.parse(sl.dataset.sessions || '[]');
  const idx = sessions.findIndex(x => x.id === S.currentSession);
  if (idx >= 0 && idx < sessions.length - 1) loadSession(S.currentProject, sessions[idx + 1].id);
});

// ── Sidebar filter ──
document.getElementById('sidebar-search').addEventListener('input', e => {
  S.sidebarFilter = e.target.value;
  document.querySelectorAll('.session-list.open').forEach(sl => {
    const projId = sl.id.replace('sl-', '');
    renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
  });
});

// ── Event listeners ──
document.getElementById('btn-theme').addEventListener('click', () => {
  S.theme = S.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', S.theme);
  applyTheme();
});
document.getElementById('btn-ts').addEventListener('click', () => {
  S.showTs = !S.showTs;
  localStorage.setItem('showTs', S.showTs);
  applyTsBtn();
});
document.getElementById('btn-font-up').addEventListener('click', () => {
  S.fontSize = Math.min(22, S.fontSize + 1);
  localStorage.setItem('fontSize', S.fontSize);
  applyFontSize();
});
document.getElementById('btn-font-down').addEventListener('click', () => {
  S.fontSize = Math.max(10, S.fontSize - 1);
  localStorage.setItem('fontSize', S.fontSize);
  applyFontSize();
});
document.getElementById('font-select').addEventListener('change', e => {
  S.fontKey = e.target.value;
  localStorage.setItem('fontKey', S.fontKey);
  applyFont();
});
document.getElementById('btn-search').addEventListener('click', () => {
  document.getElementById('search-panel').classList.add('open');
  setTimeout(() => document.getElementById('search-input').focus(), 50);
});
document.getElementById('btn-search-close').addEventListener('click', () => {
  document.getElementById('search-panel').classList.remove('open');
});
document.getElementById('search-panel').addEventListener('click', e => {
  if (e.target === document.getElementById('search-panel')) document.getElementById('search-panel').classList.remove('open');
});
document.getElementById('btn-starred').addEventListener('click', openStarredPanel);
document.getElementById('btn-help').addEventListener('click', () => {
  document.getElementById('help-modal').classList.toggle('open');
});
document.getElementById('btn-starred-close').addEventListener('click', () => {
  document.getElementById('starred-panel').classList.remove('open');
});
document.getElementById('starred-panel').addEventListener('click', e => {
  if (e.target === document.getElementById('starred-panel')) document.getElementById('starred-panel').classList.remove('open');
});
document.getElementById('btn-memo-cancel').addEventListener('click', () => {
  document.getElementById('memo-modal').classList.remove('open');
});
document.getElementById('btn-memo-save').addEventListener('click', saveMemo);
document.getElementById('lightbox').addEventListener('click', () => {
  document.getElementById('lightbox').classList.remove('open');
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName;
  const inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    document.getElementById('search-panel').classList.add('open');
    setTimeout(() => document.getElementById('search-input').focus(), 50);
  }
  if (e.key === 'Escape') {
    document.getElementById('search-panel').classList.remove('open');
    document.getElementById('starred-panel').classList.remove('open');
    document.getElementById('memo-modal').classList.remove('open');
    document.getElementById('lightbox').classList.remove('open');
    document.getElementById('help-modal').classList.remove('open');
  }
  if (!inInput && e.key === '?') {
    document.getElementById('help-modal').classList.toggle('open');
  }
  if (!inInput && e.key === 'ArrowLeft') {
    document.getElementById('btn-prev-session').click();
  }
  if (!inInput && e.key === 'ArrowRight') {
    document.getElementById('btn-next-session').click();
  }
});
document.getElementById('btn-help-close').addEventListener('click', () => {
  document.getElementById('help-modal').classList.remove('open');
});
document.getElementById('help-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('help-modal')) document.getElementById('help-modal').classList.remove('open');
});

// ── Resize handle ──
(function() {
  const handle = document.getElementById('resize-handle');
  const sidebar = document.getElementById('sidebar');
  let dragging = false, startX, startW;
  handle.addEventListener('mousedown', e => {
    dragging = true; startX = e.clientX; startW = sidebar.offsetWidth;
    handle.classList.add('dragging');
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const w = Math.max(160, Math.min(500, startW + e.clientX - startX));
    sidebar.style.width = w + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (dragging) { dragging = false; handle.classList.remove('dragging'); document.body.style.userSelect = ''; }
  });
})();

// ── Lightbox ──
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('open');
}

// ── Helpers ──
function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtDate(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('ja-JP', { month:'2-digit', day:'2-digit' });
  } catch { return ''; }
}
function fmtTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('ja-JP', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
  } catch { return ''; }
}
// ── Export ──
function exportHTML() {
  if (!S.currentSession) return;

  const title = document.getElementById('session-title').textContent;
  const dateStr = new Date().toLocaleString('ja-JP');

  // クローンして操作UIを除去
  const clone = document.getElementById('chat-messages').cloneNode(true);
  clone.querySelectorAll('.msg-toolbar').forEach(el => el.remove());

  // 折りたたみを全展開し、プレビュー重複を解消
  clone.querySelectorAll('details.msg-collapse').forEach(details => {
    details.open = true;
    // プレビュー div（直前の兄弟）を削除
    const prev = details.previousElementSibling;
    if (prev && prev.classList.contains('bubble-text')) prev.remove();
    // 下部の折りたたむボタンを削除（JS不要のため）
    details.querySelectorAll('.collapse-bottom-btn').forEach(b => b.remove());
  });

  // 現在のテーマのCSS変数を取得
  const cs = getComputedStyle(document.documentElement);
  const vars = ['--bg','--sidebar-bg','--bubble-user','--bubble-user-text',
    '--bubble-ai','--bubble-ai-text','--thinking-bg','--thinking-text',
    '--border','--text','--text-muted','--accent','--chip-bg','--chip-text',
    '--font-family','--font-size','--radius','--shadow'];
  const varBlock = vars.map(v => `  ${v}:${cs.getPropertyValue(v)};`).join('\n');

  const html = `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
:root {
${varBlock}
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-family);font-size:var(--font-size);background:var(--bg);color:var(--text);padding:16px}
.export-header{max-width:860px;margin:0 auto 20px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.export-header h1{font-size:17px;font-weight:700;margin-bottom:4px}
.export-meta{font-size:12px;color:var(--text-muted)}
#chat-messages{max-width:860px;margin:0 auto;display:flex;flex-direction:column;gap:12px}
.msg-row{display:flex;flex-direction:column;gap:4px}
.msg-row.user{align-items:flex-end}
.msg-row.assistant{align-items:flex-start}
.msg-ts{font-size:11px;color:var(--text-muted);padding:0 4px}
.msg-ts.hidden{display:none}
.bubble{max-width:72%;padding:10px 14px;border-radius:var(--radius);word-break:break-word}
.msg-row.user .bubble{background:var(--bubble-user);color:var(--bubble-user-text);border-bottom-right-radius:4px}
.msg-row.assistant .bubble{background:var(--bubble-ai);color:var(--bubble-ai-text);border-bottom-left-radius:4px;box-shadow:var(--shadow)}
.bubble-text{line-height:1.6;white-space:normal}
.bubble-text p{margin:0 0 .6em}.bubble-text p:last-child{margin-bottom:0}
.bubble-text code{background:rgba(0,0,0,.1);padding:1px 4px;border-radius:4px;font-size:.9em;font-family:monospace}
.msg-row.user .bubble-text code{background:rgba(255,255,255,.2)}
.bubble-text pre{background:rgba(0,0,0,.12);padding:8px 10px;border-radius:8px;overflow-x:auto;margin:.4em 0}
.msg-row.user .bubble-text pre{background:rgba(255,255,255,.15)}
.bubble-text pre code{background:none;padding:0}
.bubble-text h1{font-size:1.1em;font-weight:700;margin:.5em 0 .15em}.bubble-text h2{font-size:1.05em;font-weight:700;margin:.4em 0 .15em}.bubble-text h3{font-size:1em;font-weight:700;margin:.35em 0 .1em}.bubble-text h1:first-child,.bubble-text h2:first-child,.bubble-text h3:first-child{margin-top:.1em}
.bubble-text ul,.bubble-text ol{padding-left:1.4em;margin:.3em 0}
.bubble-text strong{font-weight:700}
.bubble-text em{font-style:italic}
.msg-collapse>summary{font-size:12px;color:var(--accent);cursor:pointer;list-style:none;padding:4px 0}
.msg-collapse>summary::marker{display:none}
.msg-collapse[open]>summary{display:none}
.thinking-block{margin-top:6px;background:var(--thinking-bg);border-radius:10px;overflow:hidden}
.thinking-summary{padding:6px 10px;font-size:12px;color:var(--thinking-text);cursor:pointer;display:flex;align-items:center;gap:6px}
.thinking-summary::marker{display:none}
.thinking-content{padding:8px 10px;font-size:12px;color:var(--thinking-text);white-space:pre-wrap;max-height:300px;overflow-y:auto;border-top:1px solid rgba(0,0,0,.08)}
.tool-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.tool-chip{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:3px 8px;border-radius:10px;background:var(--chip-bg);color:var(--chip-text);max-width:220px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.msg-images{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.msg-images img{max-width:200px;max-height:150px;border-radius:8px;border:1px solid var(--border)}
.md-table-wrap{overflow-x:auto;margin:.5em 0;border-radius:6px}
.md-table{border-collapse:collapse;width:100%;font-size:.93em}
.md-table th,.md-table td{border:1px solid rgba(0,0,0,.15);padding:5px 10px;white-space:nowrap;line-height:1.4}
.md-table th{background:rgba(0,0,0,.06);font-weight:600}
.md-table tr:nth-child(even) td{background:rgba(0,0,0,.025)}
.msg-row.user .md-table th,.msg-row.user .md-table td{border-color:rgba(255,255,255,.3)}
.msg-row.user .md-table th{background:rgba(255,255,255,.18)}
</style>
</head>
<body>
<div class="export-header">
  <h1>${esc(title)}</h1>
  <div class="export-meta">保存日時: ${dateStr}</div>
</div>
${clone.outerHTML}
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) + '.html';
  a.click();
  URL.revokeObjectURL(url);
}

function exportMarkdown() {
  if (!S.currentSession) return;
  const title = document.getElementById('session-title').textContent;
  const dateStr = new Date().toLocaleString('ja-JP');
  const lines = [`# ${title}`, `> 保存日時: ${dateStr}`, ''];

  for (const msg of S.messages) {
    if (!msg.text) continue;  // テキストのないメッセージ（ツールのみ等）はスキップ
    const role = msg.role === 'user' ? '## 👤 あなた' : '## 🤖 Claude';
    const ts = msg.timestamp ? `  \`${new Date(msg.timestamp).toLocaleString('ja-JP')}\`` : '';
    lines.push(role + ts);
    lines.push('');
    lines.push(msg.text);
    lines.push('');
  }

  const md = lines.join('\n');
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) + '.md';
  a.click();
  URL.revokeObjectURL(url);
}

function shortPath(p) {
  if (!p) return '';
  const parts = p.replace(/\\/g,'/').split('/');
  return parts.slice(-2).join('/') || p;
}

// Start
init();
</script>
</body>
</html>
"""
