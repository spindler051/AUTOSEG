"""AUTOSEG — Portal web completo de prestadores (v4).

Mesmas funções de negócios do desktop: clientes, OS, materiais, imagens, PDF,
financeiro, e-mail (rascunho) e NFS-e (rascunho). Cadastro de prestadores
exclusivo do desktop. Por padrão, escuta APENAS em 127.0.0.1.
"""
import html
import json
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
import re
import secrets
import threading
import time
from decimal import Decimal
from email.parser import BytesParser
from email.policy import default
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote, urlencode as urllib_parse_urlencode
import prestadores_ext as ext
import portal_negocios as neg
import fluxo_os as fluxo
import atendimento_os as aten
import cadastros_v9 as cad9
import feedback_portal as feedback
import api_financeiro as api_fin
import importacao_yaml as yaml_import
import catalogo_servicos as catalogo
import composicao
import estoque_materiais as estoque
import portal_v9 as v9
import links_publicos as links9
import produtividade_os as prod
import solicitacoes_pj as pj_publico
import socket
from versao_app import versao_local

LOG = logging.getLogger('autosseg.portal')
VERSAO_PORTAL = versao_local('9.6.0-dev.6')


CSS_MOBILE = """
.page-actions{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}
.page-actions .btn,.page-actions button{margin:0}
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
.ui-switch{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 16px;font-size:13px;color:#bbb}
.ui-switch a{border:1px solid #555;border-radius:8px;padding:8px 12px;text-decoration:none;color:#fff;background:#1b1b1b}
.ui-switch a.active{background:#ffd400;color:#111;border-color:#ffd400;font-weight:700}
"""


