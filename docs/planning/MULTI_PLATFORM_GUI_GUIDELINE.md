# Guideline de interface multiplataforma

**Status:** visão de futuro. **Agora vamos ficar apenas no site e no app GTK.**
Este documento registra a direção para quando existirem WinUI, Qt, Android
Compose e Apple SwiftUI/UIKit, sem autorizar a construção de todos ao mesmo
tempo.

**Objetivo:** ter um **workflow de trabalho consistente** e, ao mesmo tempo,
uma interface que **pareça nativa** em cada plataforma.

**Não é:** um único toolkit para tudo, um site dentro de um WebView, um tema
único aplicado em todos os lugares ou paridade pixel a pixel.

---

## 1. Princípio central

```text
Consistente no trabalho. Nativo na interação.
```

O usuário deve reconhecer o mesmo produto, os mesmos conceitos e o mesmo fluxo
em qualquer plataforma. Mas a janela, os menus, os gestos, os diálogos, a
tipografia e o comportamento do sistema devem seguir a plataforma.

A camada intermediária é uma **linguagem de produto** — não um framework de UI.

## 1.1 Similaridade visual + aparência nativa

O objetivo é duplo:

1. **Parecer o mesmo produto** em todas as plataformas: mesma hierarquia,
   mesmos conceitos, mesma organização de tela, mesmos tokens de cor/espaço,
   mesma linguagem de ícones e mesmos estados.
2. **Parecer nativo** em cada plataforma: janela, controles, navegação,
   diálogos, tipografia, gestos, teclado, tema e acessibilidade do sistema.

Isso não é contraditório se separarmos **esqueleto** de **pele**:

```text
Esqueleto do produto (igual)     Pele da plataforma (nativa)
────────────────────────────     ───────────────────────────
informação e hierarquia          janela / title bar
ordem das ações                  controles e widgets
tokens de cor e espaço           fonte do sistema
escala tipográfica               menus e atalhos
anatomia dos componentes         diálogos e sheets
estados e mensagens              gestos e transições
linguagem de ícones              tema do sistema
```

**Muito similar** significa mesma estrutura, mesma leitura visual e mesma
semântica — não o mesmo pixel, o mesmo widget ou o mesmo menu.

### Regra de conflito

Quando “parecer igual” e “parecer nativo” brigarem, a ordem é:

1. **Segurança, clareza e acessibilidade.**
2. **Convenção nativa de interação** (janela, controle, diálogo, gesto, teclado).
3. **Similaridade visual do produto** (cor, espaçamento, ícone, tipografia).

Ou seja: o **comportamento** segue a plataforma; a **linguagem visual** segue o
produto. A plataforma só perde quando a convenção dela prejudica a tarefa.

### O que fica parecido

| Elemento | Similar entre plataformas | Adaptação nativa |
|---|---|---|
| Hierarquia da tela | mesma ordem e agrupamento | sidebar, tabs ou stack conforme a plataforma |
| Cores | mesmos papéis e significados | valores do tema claro/escuro do sistema |
| Espaçamento | mesma escala e ritmo | densidade confortável/compacta |
| Tipografia | mesma escala e pesos | fonte nativa (San Francisco, Segoe, Roboto, sistema GTK) |
| Ícones | mesma linguagem e metáfora | conjunto nativo quando equivalente |
| Botões | mesma hierarquia e prioridade | forma, foco e estados nativos |
| Diálogos | mesmo texto e mesma decisão | alert/sheet/dialog nativo |
| Navegação | mesmos itens e ordem | NavigationView, sidebar, tabs, drawer |
| Movimento | mesma intenção | curva/duração nativas |
| Teclado/gestos | mesmo conceito | tecla/gesto nativo |

### Exemplo

A lista de OS deve ter as mesmas colunas, a mesma ordem, os mesmos chips de
status e a mesma ação principal em todas as plataformas. No GTK ela usa uma
`Adw` list/table; no WinUI, uma `ListView`; no Android, uma `LazyColumn`; no
Apple, uma `List`. O espaçamento, as cores e a hierarquia são da guideline; o
controle e a interação são da plataforma.

O diálogo de cancelamento de OS deve pedir o mesmo motivo e preservar o mesmo
histórico. No GTK é um `Adw.AlertDialog`; no Windows, um `ContentDialog`; no
Android, um `AlertDialog`; no Apple, um `confirmationDialog`. O texto e a
decisão são iguais; o componente é nativo.

### O que não tentar

- clonar o mesmo pixel em todas as plataformas;
- usar um WebView para “garantir” a similaridade;
- recriar controles nativos com CSS/QSS;
- ignorar a HIG da plataforma para manter o tema;
- trocar a ordem das ações por plataforma;
- chamar de “nativo” um app que só usa a fonte do sistema.

---

## 2. Plataformas previstas

