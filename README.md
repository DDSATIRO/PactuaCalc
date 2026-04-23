# GeraAcordo

Base inicial do app descrito no documento tecnico consolidado do projeto PactuaMais.

## Escopo implementado nesta primeira entrega

- Leitura de relatorio PROJEF Web em PDF com `pdfplumber`.
- Parsing orientado por ancoras textuais para campos centrais do cabecalho.
- Estruturacao inicial de subdebitos a partir da secao `I - PARTES`.
- Deteccao de honorarios a partir de `II - TOTALIZACAO`.
- Persistencia e reabertura do caso em JSON.
- Interface desktop em `tkinter` para revisar e editar os dados extraidos.
- Validacoes principais do cabecalho e dos subdebitos.

## Como executar

```bash
python app.py
```

## Estrutura

- `app.py`: ponto de entrada.
- `geracordo/models.py`: entidades, validacoes e persistencia.
- `geracordo/parser.py`: parser inicial do PDF do PROJEF.
- `geracordo/services.py`: regras de distribuicao de bloqueio e consolidacao basica.
- `geracordo/ui.py`: interface desktop.
- `tests/`: testes unitarios das regras ja implementadas.

## Observacoes

- A automacao do PROJEF Web e o motor completo de propostas ainda nao foram implementados.
- O parser foi preparado para trabalhar por ancoras textuais e deve ser refinado com PDFs reais conforme avancarmos.
