# GeraAcordo

Base inicial do app descrito no documento técnico consolidado do projeto PactuaMais. O sistema atua como uma solução completa para análise, extração e geração de propostas de acordo a partir de débitos estruturados.

## Escopo Implementado

- **Leitura de Relatórios PDF**: Extração e parsing inteligente via `pdfplumber` de relatórios do **PROJEF Web** e do **TCU**.
- **Automação Web**: Integração com Selenium para automatização do fluxo de acesso aos relatórios.
- **Motor de Propostas e PDF**: Geração automatizada de propostas de acordo em formato PDF, contemplando:
  - Cálculos de juros simples para parcelas pré-fixadas (histórico Selic via API do Banco Central).
  - Quadro comparativo e cálculo detalhado de descontos e opções de carência.
  - Demonstrações de médias mensais e consolidações por modalidade (Curto/Médio/Longo prazo, etc.).
- **Subdébitos e Bloqueios Judiciais**:
  - Classificação rigorosa em valores `PRINCIPAL` e `HONORÁRIOS`.
  - Mecanismo de distribuição inteligente de saldo judicial bloqueado.
- **Interface Gráfica (Desktop)**: Construída via `tkinter` para permitir edição de subdébitos, regras de aprovação e visualização prévia da proposta consolidada.

## Como Executar

```bash
python app.py
```

## Estrutura do Projeto

- `app.py`: Ponto de entrada da aplicação.
- `geracordo/models.py`: Entidades (CaseData, Subdebito), validações e persistência em formato JSON.
- `geracordo/parser.py`: Engine de parsing baseada em âncoras textuais para PDFs do PROJEF e TCU.
- `geracordo/proposals.py` / `proposal_render.py`: Geração e desenho dinâmico de propostas de acordo (PDF).
- `geracordo/services.py`: Regras de negócio de distribuição de bloqueio e consolidação de débito.
- `geracordo/selic_api.py`: Integração com API de séries temporais do Banco Central.
- `geracordo/ui.py`: Interface de usuário.
- `tests/`: Suíte de testes unitários que validam a lógica e o parsing.

## Observações
- A automação Web exige a presença do ChromeDriver e permissões de rede.
- Os modelos de parcelamento foram ajustados para evitar a incidência de juros sobre juros nas propostas pré-fixadas (SELIC).