| Plataforma | Stack prevista | Guideline de referência | Estado |
|---|---|---|---|
| Web | HTML/CSS/JS | WCAG 2.2, responsive web, convenções do navegador | atual |
| Desktop Linux/macOS | GTK4 + libadwaita | GNOME HIG | atual |
| Windows | WinUI 3 / Windows App SDK | Fluent Design / Windows HIG | futuro |
| Desktop alternativo | Qt 6 (Qt Quick/QML) | Qt/plataforma; decidir se realmente necessário | futuro |
| Android | Kotlin + Jetpack Compose | Material 3 / Android HIG | futuro |
| Apple | SwiftUI (e UIKit quando necessário) | Apple Human Interface Guidelines | futuro |

O nome que faltou é **SwiftUI/UIKit** (Apple Human Interface Guidelines).

---

## 3. Camadas da guideline

```text
1. Tokens de design (cor, tipo, espaço, raio, movimento)
2. Semântica e padrões de workflow (o que significa cada ação)
3. Adaptadores por plataforma (widgets, navegação, diálogos)
4. Conteúdo e terminologia (pt-BR, inglês, labels)
5. Contrato de dados/AppService (o que a tela pode fazer)
```

- **Tokens** são compartilhados.
- **Semântica** é compartilhada.
- **Widgets** são nativos por plataforma.
- **Regras de negócio** ficam no `AppService`, nunca na guideline.

Para o contrato funcional que web e GTK compartilham (telas, campos, ações,
permissões, validações e view models), ver
`docs/planning/WEB_GTK_SHARED_CONTRACT.md`. Este documento continua sendo a
guideline visual; o outro é o contrato de comportamento.

---

## 4. O que deve ser igual

- vocabulário do domínio: cliente, OS, orçamento, relatório, repasse;
- hierarquia das tarefas: encontrar → abrir → editar → confirmar;
- estados: Aberta, Iniciada, Pendente, Concluída, Cancelada;
- significado das cores de status (com contraste adequado);
- confirmações destrutivas e exigência de motivo;
- mensagens de erro compreensíveis e códigos estáveis;
- estados vazios, carregando, offline, sincronizando e conflito;
- comportamento de anexos, PDFs e financeiro;
- permissões e o que cada papel pode fazer;
- atalhos conceituais (mesmo que a tecla mude).

## 5. O que deve ser nativo

- janela, title bar, bordas, sombras e sistema de janelas;
- menus, command palette, barras de ferramentas e navegação;
- diálogos, sheets, popovers e confirmações;
- tipografia do sistema e escala de texto;
- tema claro/escuro, alto contraste e cor de destaque do sistema;
- gestos: swipe, back, long press, arrastar e soltar;
- teclado, foco, tab order e atalhos;
- seletores de arquivo, compartilhamento, impressão e PDF;
- notificações, permissões e integração com a bandeja/dock;
- APIs de acessibilidade (VoiceOver, TalkBack, Orca, UIA).

---

## 6. Matriz de adaptação

| Elemento | Web | GTK | WinUI | Qt | Android | Apple |
|---|---|---|---|---|---|---|
| Navegação principal | sidebar responsiva / rotas | AdwNavigationSplitView | NavigationView | definido no Qt | NavigationBar/Drawer | NavigationStack/TabView |
| Diálogo destrutivo | `<dialog>` + foco | Adw.AlertDialog | ContentDialog | QML Dialog | Material AlertDialog | `.alert`/`.confirmationDialog` |
| Feedback rápido | toast/inline | Adw.Toast | InfoBar | QML toast | Snackbar | banner/overlay |
| Tema | CSS variables + prefers-color-scheme | libadwaita/system | Fluent/system | Qt palette | Material 3/system | system |
| Ícones | SVG próprio | Adwaita simbólicos | Segoe Fluent Icons | tema Qt | Material Symbols | SF Symbols (só Apple) |
| Fonte | sistema/web | fonte do sistema | Segoe UI Variable | fonte do sistema | Roboto/system | San Francisco |
| Atalhos | teclado/foco web | GNOME shortcuts | WinUI accelerators | Qt shortcuts | gestos/back | keyboards/commands |

A tabela é uma direção, não uma decisão fechada.

---

## 7. Design tokens

### 7.1 Cores

Usar **papéis**, não valores fixos:

- `surface`, `surface-raised`, `surface-sunken`;
- `text`, `text-muted`, `text-inverse`;
- `accent`, `accent-hover`, `accent-contrast`;
- `success`, `warning`, `danger`, `info`;
- `line`, `focus-ring`, `overlay`.

Cada papel tem variantes claro, escuro e alto contraste. Status de OS usa a
mesma semântica em todas as plataformas, mas o componente (chip, badge, tag)
segue o padrão local.

### 7.2 Espaçamento e tipografia

- escala de espaço: 4, 8, 12, 16, 24, 32, 48;
- raios: pequeno, médio, grande, pill;
- tipografia: escala do sistema + pesos; não embutir uma fonte única em todas
  as plataformas;
- densidade: confortável e compacta para desktop/web; toque mínimo 44–48 dp;
- movimento: durações e easing consistentes, respeitando “reduzir movimento”.

### 7.3 Exportação

Os tokens devem ser exportáveis para:

- CSS variables;
- GTK CSS / libadwaita;
- QML;
- SwiftUI;
- Jetpack Compose;
- WinUI ResourceDictionary.

