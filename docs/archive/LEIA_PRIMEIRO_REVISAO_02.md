# AUTOSEG — Revisão 02: PF, PJ, responsáveis e histórico de OS

**Versão exclusiva para desenvolvimento e testes (30/10/2026). Não aplicar à produção.**

O ZIP contém todo o código necessário à revisão, recursos visuais e documentação, **sem** `.git`, `.venv`, bancos `.db`, clientes reais, senhas, logs, backups, anexos ou tokens. Ele preserva as melhorias da Revisão 01.

## 1. Regras de acesso implementadas

- A conta **PF** reside em `v9_usuarios` (CPF e senha). O cadastro comercial PF de `clientes` não equivale automaticamente a uma conta com login. Para ser nomeada, a pessoa deve possuir conta CPF ativa e sua identidade deve ser conferida pelo prestador.
- A **PJ** é `v9_organizacoes` (`Condomínio` ou `Empresa`) vinculada a `clientes` por `cliente_id`. O CNPJ não é credencial de acesso.
- Somente o **desktop** em `Gestão PJ → Condomínios e Vínculos → Nomear síndico/gestor entre PF` ou o **Portal do Prestador**, em `/organizacoes/responsaveis`, pode nomear, substituir ou revogar o responsável.
- Cada organização tem **uma nomeação ativa**: `Síndico` para condomínio ou `Gestor` para empresa, guardada em `v9_responsaveis`. O nomeado acessa as OS da organização pelo mesmo login CPF do Portal do Cliente.
- Moradores e funcionários podem solicitar atendimento normalmente, sem receber acesso global. Solicitar um papel privilegiado ou aprovar genericamente um vínculo não concede acesso geral.
- O responsável vê tanto solicitações de moradores/funcionários quanto OS abertas no desktop/portal do prestador, desde que o vínculo PJ→cliente seja inequívoco. Havendo CNPJ divergente ou dois cadastros PJ no mesmo cliente, as OS sem vínculo explícito ficam ocultas **até revisão manual**; não há mesclagem automática.
- Relatórios PDF são autorizados pelo vínculo da OS e pela nomeação, nunca apenas por um número de OS. A troca/revogação de responsável retira o acesso imediatamente.
- Senha de prestador pode ser redefinida pelo desktop, sem apagar cadastro, e sessões antigas perdem validade após a alteração.

## 2. Aplicação no Mac (somente na pasta DEV)

**Feche o aplicativo e os dois portais primeiro.** Preserve uma cópia da pasta DEV atual ou, no mínimo, o banco `dados_teste/autoseg_teste.db`; não envie bancos reais ao ChatGPT. Não apague `.git` nem `.venv` existentes.

O arquivo `AUTOSEG_DEV_COMPLETO_REV02.zip` deve ser colocado em `~/Downloads`. Use o Terminal:

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
git branch --show-current
git status --short
```

Confira que a branch é **develop**. Como a Revisão 01 pode estar ainda sem commit, o Git pode mostrar alterações; **não use `git restore` nem `git reset`**. Faça backup local da pasta antes de aplicar.

```zsh
mkdir -p "$HOME/AUTOSEG_REV02_EXTRAIDO"
unzip -q -o "$HOME/Downloads/AUTOSEG_DEV_COMPLETO_REV02.zip" -d "$HOME/AUTOSEG_REV02_EXTRAIDO"
ls "$HOME/AUTOSEG_REV02_EXTRAIDO/AUTOSEG_REVISAO_02/LEIA_PRIMEIRO_REVISAO_02.md"
```

Se o `ls` encontrou o arquivo, copie os arquivos atualizados de código (não há banco no ZIP):

```zsh
cp -R "$HOME/AUTOSEG_REV02_EXTRAIDO/AUTOSEG_REVISAO_02/." "$HOME/GestaoServicos_DEV/"
cd "$HOME/GestaoServicos_DEV" || exit 1
"$PWD/.venv/bin/python" -m pip install -r requirements.txt
./VERIFICAR_AUTOSEG_DEV.command
```

Se algum teste falhar, **não prossiga**, compartilhe a saída do Terminal. Se passar, feche outros servidores locais antigos e execute:

```zsh
./INICIAR_AUTOSEG_DEV.command
```

- Portal do Cliente: `http://127.0.0.1:8865/`
- Portal do Prestador: `http://127.0.0.1:8866/`