UI_COOKIE = 'autosseg_ui'
CSS_UNSLOP = """
:root{--u-bg:#141312;--u-side:#0f0e0d;--u-card:#1a1816;--u-card-2:#201d1a;--u-raised:#27231f;--u-line:rgba(240,235,226,.08);--u-line-2:rgba(240,235,226,.15);--u-text:#f1ece3;--u-text-2:#b5aca1;--u-muted:#8b8175;--u-accent:#d8a24a;--u-accent-soft:rgba(216,162,74,.12);--u-accent-ink:#1a1308;--u-good:#7cc7a2;--u-bad:#df8585;--u-warn:#d8a24a;--u-font:"Avenir Next","Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;--u-mono:"SF Mono","IBM Plex Mono","Roboto Mono",ui-monospace,monospace;--u-ease:cubic-bezier(.22,1,.36,1)}
body.ui-unslop{margin:0;background:var(--u-bg);color:var(--u-text);font:400 14px/1.55 var(--u-font);-webkit-font-smoothing:antialiased}
body.ui-unslop *{box-sizing:border-box}
body.ui-unslop header{display:none}
body.ui-unslop a{color:var(--u-text);text-decoration:none}
body.ui-unslop a:hover{color:var(--u-accent)}
body.ui-unslop main{margin:0 0 0 264px;max-width:1600px;min-height:calc(100vh - 64px);padding:40px 40px 96px}
body.ui-unslop footer{margin-left:264px;border-top:1px solid var(--u-line);color:var(--u-muted);font:400 12px/1.5 var(--u-mono);text-align:left;padding:16px 40px}
body.ui-unslop h1{font:500 32px/1.08 var(--u-font);letter-spacing:-.02em;margin:0 0 8px;color:var(--u-text)}
body.ui-unslop h2{font:500 16px/1.3 var(--u-font);letter-spacing:0;margin:0 0 14px;color:var(--u-text)}
body.ui-unslop h3{font:500 14px/1.35 var(--u-font);margin:18px 0 8px;color:var(--u-text)}
body.ui-unslop p{margin:0 0 12px}
body.ui-unslop .muted,body.ui-unslop small{color:var(--u-muted)}
body.ui-unslop .good{color:var(--u-good)}
body.ui-unslop .warn{color:var(--u-warn)}
body.ui-unslop .bad{color:var(--u-bad)}
body.ui-unslop .mono{font-family:var(--u-mono);font-variant-numeric:tabular-nums}
body.ui-unslop [hidden]{display:none!important}
body.ui-unslop .ui-switch{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0;font:400 12px/1.5 var(--u-mono);color:var(--u-muted)}
body.ui-unslop .ui-switch span{color:var(--u-muted)}
body.ui-unslop .ui-switch a{display:inline-block;padding:0 0 2px;border:0;border-bottom:1px solid transparent;border-radius:0;background:transparent;color:var(--u-text-2);font:inherit;text-decoration:none}
body.ui-unslop .ui-switch a:hover{color:var(--u-accent);border-bottom-color:var(--u-accent)}
body.ui-unslop .ui-switch a.active{color:var(--u-text);border-bottom-color:var(--u-line-2);font-weight:400}

/* controls */
body.ui-unslop button,body.ui-unslop .btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;margin:0;padding:0 16px;border:1px solid var(--u-text);border-radius:8px;background:var(--u-text);color:#17130d;font:500 14px/1.2 var(--u-font);letter-spacing:0;text-transform:none;text-decoration:none;white-space:nowrap;cursor:pointer;box-shadow:none;transition:background .15s var(--u-ease),border-color .15s var(--u-ease),color .15s var(--u-ease),transform .12s var(--u-ease)}
body.ui-unslop button:hover,body.ui-unslop .btn:hover{background:#fff;border-color:#fff;color:#17130d}
body.ui-unslop button:active,body.ui-unslop .btn:active{transform:scale(.985)}
body.ui-unslop button:focus-visible,body.ui-unslop .btn:focus-visible,body.ui-unslop a:focus-visible,body.ui-unslop input:focus-visible,body.ui-unslop select:focus-visible,body.ui-unslop textarea:focus-visible{outline:2px solid var(--u-accent);outline-offset:2px}
body.ui-unslop button.secondary,body.ui-unslop .btn.secondary{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-unslop button.secondary:hover,body.ui-unslop .btn.secondary:hover{background:#302b25;border-color:var(--u-line-2);color:var(--u-text)}
body.ui-unslop button.danger,body.ui-unslop .btn.danger{background:rgba(223,133,133,.1);border-color:rgba(223,133,133,.3);color:var(--u-bad)}
body.ui-unslop button.danger:hover,body.ui-unslop .btn.danger:hover{background:rgba(223,133,133,.16);border-color:rgba(223,133,133,.45);color:var(--u-bad)}
body.ui-unslop button.subtle,body.ui-unslop .btn.subtle{background:transparent;border-color:var(--u-line);color:var(--u-text-2)}
body.ui-unslop button.subtle:hover,body.ui-unslop .btn.subtle:hover{background:var(--u-raised);color:var(--u-text)}
body.ui-unslop button:disabled{opacity:.5;cursor:wait}
body.ui-unslop .btn{display:inline-flex}
body.ui-unslop table button,body.ui-unslop table .btn{min-height:32px;padding:0 12px;border-color:var(--u-line-2);background:transparent;color:var(--u-text-2);font-size:12px}
body.ui-unslop table button:hover,body.ui-unslop table .btn:hover{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-unslop form[method="get"] button{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-unslop form[method="get"] button:hover{background:#302b25;border-color:var(--u-line-2);color:var(--u-text)}
body.ui-unslop .iniciar-atendimento{background:var(--u-raised);border-color:var(--u-line-2);color:var(--u-text)}
body.ui-unslop .iniciar-atendimento:hover{background:#302b25;border-color:var(--u-line-2);color:var(--u-text)}

/* forms */
body.ui-unslop label{display:block;margin:16px 0 8px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-unslop label:first-child{margin-top:0}
body.ui-unslop input,body.ui-unslop textarea,body.ui-unslop select{width:100%;min-height:40px;padding:8px 12px;border:1px solid var(--u-line-2);border-radius:8px;background:#11100f;color:var(--u-text);font:400 14px/1.4 var(--u-font);box-shadow:none}
body.ui-unslop input::placeholder,body.ui-unslop textarea::placeholder{color:#6f675e}
body.ui-unslop input:focus,body.ui-unslop textarea:focus,body.ui-unslop select:focus{border-color:var(--u-accent);outline:2px solid var(--u-accent);outline-offset:1px}
body.ui-unslop textarea{min-height:96px;resize:vertical}
body.ui-unslop input[type=checkbox],body.ui-unslop input[type=radio]{width:16px;height:16px;min-height:0;accent-color:var(--u-accent);vertical-align:middle}
body.ui-unslop input[type=file]{padding:8px;font-size:12px;color:var(--u-text-2)}
body.ui-unslop input[type=file]::file-selector-button{margin-right:8px;padding:4px 8px;border:1px solid var(--u-line-2);border-radius:7px;background:var(--u-raised);color:var(--u-text);font:500 12px/1.2 var(--u-font);cursor:pointer}
body.ui-unslop input[readonly]{color:var(--u-muted);background:var(--u-card-2)}
body.ui-unslop fieldset{border:0;padding:0;margin:0;min-width:0}
body.ui-unslop legend{color:var(--u-text);font:500 16px/1.3 var(--u-font);padding:0}
body.ui-unslop .col2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
body.ui-unslop .material-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,.7fr) minmax(0,1fr) auto;gap:8px;align-items:end;margin:12px 0;padding:12px;border:1px solid var(--u-line);border-radius:10px;background:var(--u-card-2)}
body.ui-unslop .material-row-os{grid-template-columns:minmax(0,2fr) minmax(0,.7fr) minmax(0,.7fr) minmax(0,1fr) auto}
body.ui-unslop .material-row label{margin:0 0 4px}
body.ui-unslop .material-row input{min-height:36px}
body.ui-unslop .material-row button{min-height:36px;padding:0 12px}
body.ui-unslop .material-row select{min-height:36px}
body.ui-unslop .composicao-preview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 24px;margin:8px 0 0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .composicao-preview span{min-width:0}
body.ui-unslop .composicao-preview b{color:var(--u-text-2);font-weight:400}
body.ui-unslop .composicao-preview .aviso{grid-column:1/-1;color:var(--u-warn)}
body.ui-unslop .composicao-preview .filho{padding-left:16px;color:var(--u-muted)}
body.ui-unslop .foto-rascunho{display:grid!important;grid-template-columns:120px minmax(0,1fr)!important;gap:16px!important;align-items:start!important;margin:12px 0!important;padding:12px!important;border:1px solid var(--u-line)!important;border-radius:10px!important;background:var(--u-card-2)!important}
body.ui-unslop .foto-rascunho img{width:120px!important;height:90px!important;object-fit:cover!important;border-radius:8px!important}
body.ui-unslop .foto-rascunho label{margin-top:10px}
body.ui-unslop #nota-fiscal-upload>div[style]{border:1px solid var(--u-line)!important;background:var(--u-card-2)!important;border-radius:10px!important}
body.ui-unslop #nota-fiscal-upload{margin-top:8px!important;border-top:0!important;padding-top:0!important}
body.ui-unslop #nota-fiscal-upload>label[style]{font-weight:500!important;color:var(--u-text)!important}

/* surfaces */
body.ui-unslop .card{background:var(--u-card);border:1px solid var(--u-line);border-radius:16px;padding:24px;margin:16px 0;box-shadow:none}
body.ui-unslop .card>h2:first-child,body.ui-unslop .card>h3:first-child{margin-top:0}
body.ui-unslop .notice{background:var(--u-card-2);border:1px solid var(--u-line);border-left:2px solid var(--u-accent);border-radius:10px;color:var(--u-text-2);padding:12px 16px;font-size:12px;line-height:1.55}
body.ui-unslop .notice strong{color:var(--u-text)}
body.ui-unslop .flash{background:rgba(124,199,162,.08);border:1px solid rgba(124,199,162,.25);color:var(--u-text);border-radius:10px;padding:12px 14px}
body.ui-unslop .tag{display:inline-flex;align-items:center;gap:8px;padding:0;border:0;border-radius:0;background:transparent;color:var(--u-text-2);font:400 12px/1.2 var(--u-mono)}
body.ui-unslop .tag::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--u-muted);flex:0 0 5px}
body.ui-unslop .tag:has(+ .good),body.ui-unslop .tag.good::before{background:var(--u-good)}
body.ui-unslop .table-scroll{border:1px solid var(--u-line);border-radius:12px;overflow:auto;background:var(--u-card)}
body.ui-unslop .table-filter-label{display:none}
body.ui-unslop .table-filter-input{max-width:320px;min-height:36px;margin:0 0 8px}
body.ui-unslop .table-filter-count{display:block;margin:0 0 8px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .home-grid .table-filter-label,body.ui-unslop .home-grid .table-filter-input,body.ui-unslop .home-grid .table-filter-count,body.ui-unslop .finance-grid .table-filter-label,body.ui-unslop .finance-grid .table-filter-input,body.ui-unslop .finance-grid .table-filter-count{display:none}
body.ui-unslop table{width:100%;min-width:640px;border-collapse:collapse}
body.ui-unslop th{padding:12px;border-bottom:1px solid var(--u-line);background:transparent;color:var(--u-muted);font:400 12px/1.5 var(--u-mono);text-align:left;text-transform:none;letter-spacing:0;white-space:nowrap}
body.ui-unslop td{padding:12px;border-bottom:1px solid var(--u-line);color:var(--u-text-2);font-size:13px;vertical-align:middle}
body.ui-unslop td:first-child{color:var(--u-text)}
body.ui-unslop tbody tr:last-child td{border-bottom:0}
body.ui-unslop tbody tr:hover{background:rgba(255,255,255,.02)}
body.ui-unslop .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:0 0 20px}
body.ui-unslop .kpi{display:flex;flex-direction:column;justify-content:space-between;gap:16px;min-height:112px;margin:0;padding:20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card);box-shadow:none}
body.ui-unslop .kpi span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .kpi strong{color:var(--u-text);font:500 28px/1 var(--u-mono);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
body.ui-unslop .kpi:first-child strong{color:var(--u-accent)}
body.ui-unslop .cartao{background:var(--u-card);border:1px solid var(--u-line);border-radius:14px;box-shadow:none}
body.ui-unslop .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
body.ui-unslop .stack{display:flex;gap:8px;flex-wrap:wrap}

/* app shell */
body.ui-unslop .app-side{position:fixed;inset:0 auto 0 0;z-index:100;display:flex;flex-direction:column;gap:24px;width:264px;padding:24px 16px 20px;border-right:1px solid var(--u-line);background:var(--u-side)}
body.ui-unslop .side-brand{display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:0 12px;text-decoration:none}
body.ui-unslop .side-brand img{display:block;width:auto;height:32px;max-width:176px;object-fit:contain}
body.ui-unslop .side-brand span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .side-nav{display:flex;flex-direction:column;gap:20px;overflow-y:auto;padding-right:2px}
body.ui-unslop .side-group{display:flex;flex-direction:column;gap:2px}
body.ui-unslop .side-label{margin:0 12px 8px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .side-link{display:flex;align-items:center;gap:10px;min-height:36px;padding:0 12px;border-radius:8px;color:var(--u-text-2);font:400 14px/1.2 var(--u-font);text-decoration:none;transition:background .15s var(--u-ease),color .15s var(--u-ease)}
body.ui-unslop .side-link svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-muted);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-unslop .side-link:hover{background:var(--u-raised);color:var(--u-text)}
body.ui-unslop .side-link:hover svg{color:var(--u-text-2)}
body.ui-unslop .side-link.active{background:var(--u-raised);color:var(--u-text);box-shadow:inset 2px 0 0 var(--u-accent)}
body.ui-unslop .side-link.active svg{color:var(--u-accent)}
body.ui-unslop .side-foot{display:flex;flex-direction:column;gap:16px;margin-top:auto;padding-top:16px;border-top:1px solid var(--u-line)}
body.ui-unslop .side-user{display:flex;flex-direction:column;gap:4px;padding:0 12px}
body.ui-unslop .side-user strong{color:var(--u-text);font:500 14px/1.3 var(--u-font)}
body.ui-unslop .side-user span{color:var(--u-muted);font:400 12px/1.3 var(--u-mono)}
body.ui-unslop .side-tools{display:flex;flex-direction:column;gap:2px}
body.ui-unslop .side-tool{display:flex;align-items:center;justify-content:flex-start;gap:8px;width:100%;min-height:32px;padding:0 12px;border:0;border-radius:8px;background:transparent;color:var(--u-muted);font:400 12px/1.2 var(--u-font);text-align:left;text-decoration:none;cursor:pointer}
body.ui-unslop .side-tool svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-muted);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-unslop .side-tool:hover{background:var(--u-raised);color:var(--u-text)}
body.ui-unslop .side-tool:hover svg{color:var(--u-text-2)}
body.ui-unslop .side-tool-form{display:block;margin:0}
body.ui-unslop .side-version{padding:0 12px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .unslop-credit{padding:0 40px 24px 304px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono);text-align:left}
body.ui-unslop .unslop-credit a{color:var(--u-text-2);border-bottom:1px solid var(--u-line-2)}
body.ui-unslop .unslop-credit a:hover{color:var(--u-accent);border-bottom-color:var(--u-accent)}

/* home */
body.ui-unslop .home-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 24px}
body.ui-unslop .home-toolbar .btn{flex:0 0 auto;white-space:nowrap}
body.ui-unslop .page-meta{color:var(--u-muted);font:400 12px/1.5 var(--u-mono);margin:0}
body.ui-unslop .stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0 0 24px}
body.ui-unslop .stat{display:flex;flex-direction:column;justify-content:space-between;gap:16px;min-height:100px;padding:20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card)}
body.ui-unslop .stat span{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .stat strong{color:var(--u-text);font:500 28px/1 var(--u-mono);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
body.ui-unslop .home-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px;align-items:start}
body.ui-unslop .home-rail{display:flex;flex-direction:column;gap:16px;min-width:0}
body.ui-unslop .panel{padding:20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card)}
body.ui-unslop .panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px}
body.ui-unslop .panel-head h2{margin:0;font-size:16px}
body.ui-unslop .panel-head a{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .panel-head a:hover{color:var(--u-accent)}
body.ui-unslop .finance-figures{display:grid;grid-template-columns:1fr 1fr;gap:16px}
body.ui-unslop .finance-figures span{display:block;margin:0 0 4px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .finance-figures strong{display:block;color:var(--u-text);font:500 20px/1.1 var(--u-mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
body.ui-unslop .finance-figures .accent{color:var(--u-accent)}
body.ui-unslop .shortcut{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--u-line);color:var(--u-text-2);font-size:14px}
body.ui-unslop .shortcut:last-child{border-bottom:0;padding-bottom:0}
body.ui-unslop .shortcut:hover{color:var(--u-text)}
body.ui-unslop .shortcut svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-muted);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-unslop .home-note{margin:16px 0 0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .home-links{margin-top:20px}
body.ui-unslop .home-links details.card{margin:0;padding:14px 18px;border-radius:12px;background:var(--u-card)}
body.ui-unslop .home-links summary{color:var(--u-text-2);font:400 12px/1.5 var(--u-mono);cursor:pointer}
body.ui-unslop .home-links details.card p{margin:12px 0 4px;font-size:12px;overflow-wrap:anywhere}
body.ui-unslop .home-links details.card small{font-size:12px}

/* OS detail */
body.ui-unslop .os-ticket{display:grid;grid-template-columns:200px minmax(0,1fr) auto;margin:0 0 20px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card);overflow:hidden}
body.ui-unslop .os-ticket-stub{display:flex;flex-direction:column;justify-content:space-between;gap:20px;padding:24px;border-right:1px dashed var(--u-line-2)}
body.ui-unslop .os-kicker{margin:0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .os-ticket-stub h2{margin:0;color:var(--u-text);font:500 28px/1 var(--u-mono);letter-spacing:-.03em}
body.ui-unslop .os-status{display:inline-flex;align-items:center;gap:8px;margin:0;color:var(--u-text-2);font:400 12px/1.2 var(--u-mono)}
body.ui-unslop .os-status .dot{width:6px;height:6px;flex:0 0 6px;border-radius:50%;background:var(--u-muted)}
body.ui-unslop .os-status.status--iniciada .dot,body.ui-unslop .os-status.status--em-rota .dot{background:var(--u-accent)}
body.ui-unslop .os-status.status--pendente .dot{background:var(--u-warn)}
body.ui-unslop .os-status.status--concluida .dot{background:var(--u-good)}
body.ui-unslop .os-status.status--cancelada .dot{background:var(--u-bad)}
body.ui-unslop .os-ticket-body{display:flex;flex-direction:column;gap:16px;padding:24px;min-width:0}
body.ui-unslop .os-ticket-client{margin:0;color:var(--u-text);font:500 20px/1.3 var(--u-font)}
body.ui-unslop .os-ticket-meta{margin:0;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .os-ticket-stats{display:grid;grid-template-columns:repeat(3,minmax(80px,1fr));gap:16px}
body.ui-unslop .os-ticket-stats span{display:block;margin:0 0 4px;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .os-ticket-stats strong{display:block;color:var(--u-text);font:500 14px/1.35 var(--u-font)}
body.ui-unslop .os-ticket-stats .money{color:var(--u-accent);font-family:var(--u-mono);font-variant-numeric:tabular-nums}
body.ui-unslop .os-ticket-actions{display:flex;flex-direction:column;align-items:stretch;justify-content:center;gap:8px;padding:24px;border-left:1px solid var(--u-line)}
body.ui-unslop .os-ticket-actions .btn{min-height:36px;font-size:12px;white-space:nowrap}
body.ui-unslop .os-workflow{display:grid;grid-template-columns:1fr .8fr 1.2fr;gap:16px;margin:0 0 20px}
body.ui-unslop .os-work-status{order:-2}
body.ui-unslop .os-work-draft{order:-1}
body.ui-unslop .os-workflow .card{margin:0;padding:20px;border-radius:16px}
body.ui-unslop .os-workflow .card h2{margin:0 0 12px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-unslop .os-workflow .card p{margin:0 0 8px;font-size:12px;line-height:1.5}
body.ui-unslop .os-workflow .card .muted{font-size:12px}
body.ui-unslop .os-workflow .card form{margin:0}
body.ui-unslop .os-workflow .card button{margin-top:8px;min-height:36px;font-size:12px}
body.ui-unslop .os-workflow .card input[type=file]{padding:8px;font-size:12px}
body.ui-unslop .os-workflow .card .tag{margin-right:6px}
body.ui-unslop .os-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px;align-items:start}
body.ui-unslop .os-main{min-width:0;padding:24px;border:1px solid var(--u-line);border-radius:16px;background:var(--u-card)}
body.ui-unslop .os-form-unslop{display:block;margin:0}
body.ui-unslop .os-form-unslop>fieldset{border:0;padding:0;margin:0}
body.ui-unslop .os-form-unslop>fieldset>legend{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
body.ui-unslop .os-service-model{margin:0 0 20px;padding:16px;border:1px solid var(--u-line);border-radius:12px;background:var(--u-card-2)}
body.ui-unslop .os-service-model .card{margin:0;padding:0;border:0;background:transparent}
body.ui-unslop .os-service-model .card h2{margin:0 0 8px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-unslop .os-service-model .card p{margin:0 0 8px;font-size:12px}
body.ui-unslop .os-service-model .card label{margin-top:8px}
body.ui-unslop .os-tabs{display:flex;gap:24px;margin:0 0 24px;padding:0;border-bottom:1px solid var(--u-line);border-radius:0;background:transparent;overflow-x:auto}
body.ui-unslop .os-tab{position:relative;flex:0 0 auto;display:inline-flex;align-items:baseline;gap:8px;min-height:0;padding:0 0 12px;border:0;border-radius:0;background:transparent;color:var(--u-muted);font:500 14px/1.2 var(--u-font);white-space:nowrap}
body.ui-unslop .os-tab:hover{background:transparent;border-color:transparent;color:var(--u-text-2)}
body.ui-unslop .os-tab.active{background:transparent;border-color:transparent;color:var(--u-text)}
body.ui-unslop .os-tab.active::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--u-accent)}
body.ui-unslop .os-tab .tab-index{color:var(--u-muted);font:400 12px/1 var(--u-mono)}
body.ui-unslop .os-tab.active .tab-index{color:var(--u-accent)}
body.ui-unslop .os-panel[hidden]{display:none}
body.ui-unslop .os-panel>p:first-of-type{margin-top:0}
body.ui-unslop .os-rail{display:flex;flex-direction:column;gap:16px;min-width:0}
body.ui-unslop .os-rail .card{margin:0;padding:20px;border-radius:16px}
body.ui-unslop .os-rail .card h2{margin:0 0 12px;color:var(--u-text-2);font:500 12px/1.4 var(--u-font)}
body.ui-unslop .os-rail .card p{font-size:12px;line-height:1.55}
body.ui-unslop .os-rail .card .card{margin:8px 0;padding:12px 0;border:0;border-bottom:1px solid var(--u-line);border-radius:0;background:transparent}
body.ui-unslop .os-rail .card .card:last-child{border-bottom:0;padding-bottom:0}
body.ui-unslop .os-rail .card .card small{display:block;margin-bottom:4px;font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .os-rail .card .card p{margin:0}
body.ui-unslop .os-rail .card form{margin:8px 0 0}
body.ui-unslop .os-rail .card button{min-height:36px;font-size:12px}
body.ui-unslop .os-rail .card input[type=file]{font-size:12px;padding:8px}
body.ui-unslop .os-rail .card details{margin-top:12px}
body.ui-unslop .os-rail .card summary{cursor:pointer;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .os-close-head{margin:24px 0 0;padding-top:20px;border-top:1px solid var(--u-line)}
body.ui-unslop .os-close-head h3{margin:0 0 4px;font-size:16px}
body.ui-unslop .os-close-head p{margin:0 0 8px;color:var(--u-muted);font-size:12px}
body.ui-unslop .os-form-unslop .actions{position:sticky;bottom:8px;z-index:20;display:flex;align-items:center;justify-content:space-between;flex-wrap:nowrap;gap:12px;margin:24px 0 0;padding:8px 12px;border:1px solid var(--u-line);border-radius:12px;background:rgba(20,19,18,.96);box-shadow:0 12px 32px rgba(0,0,0,.25)}
body.ui-unslop .os-form-unslop .actions .actions-buttons button,body.ui-unslop .os-form-unslop .actions .actions-buttons .btn{min-height:36px}
body.ui-unslop .actions-note{flex:1 1 auto;min-width:0;overflow:hidden;color:var(--u-muted);font:400 12px/1.5 var(--u-mono);white-space:nowrap;text-overflow:ellipsis}
body.ui-unslop .actions-buttons{display:flex;flex:0 0 auto;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
body.ui-unslop .actions-buttons button,body.ui-unslop .actions-buttons .btn{width:auto!important;margin:0!important}
body.ui-unslop .os-form-unslop .actions .notice{margin:0;font-size:12px}
body.ui-unslop .os-status-block{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 12px;align-items:end;margin:0 0 18px;padding:14px;border:1px solid var(--u-line);border-radius:12px;background:var(--u-card-2)}
body.ui-unslop .os-status-block label{grid-column:1/-1;margin:0}
body.ui-unslop .os-status-block p{grid-column:1/-1;margin:0;color:var(--u-muted);font-size:12px;line-height:1.5}
body.ui-unslop .os-status-block button{min-height:40px}
body.ui-unslop .cancel-dialog .cancel-step{padding:24px}
body.ui-unslop .cancel-dialog .cancel-step h2{margin:0 0 8px;color:var(--u-text);font:500 20px/1.2 var(--u-font)}
body.ui-unslop .cancel-dialog .cancel-step p{margin:0 0 12px;color:var(--u-text-2);font-size:13px;line-height:1.55}
body.ui-unslop .cancel-dialog .cancel-step textarea{min-height:110px}
body.ui-unslop .os-tools{margin-top:20px;border-top:1px solid var(--u-line);padding-top:16px}
body.ui-unslop .os-tools summary{cursor:pointer;color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .os-tools summary:hover{color:var(--u-text-2)}

/* finance */
body.ui-unslop .finance-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 20px}
body.ui-unslop .finance-head .page-meta{margin:0}
body.ui-unslop .finance-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-flow:dense;gap:16px;margin-top:16px}
body.ui-unslop .finance-grid .card:nth-child(2),body.ui-unslop .finance-grid .card:nth-child(4){grid-column:1/-1}
body.ui-unslop .finance-grid .card{margin:0}
body.ui-unslop .finance-grid .card h2{font-size:15px}
body.ui-unslop .finance-note{margin:0 0 20px;color:var(--u-text-2);font-size:12px;line-height:1.6}
body.ui-unslop .finance-note strong{color:var(--u-text)}

/* login */
body.ui-unslop.ui-login main{min-height:100vh;max-width:none;margin:0;padding:0}
body.ui-unslop.ui-login main>h1{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
body.ui-unslop.ui-login footer{margin-left:0;padding:14px 32px;text-align:center}
body.ui-unslop.ui-login .unslop-credit{padding:0 32px 18px;text-align:center}
body.ui-unslop .login-shell{display:grid;grid-template-columns:minmax(0,1fr) 460px;min-height:100vh}
body.ui-unslop .login-brand{display:flex;flex-direction:column;justify-content:space-between;gap:48px;padding:56px;border-right:1px solid var(--u-line);background:var(--u-side)}
body.ui-unslop .login-brand img{display:block;width:auto;height:40px;max-width:240px;object-fit:contain}
body.ui-unslop .login-brand-copy{max-width:560px}
body.ui-unslop .login-brand h1,body.ui-unslop .login-brand .login-headline{max-width:13ch;margin:0 0 16px;color:var(--u-text);font:500 40px/1.06 var(--u-font);letter-spacing:-.03em}
body.ui-unslop .login-brand p{max-width:50ch;margin:0;color:var(--u-text-2);font-size:14px;line-height:1.65}
body.ui-unslop .login-facts{display:flex;flex-direction:column;gap:12px;margin-top:32px}
body.ui-unslop .login-fact{display:flex;align-items:center;gap:8px;color:var(--u-text-2);font-size:14px}
body.ui-unslop .login-fact svg{flex:0 0 18px;width:18px;height:18px;color:var(--u-accent);fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
body.ui-unslop .login-brand-foot{color:var(--u-muted);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .login-panel{display:flex;flex-direction:column;justify-content:center;padding:56px 48px;background:var(--u-bg)}
body.ui-unslop .login-panel .ui-switch{margin:0 0 32px}
body.ui-unslop .login-panel h2{margin:0 0 8px;font:500 28px/1.2 var(--u-font);letter-spacing:-.02em}
body.ui-unslop .login-lede{margin:0 0 24px;color:var(--u-muted);font-size:12px}
body.ui-unslop .login-form button{width:100%;margin-top:20px}
body.ui-unslop .login-note{margin:20px 0 0;color:var(--u-muted);font-size:12px;line-height:1.6}
body.ui-unslop .login-links{margin-top:28px}
body.ui-unslop .login-links details.card{margin:0;padding:16px;border-radius:12px;background:var(--u-card)}
body.ui-unslop .login-links summary{cursor:pointer;color:var(--u-text-2);font:400 12px/1.5 var(--u-mono)}
body.ui-unslop .login-links p{margin:12px 0 4px;font-size:12px;overflow-wrap:anywhere}
body.ui-unslop .login-links small{font-size:12px}

/* feedback */
body.ui-unslop .feedback-fab{display:none}
body.ui-unslop .feedback-dialog{width:min(640px,calc(100vw - 28px));max-height:calc(100vh - 48px);padding:0;border:1px solid var(--u-line-2);border-radius:16px;background:var(--u-card);color:var(--u-text);box-shadow:0 24px 80px rgba(0,0,0,.55)}
body.ui-unslop .feedback-dialog::backdrop{background:rgba(0,0,0,.7)}
body.ui-unslop .feedback-dialog form{padding:24px}
body.ui-unslop .feedback-dialog h2{margin:0 0 6px;color:var(--u-text);font:500 20px/1.2 var(--u-font)}
body.ui-unslop .feedback-dialog .feedback-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
body.ui-unslop .feedback-dialog .feedback-privacidade{color:var(--u-muted);font-size:12px;line-height:1.6}
body.ui-unslop .feedback-toast{left:50%;bottom:20px;max-width:min(560px,calc(100vw - 28px));padding:12px 16px;border:1px solid var(--u-line-2);border-left:2px solid var(--u-accent);border-radius:10px;background:var(--u-card);color:var(--u-text);box-shadow:0 16px 48px rgba(0,0,0,.45);font-size:12px;line-height:1.5;transform:translateX(-50%)}

/* responsive */
@media(max-width:1200px){
  body.ui-unslop main{padding:32px 28px 88px}
  body.ui-unslop .os-layout,body.ui-unslop .home-grid{grid-template-columns:minmax(0,1fr) 300px}
  body.ui-unslop .os-ticket{grid-template-columns:172px minmax(0,1fr)}
  body.ui-unslop .os-ticket-actions{grid-column:1/-1;flex-direction:row;justify-content:flex-end;border-left:0;border-top:1px solid var(--u-line)}
}
@media(max-width:980px){
  body.ui-unslop .app-side{position:static;width:auto;padding:16px 16px 10px;border-right:0;border-bottom:1px solid var(--u-line);gap:14px}
  body.ui-unslop .side-brand{flex-direction:row;align-items:center;gap:10px}
  body.ui-unslop .side-brand img{height:28px}
  body.ui-unslop .side-brand span{display:none}
  body.ui-unslop .side-nav{flex-direction:row;gap:4px;overflow-x:auto;padding:0 0 4px}
  body.ui-unslop .side-group{flex-direction:row;gap:4px}
  body.ui-unslop .side-label{display:none}
  body.ui-unslop .side-link{white-space:nowrap;min-height:36px;padding:0 12px}
  body.ui-unslop .side-link svg{display:none}
  body.ui-unslop .side-foot{display:none}
  body.ui-unslop .feedback-fab{display:inline-flex}
  body.ui-unslop main{margin:0;padding:28px 20px 80px}
  body.ui-unslop footer{margin-left:0;padding:14px 20px}
  body.ui-unslop .unslop-credit{padding:0 20px 18px}
  body.ui-unslop .os-layout,body.ui-unslop .home-grid{grid-template-columns:1fr}
  body.ui-unslop .os-rail{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
  body.ui-unslop .os-workflow{grid-template-columns:1fr 1fr}
  body.ui-unslop .os-workflow .card:first-child{grid-column:1/-1}
  body.ui-unslop .login-shell{grid-template-columns:1fr}
  body.ui-unslop .login-brand{border-right:0;border-bottom:1px solid var(--u-line);padding:36px 28px;gap:28px}
  body.ui-unslop .login-brand h1,body.ui-unslop .login-brand .login-headline{font-size:32px;max-width:18ch}
  body.ui-unslop .login-facts{display:none}
  body.ui-unslop .login-panel{padding:36px 28px}
}
@media(max-width:720px){
  body.ui-unslop h1{font-size:28px}
  body.ui-unslop .stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  body.ui-unslop .os-ticket{grid-template-columns:1fr}
  body.ui-unslop .os-ticket-stub{border-right:0;border-bottom:1px dashed var(--u-line-2)}
  body.ui-unslop .os-ticket-actions{border-top:1px solid var(--u-line)}
  body.ui-unslop .os-workflow{grid-template-columns:1fr}
  body.ui-unslop .os-workflow .card:first-child{grid-column:auto}
  body.ui-unslop .os-main{padding:20px}
  body.ui-unslop .col2{grid-template-columns:1fr}
  body.ui-unslop .os-status-block{grid-template-columns:1fr}
  body.ui-unslop .os-status-block button{width:100%}
  body.ui-unslop .material-row{grid-template-columns:1fr 1fr}
  body.ui-unslop .material-row>div:first-child{grid-column:1/-1}
  body.ui-unslop .material-row button{grid-column:1/-1;width:100%}
  body.ui-unslop .foto-rascunho{grid-template-columns:1fr!important}
  body.ui-unslop .foto-rascunho img{width:100%!important;height:auto!important}
  body.ui-unslop .os-form-unslop .actions{flex-direction:column;align-items:stretch;bottom:8px}
  body.ui-unslop .actions-buttons{flex-direction:column;align-items:stretch}
  body.ui-unslop .actions-buttons button,body.ui-unslop .actions-buttons .btn{width:100%!important}
  body.ui-unslop .finance-figures{grid-template-columns:1fr 1fr}
  body.ui-unslop .finance-grid{grid-template-columns:1fr}
  body.ui-unslop .finance-grid .card:nth-child(2),body.ui-unslop .finance-grid .card:nth-child(4){grid-column:auto}
  body.ui-unslop .home-toolbar{align-items:flex-start;flex-direction:column}
}
@media(max-width:520px){
  body.ui-unslop main{padding:24px 14px 72px}
  body.ui-unslop .stat-grid{grid-template-columns:1fr 1fr}
  body.ui-unslop .finance-figures{grid-template-columns:1fr}
  body.ui-unslop .login-panel{padding:28px 20px}
  body.ui-unslop .login-brand{padding:28px 20px}
  body.ui-unslop .os-ticket-stub,body.ui-unslop .os-ticket-body,body.ui-unslop .os-ticket-actions{padding:20px}
  body.ui-unslop .os-ticket-stats{grid-template-columns:1fr 1fr}
  body.ui-unslop .panel{padding:16px}
}
"""