Uma única fonte de verdade, vários formatos gerados.

---

## 8. Padrões de workflow

Documentar uma vez, adaptar em cada UI:

- lista → detalhe → edição → confirmação;
- busca, filtros, ordenação e paginação;
- ações em lote;
- formulários longos, abas e rascunho automático;
- confirmação de ações destrutivas com motivo;
- desfazer quando possível; confirmação quando irreversível;
- estados vazios e erros recuperáveis;
- offline, sincronizando, pendente e conflito;
- anexos, fotos, PDFs e notas fiscais;
- financeiro, rateio, repasse e recebimento;
- permissões por papel e por contexto.

Exemplo de regra de produto: “cancelar uma OS exige motivo e preserva
histórico”. A regra é igual em todas as plataformas; o diálogo é nativo.

---

## 9. Ícones e marca

- logotipo e marca iguais em todas as plataformas;
- ícones funcionais podem usar o conjunto nativo da plataforma;
- não usar emoji como ícone de interface;
- SF Symbols só em apps Apple (licença);
- ícones próprios em SVG, com tamanhos ópticos por plataforma;
- variantes claro/escuro e alto contraste;
- nunca depender só de cor para indicar status.

---

## 10. Acessibilidade

- Web: WCAG 2.2 AA, foco visível, navegação por teclado, landmarks, labels.
- GTK: AT-SPI/Orca, foco, atalhos, alto contraste.
- WinUI: UIA, Narrator, teclado, escala de texto.
- Qt: acessibilidade da plataforma, foco e atalhos.
- Android: TalkBack, touch targets, predictive back, font scale.
- Apple: VoiceOver, Dynamic Type, contraste, reduce motion, safe areas.

Acessibilidade não é “fase final”; é requisito de aceite de cada tela.

---

## 11. Testes de interface

- screenshots golden por plataforma e por tema;
- testes de workflow (mesmo cenário em web e GTK primeiro);
- auditoria de acessibilidade automatizada + manual;
- matriz de dispositivos: desktop, notebook, phone, tablet;
- revisão contra a HIG da plataforma;
- teste de teclado, foco e leitor de tela;
- regressão visual em claro/escuro/alto contraste;
- orçamento de movimento e de densidade.

“Parece nativo” não é aprovável só por screenshot; precisa de teclado, gesto,
foco e comportamento do sistema.

---

## 12. Governança

- um responsável pela guideline e pelos tokens;
- versionamento dos tokens (ex.: `design-tokens 1.2`);
- contrato de componente: anatomia, estados, acessibilidade, conteúdo;
- changelog de UI;
- depreciação e migração;
- revisão de plataforma por quem conhece aquela HIG;
- decisões registradas em ADR quando forem irreversíveis.

---

## 13. Roadmap de interfaces

### Agora

- site (portal do prestador/cliente);
- GTK4/libadwaita;
- tokens iniciais no CSS/GTK;
- workflow parity web ↔ GTK.

### Próximo

- consolidar a guideline e os tokens;
- `AppService`/API antes de novos clientes;
- testes de workflow e acessibilidade;
- decidir se Qt e WinUI são realmente necessários.

### Futuro distante

- WinUI 3;
- Qt (se houver demanda real; evitar dois desktops sem justificativa);
- Android Compose;
- Apple SwiftUI/UIKit;
- um cliente por vez, com capability matrix, spike de design e revisão HIG.

**Não** começar 20 GUIs em 20 toolkits. Cada cliente novo multiplica testes,
suporte, acessibilidade e manutenção.

---

## 14. Anti-padrões

- WebView embrulhado como app nativo;
- copiar widgets de uma plataforma para outra;
- um tema único que ignora o sistema;
- barra de título falsa que quebra o gerenciador de janelas;
- hambúrguer no desktop;
- emoji como ícone;
- glass/mica/blur em excesso;
- paridade pixel a pixel entre plataformas;
- regra de negócio na UI;
- prometer todos os clientes antes do `AppService` e da API;
- ignorar teclado, leitor de tela e alto contraste.

---

## 15. Decisões abertas

- nome da linguagem de design (AUTOSEG Design Language? Workaholic UI?);
- Qt: vale a pena ou GTK + WinUI cobrem desktop?
- Apple: SwiftUI only ou UIKit em telas específicas?
- Android: Material 3 com cor dinâmica ou cor de marca fixa?
- Web: framework atual ou SPA/PWA no futuro?
- ícones: conjunto próprio + nativos ou um conjunto único?
- tipografia: sistema em tudo ou fonte de marca só em títulos?
- densidade padrão por plataforma;
- navegação principal por plataforma;
- quanto de offline/sync aparece na UI.

---

## 16. Documentos relacionados

- `docs/GTK_SERVER_DECOUPLING.md`
- `docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`
- `docs/GTK4_LINUX_MACOS.md`
- `docs/PRODUCT_VISION.md`
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/archive/FUNDAMENTAL_STRUCTURAL_PROBLEMS.md` (histórico)
- `docs/planning/CONDO_SHARING_AND_TENANCY.md`
