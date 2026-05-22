# PactuaCalc

Base inicial do app descrito no documento técnico consolidado do projeto PactuaMais. O sistema atua como uma solução completa para análise, extração e geração de propostas de acordo a partir de débitos estruturados.

## Escopo Implementado

- **Leitura de Relatórios PDF**: Extração e parsing inteligente via `pdfplumber` de relatórios do **PROJEF Web** e do **TCU**.
- **Automação Web**: Integração com Playwright (Microsoft Edge nativo) para automatização do fluxo de acesso aos relatórios.
- **Motor de Propostas e PDF**: Geração automatizada de propostas de acordo em formato PDF, contemplando:
  - Cálculos de juros simples para parcelas pré-fixadas (histórico Selic via API do Banco Central).
  - Quadro comparativo e cálculo detalhado de descontos e opções de carência.
  - Demonstrações de médias mensais e consolidações por modalidade.
  - Sinalização no PDF de opções adaptadas ao caso concreto quando entrada, desconto ou parcelas forem ajustados em relação ao padrão.
- **Subdébitos e Bloqueios Judiciais**:
  - Classificação rigorosa em valores `PRINCIPAL` e `HONORÁRIOS`.
  - Honorários são reconhecidos por tipo, pela chave `UG 110060` + `GRU 91710-9` e, na importação, por texto afirmativo sem contexto negativo como "sem honorários".
  - Mecanismo de distribuição inteligente de saldo judicial bloqueado.
- **Interface Gráfica (Desktop)**: Construída via `tkinter` com botão "Sobre" com licenças embutidas, campo de condições adicionais com sinalização visual e ordem de tabulação padronizada.
- **Controle Remoto de Versão**: Sistema de kill switch e notificação de atualização via arquivo hospedado no GitHub.

## Como Executar

```bash
python app.py
```

## Estrutura do Projeto

- `app.py`: Ponto de entrada — inclui verificação remota de versão antes de abrir a UI.
- `pactuacalc/models.py`: Entidades (CaseData, Subdebito), validações e persistência em formato JSON.
- `pactuacalc/parser.py`: Engine de parsing baseada em âncoras textuais para PDFs do PROJEF e TCU.
- `pactuacalc/proposals.py` / `proposal_render.py`: Geração e desenho dinâmico de propostas de acordo (PDF).
- `pactuacalc/services.py`: Regras de negócio de distribuição de bloqueio e consolidação de débito.
- `pactuacalc/selic_api.py`: Integração com API de séries temporais do Banco Central.
- `pactuacalc/version_check.py`: Sistema de controle remoto de versão via GitHub.
- `pactuacalc/ui.py`: Interface de usuário (Tkinter).
- `version.json`: Arquivo de controle de versão remoto (editável diretamente no GitHub).
- `tests/`: Suíte de testes unitários que validam a lógica e o parsing.

## Controle Remoto de Versão

O sistema verifica automaticamente ao abrir se a versão instalada ainda é permitida, consultando o `version.json` hospedado no GitHub. Três camadas de controle independentes:

| Campo | Efeito |
|-------|--------|
| `min_version` | Bloqueia versões abaixo do piso mínimo (muito antigas) |
| `blocked_versions` | Bloqueia versões específicas com bugs, sem afetar as demais |
| `latest_version` | Avisa gentilmente que há uma versão mais recente (sem bloquear) |

Sem internet, o app abre normalmente (degradação graciosa).

## Observações
- A automação Web utiliza o Microsoft Edge nativo (Windows 10/11) via Playwright — sem download de navegador separado.
- Os modelos de parcelamento foram ajustados para evitar a incidência de juros sobre juros nas propostas pré-fixadas (SELIC).
- Nas propostas pré-fixadas, a Selic inicial considera a data efetiva da primeira parcela: nas opções com entrada, usa a data da primeira parcela após a entrada, inclusive quando ajustada pelo usuário.
- A automação possui timeouts robustos para redes lentas e só decrementa a competência de atualização se o ProjefWeb explicitamente rejeitar a data.