SESSOES = {}
TENTATIVAS = {}
LOCK_DOCS = threading.Lock()
LOCK_LOGIN = threading.Lock()
MAX_POST = 90 * 1024 * 1024


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def dinheiro(v):
    return neg.dinheiro(v)
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
  <form method="post" action="/feedback" id="form-feedback">
    <input type="hidden" name="csrf" value="{esc(usuario.get('csrf',''))}">
    <input type="hidden" name="rascunho_id" id="feedback-rascunho-id" value="{rascunho_id}">
    <input type="hidden" name="ui_mode" id="feedback-ui-mode" value="">
    <input type="hidden" name="aba" id="feedback-aba" value="">
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


def layout_unslop(titulo,corpo,usuario=None,nonce=None,path='/',cliente=False,banco=None):
    """Experimental interface: a quiet work-order shell around the same flow."""
    base=layout(titulo,corpo,usuario,nonce,cliente,banco)
    login=not usuario or cliente
    body_class='ui-unslop'+(' ui-login' if login else '')
    base=base.replace('<body>',f'<body class="{body_class}">',1)
    base=base.replace('</style>',CSS_UNSLOP+'</style>',1)
    sidebar=''
    if usuario and not cliente:
        grupos=[
            ('Operação', [('/', 'Início', 'home'), ('/os', 'Ordens de serviço', 'clipboard'),
                          ('/clientes', 'Clientes', 'users')]),
            ('Gestão', [('/servicos', 'Serviços e valores', 'wrench'),
                        ('/financeiro', 'Financeiro', 'wallet'),
                        ('/notas', 'Notas fiscais', 'receipt'),
                        ('/emails', 'E-mails', 'mail')]),
            ('Registros', [('/historico', 'Histórico e relatórios', 'history'),
                           ('/pj-publicas', 'Solicitações PJ', 'building')]),
        ]
        if usuario.get('admin'):
            grupos[-1][1].append(('/feedback/recebidos', 'Feedbacks', 'message'))
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
        sidebar=(f'<aside class="app-side">'
                 '<a class="side-brand" href="/"><img src="/logo.png" alt="AUTOSEG">'
                 '<span>Portal do prestador</span></a>'
                 f'<nav class="side-nav" aria-label="Navegação principal">{blocos}</nav>'
                 '<div class="side-foot">'
                 f'<div class="side-user"><strong>{esc(usuario.get("nome",""))}</strong>'
                 '<span>Prestador · DEV</span></div>'
                 '<div class="side-tools">'
                 '<button type="button" class="side-tool" id="abrir-feedback-side">'
                 f'{icone("message")}<span>Enviar feedback</span></button>'
                 f'<form method="post" action="/sair" class="side-tool-form">'
                 f'<input type="hidden" name="csrf" value="{csrf}">'
                 f'<button class="side-tool" type="submit">{icone("logout")}<span>Sair</span></button></form>'
                 f'<a class="side-tool" href="/ui/classic?next={quote(path,safe="/")}">{icone("layout")}<span>Desativar unslop</span></a>'
                 '</div>'
                 f'<div class="side-version">AUTOSEG {VERSAO_PORTAL} · DEV</div>'
                 '</div></aside>')
        base=base.replace(f'<body class="{body_class}">',
                          f'<body class="{body_class}">{sidebar}',1)
    credit=('<div class="unslop-credit">Interface experimental inspirada em '
            '<a href="https://github.com/heydamir/unslop" target="_blank" '
            'rel="noopener noreferrer">unslop</a>, de Damir Sokolovsky (CC BY 4.0).</div>')
    base=base.replace('</body>',credit+'</body>',1)
    return base


