"""AUTOSEG — Portal web completo de prestadores (v4).

Mesmas funções de negócios do desktop: clientes, OS, materiais, imagens, PDF,
financeiro, e-mail (rascunho) e NFS-e (rascunho). Cadastro de prestadores
exclusivo do desktop. Por padrão, escuta APENAS em 127.0.0.1.
"""
import html
import json
import yaml
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from email.parser import BytesParser
from email.policy import default
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse, quote, urlencode as urllib_parse_urlencode
from officina.core import prestadores_ext as ext
from flavors.autoseg.modules import prestador_auth
from officina.core import portal_negocios as neg
from officina.core import fluxo_os as fluxo
from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad9
from flavors.autoseg.modules import feedback_portal as feedback
from flavors.autoseg.modules import api_financeiro as api_fin
from flavors.autoseg.modules import importacao_yaml as yaml_import
from officina.core import catalogo_servicos as catalogo
from officina.core import composicao
from officina.core import empresa_financeiro as empresa
from officina.core import estoque_materiais as estoque
from flavors.autoseg.modules import portal_v9 as v9
from flavors.autoseg.modules import links_publicos as links9
from flavors.autoseg.modules import policy_shadow
from flavors.autoseg.modules import auth, login_flags, login_web
from flavors.autoseg.modules import web_cookie, web_session
from flavors.autoseg.modules import client_web, officina_web
from flavors.autoseg.modules import os_commands, account_roles, object_policy_flags
from officina.core import produtividade_os as prod
from flavors.autoseg.modules import solicitacoes_pj as pj_publico
import socket
from officina.core.versao_app import versao_local
from officina.core import runtime_config
from flavors.autoseg.modules import texto_os
from flavors.autoseg.modules import maf_loans
from officina.integration import clientes as clientes_core
from officina.repositories import ordens as ordens_repo

LOG = logging.getLogger('autosseg.portal')
VERSAO_PORTAL = versao_local('9.6.0-dev.6')


CSS_MOBILE = """
.page-actions{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}
.page-actions .btn,.page-actions button{margin:0}
.finance-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start;margin:16px 0}
.finance-columns .card{margin:0}
.finance-list{display:flex;flex-direction:column;gap:10px}
.finance-item{border:1px solid #3b3b3b;border-radius:10px;padding:12px 14px;background:#1b1b1b}
.finance-item-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.finance-item-os{font-weight:700}
.finance-item-type{font-size:12px;color:#bbb}
.finance-item-client{margin:4px 0;color:#ddd;overflow-wrap:anywhere}
.finance-item-values{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:8px 0 4px}
.finance-item-values span{font-size:12px;color:#aaa}
.finance-item-values strong{font-size:18px;color:#ffd400}
.finance-item-detail{margin:4px 0;font-size:12px;color:#aaa;overflow-wrap:anywhere}
.finance-item-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-top:8px}
.finance-item-foot form{margin:0}
.finance-item-foot button{min-height:36px;padding:8px 12px;font-size:13px}
.finance-item-foot .prazo{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.finance-item-foot .prazo label{display:flex;align-items:center;gap:6px;margin:0;font-size:12px}
.finance-item-foot .prazo input{min-height:34px;padding:6px 8px;font-size:13px}
.finance-item-foot .prazo button{min-height:34px;padding:6px 10px}
.finance-item-foot .tag.bad{background:#451b1b;color:#ffb3b3;border:1px solid #b75151}
.foto-incluir{display:flex!important;align-items:center;gap:8px;margin:8px 0;font-weight:600}
.foto-incluir input{width:18px;height:18px;min-height:0}
.foto-comprimir{display:flex!important;align-items:center;gap:8px;margin:12px 0 4px;font-weight:600}
.foto-comprimir input{width:18px;height:18px;min-height:0}
.row-link{cursor:pointer}
.total-previsto-linha{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:12px 0 8px;padding:12px 14px;border:1px solid #444;border-radius:8px;background:#1b1b1b}
.total-previsto-linha>span{color:#bbb;font-size:13px}
.total-previsto-linha strong{font-size:20px;color:#ffd400;white-space:nowrap}
.os-danger-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin:18px 0 0;padding-top:14px;border-top:1px solid #444}
@media(max-width:980px){.finance-columns{grid-template-columns:1fr}}
.lista-organizacoes-pj{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.lista-organizacoes-pj .resultado-organizacao{margin:0}
.resultado-organizacao{border:1px solid #666;border-radius:13px;padding:18px 20px;margin:14px 0;background:#202020}
.resultado-organizacao h3{margin:0 0 5px;font-size:21px}
.resultado-organizacao p{margin:4px 0 12px;color:#ddd;overflow-wrap:anywhere}
.resultado-organizacao .btn{width:100%;text-align:center;margin:0}
.aviso-claro{border-left:5px solid var(--yellow);padding:15px 18px;background:#2a2617;border-radius:8px}
.busca-pj .busca-linha{display:flex;gap:8px;align-items:flex-end}
.busca-pj .busca-linha input{flex:1;min-width:0}
@media (max-width: 760px) {
  html, body { max-width: 100%; overflow-x: hidden; }
  .top { gap: 10px; padding: 10px 14px; }
  .brand img { height: 28px !important; }
  .nav { display: flex !important; flex-wrap: wrap; gap: 6px; }
  .nav a { font-size: 13px; padding: 9px 10px; }
  main { padding: 0 12px 40px; }
  .card { padding: 16px; }
  .table-scroll { overflow-x: visible; }
  table { min-width: 0 !important; width: 100%; }
  thead { display: none; }
  tbody tr { display: block; border: 1px solid #3d3d3d; border-radius: 10px; margin: 10px 0; padding: 8px; }
  tbody td { display: block; border: 0; padding: 6px 8px; min-width: 0 !important; white-space: normal; overflow-wrap: anywhere; }
  tbody td::before { content: attr(data-label) ": "; color: #ffd400; font-weight: 700; }
  .col2 { grid-template-columns: 1fr; }
  .os-status-block { display: block; }
  .os-status-block button { width: 100%; margin-top: 8px; }
  .material-row { grid-template-columns: 1fr 1fr; }
  .material-row > div:first-child { grid-column: 1 / -1; }
  .actions button, .actions .btn, .stack button, .stack .btn { width: 100%; margin: 6px 0; }
  .foto-rascunho { grid-template-columns: 1fr !important; }
  .foto-rascunho img { width: 100% !important; height: auto !important; }
  img { max-width: 100%; height: auto; }
  input, select, textarea { font-size: 16px; }
  .busca-pj .busca-linha { display: flex; flex-direction: column; gap: 8px; }
  .busca-pj button { width: 100%; }
  .lista-organizacoes-pj { grid-template-columns: 1fr; }
}
"""

CSS_FEEDBACK = """
.feedback-fab{position:fixed;right:22px;bottom:22px;z-index:1200;box-shadow:0 8px 24px #000a;border-radius:999px;padding:14px 20px}
.feedback-dialog{width:min(680px,calc(100vw - 28px));max-height:calc(100vh - 50px);overflow:auto;border:2px solid #ffd400;border-radius:16px;background:#151515;color:#fff;padding:0;box-shadow:0 18px 60px #000d}
.feedback-dialog::backdrop{background:#000c}
.feedback-dialog form{padding:22px}
.feedback-dialog h2{margin:0 0 6px;color:#ffd400}
.feedback-dialog textarea{min-height:150px;resize:vertical}
.feedback-dialog input[readonly]{background:#222;color:#c9c9c9;border-color:#555}
.feedback-dialog .feedback-check{display:flex;gap:10px;align-items:flex-start;margin:16px 0;font-weight:600}
.feedback-dialog .feedback-check input{width:22px;height:22px;min-height:22px;margin-top:2px;flex:0 0 auto}
.feedback-dialog .feedback-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
.feedback-dialog .feedback-actions button{margin:0}
.feedback-dialog .feedback-privacidade{font-size:13px;line-height:1.5;color:#c9c9c9}
.cancel-dialog .cancel-step{padding:22px}
.cancel-dialog .cancel-step h2{margin:0 0 8px}
.cancel-dialog .cancel-step p{margin:0 0 12px}
.cancel-dialog .cancel-step textarea{min-height:110px}
.os-status-block{margin:0 0 16px;padding:12px;border:1px solid #444;border-radius:8px}
.feedback-toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:1300;max-width:min(560px,calc(100vw - 28px));background:#1e1e1e;border:1px solid #ffd400;border-radius:10px;color:#fff;padding:12px 16px;box-shadow:0 10px 30px #000c}
@media(max-width:620px){.feedback-fab{right:12px;bottom:12px;padding:12px 16px;font-size:14px}.feedback-dialog form{padding:17px}}
"""


CSS_APP = """
:root{--u-bg:#141312;--u-side:#0f0e0d;--u-card:#1a1816;--u-card-2:#201d1a;--u-raised:#27231f;--u-line:rgba(240,235,226,.08);--u-line-2:rgba(240,235,226,.15);--u-text:#f1ece3;--u-text-2:#b5aca1;--u-muted:#8b8175;--u-accent:#d8a24a;--u-accent-soft:rgba(216,162,74,.12);--u-accent-ink:#1a1308;--u-input:#11100f;--u-hover:#302b25;--u-primary-text:#17130d;--u-primary-hover:#fff;--u-good:#7cc7a2;--u-bad:#df8585;--u-warn:#d8a24a;--u-font:"Avenir Next","Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;--u-mono:"SF Mono","IBM Plex Mono","Roboto Mono",ui-monospace,monospace;--u-ease:cubic-bezier(.22,1,.36,1)}

html[data-acento="ambar"] body.ui-app{--u-accent:#d8a24a;--u-accent-soft:rgba(216,162,74,.12);--u-accent-ink:#1a1308}
html[data-acento="azul"] body.ui-app{--u-accent:#78aede;--u-accent-soft:rgba(120,174,222,.14);--u-accent-ink:#0b1721}
html[data-acento="verde"] body.ui-app{--u-accent:#7cc7a2;--u-accent-soft:rgba(124,199,162,.14);--u-accent-ink:#0b1a12}
html[data-acento="vermelho"] body.ui-app{--u-accent:#df8a8a;--u-accent-soft:rgba(223,138,138,.14);--u-accent-ink:#1e0b0b}
html[data-acento="roxo"] body.ui-app{--u-accent:#b39bdf;--u-accent-soft:rgba(179,155,223,.14);--u-accent-ink:#160f22}
html[data-acento="ciano"] body.ui-app{--u-accent:#6ec7c7;--u-accent-soft:rgba(110,199,199,.14);--u-accent-ink:#081a1a}
html[data-acento="laranja"] body.ui-app{--u-accent:#e2a06a;--u-accent-soft:rgba(226,160,106,.14);--u-accent-ink:#1d1107}
html[data-tema="claro"] body.ui-app{--u-bg:#f3f3f1;--u-side:#eaeae7;--u-card:#fff;--u-card-2:#f4f4f2;--u-raised:#e6e6e2;--u-line:rgba(24,24,24,.10);--u-line-2:rgba(24,24,24,.20);--u-text:#151515;--u-text-2:#1f1f1f;--u-muted:#333333;--u-input:#fff;--u-hover:#d9d9d4;--u-primary-text:#fff;--u-primary-hover:#74746f;--u-good:#1f6d4a;--u-bad:#9c3636;--u-warn:#7a5312}
html[data-tema="claro"] body.ui-app button,html[data-tema="claro"] body.ui-app .btn{background:#8a8a86;border-color:#8a8a86;color:#fff}
html[data-tema="claro"] body.ui-app button:hover,html[data-tema="claro"] body.ui-app .btn:hover{background:#74746f;border-color:#74746f}
html[data-tema="claro"] body.ui-app button.secondary,html[data-tema="claro"] body.ui-app .btn.secondary{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
html[data-tema="claro"] body.ui-app button.danger,html[data-tema="claro"] body.ui-app .btn.danger{background:#a34a4a;border-color:#a34a4a;color:#fff}
html[data-tema="claro"] body.ui-app .side-tool{background:transparent;border-color:var(--u-line);color:var(--u-text-2)}
html[data-tema="claro"] body.ui-app .os-tab{background:transparent;border-color:transparent;color:var(--u-muted)}
html[data-tema="claro"] body.ui-app .os-tab:hover{background:transparent;border-color:transparent;color:var(--u-text-2)}
html[data-tema="claro"] body.ui-app .os-tab.active{background:transparent;border-color:transparent;color:var(--u-text)}
html[data-tema="claro"] body.ui-app .os-form-app .actions{background:rgba(255,255,255,.97);box-shadow:0 12px 32px rgba(0,0,0,.10)}
html[data-tema="claro"] body.ui-app .theme-botoes button{background:transparent;border-color:var(--u-line-2);color:var(--u-text-2)}
html[data-tema="claro"] body.ui-app .theme-botoes button.ativo{background:var(--u-raised);color:var(--u-text);border-color:var(--u-accent)}
html[data-tema="claro"] body.ui-app .accent-botoes button{background:var(--cor);border-color:transparent}
html[data-tema="claro"] body.ui-app .accent-botoes button.ativo{border-color:var(--u-text)}
html[data-tema="claro"] body.ui-app .side-brand img{filter:none}
html[data-tema="claro"] body.ui-app .os-tab.active::after{background:var(--u-accent)}
body.ui-app .side-theme{margin:12px 0 0;padding:12px 0 0;border-top:1px solid var(--u-line)}
body.ui-app .side-theme p{margin:0 0 8px;color:var(--u-muted);font:500 11px/1.2 var(--u-mono)}
body.ui-app .theme-botoes{display:flex;gap:6px;margin-bottom:10px}
body.ui-app .theme-botoes button{flex:1;min-height:30px;padding:0 8px;border:1px solid var(--u-line-2);border-radius:7px;background:transparent;color:var(--u-text-2);font:500 11px/1.2 var(--u-font)}
body.ui-app .theme-botoes button.ativo{background:var(--u-raised);color:var(--u-text);border-color:var(--u-accent)}
body.ui-app .accent-botoes{display:flex;flex-wrap:wrap;gap:7px}
body.ui-app .accent-botoes button{width:20px;height:20px;min-height:0;padding:0;border:2px solid transparent;border-radius:50%;background:var(--cor);box-shadow:none}
body.ui-app .accent-botoes button.ativo{border-color:var(--u-text);outline:2px solid var(--u-accent);outline-offset:1px}
body.ui-app .pref-grupo{border:1px solid var(--u-line);border-radius:12px;padding:16px;margin:0 0 16px}
body.ui-app .pref-grupo legend{color:var(--u-text);font:500 14px/1.3 var(--u-font);padding:0 6px}
body.ui-app .pref-opcoes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
body.ui-app .pref-opcao{display:flex;align-items:flex-start;gap:10px;margin:0;padding:12px;border:1px solid var(--u-line);border-radius:10px;background:var(--u-card-2);cursor:pointer}
body.ui-app .pref-opcao:has(input:checked){border-color:var(--u-accent);background:var(--u-accent-soft)}
body.ui-app .pref-opcao input{margin-top:2px}
body.ui-app .pref-opcao strong{display:block;color:var(--u-text);font:500 13px/1.3 var(--u-font)}
body.ui-app .pref-opcao small{display:block;margin-top:2px;color:var(--u-muted);font:400 11px/1.4 var(--u-font)}
body.ui-app .pref-acentos{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
body.ui-app .pref-acento{display:flex;align-items:center;gap:8px;margin:0;padding:10px;border:1px solid var(--u-line);border-radius:10px;background:var(--u-card-2);cursor:pointer}
body.ui-app .pref-acento:has(input:checked){border-color:var(--u-accent);background:var(--u-accent-soft)}
body.ui-app .pref-acento input{position:absolute;opacity:0;pointer-events:none}
body.ui-app .pref-cor{width:18px;height:18px;flex:0 0 18px;border-radius:50%;background:var(--cor);box-shadow:inset 0 0 0 1px rgba(0,0,0,.15)}
body.ui-app .pref-acento em{font:500 12px/1.2 var(--u-font);font-style:normal;color:var(--u-text-2)}

body.ui-app{margin:0;background:var(--u-bg);color:var(--u-text);font:400 14px/1.55 var(--u-font);-webkit-font-smoothing:antialiased}
body.ui-app *{box-sizing:border-box}
body.ui-app header{display:none}
body.ui-app a{color:var(--u-text);text-decoration:none}
body.ui-app a:hover{color:var(--u-accent)}
body.ui-app main{margin:0 0 0 264px;max-width:1600px;min-height:calc(100vh - 64px);padding:40px 40px 96px}
body.ui-app footer{margin-left:264px;border-top:1px solid var(--u-line);color:var(--u-muted);font:400 12px/1.5 var(--u-mono);text-align:left;padding:16px 40px}
body.ui-app h1{font:500 32px/1.08 var(--u-font);letter-spacing:-.02em;margin:0 0 8px;color:var(--u-text)}
body.ui-app h2{font:500 16px/1.3 var(--u-font);letter-spacing:0;margin:0 0 14px;color:var(--u-text)}
body.ui-app h3{font:500 14px/1.35 var(--u-font);margin:18px 0 8px;color:var(--u-text)}
body.ui-app p{margin:0 0 12px}
body.ui-app .muted,body.ui-app small{color:var(--u-muted)}
body.ui-app .good{color:var(--u-good)}
body.ui-app .warn{color:var(--u-warn)}
body.ui-app .bad{color:var(--u-bad)}
body.ui-app .mono{font-family:var(--u-mono);font-variant-numeric:tabular-nums}
body.ui-app [hidden]{display:none!important}

/* controls */
body.ui-app button,body.ui-app .btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;margin:0;padding:0 16px;border:1px solid var(--u-text);border-radius:8px;background:var(--u-text);color:var(--u-primary-text);font:500 14px/1.2 var(--u-font);letter-spacing:0;text-transform:none;text-decoration:none;white-space:nowrap;cursor:pointer;box-shadow:none;transition:background .15s var(--u-ease),border-color .15s var(--u-ease),color .15s var(--u-ease),transform .12s var(--u-ease)}
body.ui-app button:hover,body.ui-app .btn:hover{background:var(--u-primary-hover);border-color:var(--u-primary-hover);color:var(--u-primary-text)}
body.ui-app button:active,body.ui-app .btn:active{transform:scale(.985)}
body.ui-app button:focus-visible,body.ui-app .btn:focus-visible,body.ui-app a:focus-visible,body.ui-app input:focus-visible,body.ui-app select:focus-visible,body.ui-app textarea:focus-visible{outline:2px solid var(--u-accent);outline-offset:2px}
body.ui-app button.secondary,body.ui-app .btn.secondary{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-app button.secondary:hover,body.ui-app .btn.secondary:hover{background:var(--u-hover);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-app button.danger,body.ui-app .btn.danger{background:rgba(223,133,133,.1);border-color:rgba(223,133,133,.3);color:var(--u-bad)}
body.ui-app button.danger:hover,body.ui-app .btn.danger:hover{background:rgba(223,133,133,.16);border-color:rgba(223,133,133,.45);color:var(--u-bad)}
body.ui-app button.subtle,body.ui-app .btn.subtle{background:transparent;border-color:var(--u-line);color:var(--u-text-2)}
body.ui-app button.subtle:hover,body.ui-app .btn.subtle:hover{background:var(--u-raised);color:var(--u-text)}
body.ui-app button:disabled{opacity:.5;cursor:wait}
body.ui-app .btn{display:inline-flex}
body.ui-app button svg,body.ui-app .btn svg{flex:0 0 16px;width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-app table button,body.ui-app table .btn{min-height:32px;padding:0 12px;border-color:var(--u-line-2);background:transparent;color:var(--u-text-2);font-size:12px}
body.ui-app table button:hover,body.ui-app table .btn:hover{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-app form[method="get"] button{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-app form[method="get"] button:hover{background:var(--u-hover);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-app .iniciar-atendimento{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-app .iniciar-atendimento:hover{background:var(--u-hover);border-color:var(--u-line-2);color:var(--u-text)}

/* forms */
body.ui-app label{display:block;margin:16px 0 8px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-app label:first-child{margin-top:0}
body.ui-app input,body.ui-app textarea,body.ui-app select{width:100%;min-height:40px;padding:8px 12px;border:1px solid var(--u-line-2);border-radius:8px;background:var(--u-input);color:var(--u-text);font:400 14px/1.4 var(--u-font);box-shadow:none}
body.ui-app input::placeholder,body.ui-app textarea::placeholder{color:#6f675e}
body.ui-app input:focus,body.ui-app textarea:focus,body.ui-app select:focus{border-color:var(--u-accent);outline:2px solid var(--u-accent);outline-offset:1px}
body.ui-app textarea{min-height:96px;resize:vertical}
body.ui-app input[type=checkbox],body.ui-app input[type=radio]{width:16px;height:16px;min-height:0;accent-color:var(--u-accent);vertical-align:middle}
body.ui-app input[type=file]{padding:8px;font-size:12px;color:var(--u-text-2)}
body.ui-app input[type=file]::file-selector-button{margin-right:8px;padding:4px 8px;border:1px solid var(--u-line-2);border-radius:7px;background:var(--u-raised);color:var(--u-text);font:500 12px/1.2 var(--u-font);cursor:pointer}
body.ui-app input[readonly]{color:var(--u-muted);background:var(--u-card-2)}
body.ui-app fieldset{border:0;padding:0;margin:0;min-width:0}
body.ui-app legend{color:var(--u-text);font:500 16px/1.3 var(--u-font);padding:0}
body.ui-app .col2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
body.ui-app .material-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,.7fr) minmax(0,1fr) auto;gap:8px;align-items:end;margin:12px 0;padding:12px;border:1px solid var(--u-line);border-radius:10px;background:var(--u-card-2)}
body.ui-app .material-add{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
body.ui-app .material-row-os{grid-template-columns:minmax(0,2fr) minmax(0,.7fr) minmax(0,.7fr) minmax(0,1fr) auto}
body.ui-app .rateio-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) auto;gap:8px;align-items:end;margin:12px 0;padding:12px;border:1px solid var(--u-line);border-radius:10px;background:var(--u-card-2)}
body.ui-app .rateio-row label{margin:0 0 4px}
body.ui-app .rateio-row input,body.ui-app .rateio-row select{min-height:36px}
body.ui-app .rateio-row button{min-height:36px;padding:0 12px}
body.ui-app .material-row label{margin:0 0 4px}
body.ui-app .material-row input{min-height:36px}
body.ui-app .material-row button{min-height:36px;padding:0 12px}
body.ui-app .material-row select{min-height:36px}
body.ui-app .composicao-preview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 24px;margin:8px 0 0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .composicao-preview span{min-width:0}
body.ui-app .composicao-preview b{color:var(--u-text-2);font-weight:400}
body.ui-app .composicao-preview .aviso{grid-column:1/-1;color:var(--u-warn)}
body.ui-app .composicao-preview .filho{padding-left:16px;color:var(--u-muted)}
body.ui-app .total-previsto-linha{border:1px solid var(--u-line);border-radius:10px;background:var(--u-card-2);padding:12px 14px}
body.ui-app .total-previsto-linha>span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .total-previsto-linha strong{color:var(--u-accent);font:500 20px/1.2 var(--u-mono)}
body.ui-app .foto-rascunho{display:grid!important;grid-template-columns:120px minmax(0,1fr)!important;gap:16px!important;align-items:start!important;margin:12px 0!important;padding:12px!important;border:1px solid var(--u-line)!important;border-radius:10px!important;background:var(--u-card-2)!important}
body.ui-app .foto-rascunho img{width:120px!important;height:90px!important;object-fit:cover!important;border-radius:8px!important}
body.ui-app .foto-rascunho label{margin-top:10px}
body.ui-app .foto-incluir{display:flex;align-items:center;gap:8px;margin:8px 0;font-weight:500}
body.ui-app .foto-incluir input{width:16px;height:16px;min-height:0}
body.ui-app .foto-comprimir{display:flex;align-items:center;gap:8px;margin:12px 0 4px;font-weight:500}
body.ui-app .foto-comprimir input{width:16px;height:16px;min-height:0}
body.ui-app #nota-fiscal-upload>div[style]{border:1px solid var(--u-line)!important;background:var(--u-card-2)!important;border-radius:10px!important}
body.ui-app #nota-fiscal-upload{margin-top:8px!important;border-top:0!important;padding-top:0!important}
body.ui-app #nota-fiscal-upload>label[style]{font-weight:500!important;color:var(--u-text)!important}

/* surfaces */
body.ui-app .card{background:var(--u-card);border:1px solid var(--u-line);border-radius:16px;padding:24px;margin:16px 0;box-shadow:none}
body.ui-app .card>h2:first-child,body.ui-app .card>h3:first-child{margin-top:0}
body.ui-app .notice{background:var(--u-card-2);border:1px solid var(--u-line);border-left:2px solid var(--u-accent);border-radius:10px;color:var(--u-text-2);padding:12px 16px;font-size:12px;line-height:1.55}
body.ui-app .notice strong{color:var(--u-text)}
body.ui-app .flash{background:rgba(124,199,162,.08);border:1px solid rgba(124,199,162,.25);color:var(--u-text);border-radius:10px;padding:12px 14px}
body.ui-app .tag{display:inline-flex;align-items:center;gap:8px;padding:0;border:0;border-radius:0;background:transparent;color:var(--u-text-2);font:400 12px/1.2 var(--u-mono)}
body.ui-app .tag::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--u-muted);flex:0 0 5px}
body.ui-app .tag:has(+ .good),body.ui-app .tag.good::before{background:var(--u-good)}
body.ui-app .table-scroll{border:1px solid var(--u-line);border-radius:12px;overflow:auto;background:var(--u-card)}
body.ui-app .table-filter-label{display:none}
body.ui-app .table-filter-input{max-width:320px;min-height:36px;margin:0 0 8px}
body.ui-app .table-filter-count{display:block;margin:0 0 8px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .home-grid .table-filter-label,body.ui-app .home-grid .table-filter-input,body.ui-app .home-grid .table-filter-count,body.ui-app .finance-grid .table-filter-label,body.ui-app .finance-grid .table-filter-input,body.ui-app .finance-grid .table-filter-count{display:none}
body.ui-app table{width:100%;min-width:640px;border-collapse:collapse}
body.ui-app th{padding:12px;border-bottom:1px solid var(--u-line);background:transparent;color:var(--u-muted);font:400 12px/1.5 var(--u-mono);text-align:left;text-transform:none;letter-spacing:0;white-space:nowrap}
body.ui-app td{padding:12px;border-bottom:1px solid var(--u-line);color:var(--u-text-2);font-size:13px;vertical-align:middle}
body.ui-app td:first-child{color:var(--u-text)}
body.ui-app tbody tr:last-child td{border-bottom:0}
body.ui-app tbody tr:hover{background:rgba(255,255,255,.02)}
body.ui-app .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:0 0 20px}
body.ui-app .kpi{display:flex;flex-direction:column;justify-content:space-between;gap:16px;min-height:112px;margin:0;padding:20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card);box-shadow:none}
body.ui-app .kpi span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .kpi strong{color:var(--u-text);font:500 28px/1 var(--u-mono);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
body.ui-app .kpi:first-child strong{color:var(--u-accent)}
body.ui-app .cartao{background:var(--u-card);border:1px solid var(--u-line);border-radius:14px;box-shadow:none}
body.ui-app .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
body.ui-app .stack{display:flex;gap:8px;flex-wrap:wrap}

/* app shell */
body.ui-app .app-side{position:fixed;inset:0 auto 0 0;z-index:100;display:flex;flex-direction:column;gap:24px;width:264px;padding:24px 16px 20px;border-right:1px solid var(--u-line);background:var(--u-side)}
body.ui-app .side-brand{display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:0 12px;text-decoration:none}
body.ui-app .side-brand img{display:block;width:auto;height:32px;max-width:176px;object-fit:contain}
body.ui-app .side-brand span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .side-menu-toggle{display:none;align-items:center;gap:8px;min-height:36px;padding:0 12px;border:1px solid var(--u-line-2);border-radius:8px;background:var(--u-raised);color:var(--u-text);font:500 12px/1.2 var(--u-font);cursor:pointer}
body.ui-app .side-mobile-head{display:none}
body.ui-app .side-nav{display:flex;flex-direction:column;gap:20px;overflow-y:auto;padding-right:2px}
body.ui-app .side-group{display:flex;flex-direction:column;gap:2px}
body.ui-app .side-label{margin:0 12px 8px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .side-link{display:flex;align-items:center;gap:10px;min-height:36px;padding:0 12px;border-radius:8px;color:var(--u-text-2);font:400 14px/1.2 var(--u-font);text-decoration:none;transition:background .15s var(--u-ease),color .15s var(--u-ease)}
body.ui-app .side-link svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-muted);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-app .side-link:hover{background:var(--u-raised);color:var(--u-text)}
body.ui-app .side-link:hover svg{color:var(--u-text-2)}
body.ui-app .side-link.active{background:var(--u-raised);color:var(--u-text);box-shadow:inset 2px 0 0 var(--u-accent)}
body.ui-app .side-link.active svg{color:var(--u-accent)}
body.ui-app .side-foot{display:flex;flex-direction:column;gap:16px;margin-top:auto;padding-top:16px;border-top:1px solid var(--u-line)}
body.ui-app .side-user{display:flex;flex-direction:column;gap:4px;padding:0 12px}
body.ui-app .side-user strong{color:var(--u-text);font:500 14px/1.3 var(--u-font)}
body.ui-app .side-user span{color:var(--u-muted);font:400 12px/1.3 var(--u-mono)}
body.ui-app .side-tools{display:flex;flex-direction:row;gap:6px}
body.ui-app .side-tool{display:flex;align-items:center;justify-content:center;gap:6px;flex:1;min-width:0;min-height:30px;padding:0 8px;border:1px solid var(--u-line);border-radius:8px;background:transparent;color:var(--u-muted);font:500 11px/1.2 var(--u-font);text-align:center;text-decoration:none;cursor:pointer}
body.ui-app .side-tool svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-muted);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-app .side-tool:hover{background:var(--u-raised);color:var(--u-text)}
body.ui-app .side-tool:hover svg{color:var(--u-text-2)}
body.ui-app .side-tool-form{display:block;margin:0}
body.ui-app .side-version{padding:0 12px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}

/* home */
body.ui-app .home-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 24px}
body.ui-app .home-toolbar .btn{flex:0 0 auto;white-space:nowrap}
body.ui-app .page-meta{color:var(--u-muted);font:400 12px/1.5 var(--u-mono);margin:0}
body.ui-app .stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0 0 24px}
body.ui-app .stat{display:flex;flex-direction:column;justify-content:space-between;gap:16px;min-height:100px;padding:20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card)}
body.ui-app .stat span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .stat strong{color:var(--u-text);font:500 28px/1 var(--u-mono);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
body.ui-app .stat:hover{border-color:var(--u-line-2);background:var(--u-card-2)}
body.ui-app .finance-figures{text-decoration:none}
body.ui-app .finance-figures:hover strong{color:var(--u-accent)}
body.ui-app a.home-note:hover{color:var(--u-accent)}
body.ui-app .home-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px;align-items:start}
body.ui-app .home-rail{display:flex;flex-direction:column;gap:16px;min-width:0}
body.ui-app .panel{padding:20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card)}
body.ui-app .panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px}
body.ui-app .panel-head h2{margin:0;font-size:16px}
body.ui-app .panel-head a{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .panel-head a:hover{color:var(--u-accent)}
body.ui-app .finance-figures{display:grid;grid-template-columns:1fr 1fr;gap:16px}
body.ui-app .finance-figures span{display:block;margin:0 0 4px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .finance-figures strong{display:block;color:var(--u-text);font:500 20px/1.1 var(--u-mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
body.ui-app .finance-figures .accent{color:var(--u-accent)}
body.ui-app .shortcut{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--u-line);color:var(--u-text-2);font-size:14px}
body.ui-app .shortcut:last-child{border-bottom:0;padding-bottom:0}
body.ui-app .shortcut:hover{color:var(--u-text)}
body.ui-app .shortcut svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-muted);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-app .home-note{margin:16px 0 0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .home-links{margin-top:20px}
body.ui-app .home-links details.card{margin:0;padding:14px 18px;border-radius:12px;background:var(--u-card)}
body.ui-app .home-links summary{color:var(--u-text-2);font:400 12px/1.5 var(--u-mono);cursor:pointer}
body.ui-app .home-links details.card p{margin:12px 0 4px;font-size:12px;overflow-wrap:anywhere}
body.ui-app .home-links details.card small{font-size:12px}

/* OS detail */
body.ui-app .os-ticket{display:grid;grid-template-columns:200px minmax(0,1fr) auto;margin:0 0 20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card);overflow:hidden}
body.ui-app .os-ticket-stub{display:flex;flex-direction:column;justify-content:space-between;gap:20px;padding:24px;border-right:1px dashed var(--u-line-2)}
body.ui-app .os-kicker{margin:0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .os-ticket-stub h2{margin:0;color:var(--u-text);font:500 28px/1 var(--u-mono);letter-spacing:-.03em}
body.ui-app .os-status{display:inline-flex;align-items:center;gap:8px;margin:0;color:var(--u-text-2);font:400 12px/1.2 var(--u-mono)}
body.ui-app .os-status .dot{width:6px;height:6px;flex:0 0 6px;border-radius:50%;background:var(--u-muted)}
body.ui-app .os-status.status--iniciada .dot,body.ui-app .os-status.status--em-rota .dot{background:var(--u-accent)}
body.ui-app .os-status.status--pendente .dot{background:var(--u-warn)}
body.ui-app .os-status.status--concluida .dot{background:var(--u-good)}
body.ui-app .os-status.status--cancelada .dot{background:var(--u-bad)}
body.ui-app .os-ticket-body{display:flex;flex-direction:column;gap:16px;padding:24px;min-width:0}
body.ui-app .os-ticket-client{margin:0;color:var(--u-text);font:500 20px/1.3 var(--u-font)}
body.ui-app .os-ticket-meta{margin:0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .os-ticket-stats{display:grid;grid-template-columns:repeat(3,minmax(80px,1fr));gap:16px}
body.ui-app .os-ticket-stats span{display:block;margin:0 0 4px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .os-ticket-stats strong{display:block;color:var(--u-text);font:500 14px/1.35 var(--u-font)}
body.ui-app .os-ticket-stats .money{color:var(--u-accent);font-family:var(--u-mono);font-variant-numeric:tabular-nums}
body.ui-app .os-ticket-actions{display:flex;flex-direction:row;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;padding:24px;border-left:1px solid var(--u-line)}
body.ui-app .os-ticket-actions .btn,body.ui-app .os-ticket-actions button{min-height:36px;font-size:12px;white-space:nowrap;width:auto}
body.ui-app .os-workflow{display:grid;grid-template-columns:1fr .8fr;gap:16px;margin:0 0 20px}
body.ui-app .os-work-status{order:-2}
body.ui-app .os-work-draft{order:-1}
body.ui-app .os-workflow .card{margin:0;padding:20px;border-radius:16px}
body.ui-app .os-workflow .card h2{margin:0 0 12px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-app .os-workflow .card p{margin:0 0 8px;font-size:12px;line-height:1.5}
body.ui-app .os-workflow .card .muted{font-size:12px}
body.ui-app .os-workflow .card form{margin:0}
body.ui-app .os-workflow .card button{margin-top:8px;min-height:36px;font-size:12px}
body.ui-app .os-workflow .card input[type=file]{padding:8px;font-size:12px}
body.ui-app .os-workflow .card .tag{margin-right:6px}
body.ui-app .os-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px;align-items:start}
body.ui-app .os-main{min-width:0;padding:24px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card)}
body.ui-app .os-form-app{display:block;margin:0}
body.ui-app .os-form-app>fieldset{border:0;padding:0;margin:0}
body.ui-app .os-form-app>fieldset>legend{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
body.ui-app .os-service-model{margin:0 0 20px;padding:16px;border:1px solid var(--u-line);border-radius:12px;background:var(--u-card-2)}
body.ui-app .os-service-model .card{margin:0;padding:0;border:0;background:transparent}
body.ui-app .os-service-model .card h2{margin:0 0 8px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-app .os-service-model .card p{margin:0 0 8px;font-size:12px}
body.ui-app .os-service-model .card label{margin-top:8px}
body.ui-app .os-tabs{display:flex;gap:24px;margin:0 0 24px;padding:0;border-bottom:1px solid var(--u-line);border-radius:0;background:transparent;overflow-x:auto}
body.ui-app .os-tab{position:relative;flex:0 0 auto;display:inline-flex;align-items:center;gap:8px;min-height:0;padding:0 0 12px;border:0;border-radius:0;background:transparent;color:var(--u-muted);font:500 14px/1.2 var(--u-font);white-space:nowrap}
body.ui-app .os-tab .tab-icon{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;line-height:0}
body.ui-app .os-tab:hover{background:transparent;border-color:transparent;color:var(--u-text-2)}
body.ui-app .os-tab.active{background:transparent;border-color:transparent;color:var(--u-text)}
body.ui-app .os-tab.active::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--u-accent)}
body.ui-app .os-tab .tab-index{color:var(--u-muted);font:400 12px/1 var(--u-mono)}
body.ui-app .os-tab.active .tab-index{color:var(--u-accent)}
body.ui-app .os-panel[hidden]{display:none}
body.ui-app .os-panel>p:first-of-type{margin-top:0}
body.ui-app .os-rail{display:flex;flex-direction:column;gap:16px;min-width:0}
body.ui-app .os-rail .card{margin:0;padding:20px;border-radius:16px}
body.ui-app .os-rail .card h2{margin:0 0 12px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-app .os-rail .card p{font-size:12px;line-height:1.55}
body.ui-app .os-rail .card .card{margin:8px 0;padding:12px 0;border:0;border-bottom:1px solid var(--u-line);border-radius:0;background:transparent}
body.ui-app .os-rail .card .card:last-child{border-bottom:0;padding-bottom:0}
body.ui-app .os-rail .card .card small{display:block;margin-bottom:4px;font:400 12px/1.5 var(--u-mono)}
body.ui-app .os-rail .card .card p{margin:0}
body.ui-app .os-rail .card form{margin:8px 0 0}
body.ui-app .os-rail .card button{min-height:36px;font-size:12px}
body.ui-app .os-rail .card input[type=file]{font-size:12px;padding:8px}
body.ui-app .os-rail .card details{margin-top:12px}
body.ui-app .os-rail .card summary{cursor:pointer;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .os-close-head{margin:24px 0 0;padding-top:20px;border-top:1px solid var(--u-line)}
body.ui-app .os-close-head h3{margin:0 0 4px;font-size:16px}
body.ui-app .os-close-head p{margin:0 0 8px;color:var(--u-muted);font-size:12px}
body.ui-app .os-form-app .actions{position:sticky;bottom:8px;z-index:20;display:flex;align-items:center;justify-content:space-between;flex-wrap:nowrap;gap:12px;margin:24px 0 0;padding:8px 12px;border:1px solid var(--u-line);border-radius:12px;background:rgba(20,19,18,.96);box-shadow:0 12px 32px rgba(0,0,0,.25)}
body.ui-app .os-form-app .actions .actions-buttons button,body.ui-app .os-form-app .actions .actions-buttons .btn{min-height:36px}
body.ui-app .actions-note{flex:1 1 auto;min-width:0;overflow:hidden;color:var(--u-muted);font:400 12px/1.5 var(--u-mono);white-space:nowrap;text-overflow:ellipsis}
body.ui-app .actions-buttons{display:flex;flex:0 0 auto;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
body.ui-app .actions-buttons button,body.ui-app .actions-buttons .btn{width:auto!important;margin:0!important}
body.ui-app .os-form-app .actions .notice{margin:0;font-size:12px}
body.ui-app .os-status-block{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 12px;align-items:end;margin:0 0 18px;padding:14px;border:1px solid var(--u-line);border-radius:12px;background:var(--u-card-2)}
body.ui-app .os-status-block label{grid-column:1/-1;margin:0}
body.ui-app .os-status-block p{grid-column:1/-1;margin:0;color:var(--u-muted);font-size:12px;line-height:1.5}
body.ui-app .os-status-block button{min-height:40px}
body.ui-app .os-status-current{color:var(--u-text-2)}
body.ui-app .os-status-actions{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
body.ui-app .os-status-actions p{flex:1 1 100%;margin:0;font-size:12px}
body.ui-app .os-status-actions button{min-height:36px}
body.ui-app .os-danger-actions{border-top:1px solid var(--u-line)}
body.ui-app .cancel-dialog .cancel-step{padding:24px}
body.ui-app .cancel-dialog .cancel-step h2{margin:0 0 8px;color:var(--u-text);font:500 20px/1.2 var(--u-font)}
body.ui-app .cancel-dialog .cancel-step p{margin:0 0 12px;color:var(--u-text-2);font-size:13px;line-height:1.55}
body.ui-app .cancel-dialog .cancel-step textarea{min-height:110px}
body.ui-app .situacao-opcoes{display:grid;grid-template-columns:1fr 1fr;gap:8px;border:0;padding:0;margin:0 0 12px}
body.ui-app .situacao-opcoes legend{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
body.ui-app .situacao-opcoes label{display:flex;align-items:center;gap:8px;margin:0;padding:10px 12px;border:1px solid var(--u-line);border-radius:8px;background:var(--u-card-2);color:var(--u-text);font:500 13px/1.2 var(--u-font);cursor:pointer}
body.ui-app .situacao-opcoes label:has(input:checked){border-color:var(--u-accent);background:var(--u-accent-soft)}
body.ui-app .situacao-opcoes input{margin:0}
body.ui-app .situacao-dialog{width:min(620px,calc(100vw - 28px))}
body.ui-app .situacao-dialog .cancel-step{padding:24px}
body.ui-app .situacao-dialog .feedback-actions{justify-content:flex-end;margin-top:18px;padding-top:14px;border-top:1px solid var(--u-line)}
body.ui-app .os-tools{margin-top:20px;border-top:1px solid var(--u-line);padding-top:16px}
body.ui-app .os-tools summary{cursor:pointer;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .os-tools summary:hover{color:var(--u-text-2)}

/* finance */
body.ui-app .finance-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 20px}
body.ui-app .finance-head .page-meta{margin:0}
body.ui-app .finance-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-flow:dense;gap:16px;margin-top:16px}
body.ui-app .finance-grid .card:nth-child(2),body.ui-app .finance-grid .card:nth-child(4){grid-column:1/-1}
body.ui-app .finance-grid .card{margin:0}
body.ui-app .finance-grid .card h2{font-size:15px}
body.ui-app .finance-note{margin:0 0 20px;color:var(--u-text-2);font-size:12px;line-height:1.6}
body.ui-app .finance-note strong{color:var(--u-text)}
body.ui-app .finance-columns .card{margin:0;padding:20px;border-radius:16px}
body.ui-app .finance-item{padding:16px;border:1px solid var(--u-line);border-radius:12px;background:var(--u-card-2)}
body.ui-app .finance-item-os{color:var(--u-text);font:500 15px/1.3 var(--u-font)}
body.ui-app .finance-item-type{color:var(--u-muted);font:400 12px/1.4 var(--u-mono)}
body.ui-app .finance-item-client{margin:4px 0;color:var(--u-text-2);font-size:13px;overflow-wrap:anywhere}
body.ui-app .finance-item-values span{color:var(--u-muted);font:400 12px/1.4 var(--u-mono)}
body.ui-app .finance-item-values strong{color:var(--u-accent);font:500 20px/1.1 var(--u-mono);letter-spacing:-.02em}
.finance-tools{display:flex;justify-content:flex-end;margin:0 0 10px}
.finance-shell.fin-masked .kpi strong,.finance-shell.fin-masked .finance-item-values strong{visibility:hidden}
.finance-shell.fin-masked .finance-item-values strong::after,.finance-shell.fin-masked .kpi strong::after{content:"R$ ••••";visibility:visible;position:absolute;inset:0;display:flex;align-items:center}
.finance-shell.fin-masked .finance-item-values strong,.finance-shell.fin-masked .kpi strong{position:relative}
body.ui-app .finance-item-detail{color:var(--u-muted);font:400 12px/1.5 var(--u-mono);overflow-wrap:anywhere}
body.ui-app .finance-item-foot .tag{display:inline-flex;align-items:center;margin:0;padding:4px 10px;border:1px solid transparent;border-radius:999px;font:600 11px/1.2 var(--u-font)}
body.ui-app .finance-item-foot .tag::before{display:none}
body.ui-app .finance-item-foot .tag.good{background:rgba(124,199,162,.14);color:var(--u-good);border-color:rgba(124,199,162,.35)}
body.ui-app .finance-item-foot .tag.bad{background:rgba(223,133,133,.12);color:var(--u-bad);border:1px solid rgba(223,133,133,.35)}
body.ui-app .finance-item-foot .prazo input{background:var(--u-card);border:1px solid var(--u-line-2);color:var(--u-text);border-radius:8px}

/* login */
body.ui-app.ui-login main{min-height:100vh;max-width:none;margin:0;padding:0}
body.ui-app.ui-login main>h1{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
body.ui-app.ui-login footer{margin-left:0;padding:14px 32px;text-align:center}
body.ui-app .login-shell{display:grid;grid-template-columns:minmax(0,1fr) 460px;min-height:100vh}
body.ui-app .login-brand{display:flex;flex-direction:column;justify-content:space-between;gap:48px;padding:56px;border-right:1px solid var(--u-line);background:var(--u-side)}
body.ui-app .login-brand img{display:block;width:auto;height:40px;max-width:240px;object-fit:contain}
body.ui-app .login-brand-copy{max-width:560px}
body.ui-app .login-brand h1,body.ui-app .login-brand .login-headline{max-width:13ch;margin:0 0 16px;color:var(--u-text);font:500 40px/1.06 var(--u-font);letter-spacing:-.03em}
body.ui-app .login-brand p{max-width:50ch;margin:0;color:var(--u-text-2);font-size:14px;line-height:1.65}
body.ui-app .login-facts{display:flex;flex-direction:column;gap:12px;margin-top:32px}
body.ui-app .login-fact{display:flex;align-items:center;gap:8px;color:var(--u-text-2);font-size:14px}
body.ui-app .login-fact svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-accent);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-app .login-brand-foot{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-app .login-panel{display:flex;flex-direction:column;justify-content:center;padding:56px 48px;background:var(--u-bg)}
body.ui-app .login-panel h2{margin:0 0 8px;font:500 28px/1.2 var(--u-font);letter-spacing:-.02em}
body.ui-app .login-lede{margin:0 0 24px;color:var(--u-muted);font-size:12px}
body.ui-app .login-form button{width:100%;margin-top:20px}
body.ui-app .login-note{margin:20px 0 0;color:var(--u-muted);font-size:12px;line-height:1.6}
body.ui-app .login-links{margin-top:28px}
body.ui-app .login-links details.card{margin:0;padding:16px;border-radius:12px;background:var(--u-card)}
body.ui-app .login-links summary{cursor:pointer;color:var(--u-text-2);font:400 12px/1.5 var(--u-mono)}
body.ui-app .login-links p{margin:12px 0 4px;font-size:12px;overflow-wrap:anywhere}
body.ui-app .login-links small{font-size:12px}

/* feedback */
body.ui-app .feedback-fab{display:none}
body.ui-app .feedback-dialog{width:min(640px,calc(100vw - 28px));max-height:calc(100vh - 48px);padding:0;border:1px solid var(--u-line-2);border-radius:16px;background:var(--u-card);color:var(--u-text);box-shadow:0 24px 80px rgba(0,0,0,.55)}
body.ui-app .feedback-dialog::backdrop{background:rgba(0,0,0,.7)}
body.ui-app .feedback-dialog form{padding:24px}
body.ui-app .feedback-dialog h2{margin:0 0 6px;color:var(--u-text);font:500 20px/1.2 var(--u-font)}
body.ui-app .feedback-dialog .feedback-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
body.ui-app .feedback-dialog .feedback-privacidade{color:var(--u-muted);font-size:12px;line-height:1.6}
body.ui-app .feedback-toast{left:50%;bottom:20px;max-width:min(560px,calc(100vw - 28px));padding:12px 16px;border:1px solid var(--u-line-2);border-left:2px solid var(--u-accent);border-radius:10px;background:var(--u-card);color:var(--u-text);box-shadow:0 16px 48px rgba(0,0,0,.45);font-size:12px;line-height:1.5;transform:translateX(-50%)}

/* responsive */
@media(max-width:1200px){
  body.ui-app main{padding:32px 28px 88px}
  body.ui-app .os-layout,body.ui-app .home-grid{grid-template-columns:minmax(0,1fr) 300px}
  body.ui-app .os-ticket{grid-template-columns:172px minmax(0,1fr)}
  body.ui-app .os-ticket-actions{grid-column:1/-1;flex-direction:row;flex-wrap:wrap;justify-content:flex-end;border-left:0;border-top:1px solid var(--u-line)}
}
@media(max-width:980px){
  body.ui-app .app-side{position:relative;width:auto;padding:12px 16px;border-right:0;border-bottom:1px solid var(--u-line);gap:12px;flex-direction:row;align-items:center;justify-content:space-between}
  body.ui-app .side-brand{flex-direction:row;align-items:center;gap:10px}
  body.ui-app .side-brand img{height:28px}
  body.ui-app .side-brand span{display:none}
  body.ui-app.menu-open{overflow:hidden}
  body.ui-app .side-menu-toggle{display:inline-flex}
  body.ui-app .side-nav{display:none;position:fixed;inset:0;z-index:1000;flex-direction:column;gap:6px;height:100dvh;max-height:none;overflow-y:auto;padding:18px 20px 104px;background:var(--u-side)}
  body.ui-app .side-nav.open{display:flex}
  body.ui-app .side-mobile-head{display:flex;align-items:center;justify-content:flex-end;gap:12px;padding:0 4px 10px;margin-bottom:4px;border-bottom:1px solid var(--u-line)}
  body.ui-app .side-mobile-head>div{display:none}
  body.ui-app .side-mobile-head strong{display:block;font:500 16px/1.3 var(--u-font)}
  body.ui-app .side-mobile-head span{display:block;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
  body.ui-app.menu-open .side-nav.open{height:calc(100dvh - var(--menu-foot-h, 0px));bottom:auto;overflow:hidden;padding:10px 16px 12px;gap:4px}
  body.ui-app.menu-open .side-nav.open .side-group{display:contents}
  body.ui-app.menu-open .side-nav.open .side-label{display:none}
  body.ui-app.menu-open .side-nav.open .side-mobile-head{flex:0 0 auto}
  body.ui-app.menu-open .side-nav.open .side-link{flex:1 1 0;min-height:0;padding:0 12px;font-size:16px}
  body.ui-app.menu-open .side-nav.open .side-link svg{width:20px;height:20px;flex:0 0 20px}
  body.ui-app.menu-open .side-foot{padding:8px 16px}
  body.ui-app.menu-open .side-foot .side-user{padding:0}
  body.ui-app.menu-open .side-foot .side-tool{min-height:28px}
  body.ui-app .os-form-app .actions{position:static;margin-bottom:28px}
  body.ui-app .os-form-app{padding-bottom:80px}
  body.ui-app #fechar-side-nav{width:40px;height:40px;min-height:40px;padding:0;border:1px solid var(--u-line-2);border-radius:10px;background:var(--u-raised);color:var(--u-text);font-size:22px;line-height:1}
  body.ui-app .side-group{flex-direction:column;gap:2px}
  body.ui-app .side-label{display:block;margin:14px 12px 6px;color:var(--u-muted);font-size:12px}
  body.ui-app .side-link{white-space:normal;min-height:46px;padding:0 14px;font-size:15px}
  body.ui-app .side-link svg{display:block;flex:0 0 20px;width:20px;height:20px}
  body.ui-app .side-foot{display:none}
  body.ui-app.menu-open .side-foot{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:1001;padding:8px 16px;background:var(--u-side);border-top:1px solid var(--u-line)}
  body.ui-app.menu-open .side-foot .side-user{flex-direction:row;align-items:center;gap:8px;padding:0}
  body.ui-app.menu-open .side-foot .side-user strong{font-size:14px}
  body.ui-app.menu-open .side-foot .side-user span{font-size:11px}
  body.ui-app.menu-open .side-foot .side-tools{flex-direction:row;gap:6px}
  body.ui-app.menu-open .side-foot .side-tool-form{flex:1}
  body.ui-app.menu-open .side-foot .side-tool{flex:1;justify-content:center;min-height:32px;padding:0 8px;border:1px solid var(--u-line);background:var(--u-raised)}
  body.ui-app.menu-open .side-foot .side-version{display:none}
  body.ui-app.menu-open .side-foot .side-user{display:flex;flex-direction:column;gap:4px}
  body.ui-app .feedback-fab{display:inline-flex}
  body.ui-app main{margin:0;padding:28px 20px 80px}
  body.ui-app footer{margin-left:0;padding:14px 20px}
  body.ui-app .os-layout,body.ui-app .home-grid{grid-template-columns:1fr}
  body.ui-app .os-rail{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
  body.ui-app .os-workflow{grid-template-columns:1fr 1fr}
  body.ui-app .os-workflow .card:first-child{grid-column:1/-1}
  body.ui-app .login-shell{grid-template-columns:1fr}
  body.ui-app .login-brand{border-right:0;border-bottom:1px solid var(--u-line);padding:36px 28px;gap:28px}
  body.ui-app .login-brand h1,body.ui-app .login-brand .login-headline{font-size:32px;max-width:18ch}
  body.ui-app .login-facts{display:none}
  body.ui-app .login-panel{padding:36px 28px}
}
@media(max-width:720px){
  body.ui-app h1{font-size:28px}
  body.ui-app .os-tabs{flex-wrap:wrap;overflow-x:visible;gap:12px 18px}
  body.ui-app .os-tab{white-space:normal}
  body.ui-app .stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  body.ui-app .os-ticket{grid-template-columns:1fr}
  body.ui-app .os-ticket-stub{order:1;border-right:0;border-bottom:1px dashed var(--u-line-2)}
  body.ui-app .os-ticket-actions{order:2;border-top:1px solid var(--u-line)}
  body.ui-app .os-ticket-body{order:3;border-top:1px solid var(--u-line)}
  body.ui-app .os-workflow{grid-template-columns:1fr}
  body.ui-app .os-workflow .card:first-child{grid-column:auto}
  body.ui-app .os-main{padding:20px}
  body.ui-app .col2{grid-template-columns:1fr}
  body.ui-app .os-status-block{grid-template-columns:1fr}
  body.ui-app .os-status-block button{width:100%}
  body.ui-app .material-row{grid-template-columns:1fr 1fr}
  body.ui-app .rateio-row{grid-template-columns:1fr 1fr}
  body.ui-app .rateio-row>div:first-child,body.ui-app .rateio-row>div:nth-child(2){grid-column:1/-1}
  body.ui-app .rateio-row button{grid-column:1/-1;width:100%}
  body.ui-app .material-row>div:first-child{grid-column:1/-1}
  body.ui-app .material-row button{grid-column:1/-1;width:100%}
  body.ui-app .foto-rascunho{grid-template-columns:1fr!important}
  body.ui-app .foto-rascunho img{width:100%!important;height:auto!important}
  body.ui-app .os-form-app .actions{flex-direction:column;align-items:stretch;bottom:8px}
  body.ui-app .actions-buttons{flex-direction:column;align-items:stretch}
  body.ui-app .actions-buttons button,body.ui-app .actions-buttons .btn{width:100%!important}
  body.ui-app .finance-figures{grid-template-columns:1fr 1fr}
  body.ui-app .finance-grid{grid-template-columns:1fr}
  body.ui-app .finance-grid .card:nth-child(2),body.ui-app .finance-grid .card:nth-child(4){grid-column:auto}
  body.ui-app .home-toolbar{align-items:flex-start;flex-direction:column}
  body.ui-app .pref-opcoes{grid-template-columns:1fr}
  body.ui-app .pref-acentos{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:520px){
  body.ui-app main{padding:24px 14px 72px}
  body.ui-app .stat-grid{grid-template-columns:1fr 1fr}
  body.ui-app .finance-figures{grid-template-columns:1fr}
  body.ui-app .login-panel{padding:28px 20px}
  body.ui-app .login-brand{padding:28px 20px}
  body.ui-app .os-ticket-stub,body.ui-app .os-ticket-body,body.ui-app .os-ticket-actions{padding:20px}
  body.ui-app .os-ticket-actions{flex-direction:column;align-items:stretch}
  body.ui-app .os-ticket-actions .btn,body.ui-app .os-ticket-actions button{width:100%}
  body.ui-app .os-ticket-stats{grid-template-columns:1fr 1fr}
  body.ui-app .panel{padding:16px}
}
"""


