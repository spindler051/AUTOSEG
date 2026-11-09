"""Thin CLI adapter; suitable to replace with Rust CLI later."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import yaml
from workaholic.domain.errors import WorkaholicError
from workaholic.domain.schema import AppSchema
from workaholic.application.service import RecordService
from workaholic.infrastructure.repositories import YamlRepository, SQLiteRepository

def build_parser():
    p = argparse.ArgumentParser(prog="workaholic-cli", description="Workaholic - gerenciamento genérico de registros")
    p.add_argument("--schema", required=True, help="Configuração YAML da aplicação")
    p.add_argument("--storage", choices=["yaml", "sqlite"], default="sqlite")
    p.add_argument("--data", required=True, help="Caminho de arquivo de dados novo ou existente")
    cmd = p.add_subparsers(dest="command", required=True)
    q = cmd.add_parser("entities", help="Listar tipos de entidade")
    q = cmd.add_parser("list", help="Listar registros")
    q.add_argument("entity")
    q.add_argument("--all", action="store_true", help="Incluir arquivados")
    q = cmd.add_parser("get", help="Consultar um registro")
    q.add_argument("entity");q.add_argument("id")
    q = cmd.add_parser("create", help="Criar registro")
    q.add_argument("entity");q.add_argument("--fields", required=True, help="Objeto JSON")
    q.add_argument("--state")
    q = cmd.add_parser("update", help="Editar campos")
    q.add_argument("entity");q.add_argument("id");q.add_argument("--fields", required=True)
    q.add_argument("--version", required=True, type=int)
    q = cmd.add_parser("transition", help="Mudar estado")
    q.add_argument("entity");q.add_argument("id");q.add_argument("state");q.add_argument("--version", required=True, type=int)
    q = cmd.add_parser("remove", help="Excluir ou arquivar conforme política")
    q.add_argument("entity");q.add_argument("id");q.add_argument("--version", required=True, type=int)
    return p

def run(argv=None) -> int:
    args = build_parser().parse_args(argv)
    with Path(args.schema).open(encoding="utf-8") as f:
        schema = AppSchema.from_dict(yaml.safe_load(f))
    repo = YamlRepository(args.data) if args.storage == "yaml" else SQLiteRepository(args.data)
    service = RecordService(schema, repo)
    if args.command == "entities":
        result = sorted(schema.entities)
    elif args.command == "list":
        result = service.list(args.entity, include_archived=args.all)
    elif args.command == "get":
        result = service.get(args.entity, args.id)
    elif args.command == "create":
        result = service.create(args.entity, json.loads(args.fields), state=args.state)
    elif args.command == "update":
        result = service.update(args.entity, args.id, json.loads(args.fields), expected_version=args.version)
    elif args.command == "transition":
        result = service.transition(args.entity, args.id, args.state, expected_version=args.version)
    else:
        result = service.remove(args.entity, args.id, expected_version=args.version)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0

def main() -> None:
    try:
        raise SystemExit(run())
    except (WorkaholicError, ValueError, yaml.YAMLError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(2)

if __name__ == "__main__":
    main()