def layout(titulo,corpo,usuario=None,nonce=None,cliente=False,banco=None):
    menus=[('/','Início'),('/clientes','Clientes'),('/os','Ordens de serviço'),('/servicos','Serviços e valores'),('/financeiro','Financeiro'),('/pj-publicas','Solicitações PJ'),('/notas','Notas fiscais'),('/emails','E-mails'),('/historico','Histórico e relatórios')]
    if usuario and usuario.get('admin') and not cliente:
        menus.append(('/feedback/recebidos','Feedbacks'))
    nav=(''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in menus[:4])
         +'<details class="nav-more"><summary>Mais opções</summary>'
         +''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in menus[4:])+'</details>') if usuario else ''
    us=f'<span class="usuario">{esc(usuario["nome"])} · Prestador</span>' if usuario else ''
    ambiente='DEV (testes)' if os.environ.get('AUTOSEG_DEV')=='1' else 'produção'
    footer=f'''<footer>AUTOSEG {VERSAO_PORTAL} · ambiente {ambiente} · relatórios por e-mail e NFS-e em anexo quando cadastrados.</footer>'''
    feedback_html=_dialogo_feedback(None if cliente else usuario, banco)
    logout=(f'<form method="post" action="/sair" class="logout"><input type="hidden" name="csrf" value="{esc(usuario["csrf"])}">'
            '<button class="subtle">Sair</button></form>') if usuario else ''
    if cliente:
        # Portal do Cliente: apenas a logo, grande, sem textos auxiliares.
        topo=('<a class="brand" href="/cliente" style="display:flex;align-items:center">'
              '<img src="/logo.png" alt="AUTOSEG" style="height:88px;max-width:380px;object-fit:contain;display:block">'
              '</a>')
    else:
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
{CSS_MOBILE}{CSS_FEEDBACK}</style><script src="/static/portal.js" defer></script></head><body><header><div class="top">{topo}{us}{logout}</div><nav class="nav">{nav}</nav></header><main><h1>{esc(titulo)}</h1>{corpo}</main>{footer}{feedback_html}</body></html>'''


class PortalPrestador:
    def __init__(self,banco,host=None,porta=8766):
        self.banco=banco
        self.host=host or os.environ.get('PRESTADOR_BIND','127.0.0.1')
        self.porta=int(os.environ.get('PRESTADOR_PORT',porta))
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
        usar_https=os.environ.get('PRESTADOR_HTTPS')=='1' 
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
            def log_message(self,formato,*args):
                LOG.info('%s %s',self.address_string(),formato%args)

            def send_bytes(self,data,mime='text/html; charset=utf-8',filename=None,status=200,cookie=None):
                self.send_response(status)
                self.send_header('Content-Type',mime)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store, max-age=0')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('X-AUTOSEG-Portal',VERSAO_PORTAL)
                self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; img-src 'self'")
                if filename:
                    fname=Path(filename).name
                    # RFC5987 evita injeção no cabeçalho; usa somente nome limpo.
                    self.send_header('Content-Disposition',f"attachment; filename*=UTF-8''{quote(fname)}")
                if cookie:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(data)

            def responder(self,html_text,status=200,cookie=None):
                return self.send_bytes(html_text.encode('utf-8'),status=status,cookie=cookie)

            def ui_unslop(self):
                try:
                    ck=SimpleCookie();ck.load(self.headers.get('Cookie',''))
                    item=ck.get(UI_COOKIE)
                    return bool(item and item.value=='unslop')
                except (KeyError,ValueError):
                    return False

            def pagina(self,titulo,conteudo,s=None,status=200):
                if self.ui_unslop():
                    pagina=layout_unslop(titulo,conteudo,s,
                                         path=urlparse(self.path).path,
                                         banco=banco)
                else:
                    pagina=layout(titulo,conteudo,s,banco=banco)
                if titulo=='Ordens de serviço ativas':
                    # Inert marker: portal.js owns the timer and pauses it while
                    # the feedback dialog is open or a form control is in use.
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
                if cookie: self.send_header('Set-Cookie',cookie)
                self.end_headers()

            def sessao(self):
                try:
                    cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                    tok=cookie['autosseg_session'].value
                except (ValueError,KeyError):return None
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

            def form(self):
                try:t=int(self.headers.get('Content-Length','0'))
                except ValueError: raise ValueError('Tamanho inválido.')
                if not (0<t<=MAX_POST): raise ValueError('O envio deve ter no máximo 90 MB no total.')
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

            def login(self):
                ativo=self.ui_unslop()
                if ativo:
                    troca=('<div class="ui-switch"><span>Interface unslop ativa</span>'
                           '<a href="/ui/classic?next=/login">Desativar unslop</a></div>')
                    fatos=(''.join(f'<div class="login-fact">{icone(nome)}<span>{esc(texto)}</span></div>'
                                   for nome,texto in (('clipboard','Ordens e relatórios'),
                                                      ('wallet','Financeiro e repasses'),
                                                      ('file','Notas fiscais e documentos'))))
                    corpo=(f'<div class="login-shell">'
                           f'<section class="login-brand">'
                           f'<div><img src="/logo.png" alt="AUTOSEG">'
                           f'<div class="login-brand-copy">'
                           f'<p class="os-kicker">Portal do prestador</p>'
                           f'<p class="login-headline">A OS, o relatório e o recebimento do prestador no mesmo lugar</p>'
                           f'<p>Acompanhe as ordens atribuídas, registre o serviço e consulte o que já foi recebido.</p>'
                           f'<div class="login-facts">{fatos}</div></div></div>'
                           f'<p class="login-brand-foot">AUTOSEG {VERSAO_PORTAL} · DEV (testes)</p>'
                           f'</section>'
                           f'<section class="login-panel">{troca}'
                           f'<h2>Entrar</h2>'
                           f'<p class="login-lede">Use seu e-mail e senha de prestador.</p>'
                           f'<form class="login-form" method="post" action="/login">'
                           +campos_escuros('E-mail','email',kind='email',required=True)
                           +campos_escuros('Senha','senha',kind='password',required=True)
                           +'<button type="submit">Entrar</button></form>'
                           f'<p class="login-note">O cadastro de prestadores é realizado somente pelo aplicativo desktop.</p>'
                           f'<div class="login-links">{v9.barra_links("prestador")}</div>'
                           f'</section></div>')
                    return self.pagina('Acesso do prestador',corpo)
                else:
                    troca=('<div class="ui-switch"><span>Interface:</span>'
                           '<a class="active" href="/ui/classic?next=/login">Atual</a>'
                           '<a href="/ui/unslop?next=/login">Ativar unslop</a></div>')
                return self.pagina('Acesso do prestador',troca+card('Entrar',
                    '<form method="post" action="/login">'
                    +campos_escuros('E-mail','email',kind='email',required=True)
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
                    os_link = (f'<a href="/os/{p["os_id"]}">OS {esc(p["os_id"])}</a>'
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
                    with ext.db(banco) as c:
                        lista=c.execute('''SELECT o.id,o.numero_os,o.status,o.descricao,o.data_abertura,
                            o.valor_total,cl.nome cliente,MAX(d.versao) versao
                            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
                            LEFT JOIN os_documentos d ON d.os_id=o.id AND d.tipo='relatorio_pdf'
                            WHERE o.status NOT IN ('Aberta','Iniciada','Pendente')
                            GROUP BY o.id ORDER BY o.id DESC LIMIT 500''').fetchall()
                    rows=[]
                    for x in lista:
                        link_pdf=(botao('Baixar PDF',f'/os/{x["id"]}/pdf') if x['versao'] else
                            '<span class="warn">Não publicado</span> '+botao('Abrir para republicar',f'/os/{x["id"]}','secondary'))
                        rows.append((f'<a href="/os/{x["id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                            f'<span class="tag">{esc(x["status"])}</span>',dinheiro(x['valor_total']),
                            str(x['versao'] or '—'),link_pdf))
                    resumo=f'<p class="muted">Ordens encerradas, relatórios publicados e PDFs centralizados. Anexos só durante o encerramento da OS.</p>'
                    return self.pagina('Histórico e relatórios',resumo+card('Histórico e documentos',
                        tabela(['OS','Cliente','Situação','Valor','Versão PDF','Documento'],rows)),s)
                ordem=parse_qs(urlparse(self.path).query).get('ordem',['status'])[0]
                if ordem not in ('status','data','cliente','os'):ordem='status'
                lista=ext.listar_os_compartilhadas(banco,ordem)
                rows=[]
                for x in lista:
                    estado=x['status']
                    try:
                        with ext.db(banco) as c:
                            if ext.em_rota_atual(c, x['id']): estado='Em rota'
                    except Exception:
                        pass
                    rows.append((f'<a href="/os/{x["id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                        f'<span class="tag">{esc(estado)}</span>',esc(x.get('responsavel') or 'Não atribuído'),
                        esc(x.get('participantes') or 'Nenhum')))
                opcoes_ordem=[
                    ('status','Situação: iniciadas e pendentes primeiro'),
                    ('data','Data de criação: mais recentes'),
                    ('cliente','Cliente: A-Z'),
                    ('os','Número da OS'),
                ]
                filtro_ordem=(f'<form method="get" action="/os" class="actions">'
                    +select('Ordenar por','ordem',opcoes_ordem,ordem)
                    +'<button type="submit">Aplicar</button></form>')
                return self.pagina('Ordens de serviço ativas',
                    '<p class="muted">Todos os prestadores veem as OS abertas, iniciadas e pendentes, mesmo quando atribuídas a outros.</p>'
                    +f'<div class="page-actions">{botao("+ Nova OS rápida","/os/rapida")} {botao("Nova OS completa","/os/nova","secondary")}</div>'
                    +filtro_ordem
                    +card('Ordens de serviço',tabela(['OS','Cliente','Status','Responsável','Participantes'],rows)),s)

            def inicio(self,s):
                with ext.db(banco) as c:
                    o=c.execute('''SELECT COUNT(*) total,
                        SUM(CASE WHEN status='Aberta' THEN 1 ELSE 0 END) abertas,
                        SUM(CASE WHEN status='Iniciada' THEN 1 ELSE 0 END) iniciadas,
                        SUM(CASE WHEN status='Pendente' THEN 1 ELSE 0 END) pendentes,
                        SUM(CASE WHEN status='Concluída' THEN 1 ELSE 0 END) concluidas FROM ordens_servico''').fetchone()
                    f=c.execute('''SELECT SUM(CASE WHEN status='Recebido' THEN valor ELSE 0 END) recebido,
                        SUM(CASE WHEN status='Aguardando pagamento' THEN valor ELSE 0 END) pendente FROM financeiro''').fetchone()
                    cl=c.execute("SELECT COUNT(*) total FROM clientes WHERE status!='Inativo'").fetchone()
                    recentes=c.execute('''SELECT o.id,o.numero_os,o.status,o.valor_total,o.data_abertura,cl.nome cliente
                        FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
                        ORDER BY o.id DESC LIMIT 6''').fetchall()
                if self.ui_unslop():
                    def stat(rotulo,valor):
                        return (f'<div class="stat"><span>{esc(rotulo)}</span>'
                                f'<strong>{esc(valor)}</strong></div>')
                    stats=(stat('OS abertas',o['abertas'] or 0)
                           +stat('OS iniciadas',o['iniciadas'] or 0)
                           +stat('OS pendentes',o['pendentes'] or 0)
                           +stat('OS concluídas',o['concluidas'] or 0))
                    linhas=[]
                    for x in recentes:
                        linhas.append((f'<a href="/os/{int(x["id"])}">{esc(x["numero_os"])}</a>',
                                       esc(x['cliente']),chip_status(x['status']),
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
                           f'<a class="btn" href="/os/nova">{icone("plus")}Nova OS</a></div>'
                           f'<div class="stat-grid">{stats}</div>'
                           f'<div class="home-grid">'
                           f'<section class="panel"><div class="panel-head"><h2>Ordens recentes</h2>'
                           f'<a href="/os">Ver todas</a></div>{recentes_html}</section>'
                           f'<aside class="home-rail">'
                           f'<section class="panel"><div class="panel-head"><h2>Financeiro</h2>'
                           f'<a href="/financeiro">Abrir</a></div>'
                           f'<div class="finance-figures">'
                           f'<div><span>A receber</span><strong class="accent">{dinheiro(f["pendente"] or 0)}</strong></div>'
                           f'<div><span>Recebido</span><strong>{dinheiro(f["recebido"] or 0)}</strong></div>'
                           f'</div></section>'
                           f'<section class="panel"><div class="panel-head"><h2>Atalhos</h2></div>'
                           f'{atalhos_html}</section>'
                           f'<p class="home-note">Clientes ativos: {int(cl["total"] or 0)}</p>'
                           f'</aside></div>'
                           f'<div class="home-links">{v9.barra_links("prestador")}</div>'
                           f'<p class="home-note">As alterações são registradas com o prestador autenticado. '
                           f'E-mails e notas fiscais dependem das APIs externas.</p>')
                    return self.pagina('Visão geral',corpo,s)
                indic=[('OS abertas',o['abertas'] or 0),('OS iniciadas',o['iniciadas'] or 0),
                       ('OS pendentes',o['pendentes'] or 0),('OS concluídas',o['concluidas'] or 0),
                       ('A receber',dinheiro(f['pendente'])),('Recebido',dinheiro(f['recebido'])),('Clientes ativos',cl['total'])]
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
                filtro=('<form method="get" action="/feedback/recebidos">'
                        +select('Filtrar por situação na DEV','status',opcoes,status_dev)
                        +'<button type="submit">Filtrar</button></form>')
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
                else:
                    triagem=''
                    detalhes=''
                return self.pagina(f'Feedback FB-{item["id"]:04d}',
                    botao('← Voltar','/feedback/recebidos' if admin else '/','secondary')
                    +card('Relato',
                        f'<p class="muted">{esc(item["criado_em"])} · {esc(item["prestador_nome"])} · '
                        f'<code>{esc(item["pagina"])}</code></p>'
                        f'<p style="white-space:pre-wrap">{esc(item["mensagem"])}</p>'
                        f'<p><span class="tag">{esc(item["status_dev"])}</span></p>')
                    +resposta+triagem+detalhes,s)

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
                    +'<form method="get" action="/servicos">'+campos_escuros('Buscar serviço por nome ou descrição','q',termo)+'<button>Pesquisar</button></form>'
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
                importar=(f'<form method="post" enctype="multipart/form-data" action="/servicos/yaml">{self.hidden(s)}'
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
                filtro=(" WHERE nome LIKE ? ESCAPE '!' OR documento LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!' OR email LIKE ? ESCAPE '!' "
                       "OR replace(replace(replace(documento,'.',''),'/',''),'-','') LIKE ? ESCAPE '!' ") if busca else ''
                params=[]
                if busca:
                    termo='%'+busca.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
                    docs=cad9.digitos(busca)
                    params=[termo]*4+['%'+docs+'%' if docs else 'documento_nunca_corresponde']
                with ext.db(banco) as c:
                    total=c.execute('SELECT COUNT(*) FROM clientes'+filtro,params).fetchone()[0]
                    rows=c.execute('SELECT id,nome,documento,cidade,telefone,email,status FROM clientes'+filtro+' ORDER BY nome LIMIT ? OFFSET ?',params+[limite,offset]).fetchall()
                linhas=[]
                for r in rows:
                    linhas.append((f'<a href="/clientes/{r["id"]}">{esc(r["nome"])}</a>',esc(cad9.formatar_documento(r['documento'])),esc(r['cidade']),
                        esc(r['telefone']),esc(r['email']),esc(r['status'])))
                pesquisa='<form method="get" action="/clientes">'+campos_escuros('Buscar por nome, CPF/CNPJ, cidade ou e-mail','q',busca)+'<button>Buscar cliente</button></form>'
                navegacao=f'<p class="muted">{total} cliente(s) encontrado(s). Página {pagina}.</p>'
                if pagina>1:navegacao+=botao('Anterior','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina-1}),'secondary')
                if offset+len(rows)<total:navegacao+=botao('Próximos clientes','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina+1}),'secondary')
                return self.pagina('Clientes','<div class="page-actions">'
                    +botao('+ Novo cliente','/clientes/novo')
                    +botao('Novo orçamento','/orcamento','secondary')
                    +botao('Nomear síndico / gestor','/clientes/responsaveis','secondary')+'</div>'
                    +card('Pesquisar clientes',pesquisa)
                    +card('Clientes cadastrados',navegacao+tabela(['Nome','Documento','Cidade','Telefone','E-mail','Status'],linhas)),s)

            def orcamento_form(self, s, erro='', cliente_id=None,
                               servicos=None, materiais=None, aviso='',
                               validade='30', condicoes=''):
                """Orçamento com cliente, vários serviços e materiais adicionais."""
                with ext.db(banco) as c:
                    clientes = c.execute(
                        "SELECT id,nome,documento FROM clientes WHERE status!='Inativo' "
                        "ORDER BY nome LIMIT 500").fetchall()
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

                form = (f'<form method="post" action="/orcamento/pdf" id="form-orcamento">{self.hidden(s)}'
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
                    f'<form method="post" enctype="multipart/form-data" action="/orcamento/yaml">'
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
                with ext.db(banco) as c:
                    x=c.execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone() if cid else None
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
                    +'<details class="ajuda"><summary>Acesso histórico (opcional, não usado no login CPF)</summary><p>Use somente quando houver necessidade de acesso legado por ID. Senhas de contas pessoais são criadas pelo próprio usuário.</p>'
                    +campos_escuros('Senha do cliente (opcional)','senha_cliente',kind='password')
                    +campos_escuros('Confirmar senha','confirmar_senha_cliente',kind='password')+'</details>'
                    +'<button type="submit">Salvar cliente</button></form>')
                if not cid:
                    importar=(f'<form method="post" action="/clientes/yaml" enctype="multipart/form-data">{self.hidden(s)}'
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
                    corpo+=f'<form method="post" action="/clientes/{cid}/desativar">{self.hidden(s)}<button class="secondary">Desativar (preservar histórico)</button></form>'
                    corpo+=f'<form method="post" action="/clientes/{cid}/excluir" data-confirm="Confirma a exclusão deste cliente sem ordens de serviço?">{self.hidden(s)}<button class="danger" type="submit">Excluir cliente sem OS vinculadas</button></form>'
                return self.pagina('Novo cliente' if cid is None else 'Editar cliente',card('Dados cadastrais',corpo),s)

            def os_rapida_form(self, s, erro='', q='', cliente_id=None):
                """Abertura rápida com busca e cartões, no mesmo padrão do Portal do Cliente."""
                with ext.db(banco) as c:
                    if cliente_id:
                        cliente = c.execute(
                            "SELECT id,nome,tipo_pessoa,cidade,bairro,email FROM clientes "
                            "WHERE id=? AND status!='Inativo'", (int(cliente_id),)).fetchone()
                        if not cliente:
                            return self.os_rapida_form(
                                s, 'Cliente não encontrado ou inativo. Escolha outro na lista.', q=q)
                        prestadores = c.execute(
                            "SELECT id,nome FROM prestadores WHERE ativo=1 AND excluido=0 ORDER BY nome").fetchall()
                        local = ' · '.join(x for x in (cliente['tipo_pessoa'], cliente['bairro'],
                                                       cliente['cidade']) if x)
                        form = (f'<form method="post" action="/os/rapida/salvar">{self.hidden(s)}'
                                f'<input type="hidden" name="cliente_id" value="{int(cliente["id"])}">'
                                f'<p class="passo">{esc(cliente["nome"])}'
                                + (f' · {esc(local)}' if local else '') + '</p>'
                                + textarea('Solicitação / descrição do serviço', 'descricao',
                                           required=True)
                                + select('Forma de pagamento', 'forma_pagamento',
                                         [('', 'Selecione a forma de pagamento')]
                                         + [(z, z) for z in neg.OS_FORMAS], '', required=True))
                        if prestadores:
                            form += select('Atribuir prestador (opcional)', 'prestador_id',
                                           [('', 'Não atribuir agora')]
                                           + [(x['id'], x['nome']) for x in prestadores])
                        else:
                            form += ('<p class="muted">Nenhum prestador ativo cadastrado; '
                                     'a OS ficará sem responsável.</p>')
                        form += ('<p class="notice">A OS será criada como <b>Aberta</b>. '
                                 'Ela só fica <b>Pendente</b> se o atendimento for iniciado e '
                                 'encerrado com essa situação.</p>'
                                 '<button type="submit" style="width:100%">Criar OS aberta</button></form>')
                        aviso = f'<p class="bad">{esc(erro)}</p>' if erro else ''
                        return self.pagina(
                            'Nova OS rápida — ' + cliente['nome'],
                            card('Solicitação para ' + cliente['nome'], aviso + form)
                            + botao('← Voltar e escolher outro cliente', '/os/rapida', 'secondary'), s)

                    termo = str(q or '').strip()[:120]
                    esc_like = termo.replace('!', '!!').replace('%', '!%').replace('_', '!_')
                    digitos = cad9.digitos(termo)
                    if termo:
                        filtro = ("WHERE status!='Inativo' AND (nome LIKE ? ESCAPE '!' "
                                  "OR documento LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!' "
                                  "OR email LIKE ? ESCAPE '!'")
                        params = ['%' + esc_like + '%'] * 4
                        if digitos:
                            filtro += " OR documento LIKE ? ESCAPE '!'"
                            params.append('%' + digitos + '%')
                        filtro += ")"
                        clientes = c.execute(
                            "SELECT id,nome,tipo_pessoa,cidade,bairro,email,documento "
                            "FROM clientes " + filtro + " ORDER BY nome LIMIT 100",
                            params).fetchall()
                    else:
                        clientes = c.execute(
                            "SELECT id,nome,tipo_pessoa,cidade,bairro,email,documento "
                            "FROM clientes WHERE status!='Inativo' ORDER BY nome LIMIT 100").fetchall()

                busca = ('<form method="get" action="/os/rapida" class="busca-pj">'
                         '<label for="q-os-rapida">Buscar condomínio, empresa ou cliente</label>'
                         '<div class="busca-linha">'
                         f'<input id="q-os-rapida" name="q" type="search" value="{esc(termo)}" '
                         'placeholder="Digite o nome, CNPJ/CPF, cidade ou e-mail" autocomplete="off">'
                         '<button type="submit">Buscar</button></div></form>')
                cards = []
                for x in clientes:
                    local = ' · '.join(y for y in (x['tipo_pessoa'], x['bairro'], x['cidade']) if y)
                    contato = (' · ' + esc(x['email'])) if x['email'] else ''
                    cards.append(
                        '<article class="resultado-organizacao">'
                        f'<h3>{esc(x["nome"])}</h3><p>{esc(local)}{contato}</p>'
                        f'<a class="btn" href="/os/rapida?cliente={int(x["id"])}">'
                        'Abrir OS para este cliente</a></article>')
                lista = ''.join(cards) or (
                    '<p class="aviso-claro">Nenhum cliente encontrado para esta busca. '
                    'Tente outro nome ou <a href="/clientes/novo">cadastre o cliente</a>.</p>')
                aviso = f'<p class="bad">{esc(erro)}</p>' if erro else ''
                return self.pagina(
                    'Nova OS rápida',
                    card('1. Encontre o cliente',
                         '<p>Busque pelo nome, CNPJ/CPF, cidade ou e-mail. '
                         'Ao escolher, você informa a solicitação e cria a OS.</p>' + aviso + busca)
                    + card('2. Escolha o cliente', '<div class="lista-organizacoes-pj">'
                           + lista + '</div>')
                    + botao('Nova OS completa', '/os/nova', 'secondary')
                    + botao('Voltar às OS', '/os', 'secondary'), s)

            def os_form(self,s,oid=None,preenchimento=None,erro=None):
                with ext.db(banco) as c:
                    cl=c.execute("SELECT id,nome,cidade,bairro,endereco,numero FROM clientes WHERE status!='Inativo' ORDER BY nome").fetchall()
                    o=c.execute('SELECT * FROM ordens_servico WHERE id=?',(oid,)).fetchone() if oid else None
                    mat=c.execute('SELECT * FROM materiais_os WHERE os_id=? ORDER BY id',(oid,)).fetchall() if oid else []
                    eventos=c.execute('SELECT * FROM os_eventos WHERE os_id=? ORDER BY id DESC LIMIT 150',(oid,)).fetchall() if oid else []
                    anexos=c.execute('''SELECT a.id,a.nome_original,a.criado_em,a.tipo,
                        COALESCE(v.legenda,'') legenda,COALESCE(v.visivel,1) visivel
                        FROM os_anexos a LEFT JOIN v9_anexos_visiveis v ON v.anexo_id=a.id
                        WHERE a.os_id=? ORDER BY a.id''',(oid,)).fetchall() if oid else []
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
                d=dict(o) if o else {}
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
                    for k in ('tecnico','valor_mao_obra','valor_materiais_manual','custo_materiais','valor_total_override','forma_pagamento'):
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
                unslop=self.ui_unslop()
                rotulo_salvar='Salvar rascunho' if unslop else 'SALVAR RASCUNHO'
                classe_form=' class="os-form-unslop" novalidate' if unslop else ''
                titulo=(('Ordem de serviço' if unslop else f'OS {d["numero_os"]}') if oid else 'Nova ordem de serviço')
                action=f'/os/{oid}/salvar' if oid else '/os/nova/salvar'
                corpo='' if unslop else botao('← Ordens de serviço','/os','secondary')
                if oid and not unslop:
                    corpo+=f'<p class="muted">Número da OS: <b>{esc(d["numero_os"])}</b> · '
                    f'identificador interno do link: <code>/os/{oid}</code></p>'
                if oid and unslop:
                    cliente_info=next((x for x in cl if x['id']==d.get('cliente_id')),None)
                    cliente_nome=cliente_info['nome'] if cliente_info else ''
                    local=' · '.join(str(cliente_info[k] or '') for k in ('bairro','cidade') if cliente_info and cliente_info[k])
                    resp_nome=next((p['nome'] for p in prestadores if p['id']==responsavel),'Não atribuído')
                    status_exibicao='Em rota' if em_rota and d['status'] in ext.ATIVAS else d['status']
                    partes_meta=[x for x in (local,f'Aberta em {data_curta(d.get("data_abertura"))}',f'/os/{oid}') if x]
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
                        f'<div class="os-ticket-actions"><a class="btn secondary" href="/os/{oid}/pdf-preview">'
                        +icone('file')+'Baixar preview do PDF</a></div>'
                        '</section>')
                if erro:corpo+=card('Corrija o arquivo YAML',f'<p class="bad" id="yaml-erro-rev08">{esc(erro)}</p><p>Você pode selecionar outro arquivo sem sair da OS.</p>')
                if preenchimento:
                    corpo+=('<p class="notice" id="yaml-importado-rev08" data-yaml-importado="1">'
                        'Prévia importada. Seus campos já digitados podem ser restaurados; '
                        'revise as informações antes de confirmar a OS.</p>'
                        '<button class="secondary" type="button" id="desfazer-yaml-rev08">'
                        'Desfazer importação YAML</button>')
                rotulo_assumir='Assumir OS' if unslop else 'ASSUMIR OS'
                rotulo_em_rota='Em rota' if unslop else 'EM ROTA'
                rotulo_cancelar_rota='Cancelar em rota' if unslop else 'CANCELAR EM ROTA'
                rotulo_iniciar='Iniciar OS' if unslop else 'INICIAR OS'
                aviso_rota='Em rota — deslocamento iniciado.' if unslop else '🚗 EM ROTA — deslocamento iniciado.'
                texto_iniciar=('Iniciar OS registra o início efetivo e encerra o deslocamento. '
                               'Se a OS não tiver responsável, ela será atribuída a você.'
                               if unslop else
                               'INICIAR OS registra o início efetivo do atendimento e encerra o deslocamento. '
                               'Ao iniciar uma OS sem responsável, ela será atribuída a você com registro explícito.')
                if oid and unslop:
                    corpo+='<div class="os-workflow">'
                if oid and d['status'] in ext.ATIVAS:
                    importar=(f'<form method="post" action="/os/{oid}/yaml" enctype="multipart/form-data">{token}'
                      '<label for="importar-relatorio-yaml">Preencher relatório com arquivo YAML (até 64 KB)</label>'
                      '<input type="file" id="importar-relatorio-yaml" name="yaml" accept=".yaml,.yml" required>'
                      '<label><input type="checkbox" name="substituir" value="1"> Substituir campos e materiais já preenchidos</label>'
                      '<button type="submit" class="secondary">Pré-visualizar relatório YAML</button></form>'
                      '<p class="muted">Modelo pronto: <a href="/modelos/relatorio.yaml">Baixar YAML de relatório</a>. Nada será salvo sem confirmação.</p>')
                    corpo+='<section class="card os-work-import"><h2>Importação de relatório</h2>'+importar+'</section>'
                    if responsavel==s['pid']:
                        corpo+=('<section class="card os-work-draft"><h2>Rascunho</h2>'
                            +botao('Recuperar rascunho',f'/os/{oid}/rascunho','secondary')
                            +'<p class="muted">Os dados salvos no servidor são recarregados ao abrir a OS.</p></section>')
                if oid:
                    nome_resp=next((p['nome'] for p in prestadores if p['id']==responsavel),'Não atribuído')
                    if unslop:
                        corpo+='<section class="card os-work-status"><h2>Andamento</h2>'
                    corpo+=f'<p><span class="tag">{esc(d["status"])}</span> · Responsável: <b>{esc(nome_resp)}</b> · Participantes: {esc(", ".join(p["nome"] for p in particip) or "Nenhum")}</p>'
                    if d['status'] in ext.ATIVAS:
                        iniciado = bool(andamento and andamento['iniciado_em'])
                        if responsavel != s['pid'] and (responsavel is None or d['status']=='Pendente'):
                            corpo+=f'<form method="post" action="/os/{oid}/assumir">{token}<button type="submit" class="secondary">{rotulo_assumir}</button></form>'
                            corpo+='<p class="muted">Assume a responsabilidade sem iniciar o atendimento.</p>'
                        if responsavel in (None, s['pid']) and not iniciado:
                            if em_rota:
                                corpo+=f'<p class="notice">{aviso_rota}</p>'
                                corpo+=f'<form method="post" action="/os/{oid}/cancelar-rota">{token}<button type="submit" class="secondary">{rotulo_cancelar_rota}</button></form>'
                            else:
                                corpo+=f'<form method="post" action="/os/{oid}/em-rota">{token}<button type="submit" class="secondary">{rotulo_em_rota}</button></form>'
                            corpo+=f'<form method="post" action="/os/{oid}/iniciar">{token}<button type="submit" class="iniciar-atendimento">{rotulo_iniciar}</button></form>'
                            corpo+=f'<p class="muted">{texto_iniciar}</p>'
                        elif iniciado:
                            corpo+='<p class="good">Atendimento iniciado em '+esc(andamento['iniciado_em'])+' por '+esc(andamento['ator_inicio'])+'.</p>'
                        elif responsavel is not None and responsavel != s['pid']:
                            corpo+='<p class="notice">OS atribuída a outro prestador. Todos podem visualizar; para assumir, aguarde pendência ou peça transferência.</p>'
                    if unslop:
                        corpo+='</section>'
                if oid and unslop:
                    corpo+='</div>'
                if not cl:
                    corpo+='<p class="notice">Cadastre primeiro um cliente.</p>'
                    return self.pagina(titulo,corpo,s)
                dados_cliente=[(x['id'],f'{x["nome"]} — ID {x["id"]}') for x in cl]
                # Carregar rascunho salvo pelo prestador se existir
                try:
                    rasc_salvo = ext.obter_rascunho_web(banco, oid, s['pid']) if oid else None
                    if rasc_salvo:
                        for k,v in rasc_salvo.items():
                            if k.startswith('_'):
                                continue
                            if k not in d and isinstance(v,(str,list)):
                                d[k]=v
                except Exception:
                    rasc_salvo = None
                if unslop:
                    corpo+='<div class="os-layout"><div class="os-main">'
                corpo+=f'<form method="post" action="{action}" id="form-os"{classe_form} data-ajax-preserve="1" enctype="multipart/form-data">{token}'
                if d.get('composicao_yaml'):
                    import json as _json_comp
                    corpo+=('<input type="hidden" name="composicao_yaml" value="'
                            +esc(_json_comp.dumps(d['composicao_yaml'],ensure_ascii=False))+'">')
                servicos_ativos=catalogo.listar(banco,ativos=True)
                bloco_modelo=''
                if servicos_ativos:
                    import json
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
                    if unslop:
                        bloco_modelo='<div class="os-service-model">'+bloco_modelo+'</div>'
                corpo+='<input type="hidden" name="materiais_presentes" value="1">'
                if oid:
                    corpo+=f'<input type="hidden" name="_versao_os" value="{esc(d.get("atualizado_em") or "") }">'
                cliente_nome_cancel=next((x['nome'] for x in cl if x['id']==d.get('cliente_id')),'')
                status_bloco=''
                cancelar_dialogo=''
                if oid and d['status'] in ext.ATIVAS:
                    status_atual='Pendente' if d['status']=='Pendente' else ''
                    status_bloco=('<div class="os-status-block">'
                        +select('Situação do atendimento','acao_status',
                            [('', 'Selecione a situação'),('Pendente','Pendente'),('Concluída','Concluído')],
                            status_atual,required=True)
                        +'<button type="button" class="danger" id="abrir-cancelar-os">Cancelar OS</button>'
                        +'<p class="muted">Pendente mantém a OS ativa. Concluído publica o PDF e encerra. '
                         'Para cancelar, use o botão vermelho e confirme o número da OS.</p>'
                        +'</div>')
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
                        '<button type="submit" class="danger" name="cancelar_os" value="1" formnovalidate>'
                        'Cancelar OS definitivamente</button>'
                        '</div></div></dialog>')
                corpo+='<fieldset><legend>Identificação e serviço</legend>'
                corpo+=status_bloco
                corpo+=cancelar_dialogo
                if bloco_modelo:
                    corpo+=bloco_modelo
                corpo+='<div class="col2"><div>'
                if solicitacao:
                    nome_cliente_solicitacao=next((x['nome'] for x in cl if x['id']==solicitacao['cliente_id']),'')
                    corpo+=('<p class="notice"><strong>Chamado de origem — somente leitura</strong><br>'
                        f'Cliente: {esc(nome_cliente_solicitacao)} · {esc(solicitacao["criado_em"])}<br>'
                        f'{esc(solicitacao["descricao_original"])}<br>'
                        f'<span class="muted">Número da OS: {esc(d.get("numero_os") or "")}. '
                        'O chamado de origem não é o número da OS.</span></p>')
                    corpo+=f'<input type="hidden" name="cliente_id" value="{int(solicitacao["cliente_id"])}">'
                else:
                    corpo+='<label for="busca-cliente-os">Buscar cliente ou condomínio</label><input type="search" id="busca-cliente-os" placeholder="Digite o nome ou ID para localizar" autocomplete="off">'
                    corpo+=select('Cliente','cliente_id',dados_cliente,d.get('cliente_id',cl[0]['id']),required=True)
                corpo+=campos_escuros('Atendido por (cliente no local)','tecnico',d.get('tecnico','') or '')
                corpo+='</div><div>'+select('Forma de pagamento','forma_pagamento',
                    [('', 'Selecione a forma de pagamento')]+[(z,z) for z in neg.OS_FORMAS],
                    d.get('forma_pagamento') or '')
                corpo+=campos_escuros('Valor de mão de obra (R$)','valor_mao_obra',d.get('valor_mao_obra') or '0',required=True)+'</div></div>'
                corpo+='<p class="muted">Serviço em garantia ou cortesia: informe <b>0,00</b> na mão de obra e <b>0,00</b> no valor cobrado dos materiais. ' \
                       'O custo real dos materiais é interno e não entra no total cobrado.</p>'
                corpo+='<div class="col2"><div>'+campos_escuros('Valor de materiais sem itens detalhados (R$)','valor_materiais_manual',d.get('valor_materiais') or '0')+'</div>'
                corpo+='<div>'+campos_escuros('Total negociado (R$), opcional — substitui a soma','valor_total_override',
                  (d.get('valor_total') if d and abs(float(d.get('valor_total') or 0)-float(d.get('valor_mao_obra') or 0)-float(d.get('valor_materiais') or 0))>0.009 else ''))+'</div></div>'
                corpo+=campos_escuros('Custo real dos materiais (R$) — interno, não cobrado','custo_materiais',d.get('custo_materiais') or '0')
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
                corpo+='</fieldset>'
                corpo+='<fieldset><legend>Materiais utilizados</legend><p class="muted">O total é calculado por mão de obra + materiais; o total negociado, quando informado, prevalece. Materiais detalhados prevalecem sobre o campo de materiais sem itens.</p>'
                corpo+=datalist_unidades_material()
                corpo+='<p class="muted">Deixe a quantidade vazia para itens sem quantidade fixa; nesse caso, o valor informado é o total do item. A unidade é livre: use uma sugestão ou digite a sua.</p>'
                linhas=list(mat)
                corpo+='<div id="lista-materiais">'
                for i,m in enumerate(linhas):
                    item=m['item'] if 'item' in m.keys() else ''
                    qtd=m['quantidade'] if 'quantidade' in m.keys() else ''
                    unidade=(m['unidade'] if 'unidade' in m.keys() else '') or ''
                    unit=m['valor_unitario'] if 'valor_unitario' in m.keys() else ''
                    corpo+='<div class="material-row material-row-os">'
                    corpo+=f'<div><label>Material<input name="material_item[]" value="{esc(item)}" placeholder="Cabo, câmera, fonte..."></label></div>'
                    corpo+=f'<div><label>Quantidade<input name="material_qtd[]" value="{esc(qtd)}" placeholder="—" inputmode="decimal"></label></div>'
                    corpo+=f'<div><label>Unidade{input_unidade_material(unidade)}</label></div>'
                    corpo+=f'<div><label>Valor unitário / total (R$)<input name="material_unit[]" value="{esc(unit)}" placeholder="0,00"></label></div>'
                    corpo+='<button type="button" class="secondary remover-material" title="Remover material">Remover</button></div>'
                corpo+='</div><p class="muted">Nenhum material é obrigatório. Use “Adicionar material” somente se necessário.</p>'
                corpo+=f'''<template id="modelo-material"><div class="material-row material-row-os"><div><label>Material<input name="material_item[]" placeholder="Cabo, câmera, fonte..."></label></div><div><label>Quantidade<input name="material_qtd[]" placeholder="—" inputmode="decimal"></label></div><div><label>Unidade{input_unidade_material("")}</label></div><div><label>Valor unitário / total (R$)<input name="material_unit[]" placeholder="0,00"></label></div><button type="button" class="secondary remover-material">Remover</button></div></template>'''
                corpo+='<button id="adicionar-material" class="secondary" type="button">+ Adicionar material</button>'
                produtos=estoque.listar(banco,ativos=True)
                if produtos:
                    import json as _jm
                    catalogo_json=_jm.dumps([{'nome':x['nome'],'valor':x['venda_centavos']/100} for x in produtos],ensure_ascii=False).replace('<','\\u003c')
                    corpo+='<label for="material-estoque-selecionar">Usar material cadastrado no estoque</label>'
                    corpo+='<select id="material-estoque-selecionar">'+''.join(f'<option value="{i}">{esc(x["nome"])}</option>' for i,x in enumerate(produtos))+'</select>'
                    corpo+='<button class="secondary" id="adicionar-do-estoque" type="button">+ Adicionar do estoque</button>'
                    corpo+=f'<script type="application/json" id="produtos-estoque-os">{catalogo_json}</script>'
                try:
                    cfg_comp=composicao.carregar()
                    bases_comp=cfg_comp.get('bases_percentuais') or {}
                    base_padrao=cfg_comp.get('base_percentuais_padrao') or 'total'
                except (ValueError,OSError):
                    bases_comp={}; base_padrao='total'
                if not bases_comp:
                    bases_comp={'total':{'nome':'Total da OS'},
                                'visita':{'nome':'Visita mínima'}}
                base_atual=str(d.get('base_percentuais') or base_padrao)
                opcoes_base=[(chave,(valor or {}).get('nome',chave))
                             for chave,valor in bases_comp.items()]
                corpo+=select('Base dos percentuais','base_percentuais',opcoes_base,base_atual)
                corpo+='<p class="muted">Visita mínima: os percentuais ficam dentro da visita. Total da OS: os percentuais entram como linhas próprias e a hora recebe o restante.</p>'
                corpo+='<label style="display:flex;align-items:center;gap:8px;font-weight:600;cursor:pointer;margin-top:14px"><input type="checkbox" name="aplicar_composicao" value="1" checked> Aplicar composição padrão (visita, custos e margem)</label>'
                corpo+='<p class="muted">A hora técnica recebe o restante do total e tem mínimo de R$ 100,00. Desmarque para usar somente mão de obra + materiais.</p>'
                corpo+='<p><strong>Total previsto: <span id="total-previsto">—</span></strong></p>'
                corpo+='<div class="composicao-preview" id="composicao-prevista" aria-live="polite"></div></fieldset>'
                corpo+='<fieldset><legend>Situação e relatório técnico</legend>'
                if oid and d['status'] in ext.ATIVAS and contatos_os:
                    selecionados_d = d.get('destinatario_sel[]') or []
                    if isinstance(selecionados_d, str):
                        selecionados_d = [selecionados_d]
                    selecionados_d = [str(x) for x in selecionados_d if str(x).strip()]
                    if not selecionados_d:
                        selecionados_d = ['cliente', 'sindico']
                    corpo+='<fieldset><legend>Destinatários do relatório</legend>'
                    corpo+='<p class="muted">Marque apenas quem deve receber o relatório. A seleção é gravada e usada no envio automático.</p>'
                    for chave,rotulo in (('cliente','Cliente'),('sindico','Síndico'),('administradora','Administradora / imobiliária')):
                        email=contatos_os.get(chave) or ''
                        if email:
                            marcado=' checked' if chave in selecionados_d else ''
                            corpo+=f'<label style="display:block;margin:5px 0"><input type="checkbox" name="destinatario_sel[]" value="{chave}"{marcado}> {rotulo}: {esc(email)}</label>'
                    corpo+=f'<label>E-mails adicionais (separe por vírgula)<input name="emails_adicionais" type="text" maxlength="500" value="{esc(str(d.get("emails_adicionais","")))}" placeholder="financeiro@imobiliaria.com.br"></label>'
                    corpo+='<p class="muted">A lista final é registrada no banco e enviada a todos os destinatários selecionados em um único e-mail.</p></fieldset>'
                corpo+=textarea('Diagnóstico','v9_diagnostico',d.get('v9_diagnostico',(detalhes['diagnostico'] if detalhes else '')) or '',rows=3)
                corpo+=textarea('Serviço executado','v9_execucao',d.get('v9_execucao',(detalhes['execucao'] if detalhes else '')) or '',rows=4)
                corpo+=textarea('Resultado e testes','v9_resultado',d.get('v9_resultado',(detalhes['resultado'] if detalhes else '')) or '',rows=3)
                corpo+=textarea('Relato técnico complementar (histórico interno)','relatorio_tecnico',d.get('relatorio_tecnico',(andamento['rascunho'] if andamento else '')) or '',rows=4)
                if oid and d['status'] in ext.ATIVAS:
                    if andamento and andamento['iniciado_em']:
                        corpo+=f'<p class="good">Atendimento iniciado em {esc(andamento["iniciado_em"])} por {esc(andamento["ator_inicio"])}</p>'
                    else:
                        corpo+='<p class="warn">OS ainda não iniciada. Assumir uma OS não inicia o atendimento automaticamente.</p>'
                if oid and d['status'] in ext.ATIVAS and responsavel==s['pid']:
                    corpo+='<div id="rateio-conclusao"><h3>Técnicos secundários — somente na conclusão</h3>'
                    corpo+='<p class="muted">Distribua valores do mesmo total cobrado à imobiliária. O restante fica com o técnico que conclui a OS. Deixar vazio não cria parcela.</p>'
                    opcoes=[('', 'Sem técnico secundário')]+[(p['id'],p['nome']) for p in prestadores if p['id']!=s['pid']]
                    for i in range(3):
                        corpo+='<div class="col2"><div>'+select('Técnico secundário','rateio_tecnico[]',opcoes,'')+'</div>'
                        corpo+='<div>'+campos_escuros('Valor da parcela (R$)','rateio_valor[]','',placeholder='0,00')+'</div></div>'
                    corpo+='</div>'
                corpo+='</fieldset>'
                if oid and d['status'] in ext.ATIVAS:
                    pode_editar_fotos = (responsavel == s['pid'])
                    pode_nota = (responsavel == s['pid']) or cad9.prestador_admin(banco, s['pid'])
                    corpo+='<fieldset><legend>Fotos do relatório e legendas</legend>'
                    if pode_editar_fotos:
                        corpo+=('<p class="muted">Para adicionar fotos: selecione os arquivos, '
                                'escreva a legenda de cada um e clique em SALVAR RASCUNHO. '
                                'A conclusão gera o PDF com as fotos e legendas. '
                                'Cada foto recebe uma legenda individual e a legenda é salva no SQLite.</p>')
                    else:
                        corpo+=('<p class="muted">Use a seção abaixo para adicionar fotos '
                                'e legendas sem assumir a OS.</p>')
                    if anexos and pode_editar_fotos:
                        corpo+='<div class="fotos-rascunho">'
                        for a in anexos:
                            legenda=esc(a['legenda'] or '')
                            vis=esc(str(a['visivel'] if a['visivel'] is not None else 1))
                            corpo+=('<div class="foto-rascunho" data-anexo-id="'+str(a['id'])+'" style="display:grid;grid-template-columns:150px 1fr;gap:12px;border:1px solid #3b3b3b;padding:10px;margin:10px 0;border-radius:8px">'
                                +'<img src="/arquivos/anexo/'+str(a['id'])+'" alt="Foto da OS" loading="lazy" style="width:150px;height:112px;object-fit:cover;border-radius:6px">'
                                +'<div>')
                            if pode_editar_fotos:
                                corpo+=('<label>Legenda da foto<input name="anexo_legenda[]" maxlength="160" value="'+legenda+'" placeholder="Ex.: Quadro elétrico antes do reparo"></label>'
                                    +'<input type="hidden" name="anexo_id[]" value="'+str(a['id'])+'">'
                                    +select('Incluir no PDF','anexo_visivel[]',[('1','Sim — incluir no PDF'),('0','Não — ocultar por privacidade')],vis)
                                    +f'<button class="secondary" type="submit" formaction="/os/{oid}/anexo/{a["id"]}/girar" formnovalidate>Girar 90°</button>')
                            else:
                                corpo+='<p><b>Legenda:</b> '+(legenda or 'Sem legenda')+'</p>'
                            corpo+='</div></div>'
                        corpo+='</div>'
                    if pode_editar_fotos:
                        corpo+='<div id="anexo-encerramento"><label for="fotos-relatorio">Adicionar fotos novas (até 10, 8 MB por foto)</label>'
                        corpo+='<input type="file" id="fotos-relatorio" name="imagens_encerramento[]" multiple accept="image/jpeg,image/png,image/webp">'
                        corpo+='<div id="lista-fotos-selecionadas" aria-live="polite"></div>'
                        corpo+='<button class="secondary" id="limpar-fotos" type="button" hidden>Limpar fotos selecionadas</button>'
                        corpo+='<p class="muted">A prévia e o campo Legenda da foto aparecem abaixo para cada arquivo. Use <b>SALVAR RASCUNHO</b> para guardar fotos e legendas sem finalizar.</p></div>'
                    else:
                        corpo+=('<p class="notice">Você pode adicionar fotos e alterar '
                                'legendas na seção abaixo, sem assumir a OS.</p>')
                    if pode_nota:
                        corpo+='<div id="nota-fiscal-upload" style="margin-top:14px;border-top:1px solid #444;padding-top:12px">'
                        corpo+='<label for="nota-fiscal-pdf">Anexar nota fiscal (PDF, até 20 MB)</label>'
                        corpo+='<input type="file" id="nota-fiscal-pdf" name="nota_fiscal" accept="application/pdf">'
                        corpo+=f'<button class="secondary" type="submit" formaction="/os/{oid}/nota-fiscal" formnovalidate>Anexar nota fiscal</button>'
                        corpo+='<div style="margin-top:12px;padding:12px;border:1px solid #E2B800;border-radius:8px;background:#2a2617">'
                        corpo+='<label style="display:flex;align-items:center;gap:8px;font-weight:700;cursor:pointer"><input type="checkbox" name="sem_nota_fiscal" value="1" style="width:18px;height:18px"> Não precisa de nota fiscal</label>'
                        corpo+='<p class="muted" style="margin:6px 0 0">Marque esta opção ou anexe o PDF da nota fiscal para poder concluir a OS.</p></div>'
                        corpo+='<p class="muted">A nota fiscal aparece na lista de documentos e é anexada ao e-mail de conclusão ou de reenvio.</p></div>'
                    corpo+='</fieldset>'
                if oid and not unslop:
                    corpo+=f'<p style="margin-top:16px"><span class="tag">{esc(d["status"])}</span> · Responsável: <b>{esc(nome_resp)}</b></p>'
                nota_acoes=('Preencha os dados para criar a OS.' if not oid else
                            f'{d["status"]} · {d["numero_os"]}')
                if unslop:
                    corpo+=('<div class="actions"><div class="actions-note">'+esc(nota_acoes)
                            +'</div><div class="actions-buttons">')
                else:
                    corpo+='<div class="actions">'
                if not oid:
                    corpo+='<button class="secondary" name="modo_envio" value="salvar" type="submit">Criar OS</button>'
                else:
                    if d['status'] in ext.ATIVAS:
                        if responsavel==s['pid']:
                            corpo+=f'<button class="secondary" type="submit" formaction="/os/{oid}/rascunho/salvar" formnovalidate>{rotulo_salvar}</button>'
                            corpo+='<button type="submit" id="confirmar-situacao" name="modo_envio" value="encerrar" data-encerrar="1">Confirmar situação da OS</button>'
                        else:
                            corpo+=('<span class="notice">Esta OS está com outro responsável. '
                                    'Você pode adicionar fotos e legendas abaixo; para salvar '
                                    'rascunho ou concluir, assuma a OS ou peça transferência.</span>')
                    else:
                        corpo+='<span class="notice">OS encerrada: edição bloqueada. Documentos publicados ficam no histórico.</span>'
                if unslop:
                    corpo+='</div></div></form>'
                else:
                    corpo+='</div></form>'
                if unslop and oid:
                    corpo+='</div><aside class="os-rail">'
                if oid and d['status'] in ext.ATIVAS and responsavel != s['pid']:
                    existentes=''
                    for a in anexos:
                        vis=imagens_v9.get(a['id'],{})
                        legenda=esc(vis.get('legenda',''))
                        incluido='1' if vis.get('visivel',1) else '0'
                        existentes+=('<div class="card">'
                            +'<img src="/arquivos/anexo/'+str(a['id'])+'" alt="Foto" loading="lazy" '
                             'style="width:110px;height:90px;object-fit:cover;display:block">'
                            +'<b>'+esc(a['nome_original'])+'</b>'
                            +'<label>Legenda da foto<input name="anexo_legenda[]" maxlength="160" '
                            +f'value="{legenda}" placeholder="Ex.: Quadro antes do reparo"></label>'
                            +f'<input type="hidden" name="anexo_id[]" value="{a["id"]}">'
                            +'<label>Incluir no PDF<select name="anexo_visivel[]">'
                            +f'<option value="1" {"selected" if incluido=="1" else ""}>Sim — incluir</option>'
                            +f'<option value="0" {"selected" if incluido=="0" else ""}>Não — ocultar por privacidade</option>'
                            +'</select></label>'
                            +f'<button class="secondary" type="submit" formaction="/os/{oid}/anexo/{a["id"]}/girar" formnovalidate>Girar 90°</button></div>')
                    corpo+=card('Adicionar fotos e legendas sem assumir a OS',
                        '<p class="muted">Você pode enviar novas fotos e alterar legendas '
                        'mesmo sem ser o responsável; elas entram no relatório quando a OS for concluída.</p>'
                        +f'<form method="post" action="/os/{oid}/fotos" data-ajax-preserve="1" enctype="multipart/form-data">{token}'
                        +('<h3>Legendas das fotos existentes</h3>'+existentes if existentes else '')
                        +'<label for="fotos-relatorio">Adicionar fotos novas (até 10, 8 MB por foto)</label>'
                        +'<input type="file" id="fotos-relatorio" name="imagens_encerramento[]" multiple '
                         'accept="image/jpeg,image/png,image/webp">'
                        +'<div id="lista-fotos-selecionadas" aria-live="polite"></div>'
                        +'<button class="secondary" id="limpar-fotos" type="button" hidden>Limpar fotos selecionadas</button>'
                        +'<p class="muted">A prévia e o campo de legenda aparecem abaixo para cada foto.</p>'
                        +'<button type="submit">Salvar fotos e legendas</button></form>')
                if not oid:
                    corpo+='<p class="muted">Depois de salvar a OS, você poderá atribuir um prestador e, no encerramento, anexar imagens e publicar PDF.</p>'
                    if unslop:
                        return self.pagina(titulo,corpo+'</div></div>',s)
                    return self.pagina(titulo,card('Dados da OS',corpo),s)
                # Atribuição e desatribuição administrativas são exclusivas do desktop.
                if d['status'] in ext.ATIVAS and not unslop:
                    corpo+=card('Atribuição',f'<p>Responsável atual: <b>{esc(next((p["nome"] for p in prestadores if p["id"]==responsavel),"Não atribuído"))}</b></p>'
                        '<p class="muted">Prestadores podem assumir apenas OS não atribuídas. Transferências são feitas no desktop.</p>')
                if anexos and d['status'] not in ext.ATIVAS:
                    itens=[]
                    for a in anexos:
                        vis=imagens_v9.get(a['id'],{})
                        form=(f'<form method="post" action="/os/{oid}/anexo/{a["id"]}/publico">{token}'
                              +campos_escuros('Legenda para o PDF','legenda',vis.get('legenda',''))
                              +select('Incluir no PDF','visivel',[('1','Sim — incluir foto (padrão)'),('0','Não — ocultar por privacidade')],str(vis.get('visivel',1)))
                              +'<button type="submit" class="secondary">Salvar visibilidade</button></form>')
                        itens.append('<div class="card"><img src="/arquivos/anexo/'+str(a['id'])+'" alt="Foto" loading="lazy" style="width:110px;height:90px;object-fit:cover;display:block"><b>'+esc(a['nome_original'])+'</b>'+form+'</div>')
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
                        +f'<form method="post" action="/os/{oid}/publicar">{token}<button class="secondary" type="submit">Publicar nova versão do relatório</button></form>')
                elif publicado:
                    corpo+=card('Documento anterior',
                        f'<p class="muted">Existe uma versão anterior (v{esc(publicado["versao"])}), '
                        'mas o PDF só fica disponível após o encerramento da OS.</p>')
                elif d['status'] in fluxo.FIM:
                    corpo+=card('Documento pendente de publicação',
                        f'<p class="warn">A OS está encerrada, mas o PDF ainda não foi publicado.</p><form method="post" action="/os/{oid}/publicar">{token}<button>Gerar e publicar PDF</button></form>')
                if d['status'] in ext.ATIVAS:
                    if unslop:
                        docs=('<p class="muted">Use o botão <b>Baixar preview do PDF</b> na ficha '
                              'da OS. A prévia não publica, não envia e-mail e não altera o status.</p>')
                    else:
                        docs=(botao('Baixar preview do PDF (não publicado)',
                                    f'/os/{oid}/pdf-preview','secondary')
                              + '<p class="muted">Prévia para conferência do relatório atual. '
                                'Não publica o PDF, não envia e-mail e não altera o status da OS.</p>')
                elif publicado:
                    docs=(botao('Baixar PDF publicado',f'/os/{oid}/pdf')
                        +botao('Preparar e-mail + PDF (.eml)',f'/os/{oid}/email'))
                    if d['status']=='Concluída':
                        docs+=botao('Preparar nota fiscal (.json)',f'/os/{oid}/nota')
                    if responsavel==s['pid'] or cad9.prestador_admin(banco,s['pid']):
                        docs+=(f'<form method="post" action="/os/{oid}/reenviar-email" style="display:inline">'
                               f'{token}<button class="secondary" type="submit">Reenviar e-mail com anexos</button></form>'
                               '<p class="muted">Use após anexar a nota fiscal. O reenvio inclui o PDF do relatório e a NFS-e mais recente.</p>')
                elif d['status'] in fluxo.FIM:
                    docs='<p class="muted">O PDF ainda não foi publicado. Use “Gerar e publicar PDF” acima.</p>'
                else:
                    docs='<p class="muted">O PDF e o rascunho de e-mail serão liberados após a conclusão/cancelamento e publicação do relatório.</p>'
                itens_notas=''
                for nota in notas_fiscais:
                    itens_notas+=(f'<p><a href="/os/{oid}/nota-fiscal/{nota["id"]}">Baixar {esc(nota["nome_original"])}</a>'
                                  f' <small>{esc(nota["criado_em"])}</small></p>')
                if not itens_notas:
                    itens_notas='<p class="muted">Nenhuma nota fiscal anexada.</p>'
                upload_nf=''
                if (responsavel==s['pid'] or cad9.prestador_admin(banco,s['pid'])) and (not unslop or d['status'] not in ext.ATIVAS):
                    upload_nf=(f'<form method="post" action="/os/{oid}/nota-fiscal" enctype="multipart/form-data" style="margin-top:10px">'
                               f'{token}'
                               '<label for="nota-fiscal-concluida">Anexar / atualizar nota fiscal (PDF, até 20 MB)</label>'
                               '<input type="file" id="nota-fiscal-concluida" name="nota_fiscal" accept="application/pdf" required>'
                               '<button type="submit" class="secondary">Anexar nota fiscal</button></form>')
                corpo+=card('Notas fiscais da OS',
                            itens_notas +
                            '<p class="muted">A nota fiscal anexada é enviada junto ao relatório no e-mail de conclusão e em cada reenvio. '
                            'O arquivo fica armazenado no servidor e só é liberado para usuários autorizados.</p>'
                            +upload_nf)
                corpo+=card('Documentos e relatórios',docs+'<p class="muted">O e-mail é enviado automaticamente na conclusão. A nota fiscal é anexada ao e-mail quando cadastrada.</p>')
                def _evento_html(e):
                    quando=data_hora_br(e['criado_em']) if unslop else e['criado_em']
                    return ('<div class="card"><small>'+esc(quando)+' · '+esc(e['ator'])+'</small>'
                            +'<p><b>'+esc(e['acao'])+'</b> — '+esc(e['descricao'])+'</p></div>')
                if unslop:
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
                with ext.db(banco) as c:
                    reg=c.execute('''SELECT f.*,o.numero_os,cl.nome cliente FROM financeiro f
                        JOIN ordens_servico o ON o.id=f.os_id JOIN clientes cl ON cl.id=f.cliente_id
                        JOIN os_encerramentos con ON con.os_id=f.os_id AND con.prestador_id=?
                        ORDER BY f.id DESC''',(s['pid'],)).fetchall()
                pessoal=prod.financeiro_pessoal(banco,s['pid'])
                partes_por_os={item['os_id']:item['partes_centavos']/100
                               for item in pessoal['brutos_proprios']}
                linhas=[]
                for x in reg:
                    acao=(f'<form method="post" action="/financeiro/{x["id"]}/receber" data-confirm="Confirma que o valor foi realmente recebido?">{self.hidden(s)}'
                          '<button type="submit">Confirmar recebimento</button></form>') if x['status']!='Recebido' else '<span class="good">Recebido</span>'
                    minha_parcela=float(x['valor'] or 0)-partes_por_os.get(x['os_id'],0)
                    linhas.append((f'<a href="/os/{x["os_id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                        dinheiro(x['valor']),dinheiro(minha_parcela),
                        esc(x['forma_pagamento']),esc(x['status']),esc(x['vencimento'] or ''),acao))
                banco_texto=prod.obter_dados_bancarios(banco,s['pid'])
                token=self.hidden(s)
                extras=card('Dados bancários para e-mail de cobrança',
                    f'<form method="post" action="/financeiro/banco/salvar">{token}'
                    +textarea('Dados bancários / Pix (texto livre)','dados_bancarios',banco_texto,rows=5)
                    +'<button type="submit">Salvar meus dados bancários</button></form>')
                dividas=[]
                for item in pessoal['repassar_a_colegas']:
                    confirmado=item['pago_centavos']
                    enviado=item['enviado_centavos']
                    a_enviar=item['valor_centavos']-confirmado-enviado
                    if a_enviar>0:
                        # O valor já foi definido no rateio; o finalizador apenas
                        # registra o envio integral. Quem recebe é que confirma.
                        acao=(f'<form method="post" action="/financeiro/repasse">{token}'
                              +f'<input type="hidden" name="os_id" value="{int(item["os_id"])}">'
                              +f'<input type="hidden" name="secundario_id" value="{int(item["tecnico_id"])}">'
                              +f'<button type="submit">Registrar envio de {dinheiro(a_enviar/100)}</button></form>')
                    elif enviado>confirmado:
                        acao='<span class="warn">Aguardando confirmação do colega</span>'
                    else:
                        acao='<span class="good">Confirmado pelo colega</span>'
                    dividas.append((esc(item['numero_os']),esc(item['tecnico']),
                                   dinheiro(item['valor_centavos']/100),
                                   dinheiro(confirmado/100),dinheiro(enviado/100),
                                   dinheiro(a_enviar/100),acao))
                extras+=card('Repasses a outros técnicos',
                    '<p class="muted">O valor da parcela já foi definido no rateio. '
                    'Registre o envio; o colega confirma o recebimento no financeiro dele.</p>'
                    +tabela(['OS','Colega','Parcela','Confirmado','Aguardando confirmação',
                             'A enviar','Ação'],dividas))
                meus=[]
                for x in pessoal['receber_de_colegas']:
                    confirmado=x['pago_centavos']
                    enviado=x['enviado_centavos']
                    pendente=max(0,enviado-confirmado)
                    acao=''
                    if pendente>0:
                        acao=(f'<form method="post" action="/financeiro/repasse/confirmar">{token}'
                              +f'<input type="hidden" name="os_id" value="{int(x["os_id"])}">'
                              +'<button type="submit">Confirmar que recebi</button></form>')
                    meus.append((esc(x['numero_os']),dinheiro(x['valor_centavos']/100),
                                 dinheiro(confirmado/100),dinheiro(pendente/100),
                                 dinheiro((x['valor_centavos']-confirmado)/100),acao))
                extras+=card('Minha produção como técnico secundário',
                    '<p class="muted">O valor só entra como recebido depois da sua confirmação.</p>'
                    +tabela(['OS','Valor','Confirmado','Aguardando confirmação','Restante','Ação'],meus))
                extras+=card('Minha parcela nas OS que eu finalizei',
                    tabela(['OS','Cobrado da imobiliária','Repasses devidos','Minha parcela'],
                        [(esc(x['numero_os']),dinheiro(x['valor']),dinheiro(x['partes_centavos']/100),
                          dinheiro(float(x['valor'])-x['partes_centavos']/100))
                          for x in pessoal['brutos_proprios']]))
                # O KPI é a produção PRÓPRIA do prestador, não o bruto da imobiliária:
                # no encerramento, desconta os rateios dos técnicos secundários;
                # nos rateios em que ele é secundário, soma a parcela dele.
                a_receber=0.0
                recebido=0.0
                for item in pessoal['brutos_proprios']:
                    parte=float(item['valor'] or 0)-item['partes_centavos']/100
                    if item['status']=='Recebido':
                        recebido+=parte
                    elif item['status']=='Aguardando pagamento':
                        a_receber+=parte
                for item in pessoal['receber_de_colegas']:
                    recebido+=item['pago_centavos']/100
                    a_receber+=(item['valor_centavos']-item['pago_centavos'])/100
                a_receber=round(a_receber,2)
                recebido=round(recebido,2)
                if self.ui_unslop():
                    rotulo_a='A receber';rotulo_r='Recebido'
                    return self.pagina('Financeiro',
                        f'<div class="finance-head"><p class="page-meta">{esc(s["nome"])} · produção própria</p></div>'
                        f'<div class="kpis"><div class="kpi"><span>{rotulo_a}</span><strong>{dinheiro(a_receber)}</strong></div>'
                        f'<div class="kpi"><span>{rotulo_r}</span><strong>{dinheiro(recebido)}</strong></div></div>'
                        +'<p class="finance-note"><strong>PIX não comprova recebimento.</strong> '
                        'Confirme apenas depois de verificar o pagamento.</p>'
                        +'<p class="finance-note">Os lançamentos mostram o valor bruto cobrado da imobiliária. '
                        'Os indicadores acima mostram somente a sua parcela, já descontados os rateios dos técnicos secundários.</p>'
                        +card('Lançamentos financeiros das OS que eu finalizei',
                            tabela(['OS','Cliente','Valor bruto','Minha parcela','Forma','Status','Vencimento','Ação'],linhas))
                        +'<div class="finance-grid">'+extras+'</div>',s)
                return self.pagina('Financeiro',f'<div class="kpis"><div class="kpi"><span>A receber (minha produção)</span><strong>{dinheiro(a_receber)}</strong></div>'
                    f'<div class="kpi"><span>Recebido (minha produção)</span><strong>{dinheiro(recebido)}</strong></div></div>'
                    +'<p class="notice">A forma de pagamento PIX não comprova recebimento. Use “Confirmar recebimento” apenas após verificar o pagamento.</p>'
                    +'<p class="muted">Os lançamentos abaixo mostram o valor bruto cobrado da imobiliária. '
                    'Os KPIs acima mostram somente a sua parcela, já descontados os rateios dos técnicos secundários.</p>'
                    +card('Lançamentos financeiros das OS que eu finalizei',
                        tabela(['OS','Cliente','Valor bruto','Minha parcela','Forma','Status','Vencimento','Ação'],linhas))+extras,s)

            def relatorios(self,s,tipo='relatorios'):
                with ext.db(banco) as c:
                    oses=c.execute('''SELECT o.id,o.numero_os,o.status,o.valor_total,o.data_abertura,c.nome cliente
                        FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id ORDER BY o.id DESC LIMIT 500''').fetchall()
                if tipo=='emails':
                    title='E-mails para clientes'; explanation='Gere um rascunho .eml com o PDF anexado. Nenhum e-mail será enviado automaticamente.'
                    acao=lambda o:(botao('Preparar .eml',f'/os/{o["id"]}/email')
                                   if o['status'] in fluxo.FIM else
                                   '<span class="muted">Após encerrar</span>')
                elif tipo=='notas':
                    title='Notas fiscais'; explanation='Rascunho JSON para futura integração NFS-e. Este arquivo NÃO é documento fiscal válido.'
                    acao=lambda o:(botao('Preparar rascunho JSON',f'/os/{o["id"]}/nota')
                                   if o['status'] in fluxo.FIM else
                                   '<span class="muted">Após encerrar</span>')
                else:
                    title='Relatórios gerais e PDFs'; explanation='Histórico das OS e relatórios individuais com materiais, atividades e anexos.'
                    acao=lambda o:(botao('Baixar PDF',f'/os/{o["id"]}/pdf')
                                   if o['status'] in fluxo.FIM else
                                   (botao('Preview PDF',f'/os/{o["id"]}/pdf-preview','secondary')
                                    if o['status'] in ext.ATIVAS else
                                    '<span class="muted">Após encerrar</span>'))
                rows=[(f'<a href="/os/{r["id"]}">{esc(r["numero_os"])}</a>',esc(r['cliente']),esc(r['status']),dinheiro(r['valor_total']),acao(r)) for r in oses]
                resumo=(f'<div class="kpis"><div class="kpi"><span>Ordens de serviço</span><strong>{len(oses)}</strong></div>'
                        f'<div class="kpi"><span>Total exibido</span><strong>{dinheiro(sum(float(x["valor_total"] or 0) for x in oses))}</strong></div></div>') if tipo=='relatorios' else ''
                return self.pagina(title,f'<p class="muted">{esc(explanation)}</p>{resumo}'+card('Ordens disponíveis',tabela(['OS','Cliente','Status','Valor','Ação'],rows)),s)

            def portal_cliente(self,s):
                url_cliente='http://127.0.0.1:'+os.environ.get('CLIENTE_PORT','8765')+'/'
                info=botao('Abrir Portal do Cliente (8765)',url_cliente)
                info+=('<p class="muted">O Portal do Cliente é um site separado, na porta 8765. '
                       'O login dele é por CPF e senha e não se mistura com o login do prestador. '
                       'As solicitações registradas lá aparecem nesta lista e no desktop.</p>')
                with ext.db(banco) as c:
                    web=c.execute("SELECT id,numero_os,status,data_abertura FROM ordens_servico WHERE origem='Portal' ORDER BY id DESC LIMIT 100").fetchall()
                registros=[(f'<a href="/os/{o["id"]}">{esc(o["numero_os"])}</a>',esc(o['status']),esc(o['data_abertura'])) for o in web]
                return self.pagina('Portal do cliente',info+card('Solicitações recebidas pelo portal',tabela(['OS','Situação','Abertura'],registros)),s)

            def documentos(self,s,oid,kind):
                with ext.db(banco) as c:
                    o=c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
                    if not o: return self.erro('OS inexistente.',404,s)
                if kind=='pdf-preview':
                    # Preview is deliberately unpublished: no os_documentos row,
                    # no e-mail, no status change. Any authenticated provider who
                    # can open the OS may download the current draft.
                    with LOCK_DOCS:
                        arq=ext.gerar_pdf(banco,oid)
                        with ext.db(banco) as c:
                            neg.audit(c,s['pid'],'Preview de PDF gerado',oid,'pdf-preview')
                        nome=f'{Path(arq).stem}_preview.pdf'
                        return self.send_bytes(Path(arq).read_bytes(),
                                               'application/pdf',filename=nome)
                prod.controlar_pdf(banco,oid,s['pid'])
                with LOCK_DOCS:
                    if kind in ('pdf','email'):
                        if o['status'] not in fluxo.FIM:
                            return self.erro('PDF disponível somente após o encerramento da OS.',409,s)
                        publicado=fluxo.ultimo_documento(banco,oid)
                        if not publicado:
                            return self.erro('PDF ainda não publicado. Abra esta OS e use Republicar PDF.',409,s)
                        pdf=fluxo.validar_pdf_publicado(publicado)
                    if kind=='pdf':
                        arq=pdf;mime='application/pdf'
                    elif kind=='email':
                        arq=ext.criar_email_rascunho(banco,oid,pdf,prestador_id=s['pid']);mime='message/rfc822'
                    elif kind=='nota':
                        arq=ext.criar_rascunho_fiscal(banco,oid);mime='application/json; charset=utf-8'
                    else:return self.erro('Arquivo inválido.',404,s)
                    with ext.db(banco) as c:
                        neg.audit(c,s['pid'],'Documento gerado',oid,kind)
                    return self.send_bytes(Path(arq).read_bytes(),mime,filename=Path(arq).name)

            def anexo(self,s,aid):
                with ext.db(banco) as c:
                    x=c.execute('SELECT os_id,nome_original,caminho FROM os_anexos WHERE id=?',(aid,)).fetchone()
                    if x and not prod.participou(c,x['os_id'],s['pid']):
                        raise PermissionError('Anexo restrito aos técnicos participantes.')
                if not x:return self.erro('Anexo não encontrado.',404,s)
                arq=Path(x['caminho']).resolve()
                if not arq.is_relative_to(ext.ANEXOS.resolve()):
                    return self.erro('Anexo fora do diretório autorizado.',403,s)
                if not arq.is_file():return self.erro('Arquivo de imagem não encontrado.',404,s)
                mime=mimetypes.guess_type(arq.name)[0] or 'application/octet-stream'
                return self.send_bytes(arq.read_bytes(),mime,filename=x['nome_original'])

            def do_OPTIONS(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                if path==api_fin.API_PREFIX or path.startswith(api_fin.API_PREFIX+'/'):
                    return api_fin.handle(self,path,banco,'OPTIONS')
                self.send_response(204)
                self.send_header('Content-Length','0')
                self.end_headers()

            def do_GET(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                try:
                    if path=='/api/versao':
                        dados=json.dumps({'app':'Gestão de Serviços — AUTOSEG','versao':VERSAO_PORTAL,
                                          'site':'portal do prestador',
                                          'porta':getattr(self.server,'server_port',None),
                                          'login_prestador':'e-mail e senha',
                                          'cadastro_prestadores':'bloqueado no portal web'}).encode('utf-8')
                        return self.send_bytes(dados,'application/json; charset=utf-8')
                    if path in ('/ui/unslop','/ui/classic'):
                        valor='unslop' if path.endswith('unslop') else 'classic'
                        qs=parse_qs(urlparse(self.path).query)
                        destino=qs.get('next',[''])[0]
                        if not (destino.startswith('/') and not destino.startswith('//')
                                and '\r' not in destino and '\n' not in destino):
                            ref=urlparse(self.headers.get('Referer',''))
                            destino=ref.path if ref.path.startswith('/') and not ref.path.startswith('//') else '/login'
                        seguro=('Secure; ' if (usar_https or self.headers.get('CF-Ray')
                                or self.headers.get('X-Forwarded-Proto','').lower()=='https') else '')
                        cookie=(f'{UI_COOKIE}={valor}; Path=/; SameSite=Lax; '
                                f'Max-Age=31536000; {seguro}')
                        return self.redir(destino,cookie)
                    if path==api_fin.API_PREFIX or path.startswith(api_fin.API_PREFIX+'/'):
                        return api_fin.handle(self,path,banco,'GET')
                    if path=='/static/portal.js':
                        return self.send_bytes((Path(__file__).parent/'portal.js').read_bytes(),'application/javascript; charset=utf-8')
                    if path in ('/logo.png','/icone.png','/favicon.ico'):
                        if path == '/logo.png':
                            arquivo = ext.BASE/'logo.png'
                            if not arquivo.is_file():
                                arquivo = Path(__file__).parent/'logo.png'
                        else:
                            arquivo = (ext.caminho_icone(ext.BASE)
                                       or ext.caminho_icone(Path(__file__).parent))
                        if arquivo and arquivo.is_file():
                            return self.send_bytes(arquivo.read_bytes(),'image/png')
                        return self.erro('Imagem não encontrada.',404,self.sessao())
                    if path=='/prestadores' or path.startswith('/prestadores/'):
                        return self.erro('O cadastro de prestadores é feito somente no aplicativo desktop.',403,self.sessao())
                    if path in ('/cliente','/pj') or path.startswith('/cliente/') or path.startswith('/pj/'):
                        return self.erro('O Portal do Cliente fica em http://127.0.0.1:8765/ (porta 8765). '
                                         'Este endereço é o Portal do Prestador.',404,self.sessao())
                    s=self.sessao()
                    if not s:return self.login()
                    if path in ('/modelos/cadastro.yaml','/modelos/relatorio.yaml','/modelos/servico.yaml','/modelos/orcamento.yaml'):
                        nome={'/modelos/cadastro.yaml':'modelo_cadastro_cliente.yaml','/modelos/relatorio.yaml':'modelo_relatorio_os.yaml','/modelos/servico.yaml':'modelo_servico.yaml','/modelos/orcamento.yaml':'modelo_orcamento.yaml'}[path]
                        arquivo=Path(__file__).parent/nome
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
                            comp=composicao.calcular_os(
                                total_centavos=(composicao.centavos_de_reais(total_txt)
                                                if total_txt else None),
                                materiais_centavos=composicao.centavos_de_reais(_valor('materiais','0')),
                                mao_obra_centavos=composicao.centavos_de_reais(_valor('mao_obra','0')),
                                horas=_valor('horas','0') or 0,
                                base_percentuais=(_valor('base','total') or 'total'),
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
                    if path=='/financeiro':return self.financeiro(s)
                    if path=='/relatorios':return self.redir('/historico')
                    if path=='/emails':return self.relatorios(s,'emails')
                    if path=='/notas':return self.relatorios(s,'notas')
                    if path=='/portal-cliente':return self.portal_cliente(s)
                    partes=path.strip('/').split('/')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='editar':
                        return self.servico_form(s,int(partes[1]))
                    if len(partes)==2 and partes[0]=='clientes' and partes[1].isdigit():
                        return self.cliente_form(s,int(partes[1]))
                    if len(partes)==2 and partes[0]=='os' and partes[1].isdigit():
                        return self.os_form(s,int(partes[1]))
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='rascunho':
                        oid=int(partes[1])
                        rascunho=prod.recuperar_rascunho(banco,oid,s['pid'])
                        if not rascunho:return self.erro('Nenhum rascunho salvo para esta OS.',404,s)
                        return self.os_form(s,oid,preenchimento=rascunho['dados'])
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2] in ('pdf','pdf-preview','email','nota'):
                        return self.documentos(s,int(partes[1]),partes[2])
                    if len(partes)==4 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='nota-fiscal' and partes[3].isdigit():
                        oid=int(partes[1]);nid=int(partes[3])
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=s['pid'] and not cad9.prestador_admin(banco,s['pid']):
                                raise PermissionError('Nota fiscal restrita ao responsável ou administrador.')
                        registro,caminho=ext.obter_nota_fiscal(banco,oid,nid)
                        return self.send_bytes(Path(caminho).read_bytes(),'application/pdf',
                                               filename=registro['nome_original'])
                    if len(partes)==3 and partes[0]=='arquivos' and partes[1]=='anexo' and partes[2].isdigit():
                        return self.anexo(s,int(partes[2]))
                    return self.erro('Página não encontrada.',404,s)
                except PermissionError as e:return self.erro(str(e),403,self.sessao())
                except ValueError as e:return self.erro(str(e),409,self.sessao())
                except Exception:
                    LOG.exception('Erro GET %s',path)
                    return self.erro('Falha interna. Consulte o log do aplicativo.',500,self.sessao())

            def do_POST(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                quer_json = ('application/json' in self.headers.get('Accept','')
                             or self.headers.get('X-Requested-With') == 'XMLHttpRequest')
                try:
                    if path==api_fin.API_PREFIX or path.startswith(api_fin.API_PREFIX+'/'):
                        return api_fin.handle(self,path,banco,'POST')
                    d=self.form()
                    if path=='/prestadores' or path.startswith('/prestadores/'):
                        return self.erro('O cadastro de prestadores é feito somente no aplicativo desktop. '
                                         'O portal web não aceita cadastro de prestadores.',403,self.sessao())
                    if path=='/login':
                        ip=self.client_address[0]
                        agora=time.time()
                        with LOCK_LOGIN:
                            tent=[t for t in TENTATIVAS.get(ip,[]) if agora-t<600]
                            if len(tent)>=10: return self.erro('Muitas tentativas. Aguarde dez minutos.',429)
                        p=ext.autenticar(banco,str(d.get('email','')),str(d.get('senha','')))
                        if not p:
                            with LOCK_LOGIN:TENTATIVAS[ip]=tent+[agora]
                            return self.erro('Usuário ou senha incorretos.',401)
                        with LOCK_LOGIN:TENTATIVAS.pop(ip,None)
                        tok=secrets.token_urlsafe(36)
                        SESSOES[tok]={'pid':p['id'],'nome':p['nome'],'cred':p['senha_hash'],
                                      'csrf':secrets.token_urlsafe(32),
                                      'telemetry_session':secrets.token_urlsafe(18),
                                      'exp':time.time()+28800}
                        return self.redir('/',self.cookie(tok))
                    s=self.sessao()
                    self.csrf(s,d)
                    if path=='/sair':
                        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                        if 'autosseg_session' in cookie:SESSOES.pop(cookie['autosseg_session'].value,None)
                        return self.redir('/',self.cookie('',True))
                    pid=s['pid']
                    def _meta_feedback():
                        meta=feedback.contexto(
                            banco,s,
                            feedback.ip_requisicao(self.client_address[0],self.headers),
                            self.headers.get('User-Agent',''))
                        meta['ui_mode']=str(d.get('ui_mode') or ('unslop' if self.ui_unslop() else 'classic'))[:20]
                        meta['aba']=str(d.get('aba') or '')[:80]
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
                        with ext.db(banco) as c:
                            cliente=c.execute('SELECT id,nome,documento FROM clientes '
                                              'WHERE id=? AND status!=\'Inativo\'',
                                              (cliente_id,)).fetchone()
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
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='yaml':
                        oid=int(partes[1]);arq=d.get('yaml')
                        if not isinstance(arq,tuple):raise ValueError('Selecione um arquivo YAML.')
                        with ext.db(banco) as c:
                            os_atual=c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
                        if not os_atual or os_atual['status'] not in ext.ATIVAS:
                            raise ValueError('Somente OS ativas podem importar relatório.')
                        try:pre=yaml_import.relatorio(arq[0],arq[1])
                        except ValueError as erro:return self.os_form(s,oid,erro=str(erro))
                        if not pre:
                            return self.os_form(s,oid,erro='O YAML está em branco. Preencha a seção "os" antes de importar.')
                        pre['_substituir']=str(d.get('substituir',''))=='1'
                        return self.os_form(s,oid,preenchimento=pre)
                    if path=='/clientes/novo/salvar' or (len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='salvar'):
                        senha_nova=str(d.get('senha_cliente',''))
                        confirmar=str(d.get('confirmar_senha_cliente',''))
                        if senha_nova or confirmar:
                            if len(senha_nova)<10:raise ValueError('A senha do cliente deve ter pelo menos 10 caracteres.')
                            if senha_nova!=confirmar:raise ValueError('A confirmação da senha não corresponde.')
                        editar=int(partes[1]) if len(partes)==3 and partes[1].isdigit() else None
                        cid=neg.cliente_salvar(banco,d,pid,editar)
                        if senha_nova:fluxo.definir_senha_cliente(banco,cid,senha_nova)
                        return self.redir(f'/clientes/{cid}')
                    if len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='excluir':
                        neg.cliente_excluir(banco,int(partes[1]),pid)
                        return self.redir('/clientes')
                    if path=='/os/rapida/salvar':
                        texto=(str(d.get('cliente_id','')).strip()
                               or str(d.get('cliente_texto','')).strip())
                        try:
                            cliente_id=int(texto.split('—',1)[0].strip())
                        except (ValueError,TypeError):
                            return self.os_rapida_form(s,erro='Selecione um cliente/condomínio válido na lista.')
                        descricao=str(d.get('descricao','')).strip()
                        if len(descricao)<5:
                            return self.os_rapida_form(s,erro='Descreva a solicitação com pelo menos 5 caracteres.',
                                                       cliente_id=cliente_id)
                        forma=str(d.get('forma_pagamento','')).strip()
                        if forma not in neg.OS_FORMAS:
                            return self.os_rapida_form(
                                s, erro='Escolha a forma de pagamento.',
                                cliente_id=cliente_id)
                        dados={'cliente_id':str(cliente_id),'descricao':descricao,'tecnico':'',
                               'forma_pagamento':forma,'valor_mao_obra':'0','valor_materiais_manual':'0',
                               'materiais_presentes':'1','acao_status':'salvar'}
                        oid=neg.os_salvar(banco,dados,pid)
                        prestador_id=str(d.get('prestador_id','')).strip()
                        if prestador_id:
                            ext.atribuir(banco,oid,int(prestador_id),ator=f'Prestador {s["nome"]}')
                        with ext.db(banco) as c:
                            numero=(c.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                                              (oid,)).fetchone() or {'numero_os': oid})['numero_os']
                        return self.pagina('OS aberta com sucesso',
                            card('OS aberta com sucesso',
                                f'<p class="good">A OS <b>{esc(numero)}</b> foi criada como <b>Aberta</b>.</p>'
                                '<p class="muted">Você não precisa preencher o atendimento agora. '
                                'Abra a OS quando for executar o serviço ou anexar fotos.</p>'
                                +botao('Abrir OS',f'/os/{oid}')
                                +botao('Abrir outra OS rápida','/os/rapida','secondary')
                                +botao('Voltar às OS','/os','secondary')),s)
                    if path=='/os/nova/salvar':
                        oid=neg.os_salvar(banco,d,pid)
                        return self.redir(f'/os/{oid}')
                    if len(partes)==5 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='anexo' and partes[3].isdigit() and partes[4]=='girar':
                        oid=int(partes[1]);aid=int(partes[3])
                        ext.girar_imagem(banco,oid,aid,pid,ator=s['nome'])
                        return self.redir(f'/os/{oid}')
                    if len(partes)==5 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='anexo' and partes[3].isdigit() and partes[4]=='publico':
                        oid=int(partes[1]);aid=int(partes[3])
                        with ext.db(banco) as c:
                            ok=c.execute('SELECT 1 FROM os_anexos WHERE id=? AND os_id=?',(aid,oid)).fetchone()
                        if not ok:raise ValueError('Anexo não pertence à OS.')
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=pid and not cad9.prestador_admin(banco,pid):
                                raise PermissionError('Somente o técnico responsável ou administrador edita a legenda do anexo.')
                        cad9.aprovar_anexo(banco,aid,str(d.get('visivel','0'))=='1',str(d.get('legenda','')),s['nome'])
                        return self.redir(f'/os/{oid}')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='fotos':
                        oid=int(partes[1])
                        with ext.db(banco) as c:
                            os_atual=c.execute('SELECT status FROM ordens_servico WHERE id=?',
                                               (oid,)).fetchone()
                        if not os_atual or os_atual['status'] not in ext.ATIVAS:
                            raise ValueError('Somente OS ativas podem receber fotos.')
                        def _lista(valor):
                            if valor is None:return []
                            return valor if isinstance(valor,list) else [valor]
                        imagens=_lista(d.get('imagens_encerramento[]'))
                        legendas=_lista(d.get('foto_legenda[]'))
                        chaves=_lista(d.get('foto_chave[]'))
                        visiveis=_lista(d.get('foto_visivel[]'))
                        anexo_ids=_lista(d.get('anexo_id[]'))
                        anexo_legendas=_lista(d.get('anexo_legenda[]'))
                        anexo_visiveis=_lista(d.get('anexo_visivel[]'))
                        imagens=[x for x in imagens if isinstance(x,tuple) and x[1]]
                        if not imagens and not anexo_ids:
                            raise ValueError('Selecione uma foto ou altere uma legenda.')
                        if len(imagens)>10:
                            raise ValueError('Envie no máximo 10 fotos por vez.')
                        with ext.db(banco) as c:
                            c.execute('BEGIN IMMEDIATE')
                            for i,(nome,conteudo) in enumerate(imagens):
                                ext.registrar_imagem_transacao(
                                    c,oid,pid,nome,conteudo,
                                    permitir_colaboracao=True,
                                    chave=chaves[i] if i<len(chaves) else None,
                                    legenda=legendas[i] if i<len(legendas) else '',
                                    visivel=str(visiveis[i])!='0' if i<len(visiveis) else 1)
                            for i,anexo_id in enumerate(anexo_ids):
                                try:
                                    anexo_id=int(anexo_id)
                                except (TypeError,ValueError):
                                    continue
                                ext.definir_legenda_anexo_c(
                                    c,oid,anexo_id,
                                    anexo_legendas[i] if i<len(anexo_legendas) else '',
                                    str(anexo_visiveis[i])!='0' if i<len(anexo_visiveis) else 1)
                        return self.redir(f'/os/{oid}')
                    if len(partes)==4 and partes[0]=='os' and partes[1].isdigit() and partes[2:] == ['rascunho','salvar']:
                        oid=int(partes[1])
                        prod.salvar_rascunho(banco,oid,pid,d)
                        dados_rasc = {k: d[k] for k in d.keys() if k not in ('csrf','modo_envio','nota_fiscal')}
                        ext.salvar_rascunho_web(banco,oid,pid,dados_rasc)
                        sem_fechar = dict(d)
                        sem_fechar['acao_status'] = 'salvar'
                        neg.os_salvar(banco,sem_fechar,pid,oid)
                        try:
                            cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                        except Exception:
                            pass
                        if str(d.get('relatorio_tecnico','')).strip():
                            with ext.db(banco) as c:
                                aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')),f'Prestador {s["nome"]}')
                        # A nota fiscal anexada no mesmo envio é gravada junto com o rascunho.
                        arquivo=d.get('nota_fiscal')
                        if isinstance(arquivo,tuple) and arquivo[0]:
                            try:
                                ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1])
                            except Exception as falha:
                                LOG.exception('Falha ao salvar NF no rascunho da OS %s', oid)
                        return self.pagina('Rascunho salvo',card('Rascunho',
                            '<p class="good">Rascunho salvo com sucesso. Ele será recuperado ao reabrir esta OS.</p>'
                            +botao('Voltar à OS',f'/os/{oid}')),s)
                    if len(partes)==3 and partes[0]=='pj-publicas' and partes[1].isdigit() and partes[2] in ('aceitar','recusar'):
                        sid=int(partes[1])
                        if partes[2]=='aceitar':
                            resultado=pj_publico.aceitar(banco,sid,ator=s['nome'])
                            return self.redir(f'/os/{resultado["os_id"]}')
                        pj_publico.recusar(banco,sid,str(d.get('motivo','')),ator=s['nome'])
                        return self.redir('/pj-publicas')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='nota-fiscal':
                        oid=int(partes[1])
                        arquivo=d.get('nota_fiscal')
                        if not isinstance(arquivo,tuple) or not arquivo[0]:
                            raise ValueError('Selecione um arquivo PDF de nota fiscal.')
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=pid and not cad9.prestador_admin(banco,pid):
                                raise PermissionError('Somente o responsável ou administrador pode anexar nota fiscal.')
                        # Anexar a NF não deve apagar os campos já preenchidos no formulário.
                        try:
                            dados_rasc = {k: d[k] for k in d.keys() if k not in ('csrf','modo_envio','nota_fiscal')}
                            ext.salvar_rascunho_web(banco,oid,pid,dados_rasc)
                            try:
                                cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),
                                                     str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                            except Exception:
                                pass
                            if str(d.get('relatorio_tecnico','')).strip():
                                with ext.db(banco) as c:
                                    aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')),f'Prestador {s["nome"]}')
                        except Exception as falha:
                            LOG.exception('Falha ao preservar rascunho ao anexar NF na OS %s', oid)
                        ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1])
                        return self.redir(f'/os/{oid}')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit():
                        oid=int(partes[1]);acao=partes[2]
                        if acao=='rota':
                            prod.marcar_em_rota(banco,oid,pid,str(d.get('ativo','0'))=='1')
                            return self.redir(f'/os/{oid}')
                        if acao=='salvar':
                            if d.get('modo_envio') in ('rascunho','salvar'):
                                try:
                                    dados_rasc = {k: d[k] for k in d.keys() if k not in ('csrf','modo_envio')}
                                    ext.salvar_rascunho_web(banco, oid, pid, dados_rasc)
                                    d2 = dict(d)
                                    d2['acao_status'] = 'salvar'
                                    try:
                                        neg.os_salvar(banco,d2,pid,oid)
                                    except Exception:
                                        pass
                                    try:
                                        cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                                    except Exception:
                                        pass
                                    if d.get('relatorio_tecnico'):
                                        try:
                                            with ext.db(banco) as c:
                                                aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')) or '', f'Prestador {s["nome"]}')
                                        except Exception:
                                            pass
                                    arquivo=d.get('nota_fiscal')
                                    if isinstance(arquivo,tuple) and arquivo[0]:
                                        try:
                                            ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1])
                                        except Exception as falha:
                                            LOG.exception('Falha ao salvar NF no rascunho da OS %s', oid)
                                    return self.pagina('Rascunho salvo',card('Rascunho',
                                        '<p class="good">Rascunho salvo com sucesso.</p>'+botao('Voltar à OS',f'/os/{oid}')),s)
                                except Exception as e:
                                    LOG.exception('Falha ao salvar rascunho da OS %s', oid)
                                    return self.erro(str(e),400,s)
                            cancelar_os = str(d.get('cancelar_os','')).lower() in ('1','on','true','sim')
                            acao_status = 'Cancelada' if cancelar_os else str(d.get('acao_status',''))
                            d = dict(d)
                            d['acao_status'] = acao_status
                            if acao_status in ('Pendente','Concluída','Cancelada') and not d.get('modo_envio'):
                                d = dict(d); d['modo_envio'] = 'encerrar'
                            if d.get('modo_envio')!='encerrar':raise ValueError('Use Confirmar situação da OS.')
                            if acao_status not in ('Pendente','Concluída','Cancelada'):
                                raise ValueError('Selecione a situação da OS: Pendente, Concluída ou Cancelada.')
                            # Só o botão de encerramento aplica o status escolhido.
                            if d.get('modo_envio')=='encerrar' and str(d.get('acao_status',''))=='Concluída' and not (str(d.get('v9_execucao','')).strip() or str(d.get('relatorio_tecnico','')).strip()):
                                raise ValueError('Preencha Serviço executado antes de concluir.')
                            # Exige nota fiscal (ou a opção "não precisa") para concluir a OS.
                            if (d.get('modo_envio')=='encerrar' and str(d.get('acao_status',''))=='Concluída'
                                    and not d.get('sem_nota_fiscal')
                                    and not ext.listar_notas_fiscais(banco, oid)):
                                raise ValueError('Anexe a nota fiscal ou marque "Não precisa de nota fiscal" antes de concluir.')
                            if not str(d.get('relatorio_tecnico','')).strip():
                                d['relatorio_tecnico']='\n'.join(str(d.get(x,'')).strip() for x in ('v9_diagnostico','v9_execucao','v9_resultado') if str(d.get(x,'')).strip())
                            with ext.db(banco) as c:
                                prod._os_ativa_responsavel(c,oid,pid)
                            if str(d.get('acao_status','')) in ('Concluída','Pendente'):
                                destinatarios=prod.destinatarios_para_os(
                                    banco,oid,d.get('destinatario_sel[]'),
                                    str(d.get('emails_adicionais','')))
                            else:
                                destinatarios=None
                            neg.os_salvar(banco,d,pid,oid)
                            prod.limpar_rota_ao_iniciar(banco,oid)
                            if d.get('acao_status') in ('Pendente','Concluída'):
                                prod.registrar_etapa(banco,oid,pid,str(d.get('acao_status')),d)
                            if destinatarios:
                                prod.registrar_envio(banco,oid,destinatarios)
                            cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                            if str(d.get('acao_status','')) in fluxo.PUBLICAVEIS:
                                try: fluxo.publicar_relatorio(banco,oid)
                                except Exception as falha:
                                    LOG.exception('Encerrada OS %s, mas falhou a publicação do PDF',oid)
                                    return self.pagina('OS encerrada — PDF pendente',card('Encerramento salvo',
                                        '<p>Os dados da OS foram preservados. Falhou apenas a publicação do PDF.</p>'
                                        +f'<p class="bad">{esc(str(falha)[:400])}</p>'
                                        +botao('Abrir OS e republicar PDF',f'/os/{oid}')),s,503)
                                if destinatarios:
                                    # Disparo automático do e-mail em segundo plano:
                                    # nunca bloqueia a resposta da conclusão da OS.
                                    try:
                                        import gmail_service
                                        gmail_service.enviar_relatorio_os_concluida(banco, oid, destinatarios)
                                    except Exception as falha:
                                        LOG.exception('Gmail: OS %s — falha ao agendar envio', oid)
                                        prod.registrar_envio(banco, oid, destinatarios, 'falhou', erro=str(falha))
                        elif acao=='publicar':
                            fluxo.publicar_relatorio(banco,oid)
                        elif acao in ('atribuir','liberar'):
                            raise PermissionError('Atribuição administrativa disponível apenas no desktop.')
                        elif acao=='assumir':
                            ext.assumir(banco,oid,pid)
                        elif acao=='em-rota':
                            ext.marcar_em_rota(banco,oid,pid,ator=f'Prestador {s["nome"]}')
                        elif acao=='cancelar-rota':
                            ext.cancelar_em_rota(banco,oid,pid,ator=f'Prestador {s["nome"]}')
                        elif acao=='iniciar':
                            aten.iniciar_assumindo(banco,oid,pid)
                            prod.limpar_rota_ao_iniciar(banco,oid)
                        elif acao=='reenviar-email':
                            with ext.db(banco) as c:
                                if ext.responsavel_atual(c,oid)!=pid and not cad9.prestador_admin(banco,pid):
                                    raise PermissionError('Somente o responsável ou administrador pode reenviar o e-mail.')
                                registro=c.execute('SELECT destinatarios_json FROM produtividade_email WHERE os_id=?',(oid,)).fetchone()
                            destinatarios=None
                            if registro and registro['destinatarios_json']:
                                try:destinatarios=json.loads(registro['destinatarios_json'])
                                except Exception:destinatarios=None
                            # Republica o PDF com as imagens/legendas atuais antes de reenviar.
                            try:
                                fluxo.publicar_relatorio(banco,oid)
                            except Exception:
                                pass
                            import gmail_service
                            gmail_service.enviar_relatorio_os_concluida(banco,oid,destinatarios)
                        else:return self.erro('Operação desconhecida.',404,s)
                        return self.redir(f'/os/{oid}')
                    if path=='/financeiro/banco/salvar':
                        prod.salvar_dados_bancarios(banco,pid,str(d.get('dados_bancarios','')))
                        return self.redir('/financeiro')
                    if path=='/financeiro/repasse':
                        prod.confirmar_repasse(
                            banco,int(d['os_id']),pid,int(d['secundario_id']),None)
                        return self.redir('/financeiro')
                    if path=='/financeiro/repasse/confirmar':
                        prod.confirmar_recebimento_repasse(
                            banco,int(d['os_id']),pid,None)
                        return self.redir('/financeiro')
                    if len(partes)==3 and partes[0]=='financeiro' and partes[1].isdigit() and partes[2]=='receber':
                        with ext.db(banco) as c:
                            autorizado=c.execute('''SELECT 1 FROM financeiro f JOIN os_encerramentos con ON con.os_id=f.os_id
                                WHERE f.id=? AND con.prestador_id=?''',(int(partes[1]),pid)).fetchone()
                        if not autorizado:raise PermissionError('Financeiro restrito ao técnico finalizador.')
                        neg.financeiro_receber(banco,int(partes[1]),pid)
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
