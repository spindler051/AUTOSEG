# Arquitetura-alvo — Workaholic

## Princípios

- **Core local-first**, sem dependência obrigatória de servidor HTTP, GUI, cloud ou serviços externos.
- Entidades, campos, estados e relações configuráveis por schema, independentemente da profissão.
- `application` é consumidor do `domain` e da abstração `Repository`; a implementação de infraestrutura não é importada pelo domínio.
- `cli` é adaptador de entrada. GUI e API futuras chamarão os mesmos casos de uso.
- `YamlRepository` e `SQLiteRepository` adotam `get/list/put/delete`, usando registros normalizados em JSON (sem objetos Python serializados).
- ID canônico UUID, versão monotônica de registro; schema com estado/fields e exclusão configurável.
- Extensões YAML e módulos Python serão introduzidos após estabilizar os contratos.
- Futuro **Rust**: núcleo deve poder ser reimplementado sem alterar formato dos registros ou semântica do CLI. **Lua**: scripts interpretados como extensão controlada; design de sandbox adiado.

## Fronteira de vocabulário e apresentação

O núcleo usa identidades semânticas (`work_item`, `party`, `state_kind`,
`transition`, `requirement`), não nomes de produto ou rótulos localizados.
Terminologia, fluxo de trabalho, requisitos de conclusão e presets de permissão
pertencem à Officina e são fornecidos por cada flavor como configuração
versionada. A decisão está registrada no
[ADR 0002](adr/0002-semantic-work-protocol.md).

## Limites do protótipo

O código v0.1.0 implementa apenas um subconjunto do desenho. `schema.yaml` ainda não possui revisões versionadas e não existe engine de auditoria ou approval, apesar de planejados. `relation` é uma referência por campo ID e não um sistema de integridade referencial abrangente.

## Padrão de importação do legado

AUTOSEG usa adaptadores externos em `applications/autoseg`, nunca dentro do `src/workaholic`. Importador deve mapear e validar dados, preservar IDs históricos como metadados de origem e fazer migração testada sem sobrescrever `dados.db`. A configuração do exemplo é demonstrativa; o desenvolvimento de GUI e burocracia técnica é responsabilidade dos respectivos colaboradores.

## Contrato de dados canônico (v1)

```json
{"id":"uuid","entity":"projeto","version":1,"state":"reservado","fields":{"titulo":"Clipe"},"archived":false,"created_at":"ISO8601","updated_at":"ISO8601"}
```
