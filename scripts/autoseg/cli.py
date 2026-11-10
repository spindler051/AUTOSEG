#!/usr/bin/env python3
"""Operational shortcuts for the AUTOSEG MAIN and DEV environments."""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)
sys.path.insert(0, str(ROOT))
from officina.core import runtime_config  # noqa: E402

STATE = runtime_config.user_data_dir() / "cli"
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(STATE, 0o700)

LEGACY = {
    "dev": "INICIAR_AUTOSEG_DEV.command",
    "app": "INICIAR_AUTOSEG.command",
    "app-web": "INICIAR_AUTOSEG_COM_WEB.command",
    "app-local": "INICIAR_AUTOSEG_SEM_WEB.command",
    "api": "INICIAR_SERVIDOR_API.command",
    "server": "INICIAR_SERVIDOR_DEV.command",
    "site": "INICIAR_SITE_DEV.command",
    "site-prod": "INICIAR_SITE.command",
    "check": "VERIFICAR_AUTOSEG_DEV.command",
    "paths": "MOSTRAR_CAMINHOS.command",
    "test": "RODAR_TESTES.command",
}


def say(text):
    print(text, flush=True)


def legacy(name, args):
    script = ROOT / "scripts/autoseg" / name
    os.execv(str(script), [str(script), *args])


def main_env():
    env = os.environ.copy()
    env.pop("AUTOSEG_DEV", None)
    env.pop("AUTOSEG_SERVER_DATA", None)
    base = env.get("AUTOSEG_BASE")
    if not base:
        candidate = Path.home() / "gestaoservicos_MAIN"
        if candidate.is_dir():
            base = str(candidate)
        else:
            base = subprocess.check_output(
                [str(PYTHON), "-c",
                 "from officina.core import runtime_config; "
                 "print(runtime_config.server_data_dir())"],
                cwd=ROOT, text=True).strip()
    env["AUTOSEG_BASE"] = base
    env.setdefault("GESTAO_BANCO", str(Path(base) / "dados.db"))
    return env


def dev_env():
    env = os.environ.copy()
    env["AUTOSEG_DEV"] = "1"
    for key in ("AUTOSEG_BASE", "GESTAO_BANCO"):
        env.pop(key, None)
    server_data = subprocess.check_output(
        [str(PYTHON), "-c",
         "from officina.core import runtime_config; "
         "print(runtime_config.server_data_dir())"],
        cwd=ROOT, env=env, text=True).strip()
    env["AUTOSEG_SERVER_DATA"] = server_data
    env["CLIENTE_PORT"] = "8865"
    env["PRESTADOR_PORT"] = "8866"
    env["AUTOSEG_WEB_ACCESS"] = "0"
    return env


def environment(context):
    return dev_env() if context == "dev" else main_env()


def ports(context, service):
    if context == "dev":
        if service == "site":
            return (8865, 8866)
        if service == "server":
            return (8766,)
        return (8865, 8866)
    if service == "site":
        return (8765, 8766)
    if service == "server":
        return (8766,)
    return (8765, 8766)


def pid_path(context, service):
    return STATE / f"{context}-{service}.pid"


def log_path(context, service, suffix=""):
    return STATE / f"{context}-{service}{suffix}.log"


def port_pids(port):
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True, text=True, timeout=4)
        return [int(item) for item in result.stdout.split() if item.isdigit()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def all_port_pids(port_list):
    pids = []
    for port in port_list:
        for pid in port_pids(port):
            if pid not in pids:
                pids.append(pid)
    return pids


def running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def command(pid):
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=4)
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def read_pid(context, service):
    try:
        return int(pid_path(context, service).read_text().strip())
    except (OSError, ValueError):
        return None


def write_pid(context, service, pid):
    path = pid_path(context, service)
    path.write_text(str(pid))
    os.chmod(path, 0o600)


def clear_pid(context, service):
    pid_path(context, service).unlink(missing_ok=True)


def tail(path, lines=20):
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def wait_ports(port_list, proc=None, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(port_pids(port) for port in port_list):
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.2)
    return all(port_pids(port) for port in port_list)


def start_service(context, service):
    env = environment(context)
    port_list = ports(context, service)
    in_use = all_port_pids(port_list)
    if service == "server" and context == "main" and port_pids(8765):
        say("A MAIN sobe site + API no mesmo processo. Use `./autoseg stop site` "
            "antes de iniciar um server separado.")
        return 1
    if in_use:
        if context == "dev" and service == "server":
            say(f"8766 já está ocupada (PID {', '.join(map(str, in_use))}), "
                "provavelmente pela MAIN. Pare a MAIN antes de iniciar o "
                "server DEV.")
        else:
            say(f"{context.upper()} {service} já está usando as portas "
                f"{', '.join(map(str, port_list))}: PID(s) "
                f"{', '.join(map(str, in_use))}.")
        return 0
    if service == "site":
        cmd = [str(PYTHON), "-u",
               str(ROOT / "flavors/autoseg/modules/servidor_backend.py"), "--site"]
    else:
        cmd = [str(PYTHON), "-u",
               str(ROOT / "flavors/autoseg/modules/servidor_backend.py"),
               "--api", "--host", "127.0.0.1", "--port", "8766"]
    log = log_path(context, service)
    with log.open("a", encoding="utf8") as out:
        os.chmod(log, 0o600)
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
    if not wait_ports(port_list, proc):
        say(f"Não foi possível iniciar {context.upper()} {service}.")
        say(tail(log))
        return 1
    pids = all_port_pids(port_list)
    write_pid(context, service, pids[0])
    say(f"{context.upper()} {service} iniciado. PID {pids[0]}. "
        f"Portas: {', '.join(map(str, port_list))}.")
    say(f"Log: {log}")
    return 0


