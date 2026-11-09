# Workaholic 0.1.0 — protótipo executável do núcleo genérico

Projeto **novo**, separado do AUTOSEG legado. CLI `workaholic-cli` (alias `workaholic`). Licença do código novo: 0BSD.

## Relação com o AUTOSEG

Workaholic é uma frente de primeira classe, não um experimento descartável.
O AUTOSEG atual usa o Workaholic apenas na fatia de **clientes**
(`integracao/clientes.py`). As demais entidades ainda estão nas tabelas legadas
e serão migradas por adaptadores, uma fatia por vez. O objetivo é que o
Workaholic se torne o motor genérico do produto — sem alterar o comportamento
visível do AUTOSEG durante a migração. Ver `../docs/PRODUCT_VISION.md`.

## O que realmente funciona

- Esquemas de entidades e campos definidos em YAML; os mesmos esquemas podem ser editados futuramente por uma GUI.
- Criar, listar, consultar, editar e arquivar/excluir registros com versionamento otimista.
- Fluxos de estado configuráveis e validação de tipos.
- YAML e SQLite seguindo a mesma interface; seleção na CLI.
- Relações por campo ID com proteção contra exclusão de registro referenciado (quando relação declarada no schema).
- Casos de uso de **artes** e **AUTOSEG demonstrativo**, sem dependência do software legado.
- Testes automatizados com biblioteca padrão `unittest`.

## Instalação no Mac (Python >=3.10)

```bash
cd ~/Downloads/Workaholic_v0.1.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
workaholic-cli --help
```

Se o Python do macOS for anterior à versão 3.10, instale/utilize Python 3.13.

## Exemplo de uso com SQLite

```bash
workaholic-cli --schema examples/arts/schema.yaml --storage sqlite --data .local/arts.db entities
workaholic-cli --schema examples/arts/schema.yaml --storage sqlite --data .local/arts.db create projeto --fields '{"titulo":"Clipe 3D","tarefas":["modelagem","renderização"],"publico":false}'
workaholic-cli --schema examples/arts/schema.yaml --storage sqlite --data .local/arts.db list projeto
```

O comando `create` retorna um `id` UUID e `version: 1`. Para atualizar, use `update projeto UUID --fields '{"notas":"Nova versão"}' --version 1`. Transições utilizam `transition projeto UUID em_producao --version 2` (sempre a versão mais recente).

## Mesmo caso com YAML

Troque apenas `--storage sqlite --data .local/arts.db` por `--storage yaml --data .local/arts.yaml`.

## Testes

```bash
python -m unittest discover -s tests -v
```

## Limites da v0.1.0

- **Não** contém GUI, servidor web, Cloudflare, autenticação, PDF, nota fiscal, automações ou motor Lua. Essas peças são futuras ou específicas das aplicações.
- Não sincroniza YAML e SQLite automaticamente; cada armazenamento tem seu próprio estado.
- Adaptador YAML é para **um escritor por vez**, sem bloqueio interprocesso; SQLite possui atomicidade por operação. A versão atual **não** oferece transações multi-entidade.
- Ainda não há execução automática de aprovação, auditoria histórica, migração de esquemas, carregador de plugins ou sincronização.
- YAML de entrada da CLI é um **schema de configuração**, não o formato legado de comissões. Não importe diretamente `comissões.yaml` sem converter e validar; nele existem chaves e IDs repetidos.
- Referências a IDs não são verificadas na criação nesta versão; apenas a exclusão de destino com vínculos ativos é protegida.
- O exemplo AUTOSEG é ilustrativo e não representa suas exigências fiscais ou jurídicas.

Consulte `docs/ARCHITECTURE.md`, `docs/MIGRATION_LEDGER.md` e `AGENTS.md` antes de ampliar o projeto.