SESSOES = {}
TENTATIVAS = {}
LOCK_DOCS = threading.Lock()
LOCK_LOGIN = threading.Lock()
MAX_POST = 90 * 1024 * 1024
PREAUTH_MAX = 64 * 1024


def _podar_mapas_sessao():
    agora=time.time()
    with LOCK_LOGIN:
        for chave,sessao in list(SESSOES.items()):
            if sessao.get('exp',0)<agora:
                SESSOES.pop(chave,None)
        for chave,tempos in list(TENTATIVAS.items()):
            recentes=[t for t in tempos if agora-t<600]
            if recentes:
                TENTATIVAS[chave]=recentes
            else:
                TENTATIVAS.pop(chave,None)


def url_os(banco, token, sufixo=''):
    """Canonical public URL for an OS, alias or internal id."""
    return ordens_repo.url_os(banco, token, sufixo)


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def dinheiro(v):
    return neg.dinheiro(v)


def numero_seguro(v):
    try: return neg.numero(v)
    except (TypeError,ValueError): return 0.0


def data_curta(valor):
    texto=str(valor or '').strip()
    if len(texto)>=10 and texto[4]=='-' and texto[7]=='-':
        return f'{texto[8:10]}/{texto[5:7]}/{texto[0:4]}'
    return texto[:10]


def data_hora_br(valor):
    texto=str(valor or '').strip()
    if len(texto)>=16 and texto[4]=='-' and texto[7]=='-' and texto[10] in (' ','T'):
        return f'{texto[8:10]}/{texto[5:7]}/{texto[0:4]} {texto[11:16]}'
    return texto




def campos_escuros(caption, name, value='', required=False, kind='text', placeholder='', readonly=False):
    return (f'<label for="c_{esc(name)}">{esc(caption)}</label>'
            f'<input id="c_{esc(name)}" type="{esc(kind)}" name="{esc(name)}" value="{esc(value)}" '
            f'placeholder="{esc(placeholder)}" {"required" if required else ""} {"readonly" if readonly else ""}>')


UNIDADES_MATERIAL = (
    ('un', 'Unidade'), ('m', 'Metro'), ('cm', 'Centímetro'), ('mm', 'Milímetro'),
    ('g', 'Grama'), ('kg', 'Quilograma'), ('L', 'Litro'), ('ml', 'Mililitro'),
    ('h', 'Hora'), ('par', 'Par'), ('rolo', 'Rolo'), ('caixa', 'Caixa'),
    ('pacote', 'Pacote'),
)


def datalist_unidades_material():
    return ('<datalist id="unidades-material">'
            + ''.join(f'<option value="{esc(chave)}">{esc(rotulo)}</option>'
                      for chave,rotulo in UNIDADES_MATERIAL)
            + '</datalist>')


def input_unidade_material(valor=''):
    return (f'<input name="material_unidade[]" list="unidades-material" '
            f'maxlength="40" value="{esc(valor or "")}" placeholder="un, m, cm, g..." '
            f'autocomplete="off" aria-label="Unidade do material">')


def textarea(caption,name,value='',rows=4,required=False):
    return f'<label for="c_{esc(name)}">{esc(caption)}</label><textarea id="c_{esc(name)}" name="{esc(name)}" rows="{int(rows)}" {"required" if required else ""}>{esc(value)}</textarea>'


def select(caption,name,items,value='',required=False):
    opts=''.join(f'<option value="{esc(k)}" {"selected" if str(value)==str(k) else ""}>{esc(v)}</option>' for k,v in items)
    return f'<label for="c_{esc(name)}">{esc(caption)}</label><select id="c_{esc(name)}" name="{esc(name)}" {"required" if required else ""}>{opts}</select>'


def botao(txt,href,kind=''):
    return f'<a class="btn {esc(kind)}" href="{esc(href)}">{esc(txt)}</a>'


def card(titulo,conteudo):
    return f'<section class="card"><h2>{esc(titulo)}</h2>{conteudo}</section>'