### Onde nomear

No desktop: **Prestadores e Atribuições → Gestão PJ → Condomínios e Vínculos**. Selecione uma organização, clique **NOMEAR SÍNDICO / GESTOR ENTRE PF**, pesquise uma conta pelo nome ou CPF e confirme. A mesma operação está disponível em **Portal do Prestador → Clientes → Condomínios, empresas e vínculos → Nomear / trocar síndico ou gestor**. Para remover, use **Revogar acesso**.

### Onde o nomeado vê as OS

Acesse o Portal do Cliente com CPF e senha da PF nomeada. Em **Meu painel**, aparece **Organizações sob sua responsabilidade → Consultar todas as OS**. Os demais clientes continuam vendo apenas suas solicitações particulares e os chamados que abriram.

## 3. Criar os 13 cadastros fictícios de teste

Feche o aplicativo antes de popular a base de testes, então execute:

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
./CRIAR_CADASTROS_FICTICIOS_DEV.command
```

O gerador recusa rodar fora do ambiente `AUTOSEG_DEV=1` e fora de `dados_teste/`. Ele não exclui cadastros anteriores nem duplica suas próprias pessoas e empresas. Cria **5 clientes PJ**, **5 clientes PF com login CPF**, **3 prestadores**, **3 responsáveis nomeados** e **3 OS** demonstrativas (incluindo pedidos de moradora e funcionária). Não envia e-mail nem consulta a internet.

As senhas fictícias são aleatórias. O programa as mostra no Terminal na primeira criação e as grava apenas em `dados_teste/CREDENCIAIS_FICTICIAS_DEV.txt`, com permissão restrita. **Esse arquivo não entra no ZIP nem no Git.** Não cole suas senhas reais nas conversas.

Em caso de base DEV com cadastros anteriores, os totais de tabelas podem ser maiores que 5/5/3; os registros gerados têm nomes e documentos fictícios reconhecíveis. A execução repetida não altera senhas.

## 4. Matriz para testar manualmente

1. O responsável do **Condomínio Horizonte Simulado** consegue ver o pedido da **Dani Simulação** e a OS administrativa de fechadura.
2. **Dani**, mesmo com vínculo de moradora aprovado, não vê as OS administrativas do condomínio.
3. O gestor da **Oficina Atlas Exemplo** vê o chamado da **Eva Homologação**, mas não as OS de outros condomínios.
4. O responsável do primeiro condomínio **não** acessa a visão geral de outro condomínio alterando o número da URL.
5. A troca ou revogação de responsável remove o acesso geral da pessoa anterior.
6. Um login de prestador com senha redefinida pelo desktop funciona; a senha antiga não funciona.
7. OS antigas de organizações com cadastros misturados devem ser auditadas manualmente; não tente mesclar cadastros reais a partir do banco de testes.

## 5. Limitações e pendências importantes

Esta revisão **não** reconcilia automaticamente dados históricos incorretos, não verifica identidade governamental de PF, não faz backup de produção, não envia e-mail via API e não corrige todos os 28 itens do planejamento. A vinculação entre PF comercial e conta CPF não é automática para impedir acesso indevido a histórico particular. A atribuição de responsável por prestador confia que a pessoa/CPF já foi verificada pelo operador. Homologação visual no Mac ainda é necessária antes de qualquer entrega à produção.

**Não fazer `git merge` com main nem copiar os arquivos para `/Users/<usuario>/GestaoServicos` sem validação manual e backup completo.**
