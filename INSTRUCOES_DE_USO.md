# PactuaCalc - Instrucoes de uso

## 1. Finalidade do aplicativo

O PactuaCalc auxilia na organizacao de subdebitos, codigos de arrecadacao e propostas de acordo. Ele permite importar ou preencher dados, consolidar debitos por chave arrecadatoria, ajustar opcoes de proposta e gerar um PDF final.

O fluxo normal de uso e:

1. Criar um caso a partir de relatorio ou abrir um JSON.
2. Conferir os dados gerais.
3. Revisar os subdebitos.
4. Completar UG/Gestao e GRU(CR).
5. Conferir os debitos consolidados.
6. Preencher condicoes adicionais, se houver.
7. Gerar opcoes da proposta.
8. Selecionar e ajustar as propostas.
9. Conferir o resumo.
10. Gerar o PDF.
11. Salvar o JSON para edicoes futuras.

## 2. Botoes superiores

### Criar a partir de relatorio

Cria um novo caso a partir de um relatorio importado. Use esta opcao quando iniciar um trabalho novo.

### Adicionar relatorio

Adiciona outro relatorio ao caso atual. O app tenta preservar dados ja preenchidos manualmente e pode alertar sobre divergencias.

### Abrir Json

Abre um rascunho salvo anteriormente. O JSON carrega dados gerais, subdebitos, codigos, condicoes adicionais e ajustes de propostas.

### Salvar Json

Salva o estado atual do caso. Este arquivo e o rascunho editavel do trabalho. Recomenda-se salvar antes e depois de gerar uma proposta.

### Ajuda

Abre estas instrucoes de uso.

### Sobre

Mostra informacoes do aplicativo, licenca e creditos.

### Sair

Fecha o aplicativo.

## 3. Dados Gerais

O quadro Dados Gerais contem os dados principais do caso.

Campos obrigatorios aparecem destacados, normalmente com fundo rosa/vermelho quando vazios ou pendentes.

### Processo

Numero do processo judicial. Campo obrigatorio.

### Devedor

Nome do devedor. Campo obrigatorio.

### CPF/CNPJ

Documento do devedor. Campo obrigatorio quando exigido pelo fluxo de proposta.

### NUP do requerimento

Numero unico de protocolo do requerimento. Campo obrigatorio.

### Competencia

Competencia da atualizacao do calculo. O app pode preencher automaticamente a partir da data de atualizacao.

### Data de atualizacao

Data-base do calculo. Campo obrigatorio.

### Tipo de parcela

Define como as parcelas serao tratadas:

- VARIAVEL (POS-FIXADO): parcelas sujeitas a atualizacao mensal.
- FIXO (PREFIXADO): parcelas calculadas com base na media da Selic dos ultimos 12 meses.

Campo obrigatorio.

### Data limite resposta

Data ate a qual o devedor deve responder a proposta. Campo obrigatorio.

Regra importante: a data limite nao pode ser posterior a data da entrada/primeira parcela.

### Data da Entrada/Primeira Parcela

Data prevista para pagamento da entrada ou da primeira parcela. Campo obrigatorio.

Regra importante: nao pode ser anterior a data atual.

### Multa (%)

Percentual de multa utilizado no calculo quando aplicavel. O padrao e 10%.

### Valor bloqueado geral

Valor total bloqueado/depositado que pode ser distribuido entre os subdebitos, quando aplicavel.

## 4. Subdebitos

O quadro Subdebitos lista os itens que compoem a divida.

Colunas principais:

- Tipo.
- Descricao.
- UG/Gestao.
- GRU(CR).
- Valor atualizado.
- Multa Art 523.
- Valor bloqueado.

Tipos aceitos:

- PRINCIPAL.
- HONORARIOS.
- MULTA (exceto art. 523).

Campos de edicao dos subdebitos ficam na parte inferior do quadro. Normalmente usam fundo amarelo claro.

### Atualizar

Altera o subdebito selecionado com os dados preenchidos no formulario.

### Adicionar

Inclui um novo subdebito manualmente.

### Excluir

Remove o subdebito selecionado.

## 5. UG/Gestao e GRU(CR)

Cada subdebito precisa ter UG/Gestao e GRU(CR) antes da geracao da proposta.