def tabela(headers, rows):
    if not rows:
        return '<p class="muted">Nenhum registro encontrado.</p>'
    def linha(cells):
        saida=''
        for i,x in enumerate(cells):
            rotulo=esc(headers[i] if i<len(headers) else '')
            saida+=f'<td data-label="{rotulo}">{x}</td>'
        return saida
    return '<div class="table-scroll"><table><thead><tr>'+''.join(f'<th>{esc(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+linha(cells)+'</tr>' for cells in rows)+'</tbody></table></div>'


def _dialogo_feedback(usuario, banco=None):
    """Botão e diálogo globais do Portal do Prestador (nunca no portal do cliente)."""
    if not usuario:
        return ''
    rascunho = None
    if banco:
        try:
            rascunho = feedback.ultimo_rascunho(banco, usuario)
        except Exception:
            rascunho = None
    mensagem_rascunho = esc(rascunho.get('mensagem') or '') if rascunho else ''
    responder_marcado = ' checked' if rascunho and rascunho.get('responder_ia') else ''
    rascunho_id = str(rascunho.get('id') or '') if rascunho else ''
    return f'''
<button type="button" class="feedback-fab" id="abrir-feedback" aria-haspopup="dialog" aria-controls="dialogo-feedback">Dê um feedback</button>
<dialog class="feedback-dialog" id="dialogo-feedback" aria-labelledby="feedback-titulo">
  <form method="post" action="/feedback" id="form-feedback" data-no-ajax>
    <input type="hidden" name="csrf" value="{esc(usuario.get('csrf',''))}">
    <input type="hidden" name="rascunho_id" id="feedback-rascunho-id" value="{rascunho_id}">
    <input type="hidden" name="ui_mode" id="feedback-ui-mode" value="">
    <input type="hidden" name="aba" id="feedback-aba" value="">
    <input type="hidden" name="diagnostico" id="feedback-diagnostico" value="">
    <h2 id="feedback-titulo">Dê um feedback</h2>
    <p class="muted">Conte o que funcionou, o que confundiu ou o que precisa melhorar nesta página.</p>
    <label for="feedback-pagina">Página atual</label>
    <input type="text" id="feedback-pagina" name="pagina" value="" readonly autocomplete="off">
    <label for="feedback-mensagem">Seu feedback</label>
    <textarea id="feedback-mensagem" name="mensagem" minlength="5" maxlength="4000" rows="6" required placeholder="Ex.: não encontrei onde alterar o preço do serviço; ou: o botão de iniciar OS não apareceu para mim.">{mensagem_rascunho}</textarea>
    <label class="feedback-check" for="feedback-responder-ia">
      <input type="checkbox" id="feedback-responder-ia" name="responder_ia" value="1"{responder_marcado}>
      <span>Pedir uma resposta da IA com base no conhecimento do AUTOSEG (opcional)</span>
    </label>
    <p class="muted feedback-privacidade">O texto digitado aqui é salvo automaticamente como feedback incompleto, mesmo que você não clique em enviar; ao enviar, ele vira um feedback completo. Use Cancelar para descartar o rascunho. Ao enviar, registramos seu usuário, a página, o navegador, o dispositivo e o endereço IP (a rede é truncada por padrão) para diagnóstico e segurança. Se você pedir resposta por IA, o texto é anonimizado antes de sair do servidor. A IA pode errar e não altera o sistema; o feedback fica para revisão humana.</p>
    <p class="muted" id="feedback-envio-status" role="status" aria-live="polite"></p>
    <div class="feedback-actions">
      <button type="submit">Enviar feedback</button>
      <button type="button" class="secondary" id="fechar-feedback">Cancelar</button>
    </div>
  </form>
</dialog>
<div class="feedback-toast" id="feedback-toast" role="status" aria-live="polite" hidden></div>'''


ICONES = {
    'home': '<path d="m3 10 9-7 9 7v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 21V12h6v9"/>',
    'clipboard': '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h6"/>',
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    'wrench': '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2z"/>',
    'wallet': '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M16 12h.01"/><path d="M2 10h20"/>',
    'receipt': '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z"/><path d="M8 7h8M8 11h8M8 15h5"/>',
    'mail': '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    'history': '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>',
    'building': '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.14.36.35.7.6 1 .3.3.7.45 1.1.45H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.55z"/>',
    'message': '<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>',
    'logout': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    'layout': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>',
    'arrow-right': '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    'arrow-left': '<path d="M19 12H5"/><path d="m11 18-6-6 6-6"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    'camera': '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
}


def icone(nome, classe=''):
    return ('<svg class="' + esc(classe) + '" viewBox="0 0 24 24" aria-hidden="true">'
            + ICONES.get(nome, ICONES['info']) + '</svg>')


def classe_status(status):
    texto=str(status or '').lower()
    for antigo,novo in (('á','a'),('à','a'),('â','a'),('ã','a'),('é','e'),('ê','e'),
                        ('í','i'),('ó','o'),('ô','o'),('õ','o'),('ú','u'),('ç','c')):
        texto=texto.replace(antigo,novo)
    return 'status--'+re.sub(r'[^a-z0-9]+','-',texto).strip('-')


def chip_status(status):
    return (f'<span class="os-status {classe_status(status)}"><i class="dot"></i>'
            f'{esc(status)}</span>')


def _grupos_navegacao(usuario, navigation=None):
    """Group data from the ONE Officina Web navigation table."""
    from flavors.autoseg.modules import officina_web
    navigation = navigation if navigation is not None else officina_web.context_for(usuario).navigation
    groups = []
    for item in navigation:
        if not groups or groups[-1][0] != item.group:
            groups.append((item.group, []))
        groups[-1][1].append((item.href, item.label, item.icon))
    return groups


def layout_app(titulo,corpo,usuario=None,nonce=None,path='/',cliente=False,banco=None,
               page_context=None,navigation=None):
    """Experimental interface: a quiet work-order shell around the same flow."""
    base=layout(titulo,corpo,usuario,nonce,cliente,banco, navigation=navigation,
                page_context=page_context)
    prefs={'tema':'auto','acento':'ambar'}
    if usuario and not cliente and banco:
        try:
            prefs=prestador_auth.obter_preferencias(banco,usuario['pid'])
        except (OSError,ValueError):
            prefs={'tema':'auto','acento':'ambar'}
    base=base.replace('<html lang="pt-BR">',
                      f'<html lang="pt-BR" data-tema="{esc(prefs["tema"])}" '
                      f'data-preferencia-tema="{esc(prefs["tema"])}" '
                      f'data-acento="{esc(prefs["acento"])}">',1)
    login=not usuario
    body_class='ui-app'+(' ui-login' if login else '')
    base=base.replace('<body>',f'<body class="{body_class}">',1)
    base=base.replace('</style>',CSS_APP+'</style>',1)
    sidebar=''
    if usuario:
        grupos=_grupos_navegacao(usuario, navigation)
        context_label = page_context.context_label if page_context else 'Portal do prestador'
        audience = 'Cliente' if page_context and page_context.kind == 'client' else 'Prestador'
        def ativo(url):
            return path==url or (url!='/' and path.startswith(url+'/'))
        blocos=''
        for rotulo,itens in grupos:
            links=''.join(
                f'<a class="side-link{" active" if ativo(url) else ""}" href="{url}">'
                f'{icone(nome_icone)}<span>{esc(nome)}</span></a>'
                for url,nome,nome_icone in itens)
            blocos+=f'<div class="side-group"><p class="side-label">{esc(rotulo)}</p>{links}</div>'
        csrf=esc(usuario.get('csrf',''))
        feedback_side = ('' if page_context and page_context.kind == 'client' else
                         '<button type="button" class="side-tool" id="abrir-feedback-side">'
                         + icone('message') + '<span>Feedback</span></button>')
        sidebar=(f'<aside class="app-side">'
                 '<a class="side-brand" href="/"><img src="/logo.png" alt="AUTOSEG">'
                 f'<span>{esc(context_label)}</span></a>'
                 '<button type="button" class="side-menu-toggle" id="toggle-side-nav" '
                 'aria-expanded="false" aria-controls="side-nav">☰ Menu</button>'
                 f'<nav class="side-nav" id="side-nav" aria-label="Navegação principal">'
                 f'<div class="side-mobile-head"><div><strong>{esc(usuario.get("nome",""))}</strong>'
                 f'<span>{esc(audience)}</span></div>'
                 '<button type="button" id="fechar-side-nav" aria-label="Fechar menu">×</button></div>'
                 f'{blocos}</nav>'
                 '<div class="side-foot">'
                 f'<div class="side-user"><strong>{esc(usuario.get("nome",""))}</strong>'
                 f'<span>{esc(audience)}</span></div>'
                 '<div class="side-tools">'
                 f'{feedback_side}'
                 f'<form method="post" action="/sair" class="side-tool-form">'
                 f'<input type="hidden" name="csrf" value="{csrf}">'
                 f'<button class="side-tool" type="submit">{icone("logout")}<span>Sair</span></button></form>'
                 '</div>'
                 f'<div class="side-version">AUTOSEG {VERSAO_PORTAL}</div>'
                 '</div></aside>')
        base=base.replace(f'<body class="{body_class}">',
                          f'<body class="{body_class}">{sidebar}',1)
    return base


def login_shell_markup(*, form_html, lede, note='', links='', kicker='Officina Web',
                       headline='A OS, o relatório e o recebimento do prestador no mesmo lugar',
                       description='Prestadores registram o serviço; clientes acompanham as ordens, '
                                   'documentos e o que já foi recebido.',
                       facts=(('clipboard', 'Ordens e relatórios'),
                              ('wallet', 'Financeiro e repasses'),
                              ('file', 'Notas fiscais e documentos')),
                       title='Entrar'):
    """Render the AUTOSEG split-screen login used by both login modes."""
    fact_html = ''.join(f'<div class="login-fact">{icone(nome)}'
                        f'<span>{esc(texto)}</span></div>' for nome, texto in facts)
    note_html = f'<p class="login-note">{esc(note)}</p>' if note else ''
    links_html = f'<div class="login-links">{links}</div>' if links else ''
    return (f'<div class="login-shell">'
            f'<section class="login-brand">'
            f'<div><img src="/logo.png" alt="AUTOSEG">'
            f'<div class="login-brand-copy">'
            f'<p class="os-kicker">{esc(kicker)}</p>'
            f'<p class="login-headline">{esc(headline)}</p>'
            f'<p>{esc(description)}</p>'
            f'<div class="login-facts">{fact_html}</div></div></div>'
            f'<p class="login-brand-foot">AUTOSEG {VERSAO_PORTAL}</p>'
            f'</section>'
            f'<section class="login-panel">'
            f'<h2>{esc(title)}</h2>'
            f'<p class="login-lede">{esc(lede)}</p>'
            f'{form_html}{note_html}{links_html}'
            f'</section></div>')


def layout(titulo,corpo,usuario=None,nonce=None,cliente=False,banco=None,
           navigation=None,page_context=None):
    # NavItem is defined once in the AUTOSEG flavor. Both surfaces consume
    # the exact same filtered navigation snapshot; never re-check admin here.
    if usuario:
        from flavors.autoseg.modules import officina_web
        from flavors.autoseg.modules.autoseg_web_navigation import top_navigation_for
        visible = navigation if navigation is not None else officina_web.context_for(usuario).navigation
        top_items = top_navigation_for(page_context, visible)
        links = tuple((item.href, item.label) for item in top_items)
        nav = (''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in links[:4])
               + '<details class="nav-more"><summary>Mais opções</summary>'
               + ''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in links[4:])
               + '</details>')
    else:
        nav = ''
    audience = 'Cliente' if page_context and page_context.kind == 'client' else 'Prestador'
    us=f'<span class="usuario">{esc(usuario["nome"])} · {audience}</span>' if usuario else ''
    ambiente='DEV (testes)' if os.environ.get('AUTOSEG_DEV')=='1' else 'produção'
    footer=f'''<footer>AUTOSEG {VERSAO_PORTAL} · ambiente {ambiente} · relatórios por e-mail e NFS-e em anexo quando cadastrados.</footer>'''
    feedback_html=_dialogo_feedback(None if cliente else usuario, banco)
    logout=(f'<form method="post" action="/sair" class="logout"><input type="hidden" name="csrf" value="{esc(usuario["csrf"])}">'
            '<button class="subtle">Sair</button></form>') if usuario else ''
    # Identical brand/topbar in both contexts; context controls text only.
    topo=('<a class="brand" href="/" style="display:flex;align-items:center;gap:10px">'
          '<img src="/logo.png" alt="AUTOSEG" style="height:34px;max-width:150px;object-fit:contain;display:block">'
          '<span style="font-size:13px;color:#ddd;font-weight:600">Gestão de Serviços</span></a>'
          '<span class="tagline">AUTOMAÇÃO E SEGURANÇA · Portal de Serviços</span>')
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)} · AUTOSEG</title><link rel="icon" href="/icone.png" type="image/png"><style>
:root{{--yellow:#ffd400;--bg:#080808;--card:#191919;--border:#424242;--muted:#bababa;--green:#52edb2;--red:#ff7d7d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:#fff;font:16px -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.45}}
a{{color:var(--yellow)}}header{{background:#171717;border-bottom:3px solid var(--yellow)}}.top{{max-width:1240px;margin:auto;display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:12px 18px}}
.brand{{color:var(--yellow);font-size:26px;font-weight:900;letter-spacing:.3px;text-decoration:none}}.tagline{{color:#ddd;font-size:13px}}
.nav{{display:flex;gap:6px;flex-wrap:wrap;max-width:1240px;margin:auto;padding:0 18px 13px}}.nav a{{color:#fff;text-decoration:none;border:1px solid #414141;padding:10px 13px;border-radius:8px;font-weight:650}}.nav a:hover{{background:var(--yellow);color:#101010}}.nav-more{{position:relative;z-index:2;border:1px solid #414141;border-radius:8px;padding:9px 13px}}.nav-more summary{{cursor:pointer;font-weight:650}}.nav-more[open]{{background:#232323}}.nav-more a{{display:block;margin:8px 0}}
main{{max-width:1240px;margin:20px auto;padding:0 18px 50px;min-width:0}}h1{{font-size:clamp(22px,4vw,32px);margin:14px 0}}h2{{font-size:21px;margin:0 0 15px}}h3{{font-size:17px;margin:10px 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin:15px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:13px}}.grid .card{{margin:0}}
label{{display:block;margin:13px 0 5px;font-weight:650}}input,textarea,select{{width:100%;font:inherit;color:#fff;background:#090909;border:1.5px solid #989898;border-radius:7px;padding:10px;max-width:100%}}
input:focus,textarea:focus,select:focus{{outline:2px solid var(--yellow)}}input[type=file]{{padding:12px}}input[type=checkbox]{{width:auto}}
button,.btn{{display:inline-flex;align-items:center;justify-content:center;max-width:100%;overflow-wrap:anywhere;white-space:normal;text-align:center;vertical-align:middle;min-width:0;border-radius:8px;font:bold 15px Arial;padding:13px 16px;cursor:pointer;color:#161616;background:var(--yellow);border:1px solid var(--yellow);text-decoration:none;margin:4px 5px 4px 0;min-height:44px}}
button.secondary,.btn.secondary{{background:#262626;border-color:#9b9b9b;color:#fff}}button.danger,.btn.danger{{background:#451b1b;color:#fff;border-color:#b75151}}button.subtle{{background:transparent;color:#fff;border:1px solid #777}}
.usuario{{color:#ddd;font-size:13px}}.logout{{margin:0 0 0 auto}}.muted,small{{color:var(--muted)}}.good{{color:var(--green)}}.warn{{color:#ffce79}}.bad{{color:var(--red)}}.tag{{background:#4a400c;color:#ffe678;border-radius:6px;padding:4px 9px;font-size:13px;white-space:nowrap}}
.table-scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:640px}}th,td{{border-bottom:1px solid #414141;padding:12px 10px;text-align:left;vertical-align:top;overflow-wrap:normal;word-break:normal}}th{{color:var(--yellow);background:#222}}td:nth-child(3){{min-width:125px}}td:nth-child(3),td:nth-child(4),td:nth-child(5){{overflow-wrap:normal;word-break:normal}} .material-row button{{min-width:90px}}.col2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px}}.actions{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.kpi{{background:#171717;border:1px solid #444;padding:17px;border-radius:10px}}.kpi strong{{display:block;font-size:26px;color:var(--yellow)}}.kpi span{{font-size:13px;color:var(--muted)}}
form{{max-width:100%;min-width:0}}.col2>div{{min-width:0}}.card{{min-width:0;overflow-wrap:anywhere}}.nav-more{{max-width:100%}}
fieldset{{border:1px solid #444;border-radius:10px;padding:14px;margin:14px 0}}legend{{color:var(--yellow);font-weight:800;padding:0 9px}}.material-row{{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1fr) minmax(0,1fr) auto;gap:8px;align-items:end;margin:7px 0}}.material-row-os{{grid-template-columns:minmax(0,2.4fr) minmax(0,.8fr) minmax(0,.8fr) minmax(0,1.1fr) auto}}.material-row label{{font-size:12px;margin:0}}.material-row input,.material-row select{{width:100%}}
.composicao-preview{{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0 0;color:#bbb;font-size:13px}}.composicao-preview span{{white-space:nowrap}}.composicao-preview b{{font-weight:600;color:#ddd}}.composicao-preview .aviso{{flex-basis:100%;color:#e2b800}}.composicao-preview .filho{{padding-left:14px;color:#aaa}}
.flash{{background:#163c29;border:1px solid #67e2a8;padding:13px;border-radius:8px}}.notice{{background:#3e320e;border:1px solid #937d2f;border-radius:9px;padding:13px}}.stack{{display:flex;gap:8px;flex-wrap:wrap}}.stack form{{display:inline}}.pic{{display:inline-block;padding:8px 12px;border:1px solid #555;border-radius:6px;margin:4px}}footer{{color:#999;padding:20px;text-align:center;border-top:1px solid #292929;font-size:13px}}
@media(max-width:620px){{.material-row,.material-row-os{{grid-template-columns:1fr 1fr}}.material-row>div:first-child{{grid-column:1/-1}}.nav a{{font-size:13px;padding:9px}}.top{{padding:12px}}main{{padding:0 12px}}}}
{CSS_MOBILE}{CSS_FEEDBACK}</style><script src="/static/portal.js?v={VERSAO_PORTAL}" defer></script></head><body><header><div class="top">{topo}{us}{logout}</div><nav class="nav">{nav}</nav></header><main><h1>{esc(titulo)}</h1>{corpo}</main>{footer}{feedback_html}</body></html>'''


class PortalPrestador:
    def __init__(self,banco,host=None,porta=8766):
        self.banco=banco
        cfg=runtime_config.provider_server(port=porta,host=host)
        self.host=cfg.host
        self.porta=cfg.port
        self.servidor=None
        self.thread=None

    def iniciar(self):
        banco=self.banco
        # Mantém erros consultáveis mesmo quando o app é iniciado por um .command.
        if not any(isinstance(h,RotatingFileHandler) for h in LOG.handlers):
            try:
                pasta=ext.BASE/'logs'
                pasta.mkdir(parents=True,exist_ok=True)
                arquivo=pasta/'portal_prestador.log'
                arq_log=RotatingFileHandler(arquivo,maxBytes=2_000_000,backupCount=3,
                                            encoding='utf-8')
                arq_log.setLevel(logging.WARNING)
                arq_log.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                LOG.setLevel(logging.WARNING)
                LOG.addHandler(arq_log)
                if os.name=='posix':os.chmod(arquivo,0o600)
            except OSError as exc:
                LOG.warning('Não foi possível iniciar log de arquivo: %s',exc)
        usar_https=runtime_config.provider_https()
        ext.instalar(banco)
        prod.instalar(banco)
        pj_publico.instalar(banco)
        fluxo.instalar(banco)
        aten.instalar(banco)
        cad9.instalar(banco)
        catalogo.instalar(banco)
        estoque.instalar(banco)
        feedback.instalar(banco)
        api_fin.instalar(banco)
        if web_session.durable_enabled():
            web_session.install(banco)
        # Repara chamados antigos que não receberam OS após falha/interrupção,
        # inclusive quando apenas o Portal do Prestador é iniciado.
        recuperadas=cad9.sincronizar_solicitacoes_pendentes(banco)
        if recuperadas:
            LOG.warning('Solicitações antigas vinculadas a OS pendentes: %d',recuperadas)
        try:
            importados=fluxo.recuperar_relatorios_antigos(banco)
            if importados:
                LOG.warning('PDFs históricos recuperados: %s',len(importados))
        except Exception:
            LOG.exception('Falha ao recuperar PDFs históricos; a operação web continuará.')
        with ext.db(banco) as c: neg.criar_auditoria(c)

        class Handler(BaseHTTPRequestHandler):
            timeout = 15
            def log_message(self,formato,*args):
                try:
                    ip=feedback.ip_requisicao(self.client_address[0],self.headers)
                except (ValueError,TypeError):
                    ip=self.address_string()
                LOG.info('acesso %s %s',ip,formato%args)

            def redirect_alias(self, destination):
                """Contractual 308 redirect preserving POST method and query."""
                if not destination.startswith('/') or destination.startswith('//'):
                    return self.erro('Página indisponível.',404)
                self.send_response(308)
                self.send_header('Location',destination)
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length','0')
                self.end_headers()

            def retired_route(self):
                return self.send_bytes(
                    ('<h1>Funcionalidade indisponível</h1><p>Este acesso foi encerrado. '
                     'Para solicitar atendimento ou recuperar histórico, entre em contato com a AUTOSEG '
                     'pelo canal de suporte.</p>').encode('utf-8'),status=410)

            def send_bytes(self,data,mime='text/html; charset=utf-8',filename=None,status=200,
                           cookie=None,inline=False,cache=None):
                self.send_response(status)
                self.send_header('Content-Type',mime)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control',cache or 'no-store, max-age=0')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('X-AUTOSEG-Portal',VERSAO_PORTAL)
                self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; img-src 'self'")
                if filename:
                    fname=Path(filename).name
                    # RFC5987 evita injeção no cabeçalho; usa somente nome limpo.
                    disposicao='inline' if inline else 'attachment'
                    self.send_header('Content-Disposition',f"{disposicao}; filename*=UTF-8''{quote(fname)}")
                if cookie:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(data)

            def responder(self,html_text,status=200,cookie=None):
                return self.send_bytes(html_text.encode('utf-8'),status=status,cookie=cookie)

            def ui_app(self):
                return True

            def pagina(self,titulo,conteudo,s=None,status=200,cliente=False):
                from officina.web import ShellPage, active_for
                from flavors.autoseg.modules import officina_web
                context=officina_web.context_for(s)
                path=urlparse(self.path).path
                page=ShellPage(titulo,conteudo,context,context.navigation,
                               active=active_for(path,context.navigation),
                               path=path,banco=banco,user=s)
                pagina=officina_web.render_page(page)
                if titulo=='Ordens de serviço ativas':
                    pagina=pagina.replace('</head>','<meta name="autoseg-auto-refresh" content="20"></head>')
                return self.responder(pagina,status)

            def cookie(self,tok,delete=False):
                attrs='Path=/; HttpOnly; SameSite=Strict; '
                if usar_https or self.headers.get('CF-Ray') or self.headers.get('X-Forwarded-Proto','').lower()=='https':attrs+='Secure; '
                return f'autosseg_session={tok}; {attrs}Max-Age={0 if delete else 28800}'

            def redir(self,path,cookie=None):
                if not path.startswith('/') or path.startswith('//'): path='/'
                self.send_response(303)
                self.send_header('Location',path)
                self.send_header('Cache-Control','no-store')
                if isinstance(cookie, (list, tuple)):
                    for item in cookie:
                        if item: self.send_header('Set-Cookie',item)
                elif cookie:
                    self.send_header('Set-Cookie',cookie)
                self.end_headers()

            def sessao(self):
                unified = login_web.provider_session(self, banco)
                if unified:
                    return unified
                try:
                    cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                    tok=cookie['autosseg_session'].value
                except (ValueError,KeyError):return None
                if len(SESSOES)>2000:
                    _podar_mapas_sessao()
                s=SESSOES.get(tok)
                if not s or s['exp']<time.time():
                    SESSOES.pop(tok,None);return None
                with ext.db(banco) as c:
                    p=c.execute('SELECT nome,senha_hash FROM prestadores WHERE id=? AND ativo=1',(s['pid'],)).fetchone()
                if not p or not secrets.compare_digest(s.get('cred',''),p['senha_hash']):
                    SESSOES.pop(tok,None);return None
                s['admin']=cad9.prestador_admin(banco,s['pid'])
                return s

            def csrf(self,s,d):
                if not s or not secrets.compare_digest(s['csrf'],str(d.get('csrf',''))):
                    raise PermissionError('Formulário expirado ou sessão inválida.')

            def hidden(self,s):
                return f'<input type="hidden" name="csrf" value="{esc(s["csrf"])}">'

            def origem_permitida(self):
                origem=self.headers.get('Origin') or self.headers.get('Referer') or ''
                if not origem or str(origem).strip().lower() == 'null':
                    return True
                try:
                    alvo=urlparse(origem)
                except ValueError:
                    return False
                host=str(self.headers.get('Host','') or '').lower()
                if not host or not alvo.netloc:
                    return False
                return alvo.scheme in ('http','https') and alvo.netloc.lower()==host

            def _login_attempt_state(self):
                ip=feedback.ip_requisicao(self.client_address[0],self.headers)
                agora=time.time()
                with LOCK_LOGIN:
                    recentes=[t for t in TENTATIVAS.get(ip,[]) if agora-t<600]
                return ip,recentes,agora,len(recentes)>=10

            def _login_failed(self,ip,recentes,agora):
                with LOCK_LOGIN:
                    TENTATIVAS[ip]=recentes+[agora]

            def _login_succeeded(self,ip):
                with LOCK_LOGIN:
                    TENTATIVAS.pop(ip,None)

            def form(self, limite=MAX_POST):
                try:t=int(self.headers.get('Content-Length','0'))
                except ValueError: raise ValueError('Tamanho inválido.')
                if not (0<t<=int(limite)): raise ValueError('O envio excede o limite permitido.')
                ct=self.headers.get('Content-Type','')
                raw=self.rfile.read(t)
                if ct.startswith('multipart/form-data'):
                    msg=BytesParser(policy=default).parsebytes(
                        ('Content-Type: '+ct+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                    d={}
                    for part in msg.iter_parts():
                        nome=part.get_param('name',header='Content-Disposition')
                        if not nome:continue
                        valor=(part.get_filename(),part.get_payload(decode=True)) if part.get_filename() else part.get_payload(decode=True).decode('utf-8')
                        if nome.endswith('[]'):d.setdefault(nome,[]).append(valor)
                        else:d[nome]=valor
                    return d
                if ct.startswith('application/x-www-form-urlencoded'):
                    parsed=parse_qs(raw.decode('utf-8'),keep_blank_values=True,max_num_fields=400)
                    return {k:(v if k.endswith('[]') else v[0]) for k,v in parsed.items()}
                raise ValueError('Formato de formulário não suportado.')

            def voltar_url(self):
                """Return the same-origin page that submitted the form, not home."""
                try:
                    ref=urlparse(self.headers.get('Referer',''))
                    host=self.headers.get('Host','').lower()
                    if (ref.scheme in ('http','https') and ref.netloc.lower()==host
                            and ref.path.startswith('/') and not ref.path.startswith('//')):
                        return ref.path + (('?'+ref.query) if ref.query else '')
                except (ValueError,TypeError):
                    pass
                return '/'

            def erro(self,msg,status=400,s=None):
                if ('application/json' in self.headers.get('Accept','')
                        or self.headers.get('X-Requested-With') == 'XMLHttpRequest'):
                    return self.send_bytes(
                        json.dumps({'ok':False,'error':str(msg)},ensure_ascii=False).encode(),
                        'application/json; charset=utf-8',status=status)
                destino=esc(self.voltar_url())
                return self.pagina('Operação não concluída',
                    card('Aviso',f'<p class="bad">{esc(msg)}</p>'
                         f'<p><a href="{destino}">Voltar à página anterior</a></p>'),s,status)

            def login(self, erro_login='', email_login=''):
                ativo=self.ui_app()
                erro_html=(f'<p class="bad login-erro" id="login-erro" role="alert">'
                           f'{esc(erro_login)}</p>' if erro_login else
                           '<p class="bad login-erro" id="login-erro" role="alert" hidden></p>')
                if ativo:
                    form_html=('<form class="login-form" method="post" action="/login" data-login-form="1">'
                               +erro_html
                               +campos_escuros('E-mail','email',email_login,kind='email',required=True)
                               +campos_escuros('Senha','senha',kind='password',required=True)
                               +'<button type="submit">Entrar</button></form>')
                    corpo=login_shell_markup(
                        form_html=form_html,
                        lede='Use seu e-mail e senha de prestador.',
                        note='O cadastro de prestadores é realizado somente pelo aplicativo desktop.',
                        links=v9.barra_links('prestador'),
                        kicker='Portal do prestador',
                        description='Acompanhe as ordens atribuídas, registre o serviço e '
                                    'consulte o que já foi recebido.')
                    return self.pagina('Acesso do prestador',corpo)
                return self.pagina('Acesso do prestador',card('Entrar',
                    '<form method="post" action="/login" data-login-form="1">'
                    +erro_html
                    +campos_escuros('E-mail','email',email_login,kind='email',required=True)
                    +campos_escuros('Senha','senha',kind='password',required=True)
                    +'<button type="submit">Entrar</button></form>'
                    '<p class="muted">O cadastro de prestadores é realizado somente pelo aplicativo desktop.</p>')+v9.barra_links('prestador'))

            def pj_publicas(self, s):
                pendentes = pj_publico.listar(banco, 'Aguardando verificação')
                historico = pj_publico.listar(banco)
                token = self.hidden(s)
                linhas = []
                for p in pendentes:
                    acoes = (
                        f'<form method="post" action="/pj-publicas/{p["id"]}/aceitar" style="display:inline">'
                        f'{token}<button type="submit">Aceitar</button></form> '
                        f'<form method="post" action="/pj-publicas/{p["id"]}/recusar" style="display:inline">'
                        f'{token}<input name="motivo" required placeholder="Motivo da recusa" '
                        f'style="max-width:220px;display:inline-block"><button class="danger" type="submit">Recusar</button></form>')
                    linhas.append((f'PJ-{p["id"]:04d}', esc(p['organizacao']), esc(p['nome']),
                                   esc(p['telefone']), esc(p['descricao'][:160]), esc(p['criado_em']), acoes))
                if pendentes:
                    tabela_pend = tabela(['Protocolo','Condomínio/empresa','Solicitante','Telefone','Solicitação','Recebido','Verificação'], linhas)
                else:
                    tabela_pend = '<p class="muted">Nenhuma solicitação aguardando verificação.</p>'
                hist = []
                for p in historico:
                    if p['status'] == 'Aguardando verificação':
                        continue
                    os_link = (f'<a href="{url_os(banco, p["os_id"])}">'
                               f'{esc(ordens_repo.numero_os(banco, p["os_id"]) or p["os_id"])}</a>'
                               if p['os_id'] else '—')
                    hist.append((f'PJ-{p["id"]:04d}', esc(p['organizacao']), esc(p['nome']),
                                 esc(p['status']), os_link, esc(p['motivo'] or ''), esc(p['decidido_em'] or '')))
                tabela_hist = (tabela(['Protocolo','Condomínio/empresa','Solicitante','Situação','OS','Motivo','Decidido em'], hist)
                               if hist else '<p class="muted">Sem histórico.</p>')
                return self.pagina('Solicitações PJ sem cadastro',
                    '<p class="muted">Pedidos de abertura de OS feitos por condomínios/empresas sem cadastro PF. '
                    'Aceitar cria uma OS <b>Aberta</b>; recusar exige motivo.</p>'
                    + card('Aguardando verificação', tabela_pend)
                    + card('Histórico de verificação', tabela_hist), s)

            def os_lista(self,s,concluidas=False):
                if concluidas:
                    lista=ordens_repo.listar_historico(banco)
                    rows=[]
                    for x in lista:
                        try:
                            if object_policy_flags.enforcement_enabled(banco):
                                os_commands.authorize_get(banco,os_commands._provider_context(banco,s),
                                                      f'/os/{int(x["id"])}')
                        except PermissionError:
                            continue
                        link_pdf=(botao('Baixar PDF',f'{url_os(banco, x["id"])}/pdf') if x['versao'] else
                            '<span class="warn">Não publicado</span> '+botao('Abrir para republicar',f'{url_os(banco, x["id"])}','secondary'))
                        rows.append((f'<a href="{url_os(banco, x["id"])}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                            f'<span class="tag">{esc(x["status"])}</span>',dinheiro(x['valor_total']),
                            str(x['versao'] or '—'),link_pdf))
                    resumo=f'<p class="muted">Ordens encerradas, relatórios publicados e PDFs centralizados. Anexos só durante o encerramento da OS.</p>'
                    return self.pagina('Histórico e relatórios',resumo+card('Histórico e documentos',
                        tabela(['OS','Cliente','Situação','Valor','Versão PDF','Documento'],rows)),s)
                ordem=parse_qs(urlparse(self.path).query).get('ordem',['status'])[0]
                if ordem not in ('status','data','cliente','os','alteracao','abertura'):ordem='status'
                lista=ext.listar_os_compartilhadas(banco,ordem,s['pid'])
                rows=[]
                for x in lista:
                    try:
                        os_commands.authorize_get(banco,os_commands._provider_context(banco,s),
                                                  f'/os/{int(x["id"])}')
                    except PermissionError:
                        continue
                    estado=x['status']
                    try:
                        with ext.db(banco) as c:
                            if ext.em_rota_atual(c, x['id']): estado='Em rota'
                    except Exception:
                        pass
                    rows.append((f'<a href="{url_os(banco, x["id"])}">{esc(x["numero_os"])}</a>',
                        f'<a href="/clientes/{int(x["cliente_id"])}">{esc(x["cliente"])}</a>',
                        f'<span class="tag">{esc(estado)}</span>',esc(x.get('responsavel') or 'Não atribuído'),
                        esc(x.get('participantes') or 'Nenhum')))
                opcoes_ordem=[
                    ('status','Situação: iniciadas e pendentes primeiro'),
                    ('alteracao','Última alteração'),
                    ('abertura','Última abertura (lida por mim)'),
                    ('data','Data de criação: mais recentes'),
                    ('cliente','Cliente: A-Z'),
                    ('os','Número da OS'),
                ]
                filtro_ordem=('<form method="get" action="/os" class="actions">'
                    '<label for="c_ordem">Ordenar por</label>'
                    '<select id="c_ordem" name="ordem">'
                    +''.join(f'<option value="{esc(k)}" {"selected" if ordem==k else ""}>{esc(v)}</option>'
                             for k,v in opcoes_ordem)
                    +'</select></form>')
                return self.pagina('Ordens de serviço ativas',
                    '<p class="muted">Ordens de serviço autorizadas para a sua conta.</p>'
                    +f'<div class="page-actions">{botao("+ Nova OS","/os/rapida")}</div>'
                    +filtro_ordem
                    +card('Ordens de serviço',tabela(['OS','Cliente','Status','Responsável','Participantes'],rows)),s)

            def inicio(self,s):
                clientes_ativos=clientes_core.contar_ativos(banco)
                o=ordens_repo.resumo(banco)
                f=ordens_repo.financeiro_resumo(banco)
                recentes=ordens_repo.recentes(banco, limite=6)
                if self.ui_app():
                    def stat(rotulo,valor,href):
                        return (f'<a class="stat" href="{href}"><span>{esc(rotulo)}</span>'
                                f'<strong>{esc(valor)}</strong></a>')
                    stats=(stat('OS abertas',o['abertas'] or 0,'/os')
                           +stat('OS iniciadas',o['iniciadas'] or 0,'/os')
                           +stat('OS pendentes',o['pendentes'] or 0,'/os')
                           +stat('OS concluídas',o['concluidas'] or 0,'/historico'))
                    linhas=[]
                    for x in recentes:
                        linhas.append((f'<a href="{url_os(banco, x["id"])}">{esc(x["numero_os"])}</a>',
                                       f'<a href="/clientes/{int(x["cliente_id"])}">{esc(x["cliente"])}</a>',
                                       chip_status(x['status']),
                                       f'<span class="mono">{dinheiro(x["valor_total"])}</span>',
                                       f'<span class="mono">{esc(data_curta(x["data_abertura"]))}</span>'))
                    recentes_html=tabela(['OS','Cliente','Status','Valor','Abertura'],linhas)
                    atalhos=[('Clientes','/clientes','users'),
                             ('Serviços e valores','/servicos','wrench'),
                             ('Notas fiscais','/notas','receipt'),
                             ('Histórico e relatórios','/historico','history')]
                    atalhos_html=''.join(
                        f'<a class="shortcut" href="{url}">'
                        f'<span>{icone(nome)} {esc(texto)}</span>{icone("arrow-right")}</a>'
                        for texto,url,nome in atalhos)
                    corpo=(f'<div class="home-toolbar"><p class="page-meta">'
                           f'{esc(s["nome"])} · {time.strftime("%d/%m/%Y")}</p>'
                           f'<div class="page-actions">{botao("+ Nova OS","/os/rapida")}</div></div>'
                           f'<div class="stat-grid">{stats}</div>'
                           f'<div class="home-grid">'
                           f'<section class="panel"><div class="panel-head"><h2>Ordens recentes</h2>'
                           f'<a href="/os">Ver todas</a></div>{recentes_html}</section>'
                           f'<aside class="home-rail">'
                           f'<section class="panel"><div class="panel-head"><h2>Financeiro</h2>'
                           f'<a href="/financeiro">Abrir</a></div>'
                           f'<a class="finance-figures" href="/financeiro">'
                           f'<div><span>A receber</span><strong class="accent">{dinheiro(f["pendente"] or 0)}</strong></div>'
                           f'<div><span>Recebido</span><strong>{dinheiro(f["recebido"] or 0)}</strong></div>'
                           f'</a></section>'
                           f'<section class="panel"><div class="panel-head"><h2>Atalhos</h2></div>'
                           f'{atalhos_html}</section>'
                           f'<a class="home-note" href="/clientes">Clientes ativos: {int(clientes_ativos or 0)}</a>'
                           f'</aside></div>'
                           f'<div class="home-links">{v9.barra_links("prestador")}</div>'
                           f'<p class="home-note">As alterações são registradas com o prestador autenticado. '
                           f'E-mails e notas fiscais dependem das APIs externas.</p>')
                    return self.pagina('Visão geral',corpo,s)
                indic=[('OS abertas',o['abertas'] or 0),('OS iniciadas',o['iniciadas'] or 0),
                       ('OS pendentes',o['pendentes'] or 0),('OS concluídas',o['concluidas'] or 0),
                       ('A receber',dinheiro(f['pendente'])),('Recebido',dinheiro(f['recebido'])),('Clientes ativos',clientes_ativos)]
                k='<div class="kpis">'+''.join(f'<div class="kpi"><span>{esc(n)}</span><strong>{esc(v)}</strong></div>' for n,v in indic)+'</div>'
                corpo=f'<p>Olá, <b>{esc(s["nome"])}</b>. Acesso completo às funcionalidades operacionais, com auditoria.</p>{k}'
                atalhos=[('Clientes','/clientes'),('Ordens de serviço','/os'),('Serviços e valores','/servicos'),('Financeiro','/financeiro'),('Notas fiscais','/notas'),('E-mails','/emails'),('Histórico e relatórios','/historico')]
                corpo+=card('Acesso rápido',''.join(botao(t,url) for t,url in atalhos))
                corpo+=v9.barra_links('prestador')
                corpo+='<div class="notice">As alterações são registradas com o prestador autenticado. E-mails e notas fiscais ainda dependem das APIs externas.</div>'
                return self.pagina('Painel principal',corpo,s)

            def feedback_admin(self,s,status_dev='',aviso='',erro=''):
                if not s.get('admin'):
                    raise PermissionError('Feedbacks recebidos são visíveis apenas para administradores.')
                contagens=feedback.contagens(banco)
                itens=feedback.listar(banco,status_dev=status_dev,limite=300)
                kpis='<div class="kpis">'+''.join(
                    f'<div class="kpi"><span>{esc(nome)}</span><strong>{int(contagens.get(nome,0))}</strong></div>'
                    for nome in feedback.STATUS_TRIAGEM)+'</div>'
                opcoes=[('','Todos os feedbacks')]+[(x,x) for x in feedback.STATUS_TRIAGEM]
                filtro=('<form method="get" action="/feedback/recebidos" data-auto-submit="1">'
                        +select('Filtrar por situação na DEV','status',opcoes,status_dev)
                        +'</form>')
                linhas=[]
                for item in itens:
                    resumo=re.sub(r'\s+',' ',item['mensagem_anonimizada']).strip()[:140]
                    linhas.append((
                        f'<a href="/feedback/{item["id"]}">FB-{item["id"]:04d}</a>',
                        esc(item['criado_em']),esc(item['prestador_nome']),
                        f'<code>{esc(item["pagina"])}</code>',esc(resumo),
                        esc(item['categoria']),esc(item['urgencia']),
                        f'{esc(item.get("ui_mode") or "—")} / {esc(item.get("aba") or "—")}',
                        f'<span class="tag">{esc(item["status_dev"])}</span>'))
                aberturas=feedback.listar_aberturas(banco,limite=30)
                linhas_aberturas=[(
                    esc(x['criado_em']),esc(x['prestador_nome']),
                    f'<code>{esc(x["pagina"])}</code>',
                    f'{esc(x.get("ui_mode") or "—")} / {esc(x.get("aba") or "—")}',
                    esc(x['dispositivo']),esc(x['navegador']),esc(x['sistema'])) for x in aberturas]
                aviso_html=f'<p class="good">{esc(aviso)}</p>' if aviso else ''
                erro_html=f'<p class="bad">{esc(erro)}</p>' if erro else ''
                return self.pagina('Feedbacks recebidos',
                    '<p class="muted">Canal interno de feedback do Portal do Prestador. '
                    'A classificação da IA é uma sugestão; a decisão de registrar uma pendência na DEV é humana. '
                    'O texto abaixo é a versão anonimizada.</p>'
                    +aviso_html+erro_html
                    +card('Resumo por situação',kpis)
                    +card('Filtrar',filtro)
                    +card('Feedbacks',
                        '<p>'+botao('Baixar pendências da DEV (.md)','/feedback/pendencias.md','secondary')
                        +botao('Exportar dados de feedback (.json)','/feedback/dados/exportar.json','secondary')+'</p>'
                        +tabela(['ID','Recebido','Prestador','Página','Relato anonimizado','Categoria','Urgência','Interface / aba','Situação na DEV'],linhas))
                    +card('Aberturas recentes do canal',
                        '<p class="muted">Registra quem abriu o diálogo, em qual página, com qual dispositivo e navegador. '
                        'Serve para diagnosticar dificuldades de uso e correlação com erros.</p>'
                        +tabela(['Quando','Prestador','Página','Interface / aba','Dispositivo','Navegador','Sistema'],linhas_aberturas)),s)

            def feedback_detalhe(self,s,fid):
                item=feedback.obter(banco,fid)
                if not item:
                    return self.erro('Feedback não encontrado.',404,s)
                if not s.get('admin') and int(item['prestador_id'])!=int(s['pid']):
                    raise PermissionError('Este feedback pertence a outro prestador.')
                resposta=''
                if item['responder_ia']:
                    if item['ia_status']=='ok':
                        resposta=card('Resposta da IA',
                            '<p class="notice">A IA pode errar. Ela não altera o sistema e não substitui a revisão humana.</p>'
                            +f'<p style="white-space:pre-wrap">{esc(item["resposta_ia"])}</p>'
                            +f'<p class="muted">Categoria sugerida: {esc(item["categoria"])} · '
                            +f'Urgência sugerida: {esc(item["urgencia"])} · Confiança: {float(item["confianca"]):.0%}</p>'
                            +((f'<p><b>Possível melhoria:</b> {esc(item["possivel_melhoria"])}</p>') if item['possivel_melhoria'] else ''))
                    else:
                        resposta=card('Resposta automática indisponível',
                            f'<p class="warn">{esc(item["ia_erro"] or "A IA não respondeu.")}</p>'
                            '<p>O feedback foi salvo e está disponível para análise humana.</p>')
                admin=False
                if s.get('admin'):
                    admin=True
                    opcoes=''.join(
                        f'<option value="{esc(x)}" {"selected" if x==item["status_dev"] else ""}>{esc(x)}</option>'
                        for x in feedback.STATUS_TRIAGEM)
                    triagem=card('Triagem para a DEV',
                        f'<form method="post" action="/feedback/{item["id"]}/triagem">{self.hidden(s)}'
                        '<label for="c_status_dev">Situação</label>'
                        f'<select id="c_status_dev" name="status_dev" required>{opcoes}</select>'
                        +textarea('Nota da triagem (opcional)','nota_dev',item['nota_dev'],rows=4)
                        +'<p class="muted">Use “Pendente na DEV” quando o relato identificou um problema real ou melhoria necessária. '
                        'A IA não decide isso sozinha.</p>'
                        +'<button type="submit">Salvar triagem</button></form>')
                    meta=tabela(['Campo','Valor'],[
                        ('Interface / aba',f'{esc(item.get("ui_mode") or "—")} / {esc(item.get("aba") or "—")}'),
                        ('IP completo (somente se configurado)',esc(item['ip'] or '—')),
                        ('Rede truncada',esc(item['ip_rede'] or '—')),
                        ('Hash do IP',esc(item['ip_hash'] or '—')),
                        ('Hash da sessão',esc(item['sessao_hash'] or '—')),
                        ('Navegador',esc(item['navegador'] or '—')),
                        ('Sistema',esc(item['sistema'] or '—')),
                        ('Dispositivo',esc(item['dispositivo'] or '—')),
                        ('User-Agent',esc(item['user_agent'] or '—')),
                        ('Texto anonimizado enviado à IA',esc(item['mensagem_anonimizada'] or '—')),
                    ])
                    detalhes=card('Contexto técnico (administrador)',meta)
                    diag=item.get('diagnostico_json') or ''
                    diagnostico=(card('Diagnóstico da tela',
                        '<pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px">'
                        +esc(diag)+'</pre>') if diag else '')
                else:
                    triagem=''
                    detalhes=''
                    diagnostico=''
                return self.pagina(f'Feedback FB-{item["id"]:04d}',
                    botao('← Voltar','/feedback/recebidos' if admin else '/','secondary')
                    +card('Relato',
                        f'<p class="muted">{esc(item["criado_em"])} · {esc(item["prestador_nome"])} · '
                        f'<code>{esc(item["pagina"])}</code></p>'
                        f'<p style="white-space:pre-wrap">{esc(item["mensagem"])}</p>'
                        f'<p><span class="tag">{esc(item["status_dev"])}</span></p>')
                    +resposta+triagem+detalhes+diagnostico,s)

            def feedback_confirmacao(self,s,item):
                """Confirmação direta após o envio; nunca mostra a triagem."""
                resposta=''
                if item['responder_ia']:
                    if item['ia_status']=='ok':
                        resposta=card('Resposta da IA',
                            '<p class="notice">A IA pode errar. Ela não altera o sistema e não substitui a revisão humana.</p>'
                            +f'<p style="white-space:pre-wrap">{esc(item["resposta_ia"])}</p>'
                            +f'<p class="muted">Categoria sugerida: {esc(item["categoria"])} · '
                            +f'Urgência sugerida: {esc(item["urgencia"])}</p>')
                    else:
                        resposta=card('Resposta automática indisponível',
                            f'<p class="warn">{esc(item["ia_erro"] or "A IA não respondeu.")}</p>'
                            '<p>O feedback foi salvo e está disponível para análise humana.</p>')
                return self.pagina('Feedback enviado',
                    f'<p class="good">Feedback FB-{int(item["id"]):04d} registrado. Obrigado.</p>'
                    +card('Seu relato',
                        f'<p class="muted">{esc(item["criado_em"])} · '
                        f'<code>{esc(item["pagina"])}</code> · '
                        f'<span class="tag">{esc(item["status_dev"])}</span></p>'
                        f'<p style="white-space:pre-wrap">{esc(item["mensagem"])}</p>')
                    +resposta
                    +'<p class="muted">A equipe fará a triagem depois. '
                    'Você não precisa abrir a tela de triagem nem fazer mais nada.</p>'
                    +botao('Voltar ao início','/','secondary'),s)

            def servicos_lista(self,s):
                termo=str(parse_qs(urlparse(self.path).query).get('q',[''])[0]).strip()[:100].casefold()
                rows=[]
                for serv in catalogo.listar(banco):
                    if termo and termo not in (serv['nome']+' '+serv['descricao']).casefold():continue
                    valor=catalogo.valores_orcamento(banco,serv['id']) if serv['ativo'] else None
                    excluir=(f'<form method="post" action="/servicos/{serv["id"]}/excluir" '
                             'data-confirm="Excluir definitivamente este serviço do catálogo?">'
                             +self.hidden(s)
                             +'<button class="danger" type="submit">Excluir</button></form>')
                    rows.append((esc(serv['nome']),esc(serv['descricao'][:100]),
                        catalogo.reais(valor['total']) if valor else 'Arquivado',
                        botao('Editar',f'/servicos/{serv["id"]}/editar','secondary')+excluir))
                return self.pagina('Serviços e valores',
                    '<p>Catálogo para propostas e preenchimento de relatórios. Os preços são editados somente por prestadores.</p>'
                    +botao('+ Novo serviço','/servicos/novo')
                    +('<form method="get" action="/servicos" data-auto-submit="1">'
                      +campos_escuros('Buscar serviço por nome ou descrição','q',termo,kind='search')
                      +'</form>')
                    +card('Serviços cadastrados',tabela(['Serviço','Descrição','Preço estimado','Ação'],rows)),s)

            def servico_form(self,s,identificador=None,preenchimento=None,erro=None):
                atual=catalogo.obter(banco,identificador) if identificador else None
                if identificador and not atual:return self.erro('Serviço não encontrado.',404,s)
                dados=preenchimento if preenchimento is not None else (atual or {})
                import json
                if 'materiais_lista' in dados:
                    itens=dados['materiais_lista']
                elif 'material_nome[]' in dados:
                    def normal(x):return x if isinstance(x,list) else [x]
                    itens=[{'nome':n,'quantidade':q,'valor_unitario':v} for n,q,v in zip(normal(dados.get('material_nome[]',[])),normal(dados.get('material_qtd[]',[])),normal(dados.get('material_valor[]',[])))]
                else:
                    itens=json.loads(dados.get('materiais_json') or '[]')
                form=(f'<form method="post" action="/servicos/salvar" id="form-servico">{self.hidden(s)}'
                   +f'<input type="hidden" name="servico_id" value="{identificador or ""}">'
                   +campos_escuros('Nome do serviço','nome',dados.get('nome') or '',required=True)
                   +textarea('Descrição para o cliente','descricao',dados.get('descricao') or '')
                   +campos_escuros('Preço base da mão de obra (R$)','preco_servico',
                       dados.get('preco_servico',str((dados.get('preco_servico_centavos') or 0)/100).replace('.',',')),required=True)
                   +'<fieldset><legend>Materiais — opcionais</legend><p class="muted">Preencha os três campos, sem usar barras ou separadores. Remova linhas que não precisar.</p>'
                   +'<div id="lista-materiais-servico">')
                for x in itens:
                    valor=x.get('valor_unitario',str(x.get('preco_centavos',0)/100).replace('.',','))
                    form+=('<div class="material-row">'
                           +f'<label>Material<input name="material_nome[]" value="{esc(x.get("nome",""))}" placeholder="Controle remoto"></label>'
                           +f'<label>Quantidade<input name="material_qtd[]" value="{esc(x.get("quantidade",""))}" placeholder="1"></label>'
                           +f'<label>Valor unitário (R$)<input name="material_valor[]" value="{esc(valor)}" placeholder="75,00"></label>'
                           +'<button type="button" class="secondary remover-material-servico">Remover</button></div>')
                form+=("""</div><button type="button" class="secondary" id="adicionar-material-servico">+ Adicionar material</button>
                    <template id="modelo-material-servico"><div class="material-row"><label>Material<input name="material_nome[]" placeholder="Nome"></label>
                    <label>Quantidade<input name="material_qtd[]" placeholder="1"></label><label>Valor unitário (R$)<input name="material_valor[]" placeholder="0,00"></label>
                    <button type="button" class="secondary remover-material-servico">Remover</button></div></template></fieldset>""")
                form+=(textarea('Modelo de relatório técnico do serviço','relatorio_padrao',dados.get('relatorio_padrao') or '',rows=6)
                   +'<p class="muted">Modelo é sugestão editável; não substitui o relatório próprio de cada atendimento.</p>'
                   +'<button type="submit">Salvar serviço</button></form>')
                if identificador and not dados.get('ativo',True):
                    form+=(f'<form method="post" action="/servicos/{identificador}/reativar">'
                           +self.hidden(s)+'<button>Reativar serviço</button></form>')
                if identificador and dados.get('ativo',True):
                    form+=(f'<form method="post" action="/servicos/{identificador}/arquivar" '
                           'data-confirm="Arquivar este serviço do catálogo?">'+self.hidden(s)
                           +'<button type="submit" class="danger">Arquivar serviço</button></form>')
                importar=(f'<form method="post" enctype="multipart/form-data" action="/servicos/yaml" data-no-ajax>{self.hidden(s)}'
                           '<label for="yaml-servico">Preencher serviço a partir de YAML (até 64 KB)</label>'
                           '<input type="file" id="yaml-servico" name="yaml" accept=".yaml,.yml" required>'
                           '<button type="submit" class="secondary">Pré-visualizar YAML de serviço</button></form>'
                           '<p class="muted"><a href="/modelos/servico.yaml">Baixar modelo YAML oficial</a> · Apenas pré-preenche; confira antes de salvar.</p>')
                aviso=card('Verifique os dados',f'<p class="bad">{esc(erro)}</p>') if erro else ''
                return self.pagina('Editar serviço' if identificador else 'Novo serviço',
                    botao('← Catálogo','/servicos','secondary')+aviso+card('Importação rápida',importar)+card('Valores e relatório padrão',form),s,400 if erro else 200)

            def clientes_lista(self,s):
                """Busca e paginação: evita lista imensa após a importação Asaas."""
                qs=parse_qs(urlparse(self.path).query)
                busca=str(qs.get('q',[''])[0]).strip()[:110]
                try:pagina=max(1,min(10000,int(qs.get('pagina',['1'])[0])))
                except (ValueError,TypeError):pagina=1
                limite=40;offset=(pagina-1)*limite
                total, rows = clientes_core.listar_paginado(
                    busca, limite, offset, banco=banco)
                linhas=[]
                for r in rows:
                    linhas.append((f'<a href="/clientes/{r["id"]}">{esc(r["nome"])}</a>',esc(cad9.formatar_documento(r['documento'])),esc(r['cidade']),
                        esc(r['telefone']),esc(r['email']),
                        esc('Dados incompletos' if r.get('dados_incompletos') else r['status'])))
                pesquisa=('<form method="get" action="/clientes" data-auto-submit="1">'
                          +campos_escuros('Buscar por nome, CPF/CNPJ, cidade ou e-mail','q',busca,kind='search')
                          +'</form>')
                navegacao=f'<p class="muted">{total} cliente(s) encontrado(s). Página {pagina}.</p>'
                if pagina>1:navegacao+=botao('Anterior','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina-1}),'secondary')
                if offset+len(rows)<total:navegacao+=botao('Próximos clientes','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina+1}),'secondary')
                return self.pagina('Clientes','<div class="page-actions">'
                    +botao('+ Novo cliente','/clientes/novo')
                    +botao('Novo orçamento','/orcamento','secondary')
                    +botao('Nomear síndico / gestor','/clientes/responsaveis','secondary')+'</div>'
                    +card('Clientes cadastrados',pesquisa+navegacao+tabela(['Nome','Documento','Cidade','Telefone','E-mail','Status'],linhas)),s)

            def orcamento_form(self, s, erro='', cliente_id=None,
                               servicos=None, materiais=None, aviso='',
                               validade='30', condicoes=''):
                """Orçamento com cliente, vários serviços e materiais adicionais."""
                clientes = clientes_core.listar_para_selecao(banco, limite=500)
                catalogo_servicos = catalogo.listar(banco, ativos=True)
                produtos = estoque.listar(banco, ativos=True)
                if not clientes:
                    return self.pagina('Novo orçamento', card('Sem clientes',
                        '<p>Cadastre um cliente antes de gerar um orçamento.</p>'
                        + botao('Cadastrar cliente','/clientes/novo')), s)
                if not catalogo_servicos and not produtos:
                    return self.pagina('Novo orçamento', card('Sem serviços ou materiais',
                        '<p>Cadastre um serviço no catálogo ou um material no estoque antes de gerar um orçamento.</p>'
                        + botao('Serviços e valores','/servicos')), s)

                selecionado = str(cliente_id or '')
                if selecionado and not any(str(x['id']) == selecionado for x in clientes):
                    selecionado = ''
                opcoes_clientes = [('', 'Selecione o cliente')] + [
                    (x['id'], f'{x["nome"]} — {cad9.formatar_documento(x["documento"])}')
                    for x in clientes]

                def total_servico(servico):
                    try:
                        itens = json.loads(servico['materiais_json'] or '[]')
                        materiais_servico = sum(
                            int(Decimal(str(m.get('quantidade', 0))) *
                                int(m.get('preco_centavos', 0)))
                            for m in itens)
                    except (TypeError, ValueError, KeyError):
                        materiais_servico = 0
                    return (servico['preco_servico_centavos'] or 0) + materiais_servico

                opcoes_servico = [
                    {'id': str(x['id']), 'nome': x['nome'],
                     'unitario': total_servico(x)}
                    for x in catalogo_servicos]
                opcoes_material = [
                    {'id': str(x['id']), 'nome': x['nome'],
                     'unitario': int(x.get('venda_centavos') or 0),
                     'unidade': x.get('unidade') or 'un'}
                    for x in produtos]

                def opcoes_html(opcoes, selecionado_id=''):
                    return ''.join(
                        f'<option value="{esc(x["id"])}" '
                        f'data-unitario-centavos="{int(x["unitario"])}"'
                        f'{" selected" if str(selecionado_id) == x["id"] else ""}>'
                        f'{esc(x["nome"])} — {esc(catalogo.reais(x["unitario"]))}</option>'
                        for x in opcoes)

                def linha_servico(item):
                    item = item or {}
                    escolhido = str(item.get('id') or '')
                    quantidade = str(item.get('quantidade') or '1')
                    return ('<div class="orcamento-servico-row">'
                            '<label>Serviço<select name="servico_id[]">'
                            '<option value="">Selecione o serviço</option>'
                            + opcoes_html(opcoes_servico, escolhido)
                            + '</select></label>'
                            '<label>Quantidade<input name="servico_qtd[]" type="number" '
                            f'min="1" max="20" step="1" value="{esc(quantidade)}"></label>'
                            '<button type="button" class="secondary remover-servico-orcamento">Remover</button>'
                            '</div>')

                def linha_material(item):
                    item = item or {}
                    escolhido = str(item.get('id') or '')
                    quantidade = str(item.get('quantidade') or '1')
                    return ('<div class="orcamento-material-row">'
                            '<label>Material<select name="material_id[]">'
                            '<option value="">Selecione o material</option>'
                            + opcoes_html(opcoes_material, escolhido)
                            + '</select></label>'
                            '<label>Quantidade<input name="material_qtd[]" type="number" '
                            f'min="0.01" max="1000" step="0.01" value="{esc(quantidade)}"></label>'
                            '<button type="button" class="secondary remover-material-orcamento">Remover</button>'
                            '</div>')

                ids_servico = {x['id'] for x in opcoes_servico}
                ids_material = {x['id'] for x in opcoes_material}
                if servicos is None:
                    linhas_servico = ([{'id': '', 'quantidade': '1'}]
                                      if opcoes_servico else [])
                else:
                    linhas_servico = [
                        {'id': str(x.get('id') or ''),
                         'quantidade': str(x.get('quantidade') or '1')}
                        for x in servicos]
                linhas_material = [
                    {'id': str(x.get('id') or ''),
                     'quantidade': str(x.get('quantidade') or '1')}
                    for x in (materiais or [])]
                linhas_servico = [
                    x for x in linhas_servico
                    if not x['id'] or x['id'] in ids_servico]
                linhas_material = [
                    x for x in linhas_material
                    if not x['id'] or x['id'] in ids_material]

                campo_busca = ('<label for="busca-cliente-os">Buscar cliente ou condomínio</label>'
                               '<input type="search" id="busca-cliente-os" '
                               'placeholder="Digite o nome ou ID para localizar" autocomplete="off">')
                secao_servicos = ''
                if opcoes_servico:
                    secao_servicos = (
                        '<fieldset><legend>Serviços</legend>'
                        '<p class="muted">Cada serviço já inclui os materiais cadastrados no próprio serviço. '
                        'Use "Materiais adicionais" apenas para itens cobrados separadamente.</p>'
                        '<div id="lista-servicos-orcamento">'
                        + ''.join(linha_servico(x) for x in linhas_servico)
                        + '</div>'
                        '<button type="button" class="secondary" id="adicionar-servico-orcamento">'
                        '+ Adicionar serviço</button>'
                        f'<template id="modelo-servico-orcamento">{linha_servico({})}</template>'
                        '</fieldset>')
                secao_materiais = ''
                if opcoes_material:
                    secao_materiais = (
                        '<fieldset><legend>Materiais adicionais — opcional</legend>'
                        '<p class="muted">Preço de venda ativo do estoque. '
                        'Não repita materiais que já fazem parte do serviço.</p>'
                        '<div id="lista-materiais-orcamento">'
                        + ''.join(linha_material(x) for x in linhas_material)
                        + '</div>'
                        '<button type="button" class="secondary" id="adicionar-material-orcamento">'
                        '+ Adicionar material</button>'
                        f'<template id="modelo-material-orcamento">{linha_material({})}</template>'
                        '</fieldset>')

                form = (f'<form method="post" action="/orcamento/pdf" id="form-orcamento" data-no-ajax>{self.hidden(s)}'
                        + campo_busca
                        + select('Cliente','cliente_id',opcoes_clientes,selecionado,required=True)
                        + secao_servicos
                        + secao_materiais
                        + '<div class="col2"><div>'
                        + campos_escuros('Validade do orçamento (dias)','validade',validade,kind='number')
                        + '</div></div>'
                        + textarea('Condições e observações (opcional)','condicoes',condicoes,rows=3)
                        + '<p><strong>Total estimado: <span id="total-orcamento">—</span></strong></p>'
                        + '<p class="notice">O PDF é apenas um orçamento estimativo. '
                          'Nenhuma ordem de serviço, cobrança ou movimentação de estoque é criada.</p>'
                        + '<button type="submit">Gerar orçamento em PDF</button></form>')
                aviso_yaml = (f'<p class="good" id="yaml-orcamento-importado">{esc(aviso)}</p>'
                              if aviso else '')
                erro_html = card('Verifique os dados', f'<p class="bad">{esc(erro)}</p>') if erro else ''
                importar = (
                    f'<form method="post" enctype="multipart/form-data" action="/orcamento/yaml" data-no-ajax>'
                    f'{self.hidden(s)}'
                    '<label for="yaml-orcamento">Criar orçamento por YAML (até 64 KB)</label>'
                    '<input type="file" id="yaml-orcamento" name="yaml" accept=".yaml,.yml" required>'
                    '<button type="submit" class="secondary">Pré-visualizar YAML de orçamento</button>'
                    '</form>'
                    '<p class="muted"><a href="/modelos/orcamento.yaml">Baixar modelo YAML oficial</a> · '
                    'A importação não cria OS nem cobrança; apenas preenche a tela para revisão.</p>')
                return self.pagina('Novo orçamento',
                    botao('← Clientes','/clientes','secondary')
                    + card('Importação por YAML', importar)
                    + erro_html
                    + card('Orçamento (não é OS)',
                           aviso_yaml
                           + '<p class="notice">Escolha um ou mais serviços e, se precisar, '
                             'materiais adicionais. Os preços vêm do catálogo e do estoque ativos.</p>'
                           + form), s)

            def cliente_form(self,s,cid=None,preenchimento=None,erro=None):
                x=clientes_core.obter_linha(cid, banco=banco) if cid else None
                if cid and not x: return self.erro('Cliente não encontrado.',404,s)
                d=dict(x) if x else {}
                if cid is None and preenchimento:d.update(preenchimento)
                erro_html=card('YAML não aplicado',f'<p class="bad">{esc(erro)}</p>') if erro else ''
                fields=[]
                campos=[('nome','Nome / Razão social'),('documento','CPF / CNPJ'),('nome_fantasia','Nome fantasia'),
                    ('endereco','Logradouro'),('numero','Número'),('complemento','Complemento'),('bairro','Bairro'),
                    ('cep','CEP'),('cidade','Cidade'),('uf','UF'),('telefone','Telefone'),('email','E-mail'),
                    ('sindico_nome','Síndico / responsável'),('sindico_telefone','Telefone do síndico'),('sindico_email','E-mail do síndico'),
                    ('administradora','Administradora / imobiliária'),('administradora_telefone','Telefone da administradora'),
                    ('administradora_email','E-mail da imobiliária / administradora')]
                for k,t in campos:
                    fields.append(campos_escuros(t,k,cad9.formatar_documento(d.get(k,'')) if k=='documento' else (d.get(k,'') or ''),required=k=='nome',kind='email' if k.endswith('email') or k=='email' else 'text'))
                corpo=(f'<div class="page-actions">{botao("← Clientes","/clientes","secondary")}'
                    + (botao("Novo orçamento",f"/orcamento?cliente_id={cid}","secondary") if cid else '')
                    + f'</div><form method="post" action="/clientes/{cid if cid else "novo"}/salvar">{self.hidden(s)}'
                    '<div class="col2"><div>'
                    +select('Tipo de pessoa','tipo_pessoa',[(z,z) for z in ('Jurídica','Física')],d.get('tipo_pessoa') or 'Jurídica')
                    +'</div><div>'+select('Situação','status',[(z,z) for z in ('Ativo','Inativo','Prospect')],d.get('status') or 'Ativo')
                    +'</div></div><div class="col2">'+''.join(f'<div>{f}</div>' for f in fields)+'</div>'
                    +textarea('Observações','observacoes',d.get('observacoes') or '')
                    +(('<details class="ajuda"><summary>Acesso histórico (opcional, não usado no login CPF)</summary><p>Somente administradores podem redefinir a senha legada. A ação será auditada.</p>'
                        +campos_escuros('Senha do cliente (opcional)','senha_cliente',kind='password')
                        +campos_escuros('Confirmar senha','confirmar_senha_cliente',kind='password')+'</details>') if s.get('admin') else '')
                    +'<button type="submit">Salvar cliente</button></form>')
                if not cid:
                    importar=(f'<form method="post" action="/clientes/yaml" enctype="multipart/form-data" data-no-ajax>{self.hidden(s)}'
                       '<label for="importar-cliente-yaml">Preencher cadastro com arquivo YAML (até 64 KB)</label>'
                       '<input type="file" id="importar-cliente-yaml" name="yaml" accept=".yaml,.yml,.txt,text/yaml,text/plain" required>'
                       '<button type="submit" class="secondary">Pré-visualizar cadastro YAML</button></form>'
                       '<p class="muted">Use o modelo pronto: <a href="/modelos/cadastro.yaml">Baixar YAML de cliente</a>. '
                       'O nome do arquivo não importa; o conteúdo precisa ser YAML válido. '
                       'Se o navegador mostrar ERR_UPLOAD_FILE_CHANGED, selecione o arquivo novamente sem movê-lo ou renomeá-lo.</p>')
                    corpo=card('Importação assistida — apenas prestador',importar)+erro_html+corpo
                    if preenchimento:
                        corpo='<p class="notice">Dados importados para revisão. Confira nome, documento, vínculos e endereço antes de salvar.</p>'+corpo
                if cid:
                    if s.get('admin'):
                        corpo+=f'<form method="post" action="/clientes/{cid}/desativar">{self.hidden(s)}<button class="secondary">Desativar (preservar histórico)</button></form>'
                        corpo+=f'<form method="post" action="/clientes/{cid}/excluir" data-confirm="Confirma a exclusão deste cliente sem ordens de serviço?">{self.hidden(s)}<button class="danger" type="submit">Excluir cliente sem OS vinculadas</button></form>'
                    if s.get('admin'):
                        with ext.db(banco) as c:
                            outros=c.execute(
                                "SELECT id,nome FROM clientes WHERE id<>? AND status!='Inativo' "
                                "ORDER BY nome",(cid,)).fetchall()
                        if outros:
                            corpo+=card('Mesclar cliente duplicado',
                                f'<form method="post" action="/clientes/{cid}/mesclar" '
                                'data-confirm="Mesclar este cliente no destino? A origem ficará inativa.">'
                                +self.hidden(s)
                                +select('Mesclar este cliente em','destino_id',
                                        [(str(x['id']),x['nome']) for x in outros],'')
                                +'<p class="muted">As OS e o financeiro da origem passam para o destino; '
                                'a origem fica inativa e o histórico é preservado.</p>'
                                +'<button class="danger" type="submit">Mesclar clientes</button></form>')
                return self.pagina('Novo cliente' if cid is None else 'Editar cliente',card('Dados cadastrais',corpo),s)






            def _os_duplicada_recente(self, cliente_id):
                """OS do mesmo cliente criada nos últimos 2 minutos."""
                limite=(datetime.now()-timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
                with ext.db(banco) as c:
                    return c.execute("""SELECT id,numero_os,criado_em,descricao
                        FROM ordens_servico WHERE cliente_id=? AND criado_em>=?
                        ORDER BY id DESC LIMIT 1""",(int(cliente_id),limite)).fetchone()

            def os_rapida_form(self, s, erro='', q='', cliente_id=None,
                               dados_form=None, duplicada=None):
                """Nova OS em uma única tela, com cliente opcional.

                O cliente pode ser escolhido agora ou associado depois; nesse
                caso a OS usa o cadastro provisório "Cliente a definir".
                """
                dados_form=dict(dados_form or {})
                with ext.db(banco) as c:
                    prestadores=c.execute(
                        "SELECT id,nome FROM prestadores WHERE ativo=1 AND excluido=0 ORDER BY nome").fetchall()
                termo=str(q or '').strip()[:120]
                clientes=clientes_core.buscar_rapida(termo,banco=banco,limite=400)
                if not clientes:
                    clientes=clientes_core.buscar_rapida('',banco=banco,limite=400)
                selecionado=str(cliente_id or dados_form.get('cliente_id') or '')
                opcoes=[('','Cliente a definir (associar depois)')]
                for x in clientes:
                    partes=[x.get('tipo_pessoa') or '',x.get('cidade') or '']
                    detalhe=' · '.join(p for p in partes if p)
                    opcoes.append((str(x['id']),x['nome']+(f' — {detalhe}' if detalhe else '')))
                if selecionado and not any(str(v)==selecionado for v,_ in opcoes):
                    atual=clientes_core.obter_linha(int(selecionado),banco=banco)
                    if atual:
                        opcoes.append((str(atual['id']),atual['nome']))
                aviso=f'<p class="bad">{esc(erro)}</p>' if erro else ''
                if duplicada:
                    existente_id=int(duplicada['id'])
                    confirmacao=(f'<form method="post" action="/os/rapida/salvar" data-no-ajax>'
                                 f'{self.hidden(s)}'
                                 f'<input type="hidden" name="cliente_id" value="{esc(str(cliente_id or ""))}">'
                                 f'<input type="hidden" name="cliente_nome" value="{esc(str(dados_form.get("cliente_nome","")))}">'
                                 f'<input type="hidden" name="descricao" value="{esc(str(dados_form.get("descricao","")))}">'
                                 f'<input type="hidden" name="urgencia" value="{esc(str(dados_form.get("urgencia","Normal")))}">'
                                 '<input type="hidden" name="confirmar_duplicidade" value="1">'
                                 '<button type="submit" class="secondary">Criar outra mesmo assim</button></form>')
                    return self.pagina('Aviso de OS duplicada',
                        card('Já existe uma OS recente para este cliente',
                             f'<p class="notice">A OS <b>{esc(duplicada["numero_os"])}</b> foi criada '
                             f'em {esc(duplicada["criado_em"])} para o mesmo cliente. '
                             'Para evitar duplicidade, confira a OS existente antes de criar outra.</p>'
                             f'<div class="actions">{botao("Abrir OS existente",url_os(banco, existente_id))}'
                             f'{confirmacao}</div>'),s)
                nome_atual=str(dados_form.get('cliente_nome','') or '')
                if selecionado:
                    achado=next((x for x in clientes if str(x['id'])==str(selecionado)),None)
                    if achado:
                        nome_atual=str(achado['nome'] or '')
                opcoes_clientes=''.join(
                    f'<option value="{esc(x["nome"])}" data-id="{int(x["id"])}"></option>'
                    for x in clientes)
                form=(f'<form method="post" action="/os/rapida/salvar" data-no-ajax>{self.hidden(s)}'
                      '<label for="cliente-rapida-nome">Cliente (opcional)</label>'
                      f'<input id="cliente-rapida-nome" name="cliente_nome" list="clientes-rapida-lista" '
                      f'value="{esc(nome_atual)}" placeholder="Digite o nome; a busca é automática" autocomplete="off">'
                      f'<input type="hidden" name="cliente_id" id="cliente-rapida-id" value="{esc(selecionado)}">'
                      f'<datalist id="clientes-rapida-lista">{opcoes_clientes}</datalist>'
                      '<p class="muted" id="cliente-rapida-status">Se o nome não existir, '
                      'a OS cria um cliente com dados incompletos para completar depois.</p>'
                      +textarea('Solicitação / descrição do serviço','descricao',
                                str(dados_form.get('descricao','')),required=True)
                      +select('Urgência','urgencia',
                              [('Baixa', 'Baixa'), ('Normal', 'Normal'),
                               ('Alta', 'Alta')],
                              str(dados_form.get('urgencia','Normal') or 'Normal'))
                      +'<p class="notice">A OS será criada como <b>Aberta</b> e você '
                       'fica responsável por ela. Outro administrador pode transferir '
                       'a responsabilidade depois.</p>'
                       '<button type="submit" style="width:100%">Criar OS</button></form>')
                importar_rapida=''
                if selecionado:
                    importar_rapida=card('Importar OS em YAML',
                        f'<form method="post" action="/os/yaml" enctype="multipart/form-data" data-no-ajax>{self.hidden(s)}'
                        f'<input type="hidden" name="cliente_id" value="{esc(selecionado)}">'
                        '<label for="importar-os-rapida-yaml">Preencher a OS a partir de YAML (até 64 KB)</label>'
                        '<input id="importar-os-rapida-yaml" type="file" name="yaml" accept=".yaml,.yml" required>'
                        '<button type="submit" class="secondary">Pré-visualizar YAML</button></form>'
                        '<p class="muted">Abre o formulário completo já preenchido para revisão; '
                        'nada é salvo antes de confirmar.</p>')
                return self.pagina(
                    'Nova ordem de serviço',
                    card('Solicitação', aviso + form)
                    + importar_rapida
                    + botao('← Voltar às OS', '/os', 'secondary'), s)

            def os_form(self,s,oid=None,preenchimento=None,erro=None):
                with ext.db(banco) as c:
                    cl=clientes_core.listar_para_os(banco)
                    o=c.execute('SELECT * FROM ordens_servico WHERE id=?',(oid,)).fetchone() if oid else None
                    mat=c.execute('SELECT * FROM materiais_os WHERE os_id=? ORDER BY id',(oid,)).fetchall() if oid else []
                    eventos=c.execute('SELECT * FROM os_eventos WHERE os_id=? ORDER BY id DESC LIMIT 150',(oid,)).fetchall() if oid else []
                    anexos=c.execute('''SELECT a.id,a.nome_original,a.criado_em,a.tipo,a.sha256,
                        COALESCE(v.legenda,'') legenda,COALESCE(v.visivel,1) visivel
                        FROM os_anexos a LEFT JOIN v9_anexos_visiveis v ON v.anexo_id=a.id
                        WHERE a.os_id=? ORDER BY a.ordem,a.id''',(oid,)).fetchall() if oid else []
                    responsavel=ext.responsavel_atual(c,oid) if oid else None
                    prestadores=c.execute('SELECT id,nome,email FROM prestadores WHERE ativo=1 ORDER BY nome').fetchall()
                    detalhes=c.execute('SELECT * FROM v9_detalhes_os WHERE os_id=?',(oid,)).fetchone() if oid else None
                    imagens_v9={r['anexo_id']:dict(r) for r in c.execute('SELECT * FROM v9_anexos_visiveis')} if oid else {}
                    solicitacao=c.execute('SELECT * FROM os_solicitacoes WHERE os_id=?',(oid,)).fetchone() if oid else None
                    andamento=c.execute('SELECT * FROM os_atendimentos WHERE os_id=?',(oid,)).fetchone() if oid else None
                    particip=c.execute('''SELECT p.nome FROM os_prestadores op JOIN prestadores p ON p.id=op.prestador_id
                        WHERE op.os_id=? ORDER BY p.nome''',(oid,)).fetchall() if oid else []
                    notas_fiscais=c.execute('SELECT id,nome_original,criado_em FROM os_notas_fiscais WHERE os_id=? ORDER BY id',
                                            (oid,)).fetchall() if oid else []
                    contatos_os=prod.contatos_email_os(banco,oid) if oid else None
                if oid and not o: return self.erro('OS não encontrada.',404,s)
                if oid:
                    # Shadow measurement only; the route still opens the OS for
                    # any authenticated provider until enforcement lands.
                    policy_shadow.evaluate_os(
                        banco,s['pid'],oid,'view',True,'os_form')
                    policy_shadow.evaluate_os(
                        banco,s['pid'],oid,'read',True,'os_form')
                d=dict(o) if o else {}
                arquivada=bool(d.get('arquivada'))
                # A pending OS is not "started" even if an older start remains
                # stored; returning it to pending resets the active start.
                iniciado_ativo=bool(andamento and andamento['iniciado_em']) and d.get('status')!='Pendente'
                if oid and d.get('cliente_id') and not any(
                        int(x['id'])==int(d['cliente_id']) for x in cl):
                    # OS criada sem cliente usa o cadastro provisório
                    # "Cliente a definir"; ele precisa aparecer no seletor
                    # para que a associação posterior seja possível.
                    provisorio=clientes_core.obter_linha(int(d['cliente_id']),banco=banco)
                    if provisorio:
                        cl.append({chave:provisorio.get(chave,'') for chave in
                                   ('id','nome','cidade','bairro','endereco','numero')})
                if oid:
                    try:
                        with ext.db(banco) as c:
                            c.execute('''INSERT INTO os_leituras(os_id,prestador_id,lido_em)
                                VALUES(?,?,?) ON CONFLICT(os_id,prestador_id)
                                DO UPDATE SET lido_em=excluded.lido_em''',
                                (oid,s['pid'],ext.agora()))
                    except Exception:
                        pass
                if preenchimento:
                    # YAML é um modelo: preenche apenas campos vazios por padrão.
                    # A escolha explícita "substituir" é necessária para sobrescrever.
                    substituir=bool(preenchimento.get('_substituir'))
                    if detalhes:
                        for chave in ('diagnostico','execucao','resultado'):
                            d.setdefault('v9_'+chave,detalhes[chave] or '')
                    if andamento:d.setdefault('relatorio_tecnico',andamento['rascunho'] or '')
                    for k,v in preenchimento.items():
                        if k.startswith('v9_') or k=='relatorio_tecnico':
                            if substituir or not str(d.get(k,'')).strip():d[k]=v
                    # Rascunho completo do servidor (produtividade_os) também chega aqui.
                    for k in ('cliente_id','tecnico','valor_mao_obra','valor_materiais_manual','custo_materiais','valor_total_override','forma_pagamento','urgencia'):
                        if k in preenchimento and (substituir or not str(d.get(k,'')).strip()):
                            d[k]=preenchimento[k]
                    if 'material_yaml' in preenchimento and (substituir or not mat):
                        mat=preenchimento['material_yaml']
                    # Composição declarativa (pai + filhos) vinda do YAML/agente.
                    if 'composicao_yaml' in preenchimento:
                        d['composicao_yaml'] = preenchimento['composicao_yaml']
                    itens=preenchimento.get('material_item[]',[])
                    quantidades=preenchimento.get('material_qtd[]',[])
                    unidades=preenchimento.get('material_unidade[]',[])
                    unitarios=preenchimento.get('material_unit[]',[])
                    if itens and (substituir or not mat):
                        mat=[dict(item=item,
                                  quantidade=quantidades[i] if i<len(quantidades) else '',
                                  unidade=unidades[i] if i<len(unidades) else '',
                                  valor_unitario=unitarios[i] if i<len(unitarios) else '')
                             for i,item in enumerate(itens) if item]
                em_rota=False
                if oid and d.get('status') in ext.ATIVAS:
                    try:
                        with ext.db(banco) as c:
                            em_rota=ext.em_rota_atual(c,oid)
                    except Exception:
                        em_rota=False
                token=self.hidden(s)
                app=self.ui_app()
                rotulo_salvar='Salvar rascunho' if app else 'SALVAR RASCUNHO'
                classe_form=' class="os-form-app" novalidate' if app else ''
                titulo=(('Ordem de serviço' if app else f'OS {d["numero_os"]}') if oid else 'Nova ordem de serviço')
                action=f'{url_os(banco, oid)}/salvar' if oid else '/os/nova/salvar'
                rotulo_assumir='Assumir OS' if app else 'ASSUMIR OS'
                rotulo_em_rota='Em rota' if app else 'EM ROTA'
                rotulo_cancelar_rota='Cancelar rota' if app else 'CANCELAR ROTA'
                rotulo_iniciar='Iniciada' if app else 'INICIADA'
                aviso_rota='Em rota — deslocamento iniciado.' if app else '🚗 EM ROTA — deslocamento iniciado.'
                texto_iniciar=('Iniciar OS registra o início efetivo e encerra o deslocamento. '
                               'Se a OS não tiver responsável, ela será atribuída a você.'
                               if app else
                               'INICIAR OS registra o início efetivo do atendimento e encerra o deslocamento. '
                               'Ao iniciar uma OS sem responsável, ela será atribuída a você com registro explícito.')
                corpo='' if app else botao('← Ordens de serviço','/os','secondary')
                if oid and not app:
                    corpo+=f'<p class="muted">Número da OS: <b>{esc(d["numero_os"])}</b></p>'
                if oid and app:
                    cliente_info=next((x for x in cl if x['id']==d.get('cliente_id')),None)
                    cliente_nome=cliente_info['nome'] if cliente_info else ''
                    local=' · '.join(str(cliente_info[k] or '') for k in ('bairro','cidade') if cliente_info and cliente_info[k])
                    resp_nome=next((p['nome'] for p in prestadores if p['id']==responsavel),'Não atribuído')
                    status_exibicao='Em rota' if em_rota and d['status'] in ext.ATIVAS else d['status']
                    partes_meta=[x for x in (local,f'Aberta em {data_curta(d.get("data_abertura"))}',f'{url_os(banco, oid)}') if x]
                    ticket_botoes=[]
                    if d['status'] in ext.ATIVAS and not arquivada:
                        iniciado=iniciado_ativo
                        if responsavel is None:
                            ticket_botoes.append(
                                f'<button type="submit" form="form-os" '
                                f'formaction="{url_os(banco, oid)}/assumir" formnovalidate '
                                'title="Assume a OS sem iniciar o atendimento.">'
                                f'{rotulo_assumir}</button>')
                        if ((responsavel==s['pid'] or s.get('admin'))
                                and responsavel is not None and not iniciado):
                            if em_rota:
                                ticket_botoes.append(
                                    f'<button type="submit" class="secondary" form="form-os" '
                                    f'formaction="{url_os(banco, oid)}/cancelar-rota" formnovalidate '
                                    'title="Cancela o deslocamento em rota.">'
                                    f'{rotulo_cancelar_rota}</button>')
                            else:
                                ticket_botoes.append(
                                    f'<button type="submit" class="secondary" form="form-os" '
                                    f'formaction="{url_os(banco, oid)}/em-rota" formnovalidate '
                                    'title="Registra o início do deslocamento.">'
                                    f'{rotulo_em_rota}</button>')
                        if (responsavel in (None,s['pid']) or s.get('admin')) and not iniciado:
                            ticket_botoes.append(
                                f'<button type="submit" form="form-os" '
                                f'formaction="{url_os(banco, oid)}/iniciar" formnovalidate '
                                f'title="{esc(texto_iniciar)}">'
                                f'{rotulo_iniciar}</button>')
                    ticket_acoes=''.join(ticket_botoes)
                    ticket_acoes+=(f'<a class="btn secondary" href="{url_os(banco, oid)}/pdf-preview">'
                                   +icone('file')+'Baixar preview do PDF</a>')
                    corpo+=('<section class="os-ticket os-summary">'
                        '<div class="os-ticket-stub">'
                        '<p class="os-kicker">Ficha da OS</p>'
                        f'<h2>{esc(d["numero_os"])}</h2>'
                        +chip_status(status_exibicao)+
                        '</div>'
                        '<div class="os-ticket-body">'
                        f'<p class="os-ticket-client">{esc(cliente_nome)}</p>'
                        f'<p class="os-ticket-meta">{esc(" · ".join(partes_meta))}</p>'
                        '<div class="os-ticket-stats">'
                        f'<div><span>Responsável</span><strong>{esc(resp_nome)}</strong></div>'
                        f'<div><span>Total</span><strong class="money">{dinheiro(d.get("valor_total") or 0)}</strong></div>'
                        f'<div><span>Fotos</span><strong>{len(anexos)}</strong></div>'
                        '</div></div>'
                        f'<div class="os-ticket-actions">{ticket_acoes}</div>'
                        '</section>')
                if erro:corpo+=card('Corrija o arquivo YAML',f'<p class="bad" id="yaml-erro-rev08">{esc(erro)}</p><p>Você pode selecionar outro arquivo sem sair da OS.</p>')
                if preenchimento:
                    corpo+=('<p class="notice" id="yaml-importado-rev08" data-yaml-importado="1">'
                        'Prévia importada. Seus campos já digitados podem ser restaurados; '
                        'revise as informações antes de confirmar a OS.</p>'
                        '<button class="secondary" type="button" id="desfazer-yaml-rev08">'
                        'Desfazer importação YAML</button>')
                if oid and app:
                    corpo+='<div class="os-workflow">'
                if oid:
                    nome_resp=next((p['nome'] for p in prestadores if p['id']==responsavel),'Não atribuído')
                    if arquivada:
                        corpo+='<p class="notice">OS arquivada pelo administrador; somente leitura. '
                        corpo+='O histórico permanece preservado.</p>'
                    elif d['status'] not in ext.ATIVAS:
                        corpo+=(f'<p><span class="tag">{esc(d["status"])}</span> · '
                                f'Responsável: <b>{esc(nome_resp)}</b> · Participantes: '
                                f'{esc(", ".join(p["nome"] for p in particip) or "Nenhum")}</p>')
                    if s.get('admin') and not arquivada and d['status'] not in ext.ATIVAS:
                        corpo+=(f'<form method="post" action="{url_os(banco, oid)}/arquivar" '
                                f'data-confirm="Arquivar {esc(d["numero_os"])}? Ela sai das listas operacionais, mas o histórico é preservado.">'
                                f'{token}<button type="submit" class="danger">Arquivar OS</button></form>')
                if oid and app:
                    corpo+='</div>'
                def campo_cliente_os(valor_id):
                    atual = next((x for x in cl if str(x['id']) == str(valor_id)), None)
                    nome_atual = atual['nome'] if atual else ''
                    opcoes_clientes = ''.join(
                        f'<option value="{esc(x["nome"])}" data-id="{int(x["id"])}"></option>'
                        for x in cl)
                    return (
                        '<label for="busca-cliente-os">Cliente da OS</label>'
                        f'<input id="busca-cliente-os" name="cliente_busca" list="clientes-os-lista" '
                        f'value="{esc(nome_atual)}" autocomplete="off" '
                        'placeholder="Digite o nome; a busca é automática">'
                        f'<datalist id="clientes-os-lista">{opcoes_clientes}</datalist>'
                        f'<input type="hidden" name="cliente_id" id="c_cliente_id" '
                        f'value="{esc(valor_id if valor_id is not None else "")}">'
                        '<p class="muted" id="cliente-os-status">Se o nome não existir, ele será '
                        'cadastrado como cliente com dados incompletos para completar depois.</p>'
                    )

                # Carregar rascunho salvo pelo prestador se existir
                try:
                    rasc_salvo = ext.obter_rascunho_web(banco, oid, s['pid']) if oid else None
                    if rasc_salvo:
                        for k,v in rasc_salvo.items():
                            if k.startswith('_') or k in ('csrf','modo_envio','nota_fiscal'):
                                continue
                            if isinstance(v,(str,list)):
                                d[k]=v
                        # O rascunho pode ter materiais ainda não persistidos em
                        # materiais_os. Restaurar as linhas exatamente como o
                        # prestador deixou, inclusive quando removeu todas.
                        if 'material_item[]' in rasc_salvo or 'materiais_presentes' in rasc_salvo:
                            def _lista_rasc(valor):
                                if valor is None:return []
                                return valor if isinstance(valor,list) else [valor]
                            itens_rasc=_lista_rasc(rasc_salvo.get('material_item[]'))
                            qtds_rasc=_lista_rasc(rasc_salvo.get('material_qtd[]'))
                            unids_rasc=_lista_rasc(rasc_salvo.get('material_unidade[]'))
                            units_rasc=_lista_rasc(rasc_salvo.get('material_unit[]'))
                            mat=[{'item':item,
                                  'quantidade':qtds_rasc[i] if i<len(qtds_rasc) else '',
                                  'unidade':unids_rasc[i] if i<len(unids_rasc) else '',
                                  'valor_unitario':units_rasc[i] if i<len(units_rasc) else ''}
                                 for i,item in enumerate(itens_rasc) if str(item).strip()]
                        # O rascunho é a fonte dos valores ainda não persistidos;
                        # sem isso o total negociado antigo reaparece ao reabrir.
                        if 'valor_materiais_manual' in rasc_salvo:
                            d['valor_materiais']=rasc_salvo.get('valor_materiais_manual') or '0'
                        if 'valor_total_override' in rasc_salvo:
                            override=str(rasc_salvo.get('valor_total_override') or '').strip()
                            if override:
                                d['valor_total']=numero_seguro(override)
                            else:
                                itens_mat=[m for m in mat if str(m.get('item','')).strip()]
                                total_mat=sum(numero_seguro(m.get('quantidade'))*
                                              numero_seguro(m.get('valor_unitario'))
                                              for m in itens_mat)
                                if not itens_mat:
                                    total_mat=numero_seguro(rasc_salvo.get('valor_materiais_manual'))
                                d['valor_total']=round(
                                    numero_seguro(rasc_salvo.get('valor_mao_obra'))+total_mat,2)
                except Exception:
                    rasc_salvo = None
                # O auto-save envia a composição como texto JSON. Normalizar
                # depois do merge evita iterar caracteres e mantém a composição
                # declarativa já gravada quando o rascunho não a trouxer.
                def _lista_composicao(valor):
                    if isinstance(valor,str):
                        try:
                            valor=json.loads(valor)
                        except (TypeError,ValueError):
                            return None
                    if isinstance(valor,dict):
                        valor=valor.get('componentes')
                    if not isinstance(valor,list):
                        return None
                    return [x for x in valor if isinstance(x,dict)]
                composicao_rascunho=_lista_composicao(d.get('composicao_yaml'))
                if composicao_rascunho is not None:
                    d['composicao_yaml']=composicao_rascunho
                else:
                    d.pop('composicao_yaml',None)
                    if oid and o and o['composicao_json']:
                        try:
                            comp_salva=json.loads(o['composicao_json'])
                        except (TypeError,ValueError):
                            comp_salva={}
                        if isinstance(comp_salva,dict) and comp_salva.get('declarativa'):
                            d['composicao_yaml']=[
                                {'id':x.get('id'),'nome':x.get('nome'),
                                 'valor':f'{int(x.get("valor_centavos") or 0)/100:.2f}'.replace('.',',')}
                                for x in comp_salva.get('componentes',[])
                                if isinstance(x,dict)]
                if app:
                    corpo+='<div class="os-layout"><div class="os-main">'
                if not oid:
                    corpo+=card('Importar OS em YAML',
                        f'<form method="post" action="/os/yaml" enctype="multipart/form-data" data-no-ajax>{token}'
                        '<label for="importar-os-yaml">Preencher a OS a partir de YAML (até 64 KB)</label>'
                        '<input id="importar-os-yaml" type="file" name="yaml" accept=".yaml,.yml" required>'
                        '<button type="submit" class="secondary">Pré-visualizar YAML</button></form>'
                        '<p class="muted">A importação apenas preenche o formulário para revisão; '
                        'nada é salvo antes de confirmar a criação da OS.</p>')
                auto_save='1' if oid and d['status'] in ext.ATIVAS and not arquivada else '0'
                corpo+=f'<form method="post" action="{action}" id="form-os"{classe_form} data-ajax-preserve="1" data-os-id="{oid or ""}" data-salvar-url="{action}" data-auto-save="{auto_save}" enctype="multipart/form-data">{token}'
                if oid:
                    corpo+='<input type="hidden" name="acao_status" id="acao-status-os" value="">'
                if auto_save=='1':
                    corpo+='<p class="muted auto-save-status" id="rascunho-auto-status" aria-live="polite">Salvamento automático ativo.</p>'
                if d.get('composicao_yaml'):
                    import json as _json_comp
                    corpo+=('<input type="hidden" name="composicao_yaml" value="'
                            +esc(_json_comp.dumps(d['composicao_yaml'],ensure_ascii=False))+'">')
                servicos_ativos=catalogo.listar(banco,ativos=True)
                bloco_modelo=''
                if servicos_ativos:
                    js_json=json.dumps([{'id':v['id'],'nome':v['nome'],
                        'preco':str(v['preco_servico_centavos']/100),
                        'relatorio':v['relatorio_padrao'],
                        'materiais':json.loads(v['materiais_json'])} for v in servicos_ativos],ensure_ascii=False).replace('<','\\u003c')
                    bloco_modelo=(card('Serviço pré-cadastrado — opcional',
                       '<p>Selecione um modelo de serviço:</p>'
                       +select('Modelo','modelo_servico_id',[('', 'Não utilizar modelo')]+[(v['id'],v['nome']) for v in servicos_ativos])
                       +'<button id="aplicar-modelo-servico" type="button" class="secondary">Preencher dados a partir do modelo</button>'
                       +'<p class="muted">Só é aplicado quando você clicar. Verifique e ajuste os valores e o relatório.</p>')
                       +f'<script type="application/json" id="catalogo-os-json">{js_json}</script>')
                    if app:
                        bloco_modelo='<div class="os-service-model">'+bloco_modelo+'</div>'
                corpo+='<input type="hidden" name="materiais_presentes" value="1">'
                if oid:
                    corpo+=f'<input type="hidden" name="_versao_os" value="{esc(d.get("atualizado_em") or "") }">'
                cliente_nome_cancel=next((x['nome'] for x in cl if x['id']==d.get('cliente_id')),'')
                status_bloco=''
                cancelar_dialogo=''
                if oid and d['status'] in ext.ATIVAS and not arquivada:
                    atual='Em rota' if em_rota else ('Iniciada' if iniciado_ativo else d['status'])
                    # O diálogo é o fechamento manual: Em rota e Iniciada têm
                    # botões próprios, e a situação atual não é uma opção.
                    opcoes_base=([('Aberta','Aberta')] if s.get('admin') else [])
                    opcoes_base.extend([('Pendente','Pendente'),('Concluída','Concluída')])
                    opcoes_situacao=[(chave,rotulo) for chave,rotulo in opcoes_base
                                     if chave!=atual]
                    radios=''.join(
                        f'<label><input type="radio" name="situacao_popup" value="{chave}">'
                        f' {rotulo}</label>'
                        for chave,rotulo in opcoes_situacao)
                    status_bloco=(
                        f'<dialog class="feedback-dialog situacao-dialog" id="dialogo-situacao-os" '
                        f'data-os-url="{url_os(banco,oid)}">'
                        '<div class="cancel-step">'
                        '<h2>Confirmar situação da OS</h2>'
                        f'<p class="muted">{esc(d["numero_os"])} · Responsável: '
                        f'<b>{esc(nome_resp)}</b></p>'
                        '<fieldset class="situacao-opcoes"><legend>Situação do atendimento</legend>'
                        +radios+'</fieldset>'
                        '<p class="muted" id="situacao-ajuda">Escolha a situação final e confirme. '
                        'Em rota e Iniciada ficam nos botões da ficha. '
                        'Concluir exige Serviço executado e nota fiscal (ou “não precisa”).</p>'
                        '<div class="feedback-actions">'
                        '<button type="button" class="secondary" data-fechar-situacao>Voltar</button>'
                        '<button type="submit" class="secondary" id="aplicar-situacao" '
                        'formnovalidate>Aplicar situação</button>'
                        '</div></div></dialog>')
                    cancelar_dialogo=(
                        f'<dialog class="feedback-dialog cancel-dialog" id="dialogo-cancelar-os" '
                        f'data-numero-os="{esc(d["numero_os"])}">'
                        '<div class="cancel-step" data-step="1">'
                        f'<h2>Cancelar {esc(d["numero_os"])}</h2>'
                        f'<p class="muted">{esc(cliente_nome_cancel)} · Total {dinheiro(d.get("valor_total") or 0)}</p>'
                        '<label for="cancelar-motivo">Por que a OS será cancelada?</label>'
                        '<textarea id="cancelar-motivo" name="motivo_encerramento" rows="4" '
                        'maxlength="2000" placeholder="Descreva o motivo do cancelamento..."></textarea>'
                        '<p class="muted">O motivo fica no histórico e é enviado ao cliente.</p>'
                        '<div class="feedback-actions">'
                        '<button type="button" class="secondary" data-fechar-cancelar>Voltar</button>'
                        '<button type="button" class="danger" data-proximo-cancelar>Continuar</button>'
                        '</div></div>'
                        '<div class="cancel-step" data-step="2" hidden>'
                        '<h2>Confirmar cancelamento</h2>'
                        f'<p class="notice"><b>{esc(d["numero_os"])}</b> · {esc(cliente_nome_cancel)}<br>'
                        f'Total {dinheiro(d.get("valor_total") or 0)}</p>'
                        '<p>Para confirmar, digite o número da OS exatamente como aparece acima.</p>'
                        '<label for="confirmar-numero-os">Número da OS</label>'
                        f'<input id="confirmar-numero-os" name="confirmar_numero_os" autocomplete="off" '
                        f'placeholder="{esc(d["numero_os"])}">'
                        '<p class="bad" id="cancelar-erro" hidden></p>'
                        '<div class="feedback-actions">'
                        '<button type="button" class="secondary" data-voltar-cancelar>Voltar</button>'
                        f'<button type="submit" class="danger" name="cancelar_os" value="1" '
                        f'formaction="{url_os(banco, oid)}/cancelar" formnovalidate>'
                        'Cancelar OS definitivamente</button>'
                        '</div></div></dialog>')
                corpo+='<fieldset><legend>Identificação e serviço</legend>'
                if bloco_modelo and not oid:
                    corpo+=bloco_modelo
                corpo+='<div class="os-client-block">'
                if solicitacao:
                    nome_cliente_solicitacao=next((x['nome'] for x in cl if x['id']==solicitacao['cliente_id']),'')
                    rotulo_origem=('Chamado de origem' if s.get('admin')
                                   else 'Chamado de origem — somente leitura')
                    corpo+=(f'<p class="notice"><strong>{esc(rotulo_origem)}</strong><br>'
                        f'Cliente: {esc(nome_cliente_solicitacao)} · {esc(solicitacao["criado_em"])}<br>'
                        f'{esc(solicitacao["descricao_original"])}<br>'
                        f'<span class="muted">Número da OS: {esc(d.get("numero_os") or "")}. '
                        'O chamado de origem não é o número da OS.</span></p>')
                    cliente_solicitacao=clientes_core.obter_linha(
                        int(solicitacao['cliente_id']),banco=banco)
                    if not cliente_solicitacao or cliente_solicitacao.get('status')=='A definir' or s.get('admin'):
                        corpo+=campo_cliente_os(d.get('cliente_id',solicitacao['cliente_id']))
                        corpo+='<p class="muted">O chamado chegou sem cliente definido. Escolha o cliente real da OS.</p>'
                    else:
                        corpo+=f'<input type="hidden" name="cliente_id" value="{int(solicitacao["cliente_id"])}">'
                else:
                    cliente_atual_id=int(d.get('cliente_id') or (cl[0]['id'] if cl else 0))
                    contato_atual=clientes_core.obter_linha(cliente_atual_id,banco=banco)
                    contato_texto=''
                    if contato_atual:
                        partes_contato=[str(contato_atual.get(k) or '') for k in
                                        ('email','telefone','sindico_nome','sindico_email')]
                        contato_texto=' · '.join(x for x in partes_contato if x)
                    corpo+=campo_cliente_os(d.get('cliente_id') or (cl[0]['id'] if cl else ''))
                    corpo+=f'<p class="muted" id="cliente-contato-os">'+(esc(contato_texto) or 'Sem e-mail ou telefone cadastrado.')+'</p>'
                corpo+='</div>'
                if oid and app and s.get('admin') and d['status'] in ext.ATIVAS and not arquivada:
                    opcoes_responsavel=(([('', 'Não atribuído')] if not responsavel else [])
                                        + [(str(p['id']), p['nome']) for p in prestadores])
                    corpo+=('<label for="prestador-destino">Responsável (admin)</label>'
                            f'<select id="prestador-destino" name="prestador_destino" '
                            f'data-atribuir-url="{url_os(banco,oid)}/atribuir" '
                            f'data-atual="{esc(str(responsavel or ""))}">'
                            +''.join(f'<option value="{esc(v)}"'
                                     f'{" selected" if str(v)==str(responsavel or "") else ""}>'
                                     f'{esc(nome)}</option>' for v,nome in opcoes_responsavel)
                            +'</select>')
                corpo+='<div class="col2"><div>'
                corpo+=campos_escuros('Atendido por (cliente no local)','tecnico',d.get('tecnico','') or '')
                corpo+='</div><div>'
                corpo+=select('Forma de pagamento','forma_pagamento',
                    [('', 'Selecione a forma de pagamento')]+[(z,z) for z in neg.OS_FORMAS],
                    d.get('forma_pagamento') or '')
                corpo+='</div></div><div class="col2"><div>'
                corpo+=select('Urgência','urgencia',
                    [('Baixa','Baixa'),('Normal','Normal'),('Alta','Alta')],
                    d.get('urgencia') or 'Normal')
                corpo+='</div><div>'
                # Saved OSs store the labor component of the composition, not
                # the service value the user typed. When there is an explicit
                # final total, show the actual hour remainder; otherwise
                # derive the service value from total - materials so reopening
                # the form does not freeze a split.
                comp_salva_form=composicao.de_json(d.get('composicao_json'))\
                    if d.get('composicao_json') else None
                hora_salva=next((x for x in (comp_salva_form or {}).get('componentes',[])
                                 if x.get('modo')=='hora' or x.get('id')=='hora_tecnica'),
                                None)
                sem_visita_atual=bool(comp_salva_form and comp_salva_form.get('sem_visita'))
                composicao_simplificada=bool(comp_salva_form and comp_salva_form.get('simplificada'))
                valor_final_override=d.get('valor_total_override') or ''
                if (not valor_final_override and oid and comp_salva_form
                        and comp_salva_form.get('valor_total_override') is not None):
                    valor_final_override=comp_salva_form.get('valor_total_override')
                valor_servico=d.get('valor_mao_obra') or '0'
                if hora_salva is not None and str(valor_final_override).strip():
                    valor_servico=int(hora_salva.get('valor_centavos') or 0)/100
                elif d.get('valor_total') is not None:
                    if oid or not str(d.get('valor_mao_obra') or '').strip():
                        valor_servico=max(
                            0.0, numero_seguro(d.get('valor_total'))
                            - numero_seguro(d.get('valor_materiais')))
                if not oid and d.get('valor_total') is not None:
                    if abs(numero_seguro(d.get('valor_total'))
                           - numero_seguro(valor_servico)
                           - numero_seguro(d.get('valor_materiais')))>0.009:
                        valor_final_override=d.get('valor_total')
                corpo+=campos_escuros('Valor do serviço — mão de obra, sem materiais (R$)','valor_mao_obra',valor_servico,required=True)+'</div></div>'
                corpo+='<p class="muted">Este é o valor da mão de obra, sem materiais. Quando há valor final informado, a mão de obra é o restante depois de materiais, visita (se cobrada) e custos percentuais; a composição não soma taxas por cima do total. ' \
                       'Em garantia ou cortesia, informe <b>0,00</b> na mão de obra e <b>0,00</b> no valor cobrado dos materiais. O custo real dos materiais é interno e não entra no total cobrado.</p>'
                corpo+=campos_escuros('Valor final da OS (R$), opcional','valor_total_override',
                  valor_final_override)
                corpo+='<p class="muted">O <b>valor final da OS</b> é o que o cliente paga. Quando informado, prevalece sobre serviço + materiais. A composição apenas distribui esse total — nunca acrescenta visita, percentuais ou custos por cima.</p>'
                if solicitacao:
                    corpo+=f'<input type="hidden" name="descricao" value="{esc(solicitacao["descricao_original"])}">'
                else:
                    corpo+=textarea('Descrição do serviço','descricao',d.get('descricao') or '',required=True)
                if solicitacao and d.get('origem')=='Portal':
                    obs_origem=str(solicitacao['observacoes_originais'] or '').replace(
                        'Solicitação #','Chamado de origem #').replace(
                        'Solicitação pública','Chamado público')
                    corpo+=f'<p class="muted">Protocolo do chamado (não é o número da OS): {esc(obs_origem)}</p>'
                    corpo+=f'<input type="hidden" name="observacoes" value="{esc(d.get("observacoes") or "") }">'
                else:
                    corpo+=textarea('Observações gerais','observacoes',d.get('observacoes') or '')
                if oid and d['status'] in ext.ATIVAS and not arquivada:
                    corpo+='<div class="os-danger-actions">'
                    corpo+=('<input type="file" id="importar-relatorio-yaml" name="yaml" '
                            'accept=".yaml,.yml" hidden '
                            f'data-importar-url="{url_os(banco, oid)}/yaml">'
                            '<label class="btn secondary" for="importar-relatorio-yaml">'
                            'Importar relatório YAML</label>')
                    corpo+=botao('Exportar relatório em YAML', f'{url_os(banco, oid)}/relatorio.yaml','secondary')
                    if s.get('admin'):
                        corpo+=(f'<button type="submit" class="secondary" formaction="{url_os(banco, oid)}/arquivar" formnovalidate '
                                f'data-confirm="Arquivar {esc(d["numero_os"])}? Ela sai das listas operacionais, mas o histórico é preservado.">'
                                'Arquivar OS</button>')
                    if responsavel==s['pid'] or s.get('admin'):
                        corpo+='<button type="button" class="danger" id="abrir-cancelar-os">Cancelar OS</button>'
                    corpo+='</div>'
                corpo+='</fieldset>'
                corpo+='<fieldset><legend>Materiais utilizados</legend><p class="muted">O total da OS é serviço + materiais, salvo quando houver um valor final informado. Materiais detalhados prevalecem sobre o campo de materiais sem itens. Sem materiais, o relatório não exibe esta seção.</p>'
                corpo+=datalist_unidades_material()
                produtos=estoque.listar(banco,ativos=True)
                attr_estoque=' list="materiais-estoque-lista"' if produtos else ''
                if produtos:
                    import json as _jm
                    opcoes_estoque=''.join(
                        f'<option value="{esc(x["nome"])}" label="{esc(x["nome"])} — '
                        f'{dinheiro((x["venda_centavos"] or 0)/100)}"></option>'
                        for x in produtos)
                    corpo+=f'<datalist id="materiais-estoque-lista">{opcoes_estoque}</datalist>'
                    catalogo_json=_jm.dumps([{'nome':x['nome'],
                                              'valor':(x['venda_centavos'] or 0)/100,
                                              'unidade':x['unidade'] or 'un'}
                                             for x in produtos],ensure_ascii=False).replace('<','\u003c')
                    corpo+=f'<script type="application/json" id="produtos-estoque-os">{catalogo_json}</script>'
                corpo+=('<p class="muted">Comece a digitar o material: se ele estiver no estoque, '
                        'o valor e a unidade são preenchidos automaticamente. Você também pode '
                        'digitar um material livre.</p>')
                corpo+='<p class="muted">Deixe a quantidade vazia para itens sem quantidade fixa; nesse caso, o valor informado é o total do item. A unidade é livre: use uma sugestão ou digite a sua.</p>'
                linhas=list(mat)
                corpo+='<div id="lista-materiais">'
                for i,m in enumerate(linhas):
                    item=m['item'] if 'item' in m.keys() else ''
                    qtd=m['quantidade'] if 'quantidade' in m.keys() else ''
                    unidade=(m['unidade'] if 'unidade' in m.keys() else '') or ''
                    unit=m['valor_unitario'] if 'valor_unitario' in m.keys() else ''
                    corpo+='<div class="material-row material-row-os">'
                    corpo+=f'<div><label>Material<input name="material_item[]" value="{esc(item)}" placeholder="Digite ou busque no estoque"{attr_estoque}></label></div>'
                    corpo+=f'<div><label>Quantidade<input name="material_qtd[]" value="{esc(qtd)}" placeholder="—" inputmode="decimal"></label></div>'
                    corpo+=f'<div><label>Unidade{input_unidade_material(unidade)}</label></div>'
                    corpo+=f'<div><label>Valor unitário / total (R$)<input name="material_unit[]" value="{esc(unit)}" placeholder="0,00"></label></div>'
                    corpo+='<button type="button" class="secondary remover-material" title="Remover material">Remover</button></div>'
                corpo+='</div><p class="muted">Nenhum material é obrigatório. Use “Adicionar material” somente se necessário.</p>'
                corpo+=f'''<template id="modelo-material"><div class="material-row material-row-os"><div><label>Material<input name="material_item[]" placeholder="Digite ou busque no estoque"{attr_estoque}></label></div><div><label>Quantidade<input name="material_qtd[]" placeholder="—" inputmode="decimal"></label></div><div><label>Unidade{input_unidade_material("")}</label></div><div><label>Valor unitário / total (R$)<input name="material_unit[]" placeholder="0,00"></label></div><button type="button" class="secondary remover-material">Remover</button></div></template>'''
                corpo+='<div class="material-add"><button id="adicionar-material" class="secondary" type="button">+ Adicionar material</button></div>'
                corpo+='<div class="col2"><div>'+campos_escuros('Valor de materiais sem itens detalhados (R$)','valor_materiais_manual',d.get('valor_materiais') or '0')+'</div>'
                corpo+='<div>'+campos_escuros('Custo real dos materiais (R$) — interno, não cobrado','custo_materiais',d.get('custo_materiais') or '0')+'</div></div>'
                corpo+='<p class="muted">Use o valor sem itens apenas quando não houver materiais detalhados. O custo real é interno e não entra no total cobrado.</p>'
                try:
                    cfg_comp=composicao.carregar()
                    bases_comp=cfg_comp.get('bases_percentuais') or {}
                    base_padrao=cfg_comp.get('base_percentuais_padrao') or 'total'
                except (ValueError,OSError):
                    bases_comp={}; base_padrao='total'
                if not bases_comp:
                    bases_comp={'total':{'nome':'Total da OS'},
                                'visita':{'nome':'Visita mínima'}}
                base_atual=('total' if sem_visita_atual
                            else str(d.get('base_percentuais') or base_padrao))
                opcoes_base=[(chave,(valor or {}).get('nome',chave))
                             for chave,valor in bases_comp.items()]
                corpo+='</fieldset>'
                corpo+='<fieldset><legend>Situação e relatório técnico</legend>'
                if oid and d['status'] in ext.ATIVAS and contatos_os:
                    selecionados_d = d.get('destinatario_sel[]') or []
                    if isinstance(selecionados_d, str):
                        selecionados_d = [selecionados_d]
                    selecionados_d = [str(x) for x in selecionados_d if str(x).strip()]
                    corpo+='<fieldset><legend>Destinatários do relatório</legend>'
                    corpo+='<p class="muted">Marque apenas quem deve receber o relatório. A seleção é gravada e usada no envio automático.</p>'
                    corpo+='<input type="hidden" name="destinatarios_presente" value="1">'
                    for chave,rotulo in (('cliente','Cliente'),('sindico','Síndico'),('administradora','Administradora / imobiliária')):
                        email=contatos_os.get(chave) or ''
                        if email:
                            marcado=' checked' if chave in selecionados_d else ''
                            corpo+=f'<label style="display:block;margin:5px 0"><input type="checkbox" name="destinatario_sel[]" value="{chave}"{marcado}> {rotulo}: {esc(email)}</label>'
                    corpo+='<p class="muted" id="destinatarios-resumo" aria-live="polite">Nenhum destinatário selecionado.</p>'
                    corpo+=f'<label>E-mails adicionais (separe por vírgula)<input name="emails_adicionais" type="text" maxlength="500" value="{esc(str(d.get("emails_adicionais","")))}" placeholder="financeiro@exemplo.com.br"></label>'
                    marcado_sem_dest=' checked' if str(d.get('sem_destinatario','')) in ('1','on','true','sim') else ''
                    corpo+=(f'<label style="display:flex;align-items:center;gap:8px;font-weight:600;cursor:pointer;margin-top:10px">'
                            f'<input type="checkbox" name="sem_destinatario" value="1"{marcado_sem_dest}> '
                            'Não precisa de destinatário</label>')
                    corpo+='<p class="muted">Marque para concluir a OS sem enviar o relatório por e-mail. '
                    corpo+='A lista final é registrada no banco e enviada a todos os destinatários selecionados em um único e-mail.</p></fieldset>'
                if oid and s.get('admin'):
                    valor_solicitacao=(d.get('solicitacao_original')
                                       or (solicitacao['descricao_original']
                                           if solicitacao else d.get('descricao')) or '')
                    corpo+=textarea('Solicitação original','solicitacao_original',
                                    valor_solicitacao,rows=4,required=True)
                    corpo+='<p class="muted">Este texto é a solicitação original do cliente. Ele aparece no PDF e no chamado de origem; editar aqui atualiza os dois.</p>'
                corpo+=textarea('Diagnóstico','v9_diagnostico',d.get('v9_diagnostico',(detalhes['diagnostico'] if detalhes else '')) or '',rows=3)
                corpo+=textarea('Serviço executado','v9_execucao',d.get('v9_execucao',(detalhes['execucao'] if detalhes else '')) or '',rows=4)
                corpo+=textarea('Resultado e testes','v9_resultado',d.get('v9_resultado',(detalhes['resultado'] if detalhes else '')) or '',rows=3)
                corpo+=textarea('Relato técnico complementar (histórico interno)','relatorio_tecnico',d.get('relatorio_tecnico',(andamento['rascunho'] if andamento else '')) or '',rows=4)
                corpo+=textarea(texto_os.rotulo(),'texto_adicional',d.get('texto_adicional',texto_os.padrao()) or '',rows=4)
                if texto_os.ajuda():
                    corpo+=f'<p class="muted">{esc(texto_os.ajuda())}</p>'
                comp_itemizado=bool(d.get('composicao_yaml'))
                if comp_itemizado:
                    itens_comp=[]
                    for x in d.get('composicao_yaml') or []:
                        if not isinstance(x,dict):
                            continue
                        nome=esc(str(x.get('nome') or x.get('id') or ''))
                        valor_c=composicao.centavos_de_reais(str(x.get('valor') or '0'))
                        itens_comp.append(f'<li>{nome} — {dinheiro(valor_c/100)}</li>')
                    corpo+=('<div class="notice"><b>Composição itemizada desta OS</b>'
                            '<ul>'+''.join(itens_comp)+'</ul>'
                            '<p class="muted">Os itens são preservados ao salvar a OS.</p></div>')
                else:
                    marcado_comp='' if composicao_simplificada else ' checked'
                    corpo+=f'<label style="display:flex;align-items:center;gap:8px;font-weight:600;cursor:pointer;margin-top:14px"><input type="checkbox" name="aplicar_composicao" value="1"{marcado_comp}> Aplicar composição padrão (custos e margem)</label>'
                    corpo+='<p class="muted">A hora técnica recebe o restante do total e tem mínimo de R$ 100,00. A taxa de visita é opcional nesta OS.</p>'
                    corpo+=('<input type="hidden" name="cobrar_visita" value="0">'
                            '<label style="display:flex;align-items:center;gap:8px;font-weight:600;cursor:pointer;margin-top:10px">'
                            f'<input type="checkbox" name="cobrar_visita" value="1"{"" if sem_visita_atual else " checked"}> '
                            'Cobrar taxa mínima de visita</label>')
                    corpo+='<p class="muted">Desmarque para uma OS negociada sem taxa de visita: os custos percentuais continuam incidindo sobre o total e a mão de obra recebe o restante.</p>'
                    corpo+=select('Composição dos valores','base_percentuais',opcoes_base,base_atual)
                    corpo+='<p class="muted">Total da OS: os percentuais entram como linhas próprias e a hora recebe o restante. Visita mínima: os percentuais ficam dentro da visita e a hora recebe o restante. Em ambas, o total final não muda.</p>'
                    corpo+='<div class="total-previsto-linha"><span>Total previsto</span><strong><span id="total-previsto">—</span></strong></div>'
                    corpo+='<div class="composicao-preview" id="composicao-prevista" aria-live="polite"></div>'
                if oid and d['status'] in ext.ATIVAS and not arquivada:
                    if iniciado_ativo:
                        corpo+=f'<p class="good">Atendimento iniciado em {esc(andamento["iniciado_em"])} por {esc(andamento["ator_inicio"])}</p>'
                    else:
                        corpo+='<p class="warn">OS ainda não iniciada. Assumir uma OS não inicia o atendimento automaticamente.</p>'
                corpo+='</fieldset>'
                if oid and d['status'] in ext.ATIVAS and not arquivada:
                    pode_editar_fotos = (responsavel == s['pid']) or bool(s.get('admin'))
                    pode_nota = (responsavel == s['pid']) or cad9.prestador_admin(banco, s['pid'])
                    try:
                        cliente_metadados=next(
                            (dict(x) for x in cl
                             if int(x['id'])==int(d.get('cliente_id'))), {}
                        ) if d.get('cliente_id') else {}
                    except (TypeError,ValueError):
                        cliente_metadados={}
                    local_metadados=' · '.join(
                        str(cliente_metadados.get(k) or '').strip()
                        for k in ('bairro','cidade')
                        if str(cliente_metadados.get(k) or '').strip())
                    corpo+=(f'<fieldset data-local-metadados="{esc(local_metadados)}">'
                            '<legend>Fotos do relatório e legendas</legend>')
                    if pode_editar_fotos:
                        corpo+=('<p class="muted">Você pode adicionar fotos e alterar legendas. '
                                'Tudo é salvo automaticamente ao selecionar arquivos ou '
                                'editar uma legenda. A conclusão gera o PDF com as fotos e '
                                'legendas.</p>'
                                '<p class="muted auto-save-status" id="fotos-auto-status" '
                                'aria-live="polite">Fotos e legendas salvas automaticamente.</p>'
                                '<p class="muted">Importar metadados usa a data da foto e o '
                                'bairro/cidade do cliente. Leitura EXIF/GPS pode ser adicionada depois.</p>')
                    else:
                        corpo+=('<p class="muted">Somente o responsável ou administrador pode '
                                'adicionar fotos e alterar legendas.</p>')
                    if pode_editar_fotos:
                        corpo+='<input type="hidden" name="anexo_incluir_modo" value="1">'
                    if anexos:
                        corpo+='<div class="fotos-rascunho">'
                        for a in anexos:
                            legenda=esc(a['legenda'] or '')
                            vis=esc(str(a['visivel'] if a['visivel'] is not None else 1))
                            versao=esc(str(a['sha256'] or a['id'])[:12])
                            corpo+=('<div class="foto-rascunho" data-anexo-id="'+str(a['id'])+'" style="display:grid;grid-template-columns:150px 1fr;gap:12px;border:1px solid #3b3b3b;padding:10px;margin:10px 0;border-radius:8px">'
                                +'<img src="/arquivos/anexo/'+str(a['id'])+'/thumb?v='+versao+'" alt="Foto da OS" loading="lazy" decoding="async" width="150" height="112" style="width:150px;height:112px;object-fit:cover;border-radius:6px">'
                                +'<div>')
                            if pode_editar_fotos:
                                marcado=' checked' if vis=='1' else ''
                                corpo+=('<label>Legenda da foto<input name="anexo_legenda[]" maxlength="160" value="'+legenda+'" placeholder="Ex.: Quadro elétrico antes do reparo"></label>'
                                    +'<button type="button" class="secondary importar-metadados" '
                                    'data-importar-metadados '
                                    f'data-metadados-data="{esc(a["criado_em"])}" '
                                    f'data-metadados-local="{esc(local_metadados)}">Importar metadados</button>'
                                    +'<input type="hidden" name="anexo_id[]" value="'+str(a['id'])+'">'
                                    +f'<label class="foto-incluir"><input type="checkbox" name="anexo_incluir[]" value="{a["id"]}"{marcado}> Incluir no PDF</label>'
                                    +f'<button class="secondary" type="button" data-mover="{url_os(banco, oid)}/anexo/{a["id"]}/mover" data-direcao="up" title="Mover para cima">↑</button>'
                                    +f'<button class="secondary" type="button" data-mover="{url_os(banco, oid)}/anexo/{a["id"]}/mover" data-direcao="down" title="Mover para baixo">↓</button>'
                                    +f'<button class="secondary" type="button" data-girar="{url_os(banco, oid)}/anexo/{a["id"]}/girar" title="Girar 90°">Girar 90°</button>'
                                    +f'<button class="danger" type="submit" formaction="{url_os(banco, oid)}/anexo/{a["id"]}/remover" formnovalidate data-confirm="Remover esta foto da OS?">Remover foto</button>')
                            else:
                                corpo+='<p><b>Legenda:</b> '+(legenda or 'Sem legenda')+'</p>'
                            corpo+='</div></div>'
                        corpo+='</div>'
                    if pode_editar_fotos:
                        corpo+='<div id="anexo-encerramento"><label for="fotos-relatorio">Adicionar fotos novas (até 10, 8 MB por foto)</label>'
                        corpo+='<input type="file" id="fotos-relatorio" name="imagens_encerramento[]" multiple accept="image/jpeg,image/png,image/webp">'
                        corpo+='<div id="lista-fotos-selecionadas" aria-live="polite"></div>'
                        corpo+='<button class="secondary" id="limpar-fotos" type="button" hidden>Limpar fotos selecionadas</button>'
                        corpo+='<p class="muted">A prévia e o campo Legenda da foto aparecem abaixo para cada arquivo. Ao salvar, as fotos e legendas ficam guardadas sem finalizar a OS.</p></div>'
                        comprimir_pdf=bool(d.get('comprimir_fotos_pdf',1))
                        corpo+='<input type="hidden" name="comprimir_fotos_pdf_presente" value="1">'
                        corpo+=(f'<label class="foto-comprimir"><input type="checkbox" name="comprimir_fotos_pdf" value="1"'
                                f'{" checked" if comprimir_pdf else ""}> Comprimir fotos no PDF</label>')
                        corpo+='<p class="muted">As imagens do site são sempre otimizadas; o original permanece no banco. '
                        corpo+='Desmarque para usar alta qualidade no PDF.</p>'
                    corpo+=('<div class="os-close-head"><h3>Fechamento</h3>'
                            '<p>Nota fiscal e confirmação da OS.</p></div>')
                    if pode_nota:
                        nota_atual=notas_fiscais[-1] if notas_fiscais else None
                        corpo+='<div id="nota-fiscal-upload" style="margin-top:14px;border-top:1px solid #444;padding-top:12px">'
                        if nota_atual:
                            nid=int(nota_atual['id'])
                            corpo+=(f'<p class="good" id="nota-fiscal-status">PDF anexado: '
                                    f'<b>{esc(nota_atual["nome_original"])}</b></p>'
                                    f'<a class="btn secondary" href="{url_os(banco, oid)}/nota-fiscal/{nid}/preview" '
                                    'target="_blank" rel="noopener">Visualizar PDF</a> '
                                    f'<a class="btn secondary" href="{url_os(banco, oid)}/nota-fiscal/{nid}">Baixar PDF</a> '
                                    '<button type="submit" class="danger" '
                                    f'formaction="{url_os(banco, oid)}/nota-fiscal/{nid}/remover" formnovalidate '
                                    'data-confirm="Remover o PDF anexado?">Remover PDF</button>'
                                    '<p class="muted">Para substituir, remova o PDF atual e escolha outro arquivo.</p>')
                        else:
                            corpo+='<label for="nota-fiscal-pdf">Anexar nota fiscal (PDF, até 20 MB)</label>'
                            corpo+=(f'<input type="file" id="nota-fiscal-pdf" name="nota_fiscal" '
                                    'accept="application/pdf" data-auto-upload-nf '
                                    f'data-upload-url="{url_os(banco, oid)}/nota-fiscal">')
                            corpo+=('<p class="muted" id="nota-fiscal-auto-status" data-nf-status>'
                                    'O PDF será anexado automaticamente ao escolher o arquivo '
                                    'e o rascunho será salvo.</p>')
                            corpo+=(f'<noscript><button class="secondary" type="submit" '
                                    f'formaction="{url_os(banco, oid)}/nota-fiscal" formnovalidate>Enviar PDF</button></noscript>')
                            corpo+='<div style="margin-top:12px;padding:12px;border:1px solid #E2B800;border-radius:8px;background:#2a2617">'
                            corpo+='<label style="display:flex;align-items:center;gap:8px;font-weight:700;cursor:pointer"><input type="checkbox" name="sem_nota_fiscal" value="1" style="width:18px;height:18px"> Não precisa de nota fiscal</label>'
                            corpo+='<p class="muted" style="margin:6px 0 0">Marque esta opção ou anexe o PDF da nota fiscal para poder concluir a OS.</p></div>'
                        corpo+='<p class="muted">A nota fiscal aparece na lista de documentos e é anexada ao e-mail de conclusão ou de reenvio.</p></div>'
                    corpo+='</fieldset>'
                if oid:
                    with ext.db(banco) as c:
                        fin_rateio=c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',
                                             (oid,)).fetchone()
                        rateios_atuais=[dict(x) for x in c.execute('''SELECT r.tecnico_id,
                            p.nome,r.valor_centavos,
                            COALESCE(rep.pago_centavos,0) pago_centavos,
                            COALESCE(rep.enviado_centavos,0) enviado_centavos
                            FROM produtividade_rateios r
                            JOIN prestadores p ON p.id=r.tecnico_id
                            LEFT JOIN produtividade_repasses rep
                              ON rep.os_id=r.os_id AND rep.tecnico_id=r.tecnico_id
                            WHERE r.os_id=? ORDER BY p.nome''',(oid,)).fetchall()]
                    finalizador_rateio=(fin_rateio['prestador_id'] if fin_rateio
                                        else responsavel)
                    admin_rateio=bool(s.get('admin'))
                    pode_editar_rateio=(admin_rateio or
                        (finalizador_rateio is not None
                         and int(finalizador_rateio)==int(s['pid'])))
                    if arquivada or d['status'] in ('Cancelada','Não realizada'):
                        pode_editar_rateio=False
                    total_rateado=sum(int(x['valor_centavos'] or 0)
                                      for x in rateios_atuais)
                    total_os_centavos=int(round(numero_seguro(d.get('valor_total'))*100))
                    corpo+=(f'<fieldset id="rateio-colaboradores" '
                            f'data-rateio-url="{url_os(banco, oid)}/rateio">'
                            '<legend>Rateio e colaboradores</legend>')
                    corpo+=('<p class="muted">Defina agora quem participa e quanto cada técnico '
                            'secundário recebe. O total cobrado do cliente não muda; o restante '
                            'fica com o responsável/finalizador.</p>')
                    corpo+='<div id="rateio-lista">'
                    if rateios_atuais:
                        for x in rateios_atuais:
                            valor_x=int(x['valor_centavos'] or 0)
                            valor_texto=f'{float(valor_x)/100:.2f}'.replace('.', ',')
                            readonly='' if pode_editar_rateio else ' readonly'
                            corpo+=(f'<div class="rateio-row" data-rateio-row '
                                    f'data-tecnico-id="{int(x["tecnico_id"])}">')
                            corpo+=(f'<div><label>Colaborador<input value="{esc(x["nome"])}" '
                                    'readonly></label></div>')
                            corpo+=(f'<div><label>Valor da parcela (R$)'
                                    f'<input name="rateio_manual_valor" value="{valor_texto}" '
                                    f'inputmode="decimal"{readonly}></label></div>')
                            if pode_editar_rateio:
                                corpo+=(f'<button type="button" class="secondary remover-rateio" '
                                        f'data-rateio-remover="{int(x["tecnico_id"])}">Remover</button>')
                            corpo+='</div>'
                    else:
                        corpo+='<p class="muted">Nenhum colaborador com parcela nesta OS.</p>'
                    corpo+='</div>'
                    corpo+=(f'<p id="rateio-totais"><b>Total da OS:</b> '
                            f'<span id="rateio-total-os">{dinheiro(total_os_centavos/100)}</span> · '
                            f'<b>Rateado:</b> <span id="rateio-total-rateado">{dinheiro(total_rateado/100)}</span> · '
                            f'<b>Restante:</b> <span id="rateio-restante">{dinheiro(max(0,total_os_centavos-total_rateado)/100)}</span></p>')
                    if pode_editar_rateio:
                        opcoes_rateio=[('', 'Selecione o colaborador')]+[
                            (p['id'], p['nome']) for p in prestadores
                            if (p['id']!=s['pid'] or admin_rateio)
                            and (finalizador_rateio is None
                                 or int(p['id'])!=int(finalizador_rateio))]
                        opcoes_html=''.join(
                            f'<option value="{pid}">{esc(nome)}</option>'
                            for pid,nome in opcoes_rateio)
                        corpo+='<div class="material-add"><button id="adicionar-rateio" class="secondary" type="button">+ Adicionar colaborador</button></div>'
                        corpo+=('<template id="modelo-rateio"><div class="rateio-row" '
                                'data-rateio-row data-novo="1">'
                                '<div><label>Colaborador<select name="rateio_manual_tecnico">'
                                +opcoes_html+'</select></label></div>'
                                '<div><label>Valor da parcela (R$)'
                                '<input name="rateio_manual_valor" placeholder="0,00" '
                                'inputmode="decimal"></label></div>'
                                '<button type="button" class="secondary remover-rateio">Remover</button>'
                                '</div></template>')
                        corpo+=('<p class="muted auto-save-status" id="rateio-auto-status" '
                                'aria-live="polite">Selecione o colaborador e digite o valor; '
                                'salva automaticamente.</p>')
                    else:
                        corpo+=('<p class="muted">Somente o responsável/finalizador ou um '
                                'administrador pode editar o rateio.</p>')
                    corpo+='</fieldset>'
                corpo+=cancelar_dialogo
                corpo+=status_bloco
                nota_acoes=('Preencha os dados para criar a OS.' if not oid else
                            f'{d["status"]} · {d["numero_os"]}')
                if app:
                    corpo+=('<div class="actions"><div class="actions-note">'+esc(nota_acoes)
                            +'</div><div class="actions-buttons">')
                else:
                    corpo+='<div class="actions">'
                if not oid:
                    corpo+='<button class="secondary" name="modo_envio" value="salvar" type="submit">Criar OS</button>'
                else:
                    if arquivada:
                        corpo+='<span class="notice">OS arquivada: edição bloqueada. O histórico permanece preservado.</span>'
                    elif d['status'] in ext.ATIVAS:
                        if responsavel==s['pid'] or s.get('admin'):
                            corpo+='<button type="button" id="abrir-situacao-os">Confirmar situação da OS</button>'
                    else:
                        corpo+='<span class="notice">OS encerrada: edição bloqueada. Documentos publicados ficam no histórico.</span>'
                if app:
                    corpo+='</div></div></form>'
                else:
                    corpo+='</div></form>'
                if app and oid:
                    corpo+='</div><aside class="os-rail">'
                if not oid:
                    corpo+='<p class="muted">Depois de salvar a OS, você poderá atribuir um prestador e, no encerramento, anexar imagens e publicar PDF.</p>'
                    if app:
                        return self.pagina(titulo,corpo+'</div></div>',s)
                    return self.pagina(titulo,card('Dados da OS',corpo),s)
                # Atribuição e desatribuição administrativas são exclusivas do desktop.
                if d['status'] in ext.ATIVAS and not app and not arquivada:
                    corpo+=card('Atribuição',f'<p>Responsável atual: <b>{esc(next((p["nome"] for p in prestadores if p["id"]==responsavel),"Não atribuído"))}</b></p>'
                        '<p class="muted">Prestadores podem assumir apenas OS não atribuídas. Transferências são feitas no desktop.</p>')
                if anexos and d['status'] not in ext.ATIVAS:
                    itens=[]
                    for a in anexos:
                        vis=imagens_v9.get(a['id'],{})
                        versao=esc(str(a['sha256'] or a['id'])[:12])
                        form=(f'<form method="post" action="{url_os(banco, oid)}/anexo/{a["id"]}/publico">{token}'
                              +campos_escuros('Legenda para o PDF','legenda',vis.get('legenda',''))
                              +select('Incluir no PDF','visivel',[('1','Sim — incluir foto (padrão)'),('0','Não — ocultar por privacidade')],str(vis.get('visivel',1)))
                              +'<button type="submit" class="secondary">Salvar visibilidade</button></form>')
                        itens.append('<div class="card"><img src="/arquivos/anexo/'+str(a['id'])+'/thumb?v='+versao+'" alt="Foto" loading="lazy" decoding="async" width="110" height="90" style="width:110px;height:90px;object-fit:cover;display:block"><b>'+esc(a['nome_original'])+'</b>'+form+'</div>')
                    corpo+=card('Fotos da OS','<p>As fotos anexadas entram automaticamente no PDF. Se houver informação particular, selecione Ocultar por privacidade. Após alterar uma OS encerrada, publique outra versão do relatório.</p>'+''.join(itens))
                if oid:
                    with ext.db(banco) as c:
                        email_log=c.execute('SELECT status,erro FROM produtividade_email WHERE os_id=?',(oid,)).fetchone()
                    if email_log:
                        corpo+=card('Envio de e-mail',
                            '<p class="'+('good' if email_log['status']=='enviado' else 'warn')+'">Status: '
                            +esc(email_log['status'])+'</p>'
                            +('<p>'+esc(email_log['erro'])+'</p>' if email_log['erro'] else ''))
                publicado=fluxo.ultimo_documento(banco,oid) if oid else None
                if publicado and d['status'] in fluxo.FIM:
                    corpo+=card('Documento liberado ao cliente',
                        '<p class="good">PDF publicado, disponível para baixar no portal do cliente. Versão '+esc(publicado['versao'])+'.</p>'
                        +f'<form method="post" action="{url_os(banco, oid)}/publicar">{token}<button class="secondary" type="submit">Publicar nova versão do relatório</button></form>')
                elif publicado:
                    corpo+=card('Documento anterior',
                        f'<p class="muted">Existe uma versão anterior (v{esc(publicado["versao"])}), '
                        'mas o PDF só fica disponível após o encerramento da OS.</p>')
                elif d['status'] in fluxo.FIM:
                    corpo+=card('Documento pendente de publicação',
                        f'<p class="warn">A OS está encerrada, mas o PDF ainda não foi publicado.</p><form method="post" action="{url_os(banco, oid)}/publicar">{token}<button>Gerar e publicar PDF</button></form>')
                if d['status'] in ext.ATIVAS:
                    if app:
                        docs=('<p class="muted">Use o botão <b>Baixar preview do PDF</b> na ficha '
                              'da OS. A prévia não publica, não envia e-mail e não altera o status.</p>')
                    else:
                        docs=(botao('Baixar preview do PDF (não publicado)',
                                    f'{url_os(banco, oid)}/pdf-preview','secondary')
                              + '<p class="muted">Prévia para conferência do relatório atual. '
                                'Não publica o PDF, não envia e-mail e não altera o status da OS.</p>')
                elif publicado:
                    docs=(botao('Baixar PDF publicado',f'{url_os(banco, oid)}/pdf')
                        +botao('Preparar e-mail + PDF (.eml)',f'{url_os(banco, oid)}/email'))
                    if d['status']=='Concluída':
                        docs+=botao('Preparar nota fiscal (.json)',f'{url_os(banco, oid)}/nota')
                    if responsavel==s['pid'] or cad9.prestador_admin(banco,s['pid']):
                        contatos=(contatos_os or {})
                        with ext.db(banco) as c:
                            registro_email=c.execute(
                                'SELECT destinatarios_json FROM produtividade_email WHERE os_id=?',
                                (oid,)).fetchone()
                        anteriores=[]
                        if registro_email and registro_email['destinatarios_json']:
                            try: anteriores=json.loads(registro_email['destinatarios_json'])
                            except Exception: anteriores=[]
                        if not anteriores:
                            anteriores=[contatos.get(k,'') for k in ('cliente','sindico') if contatos.get(k)]
                        from officina.core import os_effect_outbox as effect_outbox
                        with ext.db(banco) as c:
                            outbox_ready=effect_outbox.installed(c)
                            outbox_status=c.execute('''SELECT state,attempts,last_error,result_json
                                FROM os_effect_outbox WHERE os_id=? AND effect_type='email'
                                ORDER BY id DESC LIMIT 1''',(oid,)).fetchone() if outbox_ready else None
                        opcoes_reenvio=''
                        for chave,rotulo in (('cliente','Cliente'),('sindico','Síndico'),
                                             ('administradora','Administradora / imobiliária')):
                            email=contatos.get(chave) or ''
                            if email:
                                marcado=' checked' if (chave in anteriores or email in anteriores) else ''
                                opcoes_reenvio+=(
                                    '<label style="display:block;margin:5px 0">'
                                    f'<input type="checkbox" name="destinatario_sel[]" '
                                    f'value="{chave}"{marcado}> {rotulo}: {esc(email)}</label>')
                        docs+=(f'<form method="post" action="{url_os(banco, oid)}/reenviar-email" '
                               'style="display:block;margin-top:12px">'
                               f'{token}'
                               '<h3>Reenviar e-mail</h3>'
                               f'<input type="hidden" name="reenviar_operacao" value="{secrets.token_urlsafe(24)}">'
                               +opcoes_reenvio+
                               '<label style="display:block;margin:8px 0">'
                               '<input type="checkbox" name="confirmar_duplicata" value="1" required> '
                               'O e-mail anterior pode já ter sido entregue; reenviar pode duplicar'
                               '</label>'
                               '<button class="secondary" type="submit">Reenviar e-mail com anexos</button>'
                               '</form>'
                               '<p class="muted">Desmarque quem não deve receber. O reenvio inclui '
                               'o PDF do relatório e a NFS-e mais recente.</p>')
                        if outbox_status:
                            state=dict(outbox_status)
                            payload=json.loads(state['result_json'] or '{}')
                            docs+=(f'<p class="muted">Envio: {esc(state["state"])} · '
                                   f'Tentativas: {int(state["attempts"])} · '
                                   f'Erro: {esc(state["last_error"] or "—")} · '
                                   f'Message-ID: {esc(payload.get("provider_message_id") or "—")}</p>')
                            if state['state']=='unknown':
                                docs+=('<p class="muted">Resultado incerto: confira no provedor. '
                                       'Não há reenvio automático; uma nova tentativa pode duplicar.</p>')
                        if outbox_ready:
                            docs+=('<p class="muted">No modo recuperável, use apenas contatos '
                                   'cadastrados; e-mails avulsos precisam ser cadastrados no cliente.</p>')
                        else:
                            docs+=('<p class="muted">Reenvio indisponível: outbox DEV não instalada.</p>')
                elif d['status'] in fluxo.FIM:
                    docs='<p class="muted">O PDF ainda não foi publicado. Use “Gerar e publicar PDF” acima.</p>'
                else:
                    docs='<p class="muted">O PDF e o rascunho de e-mail serão liberados após a conclusão/cancelamento e publicação do relatório.</p>'
                itens_notas=''
                for nota in notas_fiscais:
                    itens_notas+=(f'<p><b>{esc(nota["nome_original"])}</b> '
                                  f'<a href="{url_os(banco, oid)}/nota-fiscal/{nota["id"]}/preview" target="_blank" '
                                  'rel="noopener">Visualizar</a> · '
                                  f'<a href="{url_os(banco, oid)}/nota-fiscal/{nota["id"]}">Baixar</a>'
                                  f' <small>{esc(nota["criado_em"])}</small></p>')
                if not itens_notas:
                    itens_notas='<p class="muted">Nenhuma nota fiscal anexada.</p>'
                else:
                    rotulo_nf=('PDF anexado' if len(notas_fiscais)==1
                               else f'{len(notas_fiscais)} PDFs anexados')
                    itens_notas=f'<p class="good">{rotulo_nf}</p>'+itens_notas
                upload_nf=''
                if (responsavel==s['pid'] or cad9.prestador_admin(banco,s['pid'])) and (not app or d['status'] not in ext.ATIVAS) and not arquivada:
                    upload_nf=(f'<form id="form-nota-fiscal-upload" method="post" action="{url_os(banco, oid)}/nota-fiscal" '
                               'enctype="multipart/form-data" style="margin-top:10px">'
                               f'{token}'
                               '<label for="nota-fiscal-concluida">Anexar / atualizar nota fiscal (PDF, até 20 MB)</label>'
                               '<input type="file" id="nota-fiscal-concluida" name="nota_fiscal" '
                               'accept="application/pdf" required data-auto-upload-nf '
                               f'data-upload-url="{url_os(banco, oid)}/nota-fiscal">'
                               '<p class="muted" id="nota-fiscal-concluida-status" data-nf-status>'
                               'O PDF será anexado automaticamente ao escolher o arquivo.</p>'
                               '<noscript><button type="submit" class="secondary">Enviar PDF</button></noscript></form>')
                corpo+=card('Notas fiscais da OS',
                            itens_notas +
                            '<p class="muted">A nota fiscal anexada é enviada junto ao relatório no e-mail de conclusão e em cada reenvio. '
                            'O arquivo fica armazenado no servidor e só é liberado para usuários autorizados.</p>'
                            +upload_nf)
                corpo+=card('Documentos e relatórios',docs+'<p class="muted">O e-mail é enviado automaticamente na conclusão ou na pendência. A nota fiscal é anexada ao e-mail quando cadastrada.</p>')
                def _evento_html(e):
                    quando=data_hora_br(e['criado_em']) if app else e['criado_em']
                    return ('<div class="card"><small>'+esc(quando)+' · '+esc(e['ator'])+'</small>'
                            +'<p><b>'+esc(e['acao'])+'</b> — '+esc(e['descricao'])+'</p></div>')
                if app:
                    recentes_ev=eventos[:6]
                    restantes=eventos[6:]
                    historico=''.join(_evento_html(e) for e in recentes_ev) or '<p>Nenhum evento.</p>'
                    if restantes:
                        historico+=('<details><summary>Ver todos os '+str(len(eventos))+' eventos</summary>'
                                    +''.join(_evento_html(e) for e in restantes)+'</details>')
                    corpo+=card('Histórico',historico)
                    return self.pagina(titulo,corpo+'</aside></div>',s)
                corpo+=card('Histórico permanente', ''.join(_evento_html(e) for e in eventos) or '<p>Nenhum evento.</p>')
                return self.pagina(titulo,card('Dados e execução da OS',corpo),s)

            def financeiro(self,s):
                pessoal=prod.financeiro_pessoal(banco,s['pid'])
                token=self.hidden(s)
                banco_texto=prod.obter_dados_bancarios(banco,s['pid'])
                with ext.db(banco) as c:
                    linha_email=c.execute('SELECT email FROM prestadores WHERE id=?',
                                          (s['pid'],)).fetchone()
                email_prestador=linha_email['email'] if linha_email else ''
                hoje=time.strftime('%Y-%m-%d')

                def _item_finalizador(x):
                    bruto=float(x['valor'] or 0)
                    repasses=float(x['partes_centavos'] or 0)/100
                    meu=bruto-repasses
                    recebido=x['status']=='Recebido'
                    vencimento=str(x.get('vencimento') or '')[:10]
                    atrasado=bool(vencimento and vencimento<hoje and not recebido)
                    detalhe=(f'Bruto {dinheiro(bruto)} · Repasses {dinheiro(repasses)} · '
                             f'{x.get("forma_pagamento") or "—"} · venc. {data_curta(vencimento) or "—"}')
                    if recebido:
                        acao=''
                    else:
                        prazo=(f'<form method="post" action="/financeiro/{int(x["financeiro_id"])}/vencimento" class="prazo">'
                               f'{token}<label>Vencimento <input type="date" name="vencimento" value="{esc(vencimento)}"></label>'
                               '<button type="submit">Salvar prazo</button></form>')
                        acao=(prazo
                              +f'<form method="post" action="/financeiro/{int(x["financeiro_id"])}/receber" '
                              'data-confirm-receber="Confirma que o valor foi realmente recebido?">'
                              f'{token}<button type="submit">Confirmar recebimento</button></form>'
                              f'<form method="post" action="/financeiro/{int(x["financeiro_id"])}/cancelar" '
                              'data-confirm="Cancelar este pagamento? Ele deixará de ser contabilizado.">'
                              f'{token}<button type="submit" class="danger">Cancelar pagamento</button></form>')
                    return {'tipo':'Finalizei','os_id':x['os_id'],'numero_os':x['numero_os'],
                            'cliente':x.get('cliente') or '','meu':meu,
                            'status':'Atrasado' if atrasado else ('Recebido' if recebido else 'A receber'),
                            'status_classe':'good' if recebido else 'bad',
                            'detalhe':detalhe,'acao':acao,'recebido':recebido}

                def _item_secundario(x):
                    valor=float(x['valor_centavos'] or 0)/100
                    pago=float(x['pago_centavos'] or 0)/100
                    enviado=float(x['enviado_centavos'] or 0)/100
                    recebido=pago>=valor-0.009
                    cliente_recebido=str(x.get('financeiro_status') or '')=='Recebido'
                    if recebido:
                        status='Recebido'
                        detalhe=f'Repasse · confirmado em {x.get("confirmado_em") or "—"}'
                        acao=''
                    else:
                        status='A receber'
                        pendente=max(0,enviado-pago)
                        if not cliente_recebido:
                            detalhe=('Repasse · aguardando o finalizador confirmar '
                                     'o recebimento do cliente')
                            acao='<span class="warn">Aguardando cliente</span>'
                        elif pendente>0:
                            detalhe=f'Repasse · {dinheiro(pago)} confirmado · {dinheiro(pendente)} aguardando você'
                            acao=(f'<form method="post" action="/financeiro/repasse/confirmar">{token}'
                                  f'<input type="hidden" name="os_id" value="{int(x["os_id"])}">'
                                  '<button type="submit">Confirmar que recebi</button></form>')
                        elif enviado<=0:
                            detalhe='Repasse · aguardando envio do finalizador'
                            acao='<span class="warn">Aguardando envio</span>'
                        else:
                            detalhe='Repasse · aguardando confirmação'
                            acao='<span class="warn">Aguardando confirmação</span>'
                    return {'tipo':'Secundário','os_id':x['os_id'],'numero_os':x['numero_os'],
                            'cliente':x.get('cliente') or '','meu':valor,
                            'status':status,'status_classe':'good' if recebido else 'bad',
                            'detalhe':detalhe,'acao':acao,'recebido':recebido}

                lancamentos=[_item_finalizador(x) for x in pessoal['brutos_proprios']]
                lancamentos+=[_item_secundario(x) for x in pessoal['receber_de_colegas']]
                # OS de garantia/cortesia sem parcela própria não poluem a lista.
                lancamentos=[x for x in lancamentos if x['meu']>0.009]
                a_receber=[x for x in lancamentos if not x['recebido']]
                recebidos=[x for x in lancamentos if x['recebido']]
                try:
                    emprestimos_a_receber=maf_loans.loan_receivables(s['pid'],email_prestador)
                except Exception:
                    LOG.exception('Falha ao carregar empréstimos a receber (MAF)')
                    emprestimos_a_receber=[]
                try:
                    emprestimos_recebidos=maf_loans.loan_payables(s['pid'],email_prestador)
                except Exception:
                    LOG.exception('Falha ao carregar empréstimos recebidos (MAF)')
                    emprestimos_recebidos=[]
                for emprestimo in emprestimos_a_receber:
                    pendente=float(emprestimo['pendente'] or 0)/100
                    detalhe=('Empréstimo pessoal · comprovante de devolução aguardando sua análise'
                             if pendente>0 else
                             'Empréstimo pessoal a receber · não entra no caixa da empresa')
                    a_receber.append({
                        'tipo':'Empréstimo MAF','os_id':None,
                        'numero_os':f'Empréstimo #{emprestimo["id"]}',
                        'cliente':emprestimo.get('devedor_email') or '',
                        'meu':float(emprestimo['restante'] or 0)/100,
                        'status':'A receber','status_classe':'bad',
                        'detalhe':detalhe,
                        'acao':botao('Analisar comprovante' if pendente>0 else 'Abrir',
                                     f'/financeiro/maf-emprestimo/{int(emprestimo["id"])}',
                                     'secondary'),
                        'recebido':False})
                for emprestimo in emprestimos_recebidos:
                    recebidos.append({
                        'tipo':'Empréstimo MAF','os_id':None,
                        'numero_os':f'Empréstimo #{emprestimo["id"]}',
                        'cliente':emprestimo.get('credor_email') or '',
                        'meu':float(emprestimo['restante'] or 0)/100,
                        'status':'Recebido','status_classe':'good',
                        'detalhe':('Empréstimo pessoal recebido · saldo em aberto; '
                                   'não é receita da empresa'),
                        'acao':botao('Abrir',
                                     f'/financeiro/maf-emprestimo/{int(emprestimo["id"])}',
                                     'secondary'),
                        'recebido':True})

                def _item_html(item):
                    if item.get('os_id'):
                        identificacao=(f'<a class="finance-item-os" '
                                       f'href="{url_os(banco, item["os_id"])}">'
                                       f'{esc(item["numero_os"])}</a>')
                    else:
                        identificacao=(f'<span class="finance-item-os">'
                                       f'{esc(item["numero_os"])}</span>')
                    return ('<article class="finance-item">'
                            '<div class="finance-item-top">'
                            +identificacao+
                            f'<span class="finance-item-type">{esc(item["tipo"])}</span>'
                            '</div>'
                            f'<p class="finance-item-client">{esc(item["cliente"])}</p>'
                            '<div class="finance-item-values"><span>Minha parcela</span>'
                            f'<strong>{dinheiro(item["meu"])}</strong></div>'
                            f'<p class="finance-item-detail">{esc(item["detalhe"])}</p>'
                            f'<div class="finance-item-foot"><span class="tag {esc(item.get("status_classe") or "")}">{esc(item["status"])}</span>'
                            f'{item["acao"]}</div></article>')

                def _coluna(titulo,itens,vazio,acao=''):
                    conteudo=''.join(_item_html(x) for x in itens) or f'<p class="muted">{vazio}</p>'
                    cabecalho=(f'<div class="panel-head"><h2>{esc(titulo)}</h2>{acao}</div>'
                               if acao else f'<h2>{esc(titulo)}</h2>')
                    return (f'<section class="card finance-col">{cabecalho}'
                            f'<div class="finance-list">{conteudo}</div></section>')

                emprestar=('<button type="button" class="secondary" '
                           'data-fin-target="emprestimos" data-abrir-emprestimo="1">'
                           'Emprestar</button>')
                banco_card=card('Dados bancários e cadastrais para cobrança',
                    f'<form method="post" action="/financeiro/banco/salvar">{token}'
                    +textarea('Dados bancários e cadastrais (texto livre)','dados_bancarios',banco_texto,rows=5)
                    +'<button type="submit">Salvar meus dados bancários</button></form>'
                    +'<p class="muted">Este é o mesmo campo do app GTK e o usado no e-mail de cobrança. '
                    +'O que você salvar aqui vale para os dois.</p>')
                repasses=[]
                for item in pessoal['repassar_a_colegas']:
                    confirmado=item['pago_centavos']
                    enviado=item['enviado_centavos']
                    a_enviar=item['valor_centavos']-confirmado-enviado
                    if a_enviar>0:
                        acao=(f'<form method="post" action="/financeiro/repasse">{token}'
                              +f'<input type="hidden" name="os_id" value="{int(item["os_id"])}">'
                              +f'<input type="hidden" name="secundario_id" value="{int(item["tecnico_id"])}">'
                              +f'<button type="submit">Registrar envio de {dinheiro(a_enviar/100)}</button></form>')
                    elif enviado>confirmado:
                        acao='<span class="warn">Aguardando confirmação do colega</span>'
                    else:
                        acao='<span class="good">Confirmado pelo colega</span>'
                    repasses.append((f'<a href="{url_os(banco, item["os_id"])}">{esc(item["numero_os"])}</a>',
                                     esc(item['tecnico']),
                                     dinheiro(item['valor_centavos']/100),
                                     dinheiro(confirmado/100),dinheiro(enviado/100),
                                     dinheiro(a_enviar/100),acao))
                repasses_card=card('Repasses a outros técnicos',
                    '<p class="muted">Os repasses aparecem aqui depois que você confirma o '
                    'recebimento do cliente. O valor da parcela já foi definido no rateio; '
                    'registre o envio e o colega confirma na coluna A receber do financeiro dele.</p>'
                    +tabela(['OS','Colega','Parcela','Confirmado','Aguardando confirmação',
                             'A enviar','Ação'],repasses))
                caixa_card=''
                if s.get('admin'):
                    try:
                        resumo_caixa=empresa.resumo(banco)
                        linhas_caixa=[]
                        for item in empresa.listar(banco)[:8]:
                            pessoa=' · '.join(str(x) for x in
                                              (item.get('prestador_nome'),
                                               item.get('numero_os')) if x)
                            linhas_caixa.append((
                                item['data'],
                                empresa.TIPOS.get(item['tipo'],item['tipo']),
                                esc(pessoa or '—'),esc(item['descricao']),
                                dinheiro(item['valor_centavos']/100)))
                        caixa_card=card('Caixa da empresa',
                            '<p class="muted">Controle financeiro da empresa. Empréstimos '
                            'pessoais entre prestadores não entram neste caixa.</p>'
                            +'<div class="kpis">'
                            +f'<div class="kpi"><span>Capital</span><strong>{dinheiro(resumo_caixa["aportes_centavos"]/100)}</strong></div>'
                            +f'<div class="kpi"><span>Despesas</span><strong>{dinheiro(resumo_caixa["despesas_centavos"]/100)}</strong></div>'
                            +f'<div class="kpi"><span>Saldo do controle</span><strong>{dinheiro(resumo_caixa["saldo_centavos"]/100)}</strong></div>'
                            +'</div>'
                            +tabela(['Data','Tipo','Pessoa / OS','Descrição','Valor'],linhas_caixa)
                            +botao('Abrir caixa completo','/caixa','secondary'))
                    except Exception:
                        LOG.exception('Falha ao carregar o caixa da empresa no financeiro')
                a_receber_total=0.0
                recebido_total=0.0
                for item in pessoal['brutos_proprios']:
                    parte=float(item['valor'] or 0)-item['partes_centavos']/100
                    if item['status']=='Recebido':
                        recebido_total+=parte
                    elif item['status']=='Aguardando pagamento':
                        a_receber_total+=parte
                for item in pessoal['receber_de_colegas']:
                    recebido_total+=item['pago_centavos']/100
                    a_receber_total+=(item['valor_centavos']-item['pago_centavos'])/100
                for item in emprestimos_a_receber:
                    a_receber_total+=float(item['restante'] or 0)/100
                for item in emprestimos_recebidos:
                    recebido_total+=float(item['restante'] or 0)/100
                a_receber_total=round(a_receber_total,2)
                recebido_total=round(recebido_total,2)
                if self.ui_app():
                    rotulo_a='A receber';rotulo_r='Recebido'
                    cabecalho=f'<div class="finance-head"><p class="page-meta">{esc(s["nome"])} · produção própria</p></div>'
                else:
                    rotulo_a='A receber (minha produção)';rotulo_r='Recebido (minha produção)'
                    cabecalho=''
                try:
                    with ext.db(banco) as c:
                        linha_email=c.execute('SELECT email FROM prestadores WHERE id=?',
                                              (s['pid'],)).fetchone()
                    email_prestador=linha_email['email'] if linha_email else ''
                    maf_card=maf_loans.render_card(s['pid'],email_prestador,s['csrf'])
                except Exception:
                    LOG.exception('Falha ao carregar empréstimos entre prestadores (MAF)')
                    maf_card=''
                def _tab(chave,rotulo,icone_nome,ativo=False):
                    return (f'<button type="button" class="os-tab{" active" if ativo else ""}" '
                            f'data-fin-tab="{chave}" role="tab" '
                            f'aria-selected="{"true" if ativo else "false"}" '
                            f'aria-controls="fin-panel-{chave}">'
                            f'<span class="tab-icon">{icone(icone_nome)}</span>'
                            f'<span>{esc(rotulo)}</span></button>')
                def _painel(chave,conteudo,ativo=False):
                    oculto='' if ativo else ' hidden'
                    return (f'<section class="finance-panel" id="fin-panel-{chave}" '
                            f'data-fin-panel="{chave}" role="tabpanel"{oculto}>'
                            f'{conteudo}</section>')
                tabs=('<div class="os-tabs finance-tabs" role="tablist" '
                      'aria-label="Seções do financeiro">'
                      +_tab('resumo','Resumo','home',True)
                      +_tab('financas-pessoais','Finanças pessoais','wallet')
                      +_tab('a-receber','A receber','wallet')
                      +_tab('recebidos','Recebidos','check')
                      +_tab('repasses','Repasses','users')
                      +_tab('emprestimos','Empréstimos','receipt')
                      +( _tab('caixa','Caixa da empresa','receipt') if caixa_card else '')
                      +'</div>')
                resumo_painel=(
                    f'<div class="kpis"><div class="kpi"><span>{rotulo_a}</span>'
                    +f'<strong id="kpi-a-receber">{dinheiro(a_receber_total)}</strong></div>'
                    +f'<div class="kpi"><span>{rotulo_r}</span>'
                    +f'<strong id="kpi-recebido">{dinheiro(recebido_total)}</strong></div></div>'
                    +'<p class="notice">A forma de pagamento PIX não comprova recebimento. '
                    'Use “Confirmar recebimento” apenas após verificar o pagamento.</p>'
                    +'<p class="muted">A lista mostra a sua parcela nas OS em que você participou, '
                    'como finalizador ou técnico secundário. O valor bruto e os repasses aparecem no detalhe de cada item.</p>')
                financas_pessoais_painel=(banco_card
                    +'<p class="muted">Os dados bancários valem para o site e para o app GTK; '
                    'eles aparecem apenas em cobranças com valor maior que zero.</p>')
                a_receber_painel=_coluna('A receber / Confirmar recebimento',a_receber,
                                         'Nenhum lançamento a receber.',emprestar)
                recebidos_painel=_coluna('Recebidos',recebidos,'Nenhum lançamento recebido.')
                corpo=(cabecalho
                    +'<div class="finance-tools">'
                    +'<button type="button" class="secondary" id="fin-mask-toggle" '
                    +'aria-pressed="false">Ocultar valores</button></div>'
                    +'<div class="finance-shell" id="finance-shell">'
                    +tabs
                    +_painel('resumo',resumo_painel,True)
                    +_painel('financas-pessoais',financas_pessoais_painel)
                    +_painel('a-receber',a_receber_painel)
                    +_painel('recebidos',recebidos_painel)
                    +_painel('repasses',repasses_card)
                    +_painel('emprestimos',maf_card)
                    +(_painel('caixa',caixa_card) if caixa_card else '')
                    +'</div>')
                return self.pagina('Financeiro',corpo,s)

            def relatorios(self,s,tipo='relatorios'):
                oses=ordens_repo.listar_relatorios(banco)
                if tipo=='emails':
                    title='E-mails para clientes'; explanation='Gere um rascunho .eml com o PDF anexado. Nenhum e-mail será enviado automaticamente.'
                    acao=lambda o:(botao('Preparar .eml',f'{url_os(banco, o["id"])}/email')
                                   if o['status'] in fluxo.FIM else
                                   '<span class="muted">Após encerrar</span>')
                elif tipo=='notas':
                    title='Notas fiscais'; explanation='Rascunho JSON para futura integração NFS-e. Este arquivo NÃO é documento fiscal válido.'
                    acao=lambda o:(botao('Preparar rascunho JSON',f'{url_os(banco, o["id"])}/nota')
                                   if o['status'] in fluxo.FIM else
                                   '<span class="muted">Após encerrar</span>')
                else:
                    title='Relatórios gerais e PDFs'; explanation='Histórico das OS e relatórios individuais com materiais, atividades e anexos.'
                    acao=lambda o:(botao('Baixar PDF',f'{url_os(banco, o["id"])}/pdf')
                                   if o['status'] in fluxo.FIM else
                                   (botao('Preview PDF',f'{url_os(banco, o["id"])}/pdf-preview','secondary')
                                    if o['status'] in ext.ATIVAS else
                                    '<span class="muted">Após encerrar</span>'))
                rows=[(f'<a href="{url_os(banco, r["id"])}">{esc(r["numero_os"])}</a>',esc(r['cliente']),esc(r['status']),dinheiro(r['valor_total']),acao(r)) for r in oses]
                resumo=(f'<div class="kpis"><div class="kpi"><span>Ordens de serviço</span><strong>{len(oses)}</strong></div>'
                        f'<div class="kpi"><span>Total exibido</span><strong>{dinheiro(sum(float(x["valor_total"] or 0) for x in oses))}</strong></div></div>') if tipo=='relatorios' else ''
                return self.pagina(title,f'<p class="muted">{esc(explanation)}</p>{resumo}'+card('Ordens disponíveis',tabela(['OS','Cliente','Status','Valor','Ação'],rows)),s)

            def prestadores_admin(self,s):
                if not s.get('admin'):
                    raise PermissionError('Somente administradores podem gerenciar prestadores.')
                pessoas=ext.listar_todos(banco)
                admins=cad9.listar_admins(banco)
                linhas=[]
                for p in pessoas:
                    pid=int(p['id'])
                    admin=pid in admins
                    acoes=(f'<form method="post" action="/prestadores/{pid}/admin" style="display:inline">'
                           f'{self.hidden(s)}<button class="secondary">'
                           f'{"Remover admin" if admin else "Tornar admin"}</button></form> '
                           f'<form method="post" action="/prestadores/{pid}/alternar" style="display:inline">'
                           f'{self.hidden(s)}<button class="secondary">'
                           f'{"Desativar" if p["ativo"] else "Ativar"}</button></form> '
                           f'<form method="post" action="/prestadores/{pid}/senha" style="display:inline">'
                           f'{self.hidden(s)}<input type="password" name="senha" minlength="10" '
                           f'placeholder="Nova senha" style="width:130px;display:inline-block">'
                           '<button class="secondary">Trocar senha</button></form> '
                           f'<form method="post" action="/prestadores/{pid}/arquivar" style="display:inline" '
                           'data-confirm="Arquivar este prestador e bloquear o login?">'
                           f'{self.hidden(s)}<button class="danger">Arquivar</button></form>')
                    linhas.append((pid,esc(p['nome']),esc(p['email']),esc(p['especialidade'] or ''),
                                   'Sim' if p['ativo'] else 'Não','Sim' if admin else 'Não',acoes))
                form=(f'<form method="post" action="/prestadores/novo">{self.hidden(s)}'
                      +campos_escuros('Nome','nome',required=True)
                      +campos_escuros('E-mail (login)','email',kind='email',required=True)
                      +campos_escuros('Telefone','telefone')
                      +campos_escuros('CNPJ do prestador','documento')
                      +campos_escuros('Especialidade','especialidade')
                      +campos_escuros('Senha inicial','senha',kind='password',required=True)
                      +'<button>Cadastrar prestador</button></form>')
                return self.pagina('Prestadores',
                    card('Novo prestador',form)
                    +card('Prestadores',tabela(
                        ['ID','Nome','E-mail','Especialidade','Ativo','Admin','Ações'],linhas)),s)

            def estoque_admin(self,s):
                if not s.get('admin'):
                    raise PermissionError('Somente administradores podem gerenciar o estoque.')
                itens=estoque.listar(banco)
                linhas=[]
                for item in itens:
                    linhas.append((item['id'],esc(item['nome']),esc(item['sku'] or ''),
                                   esc(item['unidade'] or ''),item['saldo'],item['minimo'],
                                   dinheiro(item['venda_centavos']/100),
                                   botao('Abrir',f'/estoque/{item["id"]}','secondary')))
                return self.pagina('Estoque',
                    card('Novo material',botao('Cadastrar material','/estoque/novo',''))
                    +card('Materiais',tabela(
                        ['ID','Material','Código','Unidade','Saldo','Mínimo','Venda','Ação'],
                        linhas)),s)

            def estoque_item(self,s,produto_id=None):
                if not s.get('admin'):
                    raise PermissionError('Somente administradores podem gerenciar o estoque.')
                item=None
                if produto_id is not None:
                    item=next((x for x in estoque.listar(banco)
                               if int(x['id'])==int(produto_id)),None)
                    if item is None:
                        raise ValueError('Material não encontrado.')
                dados=item or {'nome':'','sku':'','unidade':'un','custo_centavos':0,
                               'venda_centavos':0,'minimo':0}
                form=(f'<form method="post" action="/estoque/salvar">{self.hidden(s)}'
                      +(f'<input type="hidden" name="id" value="{int(produto_id)}">'
                        if produto_id is not None else '')
                      +campos_escuros('Nome','nome',dados['nome'],required=True)
                      +campos_escuros('Código / SKU','sku',dados['sku'] or '')
                      +campos_escuros('Unidade','unidade',dados['unidade'] or 'un')
                      +campos_escuros('Custo (R$)','custo',
                                      dinheiro((dados['custo_centavos'] or 0)/100))
                      +campos_escuros('Venda (R$)','venda',
                                      dinheiro((dados['venda_centavos'] or 0)/100))
                      +campos_escuros('Estoque mínimo','minimo',
                                      str(dados['minimo'] or 0))
                      +'<button>Salvar material</button></form>')
                extra=''
                if produto_id is not None:
                    ajuste=(f'<form method="post" action="/estoque/{int(produto_id)}/ajuste">'
                            f'{self.hidden(s)}'
                            +campos_escuros('Quantidade com sinal','delta','+1',required=True)
                            +campos_escuros('Motivo','motivo',required=True)
                            +'<button>Registrar ajuste</button></form>')
                    movs=estoque.movimentos(banco,int(produto_id),200)
                    linhas=[(m['criado_em'],m['nome'],f'{m["delta"]:+g}',m['tipo'],
                             m['os_id'] or '—',m['motivo']) for m in movs]
                    extra=(card('Ajustar saldo',ajuste)
                           +card('Movimentações',tabela(
                               ['Data','Material','Delta','Tipo','OS','Motivo'],linhas)))
                    excluir=(f'<form method="post" action="/estoque/{int(produto_id)}/excluir" '
                             'data-confirm="Excluir ou arquivar este material?">'
                             f'{self.hidden(s)}<button class="danger">Excluir material</button></form>')
                    extra+=card('Excluir',excluir)
                return self.pagina('Material de estoque',
                    card('Material',form)+extra
                    +botao('Voltar ao estoque','/estoque','secondary'),s)

            def caixa_admin(self,s):
                if not s.get('admin'):
                    raise PermissionError('Somente administradores podem acessar o caixa da empresa.')
                resumo=empresa.resumo(banco)
                movimentos=empresa.listar(banco)
                prestadores=ext.listar_todos(banco)
                oses=ordens_repo.listar_relatorios(banco,limite=300)
                linhas=[]
                for item in movimentos:
                    pessoa=' · '.join(str(x) for x in
                                      (item.get('prestador_nome'),item.get('numero_os')) if x)
                    linhas.append((item['id'],item['data'],
                                   empresa.TIPOS.get(item['tipo'],item['tipo']),
                                   esc(pessoa or '—'),esc(item['descricao']),
                                   dinheiro(item['valor_centavos']/100),
                                   f'<form method="post" action="/caixa/movimentos/{item["id"]}/arquivar" '
                                   'data-confirm="Arquivar este lançamento?">'
                                   f'{self.hidden(s)}<button class="danger">Arquivar</button></form>'))
                tipos=[(codigo,rotulo) for codigo,rotulo in empresa.TIPOS.items()]
                form=(f'<form method="post" action="/caixa/movimentos">{self.hidden(s)}'
                      +select('Tipo','tipo',tipos)
                      +campos_escuros('Data','data',datetime.now().strftime('%d/%m/%Y'))
                      +campos_escuros('Descrição','descricao',required=True)
                      +campos_escuros('Valor (R$)','valor',required=True)
                      +select('Investidor / pago por','prestador_id',
                              [('','Nenhum')]+[(str(p['id']),p['nome']) for p in prestadores])
                      +select('OS vinculada (opcional)','os_id',
                              [('','Nenhuma')]+[(str(o['id']),o['numero_os']) for o in oses])
                      +campos_escuros('Categoria','categoria')
                      +campos_escuros('Finalidade do aporte','finalidade')
                      +textarea('Observação','observacao','',3)
                      +'<button>Registrar lançamento</button></form>')
                resumo_card=card('Resumo',f'<p>Capital: <b>{dinheiro(resumo["aportes_centavos"]/100)}</b> · '
                                 f'Despesas: <b>{dinheiro(resumo["despesas_centavos"]/100)}</b> · '
                                 f'Saldo do controle: <b>{dinheiro(resumo["saldo_centavos"]/100)}</b></p>')
                return self.pagina('Caixa da empresa',
                    resumo_card+card('Novo lançamento',form)
                    +card('Lançamentos',tabela(
                        ['ID','Data','Tipo','Pessoa / OS','Descrição','Valor','Ação'],
                        linhas)),s)

            def _composicao_config(self):
                try:
                    return composicao.carregar()
                except (ValueError,OSError):
                    return {'versao':1,'componentes':[],
                            'bases_percentuais':{'total':{'nome':'Total da OS'}},
                            'base_percentuais_padrao':'total'}

            def _composicao_valor_texto(self,componente):
                modo=componente.get('modo','')
                if modo=='percentual':
                    return f"{float(componente.get('valor',0) or 0):g}"
                if modo in ('fixo','hora'):
                    return dinheiro((componente.get('valor',0) or 0)/100).replace('R$','').strip()
                return ''

            def composicao_admin(self,s):
                if not s.get('admin'):
                    raise PermissionError('Somente administradores podem editar a composição.')
                config=self._composicao_config()
                componentes=sorted(config.get('componentes',[]),
                                   key=lambda c:(c.get('ordem',0),c.get('id','')))
                linhas=[]
                for i,c in enumerate(componentes):
                    cid=esc(str(c.get('id','')))
                    acoes=(f'<a class="btn secondary" href="/composicao/{cid}/editar">Editar</a> '
                           f'<form method="post" action="/composicao/{cid}/alternar" style="display:inline">'
                           f'{self.hidden(s)}<button class="secondary">'
                           f'{"Desativar" if c.get("ativo",True) else "Ativar"}</button></form> '
                           f'<form method="post" action="/composicao/{cid}/mover" style="display:inline">'
                           f'{self.hidden(s)}<input type="hidden" name="direcao" value="up">'
                           '<button class="secondary" title="Subir">↑</button></form> '
                           f'<form method="post" action="/composicao/{cid}/mover" style="display:inline">'
                           f'{self.hidden(s)}<input type="hidden" name="direcao" value="down">'
                           '<button class="secondary" title="Descer">↓</button></form> '
                           f'<form method="post" action="/composicao/{cid}/excluir" style="display:inline" '
                           'data-confirm="Excluir este componente da composição?">'
                           f'{self.hidden(s)}<button class="danger">Excluir</button></form>')
                    linhas.append((c.get('ordem',i+1),esc(c.get('nome','')),
                                   composicao.MODOS.get(c.get('modo',''),c.get('modo','')),
                                   esc(self._composicao_valor_texto(c)) or '—',
                                   'Sim' if c.get('ativo',True) else 'Não',
                                   'Sim' if c.get('obrigatorio') else 'Não',
                                   esc(', '.join(c.get('aplicavel_a') or [])) or 'Todos',
                                   acoes))
                bases=config.get('bases_percentuais') or {}
                linhas_bases=''
                for chave,base in bases.items():
                    cobertura=str(base.get('cobertura') or 'separado')
                    linhas_bases+=(
                        '<div class="col2">'
                        f'<input type="hidden" name="base_chave[]" value="{esc(chave)}">'
                        +campos_escuros('Nome','base_nome[]',base.get('nome') or chave)
                        +select('Cobertura','base_cobertura[]',
                                [('separado','Separado'),('incluido','Incluído')],cobertura)
                        +campos_escuros('Componente','base_componente[]',base.get('componente') or '')
                        +campos_escuros('Campo','base_campo[]',base.get('campo') or '')
                        +'</div>')
                padrao=str(config.get('base_percentuais_padrao') or 'total')
                form_bases=(f'<form method="post" action="/composicao/bases/salvar">'
                            +self.hidden(s)+linhas_bases
                            +select('Composição padrão da OS','base_padrao',
                                    [(chave,(base or {}).get('nome',chave))
                                     for chave,base in bases.items()],padrao)
                            +'<button class="secondary">Salvar composições</button></form>')
                recalc=(f'<form method="post" action="/composicao/recalcular">{self.hidden(s)}'
                        '<button class="secondary">Recalcular serviços e OS abertas</button></form>')
                texto=yaml.safe_dump(config,allow_unicode=True,sort_keys=False)
                avancado=(f'<details class="composicao-avancado"><summary>YAML avançado</summary>'
                          f'<form method="post" action="/composicao/yaml">{self.hidden(s)}'
                          +textarea('composicao.yaml','yaml',texto,22,True)
                          +'<button class="secondary">Salvar YAML</button></form></details>')
                return self.pagina('Composição de valores',
                    card('Componentes',
                         '<p class="muted">Cada componente é uma linha do valor final. '
                         'A soma sempre fecha com o total do serviço.</p>'
                         +f'<div class="page-actions"><a class="btn" href="/composicao/novo">Novo componente</a></div>'
                         +tabela(['Ordem','Componente','Modo','Valor','Ativo','Obrigatório',
                                  'Aplicável a','Ações'],linhas))
                    +card('Composições de valores',
                          '<p class="muted">Cada composição é uma forma de distribuir o total da OS. '
                          'Ela fica disponível na aba Situação e relatório.</p>'+form_bases)
                    +card('Manutenção',recalc+avancado),s)

            def composicao_form(self,s,identificador=None):
                if not s.get('admin'):
                    raise PermissionError('Somente administradores podem editar a composição.')
                config=self._composicao_config()
                componente=None
                if identificador:
                    componente=next((c for c in config.get('componentes',[])
                                     if str(c.get('id'))==str(identificador)),None)
                    if componente is None:
                        raise ValueError('Componente não encontrado.')
                dados=componente or {'id':'','nome':'','descricao':'','modo':'fixo',
                                     'valor':0,'formula':'','horas_padrao':0.0,
                                     'minimo_centavos':0,'aplicavel_a':[],
                                     'ativo':True,'obrigatorio':False,'ordem':''}
                identificador_atual=str(identificador or '')
                modo_atual=str(dados.get('modo') or 'fixo')
                form=(f'<form method="post" action="/composicao/salvar">{self.hidden(s)}'
                      f'<input type="hidden" name="id_atual" value="{esc(identificador_atual)}">'
                      +campos_escuros('Nome','nome',dados.get('nome',''),required=True)
                      +campos_escuros('Identificador (opcional)','id_novo',dados.get('id',''),
                                      placeholder='gerado a partir do nome')
                      +campos_escuros('Descrição','descricao',dados.get('descricao',''))
                      +select('Modo de cálculo','modo',
                              [(chave,rotulo) for chave,rotulo in composicao.MODOS.items()],
                              modo_atual,required=True)
                      +campos_escuros('Valor (R$ ou %)','valor',
                                      self._composicao_valor_texto(dados),
                                      placeholder='Ex.: 10 para 10% ou 150,00 para fixo')
                      +campos_escuros('Fórmula','formula',dados.get('formula',''),
                                      placeholder='Ex.: hora_tecnica * 0.2')
                      +campos_escuros('Horas padrão','horas_padrao',
                                      str(dados.get('horas_padrao',0) or 0))
                      +campos_escuros('Mínimo em R$ (modo hora)','minimo',
                                      dinheiro((dados.get('minimo_centavos',0) or 0)/100).replace('R$','').strip())
                      +campos_escuros('Aplicável a (serviços separados por vírgula)',
                                      'aplicavel_a',', '.join(dados.get('aplicavel_a') or []))
                      +campos_escuros('Ordem','ordem',str(dados.get('ordem','') or '')))
                form+=('<label class="foto-incluir"><input type="checkbox" name="ativo" value="1"'
                       +(' checked' if dados.get('ativo',True) else '')+'> Ativo</label>')
                form+=('<label class="foto-incluir"><input type="checkbox" name="obrigatorio" value="1"'
                       +(' checked' if dados.get('obrigatorio') else '')+'> Obrigatório</label>')
                form+='<div class="actions"><button type="submit">Salvar componente</button>'
                form+='<a class="btn secondary" href="/composicao">Cancelar</a></div></form>'
                return self.pagina('Novo componente' if not identificador else 'Editar componente',
                                   card(dados.get('nome') or 'Componente',form),s)

            def _composicao_salvar(self,config):
                composicao.salvar(config)
                composicao.recalcular_tudo(banco)

            def configuracoes(self,s):
                prefs=prestador_auth.obter_preferencias(banco,s['pid'])
                def opcao_tema(valor,rotulo,ajuda):
                    marcado=' checked' if prefs['tema']==valor else ''
                    return (f'<label class="pref-opcao"><input type="radio" name="tema" '
                            f'value="{valor}"{marcado}><span><strong>{rotulo}</strong>'
                            f'<small>{ajuda}</small></span></label>')
                temas=(opcao_tema('auto','Auto','segue o tema do sistema')
                       +opcao_tema('claro','Claro','interface clara')
                       +opcao_tema('escuro','Escuro','interface escura'))
                acentos=''
                for chave,rotulo,cor in (
                        ('ambar','Âmbar','#d8a24a'),('azul','Azul','#78aede'),
                        ('verde','Verde','#7cc7a2'),('vermelho','Vermelho','#df8a8a'),
                        ('roxo','Roxo','#b39bdf'),('ciano','Ciano','#6ec7c7'),
                        ('laranja','Laranja','#e2a06a')):
                    marcado=' checked' if prefs['acento']==chave else ''
                    acentos+=(f'<label class="pref-acento" style="--cor:{cor}">'
                              f'<input type="radio" name="acento" value="{chave}"{marcado}>'
                              f'<span class="pref-cor"></span><em>{rotulo}</em></label>')
                form=(f'<form method="post" action="/configuracoes" id="form-preferencias">'
                      +self.hidden(s)
                      +'<fieldset class="pref-grupo"><legend>Tema</legend>'
                      +f'<div class="pref-opcoes">{temas}</div></fieldset>'
                      +'<fieldset class="pref-grupo"><legend>Cor de acento</legend>'
                      +f'<div class="pref-acentos">{acentos}</div></fieldset>'
                      +'<p class="muted">Estas preferências ficam associadas à sua conta '
                       'e valem somente para o site. O aplicativo GTK tem aparência própria.</p>'
                      +'<noscript><button type="submit">Salvar preferências</button></noscript>'
                      +'</form>')
                return self.pagina('Configurações',card('Aparência do site',form),s)

            def portal_cliente(self,s):
                info=botao('Abrir Officina Web','/')
                info+=('<p class="muted">Prestadores e clientes acessam a mesma origem Officina Web. '
                       'O cliente entra por /login e acompanha os pedidos no próprio site.</p>')
                web=ordens_repo.listar_origem_portal(banco)
                registros=[(f'<a href="{url_os(banco, o["id"])}">{esc(o["numero_os"])}</a>',esc(o['status']),esc(o['data_abertura'])) for o in web]
                return self.pagina('Portal do cliente',info+card('Solicitações recebidas pelo portal',tabela(['OS','Situação','Abertura'],registros)),s)




            def _normalizar_os(self, path):
                partes = path.strip('/').split('/')
                if len(partes) >= 2 and partes[0] == 'os' and partes[1] not in ('nova', 'rapida', 'yaml'):
                    token = unquote(partes[1])
                    registro = ordens_repo.obter_por_token(banco, token)
                    if registro:
                        partes[1] = str(registro['id'])
                        return '/' + '/'.join(partes)
                return path

            def _redirecionar_os(self, path):
                partes = path.strip('/').split('/')
                if len(partes) >= 2 and partes[0] == 'os' and partes[1] not in ('nova', 'rapida', 'yaml'):
                    token = unquote(partes[1])
                    registro = ordens_repo.obter_por_token(banco, token)
                    if registro and token != str(registro['numero_os']):
                        sufixo = ('/' + '/'.join(partes[2:])) if len(partes) > 2 else ''
                        return ordens_repo.url_os(banco, token, sufixo)
                return None

            def do_OPTIONS(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                if path==api_fin.API_PREFIX or path.startswith(api_fin.API_PREFIX+'/'):
                    return api_fin.handle(self,path,banco,'OPTIONS')
                self.send_response(204)
                self.send_header('Content-Length','0')
                self.end_headers()

            def do_GET(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                if path == '/entrar':
                    return self.erro('Página não encontrada.', 404)
                from flavors.autoseg.modules.autoseg_web_navigation import (
                    canonical_client_path, retired_client_path)
                if retired_client_path(path):
                    return self.retired_route()
                alias=canonical_client_path(path)
                if alias is not None:
                    query=urlparse(self.path).query
                    return self.redirect_alias(alias+(('?' + query) if query else ''))
                # Shared public assets and diagnostics live on this one origin.
                if path == '/static/cliente_whatsapp.js':
                    asset=Path(__file__).resolve().parent.parent/'web'/'site'/'cliente_whatsapp.js'
                    if not asset.is_file():
                        return self.erro('Recurso não encontrado.',404)
                    return self.send_bytes(asset.read_bytes(),'application/javascript; charset=utf-8')
                if path == '/api/health':
                    return self.send_bytes(b'{"ok":true,"site":"officina"}',
                                           'application/json; charset=utf-8')
                if path == '/api/info':
                    payload=json.dumps({'site':'officina','versao':VERSAO_PORTAL,
                           'porta':getattr(self.server,'server_port',None)}).encode('utf-8')
                    return self.send_bytes(payload,'application/json; charset=utf-8')
                if path == '/manifest.webmanifest':
                    payload=json.dumps({'name':'Officina Web · Gestão de Serviços',
                          'short_name':'Officina Web','start_url':'/','display':'standalone',
                          'background_color':'#0A0A0A','theme_color':'#FFD400'}).encode('utf-8')
                    return self.send_bytes(payload,'application/manifest+json')
                customer = login_web.client_session(self, banco)
                if customer is not None:
                    if path == '/login':
                        return self.redir('/')
                    try:
                        if officina_web.client_path_allowed(path):
                            return client_web.dispatch_get(self,banco,customer,path)
                    except PermissionError:
                        return self.erro('Recurso indisponível.',404)
                    except ValueError:
                        return self.erro('Recurso indisponível.',400)
                    except Exception:
                        LOG.warning('Falha no serviço do cliente.')
                        return self.erro('Falha interna.',500)
                    if path == '/cliente' or path.startswith('/cliente/'):
                        return self.erro('Página indisponível.',404)
                    if path not in ('/logo.png','/icone.png','/favicon.ico',
                                    '/static/portal.js','/login'):
                        return self.erro('Acesso não autorizado.',403)
                if path.startswith('/os/'):
                    try:
                        normalized=self._normalizar_os(path)
                        parts=normalized.strip('/').split('/')
                        if len(parts)>=2 and parts[1].isdigit():
                            session=self.sessao()
                            if session is None:
                                return self.login()
                            principal=os_commands._provider_context(banco,session)
                            os_commands.authorize_get(banco,principal,normalized)
                    except PermissionError:
                        return self.erro('Recurso indisponível.',404)
                redirecionar = self._redirecionar_os(path)
                if redirecionar:
                    query = urlparse(self.path).query
                    return self.redir(redirecionar + (('?' + query) if query else ''))
                path = self._normalizar_os(path)
                try:
                    if path=='/login':
                        if self.sessao():
                            return self.redir('/')
                        if login_flags.unified_login_enabled(banco):
                            return login_web.render_login(self)
                        return self.login()
                    if path=='/api/versao':
                        dados=json.dumps({'app':'Gestão de Serviços — AUTOSEG','versao':VERSAO_PORTAL,
                                          'site':'portal do prestador',
                                          'porta':getattr(self.server,'server_port',None),
                                          'login_prestador':'e-mail e senha',
                                          'cadastro_prestadores':'bloqueado no portal web'}).encode('utf-8')
                        return self.send_bytes(dados,'application/json; charset=utf-8')
                    if path==api_fin.API_PREFIX or path.startswith(api_fin.API_PREFIX+'/'):
                        return api_fin.handle(self,path,banco,'GET')
                    if path=='/static/portal.js':
                        return self.send_bytes((Path(__file__).resolve().parent.parent/'web'/'portal.js').read_bytes(),'application/javascript; charset=utf-8')
                    if path in ('/logo.png','/icone.png','/favicon.ico'):
                        if path == '/logo.png':
                            arquivo = ext.BASE/'logo.png'
                            if not arquivo.is_file():
                                arquivo = Path(__file__).resolve().parent.parent/'branding'/'logo.png'
                            if not arquivo.is_file():
                                arquivo = Path(__file__).resolve().parent.parent/'branding'/'logo.png'
                        else:
                            arquivo = (ext.caminho_icone(ext.BASE)
                                       or ext.caminho_icone(Path(__file__).resolve().parent.parent/'branding')
                                       or ext.caminho_icone(Path(__file__).parent))
                        if arquivo and arquivo.is_file():
                            return self.send_bytes(arquivo.read_bytes(),'image/png')
                        return self.erro('Imagem não encontrada.',404,self.sessao())
                    if path == '/cliente' or path.startswith('/cliente/'):
                        return self.erro('Página indisponível.',404)
                    if path == '/pj' or path.startswith('/pj/'):
                        return self.erro('Página indisponível.',404)
                    s=self.sessao()
                    if not s:return self.login()
                    if path=='/contas':
                        if not object_policy_flags.enforcement_enabled(banco):
                            return self.erro('Página não encontrada.',404,s)
                        principal=os_commands._provider_context(banco,s)
                        return account_roles.render_accounts(self,banco,s,principal)
                    if path in ('/modelos/cadastro.yaml','/modelos/relatorio.yaml','/modelos/servico.yaml','/modelos/orcamento.yaml'):
                        nome={'/modelos/cadastro.yaml':'modelo_cadastro_cliente.yaml','/modelos/relatorio.yaml':'modelo_relatorio_os.yaml','/modelos/servico.yaml':'modelo_servico.yaml','/modelos/orcamento.yaml':'modelo_orcamento.yaml'}[path]
                        arquivo=Path(__file__).resolve().parent.parent/'templates'/nome
                        return self.send_bytes(arquivo.read_bytes(),'application/x-yaml; charset=utf-8',filename=nome)
                    if path=='/feedback/recebidos':
                        if not s.get('admin'):
                            raise PermissionError('Feedbacks recebidos são visíveis apenas para administradores.')
                        qs=parse_qs(urlparse(self.path).query)
                        status_dev=str(qs.get('status',[''])[0]).strip()
                        if status_dev and status_dev not in feedback.STATUS_TRIAGEM:
                            status_dev=''
                        return self.feedback_admin(s,status_dev=status_dev)
                    if path=='/feedback/pendencias.md':
                        if not s.get('admin'):
                            raise PermissionError('Pendências de feedback são visíveis apenas para administradores.')
                        with ext.db(banco) as c:
                            neg.audit(c,s['pid'],'Feedback exportado','pendencias','markdown')
                        corpo=feedback.pendencias_markdown(banco).encode('utf-8')
                        return self.send_bytes(corpo,'text/markdown; charset=utf-8',
                                               filename='pendencias_feedback_dev.md')
                    if path=='/feedback/dados/exportar.json':
                        if not s.get('admin'):
                            raise PermissionError('Exportação de feedback restrita a administradores.')
                        with ext.db(banco) as c:
                            neg.audit(c,s['pid'],'Feedback exportado','dados','json')
                        corpo=json.dumps(feedback.exportar_dados(banco),ensure_ascii=False,
                                         indent=2).encode('utf-8')
                        return self.send_bytes(corpo,'application/json; charset=utf-8',
                                               filename='feedback_export.json')
                    partes_feedback=path.strip('/').split('/')
                    if len(partes_feedback)==2 and partes_feedback[0]=='feedback' and partes_feedback[1].isdigit():
                        return self.feedback_detalhe(s,int(partes_feedback[1]))
                    if path in ('/chamados','/organizacoes'):
                        return self.redir('/os' if path=='/chamados' else '/clientes')
                    if path in ('/clientes/responsaveis','/organizacoes/responsaveis'):
                        return v9.get(self,'/organizacoes/responsaveis',banco,s)
                    if path=='/composicao/simular':
                        qs=parse_qs(urlparse(self.path).query)
                        def _valor(k,padrao=''):
                            return str(qs.get(k,[padrao])[0])
                        try:
                            total_txt=_valor('total').strip()
                            campos={}
                            for chave,valores in qs.items():
                                if chave in ('total','materiais','mao_obra','horas','base'):
                                    continue
                                try:
                                    campos[chave]=composicao.centavos_de_reais(str(valores[0]))
                                except (ValueError,TypeError):
                                    continue
                            materiais_centavos=composicao.centavos_de_reais(
                                _valor('materiais','0'))
                            mao_obra_centavos=composicao.centavos_de_reais(
                                _valor('mao_obra','0'))
                            # Without an explicit final total, the preview uses
                            # labor + materials. The composition may split that
                            # value, never increase it.
                            total_centavos=(composicao.centavos_de_reais(total_txt)
                                            if total_txt else None)
                            if total_centavos is None:
                                total_centavos=(materiais_centavos
                                                + mao_obra_centavos)
                            cobrar_visita=str(_valor('cobrar_visita','1')).strip().lower() not in (
                                '0','nao','não','false','off')
                            if cobrar_visita:
                                comp=composicao.calcular_os(
                                    total_centavos=total_centavos,
                                    materiais_centavos=materiais_centavos,
                                    mao_obra_centavos=mao_obra_centavos,
                                    horas=_valor('horas','0') or 0,
                                    base_percentuais=(_valor('base','total') or 'total'),
                                    campos=campos)
                            else:
                                comp=composicao.calcular_os_sem_visita(
                                    total_centavos=total_centavos,
                                    materiais_centavos=materiais_centavos,
                                    mao_obra_centavos=mao_obra_centavos,
                                    horas=_valor('horas','0') or 0,
                                    campos=campos)
                            componentes=[]
                            for x in comp['componentes']:
                                item={'nome':x['nome'],
                                      'valor_centavos':x['valor_centavos'],
                                      'percentual':x['percentual']}
                                if x.get('filhos'):
                                    item['filhos']=[{'nome':f['nome'],
                                                     'valor_centavos':f['valor_centavos'],
                                                     'percentual':f['percentual']}
                                                    for f in x['filhos']]
                                componentes.append(item)
                            dados={'ok':True,'total_centavos':comp['total_centavos'],
                                   'base_percentuais':comp.get('base_percentuais',''),
                                   'sem_visita':bool(comp.get('sem_visita')),
                                   'aviso':comp.get('aviso',''),
                                   'componentes':componentes}
                            return self.send_bytes(json.dumps(dados,ensure_ascii=False).encode(),
                                                   'application/json; charset=utf-8')
                        except (ValueError,TypeError) as exc:
                            return self.erro(str(exc),400,self.sessao())
                    if path=='/':return self.inicio(s)
                    if path=='/os':return self.os_lista(s)
                    if path=='/pj-publicas':return self.pj_publicas(s)
                    if path=='/servicos':return self.servicos_lista(s)
                    if path=='/servicos/novo':return self.servico_form(s)
                    if path=='/historico':return self.os_lista(s,True)
                    if path=='/os/rapida':
                        qs=parse_qs(urlparse(self.path).query)
                        q=qs.get('q',[''])[0][:120]
                        try:cliente_rapido=int(qs.get('cliente',['0'])[0]) or None
                        except (ValueError,TypeError):cliente_rapido=None
                        return self.os_rapida_form(s,q=q,cliente_id=cliente_rapido)
                    if path=='/os/nova':return self.os_form(s)
                    if path=='/clientes':return self.clientes_lista(s)
                    if path=='/orcamento':
                        qs=parse_qs(urlparse(self.path).query)
                        try:cliente_orcamento=int(qs.get('cliente_id',['0'])[0]) or None
                        except (ValueError,TypeError):cliente_orcamento=None
                        return self.orcamento_form(s,cliente_id=cliente_orcamento)
                    if path=='/clientes/novo':return self.cliente_form(s)
                    if path.startswith('/financeiro/maf-emprestimo/') and path.rsplit('/',1)[-1].isdigit():
                        oid=int(path.rsplit('/',1)[-1])
                        with ext.db(banco) as c:
                            linha=c.execute('SELECT email FROM prestadores WHERE id=?',
                                            (s['pid'],)).fetchone()
                        email=linha['email'] if linha else ''
                        corpo_maf=maf_loans.render_detail(s['pid'],email,oid,s['csrf'])
                        if not corpo_maf:
                            return self.erro('Empréstimo não encontrado.',404,s)
                        return self.pagina('Empréstimo entre prestadores',corpo_maf,s)
                    if path.startswith('/financeiro/maf-comprovante/') and path.rsplit('/',1)[-1].isdigit():
                        did=int(path.rsplit('/',1)[-1])
                        with ext.db(banco) as c:
                            linha=c.execute('SELECT email FROM prestadores WHERE id=?',
                                            (s['pid'],)).fetchone()
                        email=linha['email'] if linha else ''
                        caminho=maf_loans.proof_return(s['pid'],email,did)
                        if not caminho:
                            return self.erro('Comprovante não encontrado.',404,s)
                        mime={'.pdf':'application/pdf','.png':'image/png',
                              '.jpg':'image/jpeg','.jpeg':'image/jpeg'}.get(
                                  caminho.suffix.lower(),'application/octet-stream')
                        return self.send_bytes(caminho.read_bytes(),mime)
                    if path=='/financeiro':return self.financeiro(s)
                    if path=='/prestadores/novo':
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem gerenciar prestadores.')
                        return self.redir('/prestadores')
                    if path=='/prestadores':return self.prestadores_admin(s)
                    if path=='/estoque':return self.estoque_admin(s)
                    if path=='/estoque/novo':return self.estoque_item(s)
                    if path=='/caixa':return self.caixa_admin(s)
                    if path=='/composicao':return self.composicao_admin(s)
                    if path=='/configuracoes':return self.configuracoes(s)
                    if path=='/composicao/novo':return self.composicao_form(s)
                    partes_comp_get=path.strip('/').split('/')
                    if len(partes_comp_get)==3 and partes_comp_get[0]=='composicao' and partes_comp_get[2]=='editar':
                        return self.composicao_form(s,partes_comp_get[1])
                    if path=='/relatorios':return self.redir('/historico')
                    if path=='/emails':return self.relatorios(s,'emails')
                    if path=='/notas':return self.relatorios(s,'notas')
                    if path=='/portal-cliente':return self.portal_cliente(s)
                    partes=path.strip('/').split('/')
                    if len(partes)==2 and partes[0]=='estoque' and partes[1].isdigit():
                        return self.estoque_item(s,int(partes[1]))
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='editar':
                        return self.servico_form(s,int(partes[1]))
                    if len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='contato':
                        contato=clientes_core.obter_linha(int(partes[1]),banco=banco)
                        if not contato:
                            return self.send_bytes(json.dumps({'error':'Cliente não encontrado.'}).encode(),
                                                   'application/json; charset=utf-8',status=404)
                        return self.send_bytes(json.dumps({
                            'id':int(contato['id']),'nome':contato['nome'],
                            'email':contato.get('email') or '',
                            'telefone':contato.get('telefone') or '',
                            'sindico_nome':contato.get('sindico_nome') or '',
                            'sindico_email':contato.get('sindico_email') or '',
                        },ensure_ascii=False).encode(),'application/json; charset=utf-8')
                    if len(partes)==2 and partes[0]=='clientes' and partes[1].isdigit():
                        return self.cliente_form(s,int(partes[1]))
                    if len(partes)==2 and partes[0]=='os' and partes[1].isdigit():
                        return self.os_form(s,int(partes[1]))
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='relatorio.yaml':
                        oid=int(partes[1])
                        try:
                            texto=yaml_import.relatorio_os_yaml(banco,oid)
                        except ValueError as exc:
                            return self.erro(str(exc),404,s)
                        return self.send_bytes(texto.encode('utf-8'),
                                               'application/x-yaml; charset=utf-8',
                                               filename=f'relatorio_os_{oid}.yaml')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='rascunho':
                        oid=int(partes[1])
                        rascunho=prod.recuperar_rascunho(banco,oid,s['pid'])
                        if not rascunho:return self.erro('Nenhum rascunho salvo para esta OS.',404,s)
                        return self.os_form(s,oid,preenchimento=rascunho['dados'])
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2] in ('pdf','pdf-preview','email','nota'):
                        return os_commands.document_get(banco,(os_commands._provider_context(banco,s) if object_policy_flags.enforcement_enabled(banco) else None),int(partes[1]),ui=self,session=s,kind=partes[2])
                    if len(partes)==5 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='nota-fiscal' and partes[3].isdigit() and partes[4]=='preview':
                        oid=int(partes[1]);nid=int(partes[3])
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=s['pid'] and not cad9.prestador_admin(banco,s['pid']):
                                raise PermissionError('Nota fiscal restrita ao responsável ou administrador.')
                        registro,caminho=ext.obter_nota_fiscal(banco,oid,nid)
                        return self.send_bytes(Path(caminho).read_bytes(),'application/pdf',
                                               filename=registro['nome_original'],inline=True)
                    if len(partes)==4 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='nota-fiscal' and partes[3].isdigit():
                        oid=int(partes[1]);nid=int(partes[3])
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=s['pid'] and not cad9.prestador_admin(banco,s['pid']):
                                raise PermissionError('Nota fiscal restrita ao responsável ou administrador.')
                        registro,caminho=ext.obter_nota_fiscal(banco,oid,nid)
                        return self.send_bytes(Path(caminho).read_bytes(),'application/pdf',
                                               filename=registro['nome_original'])
                    if len(partes)==4 and partes[0]=='arquivos' and partes[1]=='anexo' and partes[2].isdigit() and partes[3]=='thumb':
                        return os_commands.read_anexo_thumb(banco,(os_commands._provider_context(banco,s) if object_policy_flags.enforcement_enabled(banco) else None),int(partes[2]),ui=self,session=s)
                    if len(partes)==3 and partes[0]=='arquivos' and partes[1]=='anexo' and partes[2].isdigit():
                        return os_commands.read_anexo(banco,(os_commands._provider_context(banco,s) if object_policy_flags.enforcement_enabled(banco) else None),int(partes[2]),ui=self,session=s)
                    return self.erro('Página não encontrada.',404,s)
                except PermissionError as e:return self.erro(str(e),403,self.sessao())
                except ValueError as e:return self.erro(str(e),409,self.sessao())
                except Exception:
                    LOG.exception('Erro GET %s',path)
                    return self.erro('Falha interna. Consulte o log do aplicativo.',500,self.sessao())

            def do_POST(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                path = self._normalizar_os(path)
                if path == '/entrar':
                    return self.erro('Página não encontrada.', 404)
                from flavors.autoseg.modules.autoseg_web_navigation import (
                    canonical_client_path, retired_client_path, MIGRATED_POST)
                if retired_client_path(path):
                    return self.retired_route()
                alias=canonical_client_path(path)
                if alias is not None:
                    return self.redirect_alias(alias)
                quer_json = ('application/json' in self.headers.get('Accept','')
                             or self.headers.get('X-Requested-With') == 'XMLHttpRequest')
                if not self.origem_permitida():
                    return self.erro('Origem da requisição inválida.',403,self.sessao())
                try:
                    customer = login_web.client_session(self, banco)
                    if customer is not None:
                        if path == '/login':
                            return self.redir('/')
                        if path in ('/cliente/sair', '/sair'):
                            d = self.form(PREAUTH_MAX)
                            if not web_cookie.csrf_valid(customer, str(d.get('csrf', ''))):
                                return self.erro('Formulário expirado ou sessão inválida.', 403)
                            token = web_cookie.token_from_headers(self.headers)
                            if token:
                                web_session.revoke(banco, token)
                            cookies = SimpleCookie()
                            cookies.load(self.headers.get('Cookie', ''))
                            if 'autosseg_session' in cookies:
                                SESSOES.pop(cookies['autosseg_session'].value, None)
                            return self.redir('/login', (
                                web_cookie.clear_cookie(secure=web_cookie.secure_request(self.headers)),
                                self.cookie('', True),
                            ))
                        if path == '/solicitar' or path in MIGRATED_POST:
                            return client_web.dispatch_post(self, banco, customer, path,
                                                            self.form(PREAUTH_MAX))
                        return self.erro('Acesso não autorizado.', 403)
                    if path.startswith('/cliente/') or path == '/cliente':
                        return self.erro('Página indisponível.',404)
                    if path==api_fin.API_PREFIX or path.startswith(api_fin.API_PREFIX+'/'):
                        return api_fin.handle(self,path,banco,'POST')
                    s_inicial=self.sessao()
                    d=self.form(PREAUTH_MAX if not s_inicial else MAX_POST)
                    if path=='/login':
                        ip,tent,agora,limitado=self._login_attempt_state()
                        unified_login = login_flags.unified_login_enabled(banco)
                        if limitado:
                            if unified_login:
                                return self.erro('Muitas tentativas. Aguarde dez minutos.', 429)
                            if quer_json:
                                return self.erro('Muitas tentativas. Aguarde dez minutos.',429)
                            return self.login(erro_login='Muitas tentativas. Aguarde dez minutos.',
                                              email_login=str(d.get('email','')))
                        if unified_login:
                            identifier=str(d.get('identificador') or d.get('email') or d.get('cpf') or '')
                            try:
                                token, _session = login_web.authenticate_and_create(
                                    banco, identifier, str(d.get('senha','')))
                            except auth.LoginError:
                                self._login_failed(ip,tent,agora)
                                return login_web.render_login(self, 'invalid', identifier)
                            self._login_succeeded(ip)
                            return self.redir('/', web_cookie.set_cookie(
                                token, secure=web_cookie.secure_request(self.headers)))
                        email_login=str(d.get('email',''))
                        p=ext.autenticar(banco,email_login,str(d.get('senha','')))
                        if not p:
                            self._login_failed(ip,tent,agora)
                            if quer_json:
                                return self.erro('Usuário ou senha incorretos.',401)
                            return self.login(erro_login='Usuário ou senha incorretos.',
                                              email_login=email_login)
                        self._login_succeeded(ip)
                        tok=secrets.token_urlsafe(36)
                        SESSOES[tok]={'pid':p['id'],'nome':p['nome'],'cred':p['senha_hash'],
                                      'csrf':secrets.token_urlsafe(32),
                                      'telemetry_session':secrets.token_urlsafe(18),
                                      'exp':time.time()+28800}
                        return self.redir('/',self.cookie(tok))
                    s=self.sessao()
                    self.csrf(s,d)
                    if path=='/sair':
                        token=web_cookie.token_from_headers(self.headers)
                        if token:
                            web_session.revoke(banco, token)
                        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                        if 'autosseg_session' in cookie:SESSOES.pop(cookie['autosseg_session'].value,None)
                        return self.redir('/login',(
                            web_cookie.clear_cookie(secure=web_cookie.secure_request(self.headers)),
                            self.cookie('',True),
                        ))
                    pid=s['pid']
                    if path.startswith("/os/"):
                        principal=(os_commands._provider_context(banco,s)
                                   if object_policy_flags.enforcement_enabled(banco) else None)
                        return os_commands.execute_http(self,banco,principal,path,d,s,quer_json)
                    if path.startswith('/contas/') and path.endswith('/papel'):
                        if not object_policy_flags.enforcement_enabled(banco):
                            return self.erro('Página não encontrada.',404,s)
                        parts=path.strip('/').split('/')
                        if len(parts)!=3 or not parts[1].isdigit():
                            raise PermissionError('Operação indisponível.')
                        principal=os_commands._provider_context(banco,s)
                        account_roles.change_role(banco,principal,int(parts[1]),
                                                  str(d.get('papel','')))
                        return self.redir('/contas')
                    if path=='/prestadores/novo' or path.startswith('/prestadores/'):
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem gerenciar prestadores.')
                        if path=='/prestadores/novo':
                            senha=str(d.get('senha',''))
                            if len(senha)<10:
                                raise ValueError('A senha inicial deve ter pelo menos 10 caracteres.')
                            ext.cadastrar(banco,nome=str(d.get('nome','')),
                                          email=str(d.get('email','')),senha=senha,
                                          telefone=str(d.get('telefone','')),
                                          documento=str(d.get('documento','')),
                                          especialidade=str(d.get('especialidade','')))
                            return self.redir('/prestadores')
                        partes=path.strip('/').split('/')
                        if len(partes)==3 and partes[1].isdigit():
                            alvo=int(partes[1])
                            if partes[2]=='alternar':
                                ext.alternar_ativo(banco,alvo)
                                web_session.revoke_identity(banco, 'provider',alvo)
                            elif partes[2]=='arquivar':
                                ext.arquivar_prestador(banco,alvo)
                                web_session.revoke_identity(banco, 'provider',alvo)
                            elif partes[2]=='senha':
                                ext.redefinir_senha_prestador_desktop(
                                    banco,alvo,str(d.get('senha','')))
                                web_session.revoke_identity(banco, 'provider',alvo)
                            elif partes[2]=='admin':
                                cad9.definir_admin(banco,alvo,
                                                   not cad9.prestador_admin(banco,alvo))
                                web_session.revoke_identity(banco, 'provider',alvo)
                            else:
                                raise ValueError('Ação de prestador inválida.')
                            return self.redir('/prestadores')
                        raise ValueError('Prestador inválido.')
                    if path=='/estoque/salvar' or path.startswith('/estoque/'):
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem gerenciar o estoque.')
                        partes=path.strip('/').split('/')
                        if path=='/estoque/salvar':
                            identificador=d.get('id')
                            identificador=int(identificador) if str(identificador or '').strip() else None
                            estoque.cadastrar(
                                banco,nome=str(d.get('nome','')),
                                sku=str(d.get('sku','')),
                                unidade=str(d.get('unidade','un')),
                                custo=str(d.get('custo','0')),
                                venda=str(d.get('venda','0')),
                                minimo=str(d.get('minimo','0')),
                                identificador=identificador)
                            return self.redir('/estoque')
                        if len(partes)==3 and partes[1].isdigit():
                            alvo=int(partes[1])
                            if partes[2]=='ajuste':
                                estoque.ajuste(banco,alvo,str(d.get('delta','')),
                                               str(d.get('motivo','')),ator=s['nome'])
                            elif partes[2]=='excluir':
                                estoque.excluir(banco,alvo)
                            else:
                                raise ValueError('Ação de estoque inválida.')
                            return self.redir(f'/estoque/{alvo}')
                        raise ValueError('Material inválido.')
                    if path=='/caixa/movimentos' or path.startswith('/caixa/movimentos/'):
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem acessar o caixa da empresa.')
                        partes=path.strip('/').split('/')
                        if path=='/caixa/movimentos':
                            empresa.registrar(
                                banco,tipo=str(d.get('tipo','')),
                                descricao=str(d.get('descricao','')),
                                valor=str(d.get('valor','0')),
                                data=str(d.get('data','')),
                                prestador_id=str(d.get('prestador_id','')).strip() or None,
                                os_id=str(d.get('os_id','')).strip() or None,
                                categoria=str(d.get('categoria','')),
                                finalidade=str(d.get('finalidade','')),
                                observacao=str(d.get('observacao','')),
                                criado_por=s['nome'])
                            return self.redir('/caixa')
                        if len(partes)==4 and partes[3]=='arquivar' and partes[2].isdigit():
                            empresa.arquivar(banco,int(partes[2]),ator=s['nome'])
                            return self.redir('/caixa')
                        raise ValueError('Lançamento inválido.')
                    if path=='/configuracoes':
                        prestador_auth.salvar_preferencias(
                            banco,pid,str(d.get('tema','auto')),
                            str(d.get('acento','ambar')))
                        return self.redir('/configuracoes')
                    if path.startswith('/composicao/'):
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem editar a composição.')
                        config=self._composicao_config()
                        partes_comp=path.strip('/').split('/')
                        try:
                            if path=='/composicao/bases/salvar':
                                def _lista_base(valor):
                                    if valor is None:return []
                                    return valor if isinstance(valor,list) else [valor]
                                chaves=_lista_base(d.get('base_chave[]'))
                                nomes=_lista_base(d.get('base_nome[]'))
                                coberturas=_lista_base(d.get('base_cobertura[]'))
                                componentes_base=_lista_base(d.get('base_componente[]'))
                                campos_base=_lista_base(d.get('base_campo[]'))
                                bases_novas={}
                                for indice,chave in enumerate(chaves):
                                    chave=str(chave).strip()
                                    if not chave:continue
                                    bases_novas[chave]={
                                        'nome':str(nomes[indice] if indice<len(nomes) else chave).strip() or chave,
                                        'cobertura':str(coberturas[indice] if indice<len(coberturas) else 'separado'),
                                        'componente':str(componentes_base[indice] if indice<len(componentes_base) else '').strip(),
                                        'campo':str(campos_base[indice] if indice<len(campos_base) else '').strip(),
                                    }
                                if not bases_novas:
                                    raise ValueError('Mantenha pelo menos uma composição de valores.')
                                padrao=str(d.get('base_padrao','')).strip()
                                if padrao not in bases_novas:
                                    padrao=next(iter(bases_novas))
                                config['bases_percentuais']=bases_novas
                                config['base_percentuais_padrao']=padrao
                                composicao.salvar(config)
                                composicao.recalcular_tudo(banco)
                                return self.redir('/composicao')
                            if path=='/composicao/recalcular':
                                composicao.recalcular_tudo(banco)
                                return self.redir('/composicao')
                            if path=='/composicao/yaml':
                                try:
                                    config=yaml.safe_load(str(d.get('yaml','')))
                                except yaml.YAMLError as erro:
                                    raise ValueError(f'YAML inválido: {erro}') from erro
                                composicao.salvar(config)
                                composicao.recalcular_tudo(banco)
                                return self.redir('/composicao')
                            if len(partes_comp)==3 and partes_comp[2] in ('alternar','mover','excluir'):
                                alvo=partes_comp[2]; cid=partes_comp[1]
                                componentes=sorted(config.get('componentes',[]),
                                                   key=lambda c:(c.get('ordem',0),c.get('id','')))
                                if alvo=='excluir':
                                    if len(componentes)<=1:
                                        raise ValueError('Mantenha pelo menos um componente.')
                                    config['componentes']=[c for c in componentes if str(c.get('id'))!=cid]
                                else:
                                    atual=next((c for c in componentes if str(c.get('id'))==cid),None)
                                    if atual is None:
                                        raise ValueError('Componente não encontrado.')
                                    if alvo=='alternar':
                                        atual['ativo']=not atual.get('ativo',True)
                                    else:
                                        direcao=str(d.get('direcao','up'))
                                        indice=componentes.index(atual)
                                        destino=indice-1 if direcao=='up' else indice+1
                                        if 0<=destino<len(componentes):
                                            componentes[indice],componentes[destino]=componentes[destino],componentes[indice]
                                        for posicao,item in enumerate(componentes):
                                            item['ordem']=posicao+1
                                        config['componentes']=componentes
                                self._composicao_salvar(config)
                                return self.redir('/composicao')
                            if path=='/composicao/salvar':
                                nome=str(d.get('nome','')).strip()
                                if not nome:
                                    raise ValueError('Informe o nome do componente.')
                                modo=str(d.get('modo','')).strip()
                                if modo not in composicao.MODOS:
                                    raise ValueError('Escolha um modo de cálculo válido.')
                                valor_txt=str(d.get('valor','0')).strip().replace('%','')
                                if modo=='percentual':
                                    try:
                                        valor=float(valor_txt.replace(',','.') or 0)
                                    except ValueError:
                                        raise ValueError('Percentual inválido.') from None
                                elif modo in ('fixo','hora'):
                                    valor=composicao.centavos_de_reais(valor_txt or '0')
                                else:
                                    valor=0
                                try:
                                    horas=float(str(d.get('horas_padrao','0') or '0').replace(',','.'))
                                except ValueError:
                                    raise ValueError('Horas padrão inválidas.') from None
                                ordem_txt=str(d.get('ordem','')).strip()
                                try:
                                    ordem=int(ordem_txt) if ordem_txt else 0
                                except ValueError:
                                    raise ValueError('Ordem inválida.') from None
                                id_atual=str(d.get('id_atual','')).strip()
                                id_novo=str(d.get('id_novo','')).strip()
                                existentes=[str(c.get('id')) for c in config.get('componentes',[])]
                                if id_atual:
                                    cid=id_atual
                                else:
                                    cid=(id_novo or composicao.novo_id(nome,existentes)).strip()
                                    base=cid; numero=2
                                    while cid in existentes:
                                        cid=f'{base}_{numero}'; numero+=1
                                if not ordem:
                                    ordem=(max([int(c.get('ordem',0) or 0)
                                                for c in config.get('componentes',[])]+[0])+1)
                                componente={
                                    'id':cid,'nome':nome,
                                    'descricao':str(d.get('descricao','')).strip(),
                                    'modo':modo,'valor':valor,
                                    'formula':str(d.get('formula','')).strip(),
                                    'horas_padrao':horas,
                                    'minimo_centavos':(composicao.centavos_de_reais(
                                        str(d.get('minimo','0') or '0')) if modo=='hora' else 0),
                                    'aplicavel_a':[x.strip() for x in
                                        str(d.get('aplicavel_a','')).split(',') if x.strip()],
                                    'ativo':str(d.get('ativo','')) in ('1','on','true','sim'),
                                    'obrigatorio':str(d.get('obrigatorio','')) in ('1','on','true','sim'),
                                    'ordem':ordem,
                                }
                                componentes=list(config.get('componentes',[]))
                                if id_atual:
                                    for indice,atual in enumerate(componentes):
                                        if str(atual.get('id'))==id_atual:
                                            componentes[indice]=componente; break
                                else:
                                    componentes.append(componente)
                                config['componentes']=componentes
                                self._composicao_salvar(config)
                                return self.redir('/composicao')
                        except ValueError as erro:
                            return self.erro(str(erro),400,s)
                        raise ValueError('Ação de composição inválida.')
                    def _meta_feedback():
                        meta=feedback.contexto(
                            banco,s,
                            feedback.ip_requisicao(self.client_address[0],self.headers),
                            self.headers.get('User-Agent',''))
                        meta['ui_mode']=str(d.get('ui_mode') or ('app' if self.ui_app() else 'classic'))[:20]
                        meta['aba']=str(d.get('aba') or '')[:80]
                        meta['diagnostico']=str(d.get('diagnostico') or '')[:8000]
                        return meta
                    if path=='/telemetria/ui':
                        pagina=str(d.get('pagina') or urlparse(self.headers.get('Referer','')).path or '/')[:300]
                        meta=_meta_feedback()
                        feedback.registrar_ui(banco,s,pagina,
                                              str(d.get('ui_mode','')),
                                              str(d.get('aba','')),meta)
                        return self.send_bytes(b'','text/plain; charset=utf-8',status=204)
                    if path=='/feedback/aberto':
                        pagina=str(d.get('pagina') or urlparse(self.headers.get('Referer','')).path or '/')[:300]
                        meta=_meta_feedback()
                        feedback.registrar_abertura(banco,s,pagina,meta)
                        return self.send_bytes(b'','text/plain; charset=utf-8',status=204)
                    if path in ('/feedback/rascunho','/feedback/rascunho/descartar'):
                        pagina=str(d.get('pagina') or urlparse(self.headers.get('Referer','')).path or '/')[:300]
                        meta=_meta_feedback()
                        rascunho_id=d.get('rascunho_id')
                        if path.endswith('/descartar'):
                            removidos=feedback.descartar_rascunho(banco,s,rascunho_id)
                            dados={'ok':True,'removidos':removidos}
                        else:
                            fid=feedback.salvar_rascunho(
                                banco,s,pagina,str(d.get('mensagem','')),
                                str(d.get('responder_ia','')) in ('1','on','true','sim'),
                                meta,rascunho_id)
                            dados={'ok':True,'id':fid}
                        return self.send_bytes(json.dumps(dados,ensure_ascii=False).encode(),
                                               'application/json; charset=utf-8')
                    if path=='/feedback':
                        pagina=str(d.get('pagina') or urlparse(self.headers.get('Referer','')).path or '/')[:300]
                        meta=_meta_feedback()
                        try:
                            _,item=feedback.criar(
                                banco,s,pagina,str(d.get('mensagem','')),
                                str(d.get('responder_ia','')) in ('1','on','true','sim'),
                                meta,d.get('rascunho_id'))
                        except ValueError as erro:
                            if quer_json:
                                return self.send_bytes(
                                    json.dumps({'ok':False,'error':str(erro)},
                                               ensure_ascii=False).encode(),
                                    'application/json; charset=utf-8',status=400)
                            return self.pagina('Feedback não enviado',
                                card('Não foi possível enviar',
                                     f'<p class="bad">{esc(erro)}</p>'
                                     '<p>Seu texto não foi perdido pelo sistema; volte e tente novamente.</p>'
                                     +botao('Voltar à página anterior',self.voltar_url(),'secondary')),s,400)
                        if quer_json:
                            return self.send_bytes(
                                json.dumps({
                                    'ok': True,
                                    'id': int(item['id']),
                                    'status_dev': item['status_dev'],
                                    'responder_ia': bool(item['responder_ia']),
                                    'ia_status': item['ia_status'],
                                    'resposta_ia': item['resposta_ia'] or '',
                                    'ia_erro': item['ia_erro'] or '',
                                }, ensure_ascii=False).encode(),
                                'application/json; charset=utf-8')
                        return self.feedback_confirmacao(s,item)
                    partes_feedback=path.strip('/').split('/')
                    if len(partes_feedback)==3 and partes_feedback[0]=='feedback' and partes_feedback[1].isdigit() and partes_feedback[2]=='triagem':
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem triar feedbacks.')
                        feedback.triar(banco,int(partes_feedback[1]),str(d.get('status_dev','')),
                                       str(d.get('nota_dev','')),s)
                        return self.redir(f'/feedback/{int(partes_feedback[1])}')
                    if path.startswith('/chamados/') or path.startswith('/organizacoes/') or path=='/organizacoes/mesclar' or (path.startswith('/clientes/') and path.endswith('/desativar')):
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem alterar organizações, vínculos ou desativar clientes.')
                        return v9.post(self,path,d,banco,s)
                    partes=path.strip('/').split('/')
                    if path=='/servicos/yaml':
                        arq=d.get('yaml')
                        if not isinstance(arq,tuple):
                            return self.servico_form(
                                s, erro='Selecione um arquivo YAML de serviço.')
                        try:
                            pre=yaml_import.servico(arq[0],arq[1])
                        except ValueError as erro:
                            return self.servico_form(s, erro=str(erro))
                        return self.servico_form(s,preenchimento=pre)
                    if path=='/servicos/salvar':
                        sid=str(d.get('servico_id','')).strip()
                        try:catalogo.salvar(banco,d,int(sid) if sid else None)
                        except ValueError as e:return self.servico_form(s,int(sid) if sid else None,preenchimento=d,erro=str(e))
                        return self.redir('/servicos')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='arquivar':
                        catalogo.arquivar(banco,int(partes[1]))
                        return self.redir('/servicos')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='excluir':
                        catalogo.excluir(banco,int(partes[1]))
                        return self.redir('/servicos')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='reativar':
                        catalogo.reativar(banco,int(partes[1]))
                        return self.redir('/servicos')
                    if path=='/clientes/yaml':
                        arq=d.get('yaml')
                        if not isinstance(arq,tuple):
                            return self.cliente_form(
                                s, erro='Selecione um arquivo YAML. O nome do arquivo não importa; '
                                        'o conteúdo precisa ser YAML válido.')
                        try:
                            pre=yaml_import.cliente(arq[0],arq[1])
                        except ValueError as erro:
                            return self.cliente_form(s, erro=str(erro))
                        return self.cliente_form(s,preenchimento=pre)
                    if path=='/orcamento/yaml':
                        arq=d.get('yaml')
                        if not isinstance(arq,tuple):
                            raise ValueError('Selecione um arquivo YAML de orçamento.')
                        try:
                            pre=yaml_import.orcamento(arq[0],arq[1],banco)
                        except ValueError as erro:
                            return self.orcamento_form(s,erro=str(erro))
                        if not pre:
                            return self.orcamento_form(
                                s,erro='O YAML está em branco. Preencha a seção "orcamento" '
                                       'e remova as instruções antes de importar.')
                        return self.orcamento_form(
                            s,cliente_id=pre['cliente_id'],
                            servicos=pre['servicos'],materiais=pre['materiais'],
                            aviso='YAML importado. Confira cliente, serviços, materiais e '
                                  'quantidades antes de gerar o PDF.')
                    if path=='/orcamento/pdf':
                        try:
                            cliente_id=int(str(d.get('cliente_id','')).strip())
                        except (TypeError,ValueError):
                            return self.orcamento_form(s,'Selecione o cliente.',None)
                        try:
                            validade=int(str(d.get('validade','30')).strip() or '30')
                        except (TypeError,ValueError):
                            return self.orcamento_form(
                                s,'Informe a validade em dias (1 a 365).',cliente_id)
                        if not 1<=validade<=365:
                            return self.orcamento_form(
                                s,'Informe a validade em dias (1 a 365).',cliente_id,
                                validade=str(validade))
                        condicoes=str(d.get('condicoes','')).strip()[:1000]
                        cliente=clientes_core.obter_para_orcamento(cliente_id, banco=banco)
                        if not cliente:
                            return self.orcamento_form(
                                s,'Cliente não encontrado.',cliente_id,
                                validade=str(validade),condicoes=condicoes)
                        try:
                            itens=catalogo.itens_orcamento_formulario(banco,d)
                        except ValueError as erro:
                            try:
                                brutos=catalogo.linhas_orcamento_formulario(d)
                            except ValueError:
                                brutos={'servicos':None,'materiais':None}
                            return self.orcamento_form(
                                s,str(erro),cliente_id=cliente_id,
                                servicos=brutos['servicos'],materiais=brutos['materiais'],
                                validade=str(validade),condicoes=condicoes)
                        try:
                            if len(itens['servicos'])==1 and not itens['materiais']:
                                servico=itens['servicos'][0]
                                pdf=catalogo.pdf_orcamento(
                                    banco,servico['id'],servico['quantidade'],
                                    cliente=cliente['nome'],
                                    cliente_documento=cliente['documento'] or '',
                                    validade=validade,condicoes=condicoes)
                                nome_pdf=f'Orcamento_{cliente_id}_{servico["id"]}.pdf'
                            else:
                                pdf=catalogo.pdf_orcamento_itens(
                                    banco,cliente['nome'],cliente['documento'] or '',itens,
                                    validade=validade,condicoes=condicoes)
                                nome_pdf=f'Orcamento_{cliente_id}.pdf'
                        except ValueError as erro:
                            return self.orcamento_form(
                                s,str(erro),cliente_id=cliente_id,
                                servicos=itens['servicos'],materiais=itens['materiais'],
                                validade=str(validade),condicoes=condicoes)
                        return self.send_bytes(pdf,'application/pdf',filename=nome_pdf)
                    if path=='/clientes/novo/salvar' or (len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='salvar'):
                        senha_nova=str(d.get('senha_cliente',''))
                        confirmar=str(d.get('confirmar_senha_cliente',''))
                        if (senha_nova or confirmar) and not s.get('admin'):
                            raise PermissionError('Somente administradores podem redefinir a senha do cliente.')
                        if senha_nova or confirmar:
                            if len(senha_nova)<10:raise ValueError('A senha do cliente deve ter pelo menos 10 caracteres.')
                            if senha_nova!=confirmar:raise ValueError('A confirmação da senha não corresponde.')
                        editar=int(partes[1]) if len(partes)==3 and partes[1].isdigit() else None
                        cid=neg.cliente_salvar(banco,d,pid,editar)
                        if senha_nova:fluxo.definir_senha_cliente(banco,cid,senha_nova)
                        return self.redir(f'/clientes/{cid}')
                    if len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='excluir':
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem excluir clientes.')
                        neg.cliente_excluir(banco,int(partes[1]),pid)
                        return self.redir('/clientes')
                    if len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='mesclar':
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem mesclar clientes.')
                        try:
                            destino=int(str(d.get('destino_id','')).strip())
                        except (TypeError,ValueError):
                            raise ValueError('Escolha o cliente de destino.') from None
                        cad9.mesclar_clientes(banco,int(partes[1]),destino,str(s['nome']))
                        return self.redir(f'/clientes/{destino}')
                    if len(partes)==3 and partes[0]=='pj-publicas' and partes[1].isdigit() and partes[2] in ('aceitar','recusar'):
                        sid=int(partes[1])
                        if partes[2]=='aceitar':
                            resultado=pj_publico.aceitar(banco,sid,ator=s['nome'])
                            return self.redir(f'{url_os(banco, resultado["os_id"])}')
                        pj_publico.recusar(banco,sid,str(d.get('motivo','')),ator=s['nome'])
                        return self.redir('/pj-publicas')
                    if path.startswith('/financeiro/maf-'):
                        with ext.db(banco) as c:
                            linha=c.execute('SELECT email FROM prestadores WHERE id=?',
                                            (s['pid'],)).fetchone()
                        email=linha['email'] if linha else ''
                        if path=='/financeiro/maf-vinculo/solicitar':
                            maf_loans.request_link_code(s['pid'],email)
                            return self.redir('/financeiro')
                        if path=='/financeiro/maf-vinculo/confirmar':
                            maf_loans.confirm_link_code(s['pid'],email,
                                                        str(d.get('codigo','')).strip())
                            return self.redir('/financeiro')
                        if path=='/financeiro/maf-emprestimo/criar':
                            valor=neg.numero(d.get('valor','0'),'Valor do empréstimo')
                            venc=str(d.get('vencimento','')).strip() or None
                            maf_loans.create_loan(
                                s['pid'],email,str(d.get('devedor_email','')),
                                str(d.get('descricao','')),int(round(valor*100)),venc)
                            return self.redir('/financeiro')
                        partes=path.strip('/').split('/')
                        if (len(partes)==4 and partes[1]=='maf-emprestimo'
                                and partes[2].isdigit()):
                            lid=int(partes[2]); acao=partes[3]
                            extra=dict(d)
                            if acao in ('devolver','alterar'):
                                bruto=str(d.get('valor','')).strip()
                                if bruto:
                                    extra['valor_centavos']=int(round(
                                        neg.numero(bruto,'Valor')*100))
                            maf_loans.act(s['pid'],email,lid,acao,extra)
                            return self.redir(f'/financeiro/maf-emprestimo/{lid}')
                        return self.erro('Operação de empréstimo inválida.',404,s)
                    if path=='/financeiro/banco/salvar':
                        prod.salvar_dados_bancarios(banco,pid,str(d.get('dados_bancarios','')))
                        return self.redir('/financeiro')
                    if path=='/financeiro/repasse':
                        secundario=int(d['secundario_id'])
                        prod.confirmar_repasse(
                            banco,int(d['os_id']),pid,secundario,None)
                        return self.redir('/financeiro')
                    if path=='/financeiro/repasse/confirmar':
                        prod.confirmar_recebimento_repasse(
                            banco,int(d['os_id']),pid,None)
                        return self.redir('/financeiro')
                    if len(partes)==3 and partes[0]=='financeiro' and partes[1].isdigit() and partes[2] in ('receber','cancelar','vencimento'):
                        fid=int(partes[1])
                        with ext.db(banco) as c:
                            autorizado=c.execute('''SELECT 1 FROM financeiro f JOIN os_encerramentos con ON con.os_id=f.os_id
                                WHERE f.id=? AND con.prestador_id=?''',(fid,pid)).fetchone()
                        if not autorizado and not s.get('admin'):
                            raise PermissionError('Financeiro restrito ao técnico finalizador ou administrador.')
                        if partes[2]=='cancelar':
                            neg.financeiro_cancelar(banco,fid,pid,str(d.get('motivo_cancelamento','')))
                        elif partes[2]=='vencimento':
                            neg.financeiro_definir_vencimento(
                                banco,fid,pid,str(d.get('vencimento','')))
                        else:
                            neg.financeiro_receber(banco,fid,pid)
                            if quer_json:
                                with ext.db(banco) as c:
                                    linha=c.execute(
                                        'SELECT status FROM financeiro WHERE id=?',
                                        (fid,)).fetchone()
                                return self.send_bytes(json.dumps({
                                    'ok':True,
                                    'status':(linha['status'] if linha else 'Recebido')
                                }).encode(),'application/json; charset=utf-8')
                        return self.redir('/financeiro')
                    return self.erro('Operação desconhecida.',404,s)
                except PermissionError as e:
                    if quer_json:
                        return self.send_bytes(
                            json.dumps({'ok':False,'error':str(e)},ensure_ascii=False).encode(),
                            'application/json; charset=utf-8',status=403)
                    return self.erro(str(e),403,self.sessao())
                except (KeyError,ValueError,TypeError) as e:
                    LOG.warning('Validação POST %s: %s',path,e)
                    if quer_json:
                        return self.send_bytes(
                            json.dumps({'ok':False,'error':str(e)},ensure_ascii=False).encode(),
                            'application/json; charset=utf-8',status=400)
                    return self.erro(str(e),400,self.sessao())
                except Exception:
                    LOG.exception('Erro POST %s',path)
                    if quer_json:
                        return self.send_bytes(
                            json.dumps({'ok':False,'error':'Falha interna ao salvar. Consulte o log.'},
                                       ensure_ascii=False).encode(),
                            'application/json; charset=utf-8',status=500)
                    return self.erro('Falha interna ao salvar. Consulte o log.',500,self.sessao())

        try:
            self.servidor=ThreadingHTTPServer((self.host,self.porta),Handler)
        except OSError as exc:
            LOG.error('Porta %s indisponível: %s',self.porta,exc)
            raise RuntimeError(
                f'A porta {self.porta} já está em uso. Feche o outro AUTOSEG (ou o processo '
                f'antigo) antes de iniciar. Nenhuma versão antiga deve continuar atendendo /cliente.'
            ) from exc
        self.porta=self.servidor.server_port
        self.thread=threading.Thread(target=self.servidor.serve_forever,daemon=True)
        self.thread.start()
        host_exibido='127.0.0.1' if self.host in ('0.0.0.0','::') else self.host
        return f'http://{host_exibido}:{self.porta}'

    def url_rede(self):
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                s.connect(('192.0.2.1',80))
                ip=s.getsockname()[0]
            return f'http://{ip}:{self.porta}'
        except OSError:
            return f'http://127.0.0.1:{self.porta}'

    def parar(self):
        if self.servidor:
            self.servidor.shutdown();self.servidor.server_close();self.servidor=None