def stop_service(context, service):
    if context == "main" and service == "server" and port_pids(8765):
        say("A API da MAIN está embutida no site. Use `./autoseg stop site`.")
        return 0
    if context == "dev" and service == "server":
        pids = port_pids(8766)
        if pids and "--api" not in command(pids[0]):
            say("A porta 8766 pertence à MAIN (site), não ao server DEV. "
                "Nada foi parado.")
            return 0
    pid = read_pid(context, service)
    port_list = ports(context, service)
    pids = []
    if pid and running(pid):
        pids.append(pid)
    for item in all_port_pids(port_list):
        if item not in pids:
            pids.append(item)
    if not pids:
        clear_pid(context, service)
        say(f"{context.upper()} {service} não está rodando.")
        return 0
    alvos = []
    for pid in pids:
        text = command(pid)
        if not text:
            continue
        if service in ("site", "server") and "servidor_backend.py" not in text:
            say(f"PID {pid} não parece ser o {service} AUTOSEG; ignorando.")
            continue
        if service == "tunnel" and "cloudflared" not in text:
            say(f"PID {pid} não parece ser um túnel cloudflared; ignorando.")
            continue
        alvos.append(pid)
    if not alvos:
        clear_pid(context, service)
        say(f"{context.upper()} {service} não está rodando.")
        return 0
    for pid in alvos:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 6
    while time.time() < deadline and any(running(pid) for pid in alvos):
        time.sleep(0.2)
    for pid in alvos:
        if running(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    clear_pid(context, service)
    say(f"{context.upper()} {service} parado. PID(s) {', '.join(map(str, alvos))}.")
    return 0


def cloudflared():
    return shutil.which("cloudflared") or (
        "/usr/local/bin/cloudflared"
        if Path("/usr/local/bin/cloudflared").is_file() else None)


def tunnel_urls(context, port_list):
    found = {}
    for port in port_list:
        log = log_path(context, "tunnel", f"-{port}")
        try:
            text = log.read_text(errors="replace")
        except OSError:
            continue
        match = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
        if match:
            found[port] = match[-1]
    return found


def start_tunnel(context):
    if context == "dev":
        env = environment(context)
        result = subprocess.run(
            [str(PYTHON), str(ROOT / "flavors/autoseg/modules/tuneis_dev.py"),
             "iniciar"], cwd=ROOT, env=env)
        return result.returncode
    exe = cloudflared()
    if not exe:
        say("cloudflared não encontrado.")
        return 1
    started = []
    for port in (8765, 8766):
        marker = f"cloudflared tunnel --url http://127.0.0.1:{port}"
        try:
            current = subprocess.run(
                ["pgrep", "-f", marker], capture_output=True, text=True,
                timeout=4).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            current = []
        if current:
            say(f"Túnel MAIN {port} já ativo: PID {', '.join(current)}.")
            continue
        log = log_path(context, "tunnel", f"-{port}")
        with log.open("w", encoding="utf8") as out:
            os.chmod(log, 0o600)
            proc = subprocess.Popen(
                [exe, "tunnel", "--url", f"http://127.0.0.1:{port}"],
                cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True)
        write_pid(context, "tunnel", proc.pid)
        started.append(port)
        say(f"Túnel MAIN {port} iniciado: PID {proc.pid}. Log: {log}")
    if not started:
        say("Nenhum túnel novo; os túneis existentes foram mantidos.")
        return 0
    for _ in range(40):
        urls = tunnel_urls(context, started)
        if len(urls) == len(started):
            break
        time.sleep(0.5)
    urls = tunnel_urls(context, started)
    for port in started:
        if port in urls:
            say(f"MAIN {port}: {urls[port]}")
        else:
            say(f"MAIN {port}: URL ainda não disponível; confira o log.")
    return 0


def stop_tunnel(context):
    if context == "dev":
        env = environment(context)
        result = subprocess.run(
            [str(PYTHON), str(ROOT / "flavors/autoseg/modules/tuneis_dev.py"),
             "parar"], cwd=ROOT, env=env)
        return result.returncode
    pids = []
    pid = read_pid(context, "tunnel")
    if pid and running(pid):
        pids.append(pid)
    for port in (8765, 8766):
        marker = f"cloudflared tunnel --url http://127.0.0.1:{port}"
        try:
            found = subprocess.run(
                ["pgrep", "-f", marker], capture_output=True, text=True,
                timeout=4).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            found = []
        for item in found:
            if item.isdigit() and int(item) not in pids:
                pids.append(int(item))
    if not pids:
        clear_pid(context, "tunnel")
        say("Nenhum túnel MAIN ativo.")
        return 0
    for pid in pids:
        if "cloudflared" in command(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    clear_pid(context, "tunnel")
    say(f"Túneis MAIN parados. PID(s) {', '.join(map(str, pids))}.")
    return 0


def status(context):
    label = "DEV" if context == "dev" else "MAIN"
    say(f"AUTOSEG {label}")
    site_ports = ports(context, "site")
    site_pids = all_port_pids(site_ports)
    say(f"Site: {'ativo' if site_pids else 'parado'} "
        f"({', '.join(f'{port}={port_pids(port)}' for port in site_ports)})")
    api_pids = port_pids(8766)
    if context == "dev":
        if not api_pids:
            say("Server/API 8766: parado")
        else:
            texto = command(api_pids[0])
            if "--api" in texto and "servidor_backend.py" in texto:
                say(f"Server/API 8766: ativo (PID {', '.join(map(str, api_pids))})")
            else:
                say(f"Server/API 8766: ocupada pela MAIN/outro processo "
                    f"(PID {', '.join(map(str, api_pids))})")
    else:
        say(f"API 8766: {'ativa/embutida' if api_pids else 'parada'}"
            + (f" (PID {', '.join(map(str, api_pids))})" if api_pids else ""))
    tunnel_ports = ports(context, "tunnel")
    tunnels = []
    for port in tunnel_ports:
        found = []
        try:
            found = subprocess.run(
                ["pgrep", "-f", f"cloudflared tunnel --url http://127.0.0.1:{port}"],
                capture_output=True, text=True, timeout=4).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            pass
        if found:
            tunnels.append(f"{port}={','.join(found)}")
    say(f"Túneis: {'ativos' if tunnels else 'parados'}"
        + (f" ({'; '.join(tunnels)})" if tunnels else ""))
    return 0


def stop_all(context):
    stop_tunnel(context)
    stop_service(context, "site")
    stop_service(context, "server")
    return 0


def start_all(context):
    code = start_service(context, "site")
    if code:
        return code
    return start_tunnel(context)


def help_text():
    say("""uso:
  ./autoseg start site|server|tunnel|all
  ./autoseg stop  site|server|tunnel|all
  ./autoseg update [main|dev|all]
  ./autoseg status
  ./autoseg-dev start site|server|tunnel|all
  ./autoseg-dev stop  site|server|tunnel|all
  ./autoseg-dev update
  ./autoseg-dev status

MAIN: site em 8765/8766 (a API vai embutida no site).
DEV:  site em 8865/8866; server/API em 8766 (só com a MAIN parada).
Atualização: `./autoseg update main`, `update dev` ou `update` (MAIN → DEV).
Atualizações isoladas são permitidas.

Compatibilidade: dev, app, app-web, app-local, api, server, site,
site-prod, stop, check, paths, test.""")


def main():
    args = sys.argv[1:]
    context = "main"
    if args and args[0] == "--dev":
        context = "dev"
        args = args[1:]
    if args and args[0] == "dev":
        if len(args) > 1 and args[1] in ("start", "stop", "status"):
            context = "dev"
            args = args[1:]
        else:
            legacy(LEGACY["dev"], args[1:])
            return 0
    if not args or args[0] in ("help", "-h", "--help"):
        help_text()
        return 0
    command_name = args[0]
    if command_name in LEGACY:
        extra = args[1:]
        if command_name == "test" and not extra:
            extra = ["-v"]
        legacy(LEGACY[command_name], extra)
        return 0
    if command_name == "stop" and len(args) == 1:
        env = dev_env()
        result = subprocess.run(
            [str(PYTHON), str(ROOT / "flavors/autoseg/modules/tuneis_dev.py"),
             "parar"], cwd=ROOT, env=env)
        return result.returncode
    if command_name == "update":
        target = args[1] if len(args) > 1 else (
            "dev" if context == "dev" else "all")
        if target not in ("main", "dev", "all"):
            say(f"Alvo inválido: {target}")
            help_text()
            return 1
        if target in ("all", "main"):
            stop_service("main", "site")
            code = start_service("main", "site")
            if code:
                return code
        if target in ("all", "dev"):
            stop_service("dev", "site")
            code = start_service("dev", "site")
            if code:
                return code
        return 0
    if command_name not in ("start", "stop", "status"):
        say(f"Comando desconhecido: {command_name}")
        help_text()
        return 1
    target = args[1] if len(args) > 1 else "all"
    if target not in ("site", "server", "tunnel", "all"):
        say(f"Alvo inválido: {target}")
        help_text()
        return 1
    if command_name == "status":
        return status(context)
    if target == "all":
        return start_all(context) if command_name == "start" else stop_all(context)
    if target == "tunnel":
        return start_tunnel(context) if command_name == "start" else stop_tunnel(context)
    return (start_service(context, target) if command_name == "start"
            else stop_service(context, target))


if __name__ == "__main__":
    raise SystemExit(main())