### UG/Gestao

A UG e escolhida em lista suspensa. A Gestao e preenchida automaticamente conforme a UG selecionada.

A lista pode mostrar a descricao da UG para facilitar a escolha, mas o codigo gravado no app, no JSON e no PDF e o codigo.

### GRU(CR)

A GRU(CR) tambem e escolhida em lista suspensa. A descricao ajuda na escolha, mas o codigo e o dado usado pelo app.

### Aplicar aos selecionados

Permite aplicar UG/Gestao e GRU(CR) a varios subdebitos selecionados de uma vez.

## 6. Debitos consolidados

O quadro Debitos consolidados mostra uma visao agrupada dos subdebitos.

A consolidacao serve para:

- agrupar valores por chave arrecadatoria;
- facilitar a conferencia da arrecadacao;
- gerar linhas consolidadas no PDF;
- permitir alterar a descricao consolidada usada na proposta.

Na consolidacao, sao somados valores como:

- valor atualizado;
- multa Art 523;
- valor bloqueado.

Se dois subdebitos tiverem a mesma chave de arrecadacao, podem aparecer como uma linha consolidada. Isso ajuda a evitar repeticao desnecessaria no PDF.

### Alterar descricao consolidada

Para alterar:

1. Selecione um debito consolidado.
2. Digite a nova descricao.
3. Clique no botao de alteracao.

A alteracao vale para a apresentacao consolidada e para a proposta gerada.

## 7. Condicoes adicionais

O campo Condicoes adicionais permite incluir informacoes especificas do caso.

Exemplos:

- condicoes juridicas adicionais;
- observacoes relevantes;
- ressalvas;
- informacoes acordadas no atendimento.

O texto preenchido sera levado ao PDF.

## 8. Gerar opcoes da proposta

O botao GERAR OPCOES DA PROPOSTA inicia o fluxo de proposta.

Antes disso, confira:

- dados obrigatorios preenchidos;
- datas validas;
- subdebitos revisados;
- UG/Gestao em todos os subdebitos;
- GRU(CR) em todos os subdebitos;
- condicoes adicionais, se houver.

Se faltar UG/Gestao ou GRU(CR), o app exibira alerta e nao gerara a proposta.

## 9. Selecao das opcoes da proposta

Apos clicar em gerar, o app mostra as opcoes que podem constar na proposta.

Opcoes:

- 1 - Parcelamento comum.
- 2 - Pagamento a vista.
- 3.A - Parcelado sem entrada.
- 3.B - Parcelado sem entrada.
- 4.A - Com entrada.
- 4.B - Com entrada.
- 4.C - Com entrada.
- 4.D - Com entrada.

O usuario pode marcar uma ou mais opcoes.

Se nenhuma opcao for selecionada, o app exibira alerta.

## 10. Desconto da opcao a vista

Quando a opcao 2 estiver selecionada, o app pergunta como calcular o desconto:

- Percentual unico por faixa.
- Faixa progressiva.

### Percentual unico por faixa

E o padrao.

Faixas:

- ate R$ 20.000,00: 50%.
- ate R$ 60.000,00: 35%.
- ate R$ 100.000,00: 30%.
- acima de R$ 100.000,00: 25%.

O percentual encontrado e aplicado sobre toda a base geral da opcao a vista.

### Faixa progressiva

E uma opcao excepcional.

Ao selecionar essa opcao, o app alerta:

"Esta opcao e excepcional. Verifique se e possivel concede-lo, antes de prosseguir."

Use somente quando houver autorizacao para esse modo de calculo.

### Honorarios e encargos

Para definir a faixa, o app exclui honorarios e encargos.

Exemplo:

- Principal: R$ 80.000,00.
- Honorarios: R$ 20.000,00.
- Total: R$ 100.000,00.

A faixa sera definida por R$ 80.000,00, resultando em 30%.

Depois, o percentual sera aplicado sobre a base geral.

Se houver somente honorarios/encargos, a faixa usa o valor total.

## 11. Ajustes de entrada, desconto e parcelas

Depois da selecao das opcoes, o app abre o quadro de ajustes.

Campos alterados ficam em vermelho e negrito.

### Entrada

Nas propostas com entrada obrigatoria, a entrada so pode aumentar.

Nas opcoes 1, 3.A e 3.B, o usuario pode preencher uma entrada opcional.

Importante: a entrada opcional nas opcoes 1, 3.A e 3.B nao gera desconto. Ela apenas reduz o saldo a parcelar.

### Desconto

O desconto so pode diminuir.

O app impede imediatamente valor maior que o desconto padrao da proposta.

Tambem impede valor negativo.

### Parcelas

As parcelas podem ser reduzidas dentro da faixa permitida.

O app impede aumentar acima do padrao da proposta.

Faixas:

- Proposta 1: 1 a 60.
- Proposta 3.A: 2 a 12.
- Proposta 3.B: 13 a 24.
- Proposta 4.A: 2 a 12.
- Proposta 4.B: 13 a 24.
- Proposta 4.C: 25 a 36.
- Proposta 4.D: 37 a 60.

### Data da primeira parcela nas opcoes com entrada

Nas opcoes com entrada, a entrada fica prevista para a Data da Entrada/Primeira Parcela dos Dados Gerais.

O app calcula automaticamente a primeira parcela para o ultimo dia do mes seguinte.

Exemplo:

- Entrada: 25/05/2026.
- Primeira parcela padrao: 30/06/2026.

O usuario pode antecipar essa data, mas nao pode posterga-la.

O app impede imediatamente data posterior ao padrao calculado.

### Resetar alteracoes

O botao Resetar alteracoes (voltar ao padrao geral) retorna todos os campos ao padrao:

- entrada;
- desconto;
- parcelas;
- data da primeira parcela das opcoes com entrada.

## 12. Resumo antes do PDF

Antes de gerar o PDF, o app mostra uma pre-visualizacao das opcoes.

O usuario pode:

- voltar para editar;
- gerar o PDF da proposta.

Tudo que nao foi alterado permanece no padrao do app.

## 13. PDF gerado

O PDF contem:

- dados gerais;
- quadro demonstrativo;
- debitos consolidados;
- opcoes selecionadas;
- valores de entrada, desconto, saldo e parcela;
- condicoes gerais;
- observacoes;
- condicoes adicionais;
- memoria da Selic, quando houver parcela pre-fixada.

### Parcelas variaveis

Sao parcelas sujeitas a atualizacao mensal conforme as condicoes gerais.

### Parcelas pre-fixadas

Sao calculadas com base na media da Selic dos ultimos 12 meses.

Quando esse modo e usado, o PDF inclui uma memoria de calculo com os meses considerados e a taxa media.

## 14. JSON

O JSON e o arquivo de rascunho do caso.

Ele guarda:

- dados gerais;
- subdebitos;
- codigos UG/Gestao e GRU(CR);
- condicoes adicionais;
- regras de proposta;
- ajustes de entrada, desconto e parcelas;
- data da primeira parcela nas opcoes com entrada.

Ao abrir um JSON depois, os dados salvos sao recuperados.

Se nao houver ajustes de proposta salvos, o app usa o padrao geral.

## 15. Alertas comuns

### Campos obrigatorios ausentes

O app avisa quando dados essenciais estao faltando.

### Datas invalidas

Pode ocorrer quando:

- a data esta em formato invalido;
- a data limite e posterior a entrada/primeira parcela;
- a primeira parcela com entrada foi postergada alem do limite permitido.

### Subdebito sem UG/Gestao ou GRU(CR)

O app nao gera proposta enquanto houver subdebito sem codigo de arrecadacao completo.

### Selecao vazia de propostas

E necessario selecionar ao menos uma opcao.

### Calculo progressivo excepcional

O app alerta porque essa opcao deve ser usada somente quando juridicamente cabivel.

### Erro na Selic

Se nao for possivel atualizar a base da Selic, o app tentara usar a base local disponivel.

## 16. Boas praticas

- Confira os dados importados do relatorio.
- Revise processo, devedor, CPF/CNPJ e NUP.
- Confira datas antes de gerar a proposta.
- Complete UG/Gestao e GRU(CR) em todos os subdebitos.
- Confira os debitos consolidados.
- Salve o JSON antes de gerar o PDF.
- Revise o PDF antes de enviar ao devedor.
- Use a faixa progressiva somente se houver autorizacao.

