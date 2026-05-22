# PactuaCalc - Instruções de uso

## 1. Finalidade do aplicativo

O PactuaCalc auxilia na organização de subdébitos, códigos de arrecadação e propostas de acordo. Ele permite importar ou preencher dados, consolidar débitos por chave arrecadatória, ajustar opções de proposta e gerar um PDF final.

O fluxo normal de uso é:

1. Criar um caso a partir de relatório ou abrir um JSON.
2. Conferir os dados gerais.
3. Revisar os subdébitos.
4. Completar UG/Gestão e GRU(CR).
5. Conferir os débitos consolidados.
6. Preencher condições adicionais, se houver.
7. Gerar opções da proposta.
8. Selecionar e ajustar as propostas.
9. Conferir o resumo.
10. Gerar o PDF.
11. Salvar o JSON para edições futuras.

## 2. Botões superiores

### Criar a partir de relatório

Cria um novo caso a partir de um relatório importado. Use esta opção quando iniciar um trabalho novo.

### Adicionar relatório

Adiciona outro relatório ao caso atual. O app tenta preservar dados já preenchidos manualmente e pode alertar sobre divergências.

### Abrir JSON

Abre um rascunho salvo anteriormente. O JSON carrega dados gerais, subdébitos, códigos, condições adicionais e ajustes de propostas.

### Salvar JSON

Salva o estado atual do caso. Este arquivo é o rascunho editável do trabalho. Recomenda-se salvar antes e depois de gerar uma proposta.

### Ajuda

Abre estas instruções de uso.

### Sobre

Mostra informações do aplicativo, licença e créditos.

### Sair

Fecha o aplicativo.

## 3. Dados Gerais

O quadro Dados Gerais contém os dados principais do caso.

Campos obrigatórios aparecem destacados, normalmente com fundo rosa/vermelho quando vazios ou pendentes.

### Processo

Número do processo judicial. Campo obrigatório.

### Devedor

Nome do devedor. Campo obrigatório.

### CPF/CNPJ

Documento do devedor. Campo obrigatório quando exigido pelo fluxo de proposta.

### NUP do requerimento

Número único de protocolo do requerimento. Campo obrigatório.

### Competência

Competência da atualização do cálculo. O app pode preencher automaticamente a partir da data de atualização.

### Data de atualização

Data-base do cálculo. Campo obrigatório.

### Tipo de parcela

Define como as parcelas serão tratadas:

- VARIÁVEL (PÓS-FIXADO): parcelas sujeitas a atualização mensal.
- FIXO (PREFIXADO): parcelas calculadas com base na média da Selic dos últimos 12 meses.

Campo obrigatório.

### Data limite resposta

Data até a qual o devedor deve responder a proposta. Campo obrigatório.

Regra importante: a data limite não pode ser posterior a data da entrada/primeira parcela.

### Data da Entrada/Primeira Parcela

Data prevista para pagamento da entrada ou da primeira parcela. Campo obrigatório.

Regra importante: não pode ser anterior a data atual.

### Multa (%)

Percentual de multa utilizado no cálculo quando aplicável. O padrão é 10%.

### Valor bloqueado geral

Valor total bloqueado/depositado que pode ser distribuído entre os subdébitos, quando aplicável.

## 4. Subdébitos

O quadro Subdébitos lista os itens que compõem a dívida.

Colunas principais:

- Tipo.
- Descrição.
- UG/Gestão.
- GRU(CR).
- Valor atualizado.
- Multa art. 523.
- Valor bloqueado.

Tipos aceitos:

- PRINCIPAL.
- HONORÁRIOS.
- MULTA (exceto art. 523).

### Identificação de honorários

Na edição manual, o app considera um subdébito como honorários quando:

- o Tipo for HONORÁRIOS, com ou sem acento e independentemente de maiúsculas/minúsculas; ou
- a combinação de códigos for exatamente UG 110060 e GRU(CR) 91710-9.

Nesses casos, o Tipo é ajustado automaticamente para HONORÁRIOS e os códigos oficiais de honorários são preservados.

A Descrição, sozinha, não transforma um subdébito manual em honorários. Assim, descrições como "principal sem honorários" ou "principal (excluído honorário)" não alteram o Tipo se os códigos e o Tipo indicarem PRINCIPAL.

Na importação de relatórios, o app também pode reconhecer honorários por texto afirmativo do relatório, mas evita classificar como honorários quando o texto indicar contexto negativo, como "sem honorários", "exceto honorários", "excluído honorário" ou "não inclui honorários".

Subdébitos destacados em vermelho são considerados honorários. Eles usam a faixa de desconto definida pelos subdébitos principais, salvo quando houver somente honorários/encargos.

Campos de edição dos subdébitos ficam na parte inferior do quadro. Normalmente usam fundo amarelo claro.

### Atualizar

Altera o subdébito selecionado com os dados preenchidos no formulário.

### Adicionar

Inclui um novo subdébito manualmente.

### Excluir

Remove o subdébito selecionado.

## 5. UG/Gestão e GRU(CR)

Cada subdébito precisa ter UG/Gestão e GRU(CR) antes da geração da proposta.

### UG/Gestão

A UG é escolhida em lista suspensa. A Gestão é preenchida automaticamente conforme a UG selecionada.

A lista pode mostrar a descrição da UG para facilitar a escolha, mas o código gravado no app, no JSON e no PDF é o código.

### GRU(CR)

A GRU(CR) também é escolhida em lista suspensa. A descrição ajuda na escolha, mas o código é o dado usado pelo app.

Para honorários advocatícios, use UG 110060 e GRU(CR) 91710-9. Ao inserir essa combinação, o app identifica o subdébito como honorários e ajusta o Tipo automaticamente.

### Aplicar aos selecionados

Permite aplicar UG/Gestão e GRU(CR) a vários subdébitos selecionados de uma vez.

## 6. Débitos consolidados

O quadro Débitos consolidados mostra uma visão agrupada dos subdébitos.

A consolidação serve para:

- agrupar valores por chave arrecadatória;
- facilitar a conferência da arrecadação;
- gerar linhas consolidadas no PDF;
- permitir alterar a descrição consolidada usada na proposta.

Na consolidação, são somados valores como:

- valor atualizado;
- multa Art 523;
- valor bloqueado.

Se dois subdébitos tiverem a mesma chave de arrecadação, podem aparecer como uma linha consolidada. Isso ajuda a evitar repetição desnecessária no PDF.

### Alterar descrição consolidada

Para alterar:

1. Selecione um débito consolidado.
2. Digite a nova descrição.
3. Clique no botão de alteração.

A alteração vale para a apresentação consolidada e para a proposta gerada.

## 7. Regras de cálculo

Esta seção resume as regras usadas pelo app para montar os valores das propostas.

### Valor total do subdébito

Para cada subdébito, o valor total é:

- valor atualizado; mais
- multa Art 523.

O valor bloqueado não aumenta o valor total. Ele é usado como abatimento na montagem da proposta.

### Consolidação por chave arrecadatória

Antes de gerar propostas e PDF, o app consolida subdébitos que tenham a mesma UG/Gestão e a mesma GRU(CR).

Na consolidação, são somados:

- valor atualizado;
- multa Art 523;
- valor bloqueado.

Subdébitos sem UG/Gestão ou sem GRU(CR) ficam separados e impedem a geração da proposta até que os códigos sejam preenchidos.

### Valor bloqueado geral

Quando o campo Valor bloqueado geral for preenchido, o app pode distribuir esse valor entre os subdébitos proporcionalmente ao valor total de cada um.

Nenhum subdébito recebe valor bloqueado maior que o seu valor total.

Nas propostas, o valor bloqueado efetivo é abatido do saldo. Nas opções com entrada obrigatória, quando a regra de aproveitar bloqueio como entrada estiver ativa, o bloqueio reduz a entrada GRU a pagar.

### Base de desconto

A base de desconto normalmente considera o saldo de cada subdébito depois do valor bloqueado.

Quando a regra "desconto sobre total" estiver ativa, o desconto também incide sobre valores bloqueados.

O desconto total de uma proposta é distribuído proporcionalmente entre as linhas consolidadas conforme a base de desconto de cada uma.

### Honorários e encargos na faixa da opção a vista

Para definir a faixa de desconto da opção 2, o app exclui honorários e encargos da base de faixa.

Honorários são identificados pela regra descrita na seção Subdébitos:

- Tipo HONORÁRIOS; ou
- combinação UG 110060 + GRU(CR) 91710-9.

Na importação, também pode haver identificação por texto afirmativo, desde que não exista contexto negativo como "sem honorários" ou "excluído honorário".

O percentual encontrado para a opção a vista é aplicado sobre a base geral de desconto. Se houver somente honorários/encargos, a faixa usa o valor total.

### Opção 2 - pagamento a vista

Na opção 2, o usuário escolhe o modo de cálculo do desconto:

- percentual único por faixa; ou
- faixa progressiva.

No percentual único por faixa, o app encontra uma única faixa com base no valor elegível e aplica o percentual encontrado sobre toda a base geral da opção a vista.

Na faixa progressiva, o app calcula um percentual efetivo pelas faixas progressivas e aplica esse percentual efetivo sobre a base geral da opção a vista.

As faixas atuais são:

- até R$ 20.000,00: 50%.
- até R$ 60.000,00: 35%.
- até R$ 100.000,00: 30%.
- acima de R$ 100.000,00: 25%.

### Modalidades padrão

As modalidades padrão são:

- Opção 1: parcelamento comum, até 60 parcelas, sem desconto e sem entrada mínima.
- Opção 2: pagamento a vista, parcela única, desconto conforme faixa.
- Opção 3.A: parcelado sem entrada, até 12 parcelas, desconto de 20%.
- Opção 3.B: parcelado sem entrada, até 24 parcelas, desconto de 15%.
- Opção 4.A: com entrada mínima de 20%, até 12 parcelas, desconto de 25%.
- Opção 4.B: com entrada mínima de 20%, até 24 parcelas, desconto de 20%.
- Opção 4.C: com entrada mínima de 20%, até 36 parcelas, desconto de 10%.
- Opção 4.D: com entrada mínima de 20%, até 60 parcelas, desconto de 5%.

### Entrada

Nas opções com entrada mínima, a entrada é calculada sobre o valor total da dívida consolidada.

Se houver valor bloqueado e a regra de aproveitar bloqueio como entrada estiver ativa, o app calcula:

- entrada GRU = entrada mínima exigida menos valor bloqueado efetivo.

Se o bloqueio for maior ou igual a entrada mínima exigida, a entrada GRU fica zerada.

Nas opções 1, 3.A e 3.B, a entrada é opcional. Ela não gera desconto, apenas reduz o saldo a parcelar.

### Saldo, parcelas e valor final

O saldo remanescente é:

- valor total da dívida;
- menos valor bloqueado efetivo;
- menos entrada GRU;
- menos desconto.

O valor da parcela é o saldo remanescente dividido pela quantidade de parcelas, salvo quando houver parcela FIXO (PREFIXADO), que aplica a regra de pré-fixação pela Selic.

O valor final apresentado é:

- valor bloqueado efetivo;
- mais entrada GRU;
- mais saldo remanescente.

### Parcelas pré-fixadas pela Selic

Quando o Tipo de parcela for FIXO (PREFIXADO) e a proposta tiver mais de uma parcela, o app calcula a parcela fixa com base na média aritmética da Selic dos últimos 12 meses.

O app considera a data de atualização e a data efetiva da primeira parcela para estimar o período de correção, calcula a primeira e a última parcela com juros simples e usa a média entre elas como parcela fixa.

Nas opções sem entrada, a data efetiva da primeira parcela é a Data da Entrada/Primeira Parcela dos Dados Gerais.

Nas opções com entrada, a Data da Entrada/Primeira Parcela dos Dados Gerais corresponde à entrada. A primeira parcela usa a data própria das opções com entrada, definida automaticamente para o mês seguinte ou ajustada pelo usuário no quadro de propostas.

A quantidade de Selics aplicadas à primeira parcela é a diferença de meses entre a data de atualização e a data efetiva da primeira parcela. Se estiverem no mesmo mês, não há acréscimo inicial; se a primeira parcela estiver no mês seguinte, há uma Selic; se estiver dois meses à frente, há duas Selics, e assim por diante.

Quando esse modo é usado, o PDF inclui memória de cálculo com a taxa média da Selic e os valores considerados.

### Ajustes permitidos pelo usuário

Nos ajustes finais das propostas:

- o desconto pode ser reduzido, mas não aumentado acima do padrão da modalidade;
- o desconto não pode ser negativo;
- a entrada obrigatória não pode ser reduzida abaixo do mínimo da modalidade;
- nas opções 1, 3.A e 3.B, a entrada opcional pode ser preenchida;
- a quantidade de parcelas pode ser reduzida, mas não aumentada acima do padrão da modalidade;
- a quantidade de parcelas deve respeitar os limites da modalidade.

Quando houver alteração em relação ao padrão predefinido da modalidade, o PDF identifica a proposta como opção adaptada ao caso concreto.

Nas opções 1, 3.A e 3.B, se o usuário informar entrada maior que zero, o título da opção no PDF passa a indicar entrada. Exemplo: "OPÇÃO 3.A: PARCELADO SEM ENTRADA" passa a "OPÇÃO 3.A: PARCELADO COM ENTRADA".

Os limites de parcelas são:

- Opção 1: 1 a 60.
- Opção 2: 1.
- Opção 3.A: 2 a 12.
- Opção 3.B: 13 a 24.
- Opção 4.A: 2 a 12.
- Opção 4.B: 13 a 24.
- Opção 4.C: 25 a 36.
- Opção 4.D: 37 a 60.

### Data da primeira parcela nas opções com entrada

Nas opções com entrada, a entrada usa a Data da Entrada/Primeira Parcela dos Dados Gerais.

A primeira parcela padrão é calculada para o último dia do mês seguinte ao pagamento da entrada.

O usuário pode antecipar essa data, mas não pode postergá-la além do padrão calculado.

Essa data também é usada no cálculo da parcela pré-fixada quando houver entrada.

## 8. Condições adicionais

O campo Condições adicionais permite incluir informações específicas do caso.

Exemplos:

- condições jurídicas adicionais;
- observações relevantes;
- ressalvas;
- informações acordadas no atendimento.

O texto preenchido será levado ao PDF.

## 9. Gerar opções da proposta

O botão GERAR OPÇÕES DA PROPOSTA inicia o fluxo de proposta.

Antes disso, confira:

- dados obrigatórios preenchidos;
- datas válidas;
- subdébitos revisados;
- UG/Gestão em todos os subdébitos;
- GRU(CR) em todos os subdébitos;
- condições adicionais, se houver.

Se faltar UG/Gestão ou GRU(CR), o app exibirá alerta e não gerará a proposta.

## 10. Seleção das opções da proposta

Após clicar em gerar, o app mostra as opções que podem constar na proposta.

Opções:

- 1 - Parcelamento comum.
- 2 - Pagamento a vista.
- 3.A - Parcelado sem entrada.
- 3.B - Parcelado sem entrada.
- 4.A - Com entrada.
- 4.B - Com entrada.
- 4.C - Com entrada.
- 4.D - Com entrada.

O usuário pode marcar uma ou mais opções.

Se nenhuma opção for selecionada, o app exibirá alerta.

## 11. Desconto da opção a vista

Quando a opção 2 estiver selecionada, o app pergunta como calcular o desconto:

- Percentual único por faixa.
- Faixa progressiva.

### Percentual único por faixa

É o padrão.

Faixas:

- até R$ 20.000,00: 50%.
- até R$ 60.000,00: 35%.
- até R$ 100.000,00: 30%.
- acima de R$ 100.000,00: 25%.

O percentual encontrado é aplicado sobre toda a base geral da opção a vista.

### Faixa progressiva

É uma opção excepcional.

Ao selecionar essa opção, o app alerta:

"Esta opção é excepcional. Verifique se é possível concedê-lo, antes de prosseguir."

Use somente quando houver autorização para esse modo de cálculo.

### Honorários e encargos

Para definir a faixa, o app exclui honorários e encargos.

Honorários são identificados pela regra descrita na seção Subdébitos: Tipo HONORÁRIOS ou combinação UG 110060 + GRU(CR) 91710-9. Na importação, também pode haver identificação por texto afirmativo, desde que não exista contexto negativo como "sem honorários" ou "excluído honorário".

Exemplo:

- Principal: R$ 80.000,00.
- Honorários: R$ 20.000,00.
- Total: R$ 100.000,00.

A faixa será definida por R$ 80.000,00, resultando em 30%.

Depois, o percentual será aplicado sobre a base geral.

Se houver somente honorários/encargos, a faixa usa o valor total.

## 12. Ajustes de entrada, desconto e parcelas

Depois da seleção das opções, o app abre o quadro de ajustes.

Campos alterados ficam em vermelho e negrito.

### Entrada

Nas propostas com entrada obrigatória, a entrada só pode aumentar.

Nas opções 1, 3.A e 3.B, o usuário pode preencher uma entrada opcional.

Importante: a entrada opcional nas opções 1, 3.A e 3.B não gera desconto. Ela apenas reduz o saldo a parcelar.

### Desconto

O desconto só pode diminuir.

O app impede imediatamente valor maior que o desconto padrão da proposta.

Também impede valor negativo.

### Parcelas

As parcelas podem ser reduzidas dentro da faixa permitida.

O app impede aumentar acima do padrão da proposta.

Faixas:

- Proposta 1: 1 a 60.
- Proposta 3.A: 2 a 12.
- Proposta 3.B: 13 a 24.
- Proposta 4.A: 2 a 12.
- Proposta 4.B: 13 a 24.
- Proposta 4.C: 25 a 36.
- Proposta 4.D: 37 a 60.

### Data da primeira parcela nas opções com entrada

Nas opções com entrada, a entrada fica prevista para a Data da Entrada/Primeira Parcela dos Dados Gerais.

O app calcula automaticamente a primeira parcela para o último dia do mês seguinte.

Exemplo:

- Entrada: 25/05/2026.
- Primeira parcela padrão: 30/06/2026.

O usuário pode antecipar essa data, mas não pode postergá-la.

O app impede imediatamente data posterior ao padrão calculado.

### Resetar alterações

O botão Resetar alterações (voltar ao padrão geral) retorna todos os campos ao padrão:

- entrada;
- desconto;
- parcelas;
- data da primeira parcela das opções com entrada.

## 13. Resumo antes do PDF

Antes de gerar o PDF, o app mostra uma pré-visualização das opções.

O usuário pode:

- voltar para editar;
- gerar o PDF da proposta.

Tudo que não foi alterado permanece no padrão do app.

## 14. PDF gerado

O PDF contém:

- dados gerais;
- quadro demonstrativo;
- débitos consolidados;
- opções selecionadas;
- valores de entrada, desconto, saldo e parcela;
- indicação de opção adaptada ao caso concreto, quando houver alteração nos padrões predefinidos;
- condições gerais;
- observações;
- condições adicionais;
- memória da Selic, quando houver parcela pré-fixada.

### Parcelas variáveis

São parcelas sujeitas a atualização mensal conforme as condições gerais.

### Parcelas pré-fixadas

São calculadas com base na média da Selic dos últimos 12 meses.

Quando esse modo é usado, o PDF inclui uma memória de cálculo com os meses considerados e a taxa média.

Nas opções sem entrada, os meses considerados partem da Data da Entrada/Primeira Parcela dos Dados Gerais. Nas opções com entrada, partem da data da primeira parcela após a entrada, inclusive quando essa data for alterada no quadro de ajustes.

## 15. JSON

O JSON é o arquivo de rascunho do caso.

Ele guarda:

- dados gerais;
- subdébitos;
- códigos UG/Gestão e GRU(CR);
- condições adicionais;
- regras de proposta;
- ajustes de entrada, desconto e parcelas;
- data da primeira parcela nas opções com entrada.

Ao abrir um JSON depois, os dados salvos são recuperados.

Se não houver ajustes de proposta salvos, o app usa o padrão geral.

Ao salvar o JSON, o app sugere o mesmo padrão de nome do PDF, mas sem data e hora. Assim, o rascunho tende a ser salvo sobre o JSON anterior do mesmo caso, salvo se o usuário alterar o nome.

## 16. Alertas comuns

### Campos obrigatórios ausentes

O app avisa quando dados essenciais estão faltando.

### Datas inválidas

Pode ocorrer quando:

- a data está em formato inválido;
- a data limite é posterior a entrada/primeira parcela;
- a primeira parcela com entrada foi postergada além do limite permitido.

### Subdébito sem UG/Gestão ou GRU(CR)

O app não gera proposta enquanto houver subdébito sem código de arrecadação completo.

### Seleção vazia de propostas

É necessário selecionar ao menos uma opção.

### Cálculo progressivo excepcional

O app alerta porque essa opção deve ser usada somente quando juridicamente cabível.

### Erro na Selic

Se não for possível atualizar a base da Selic, o app tentará usar a base local disponível.

## 17. Boas práticas

- Confira os dados importados do relatório.
- Revise processo, devedor, CPF/CNPJ e NUP.
- Confira datas antes de gerar a proposta.
- Complete UG/Gestão e GRU(CR) em todos os subdébitos.
- Confira os débitos consolidados.
- Salve o JSON antes de gerar o PDF.
- Revise o PDF antes de enviar ao devedor.
- Use a faixa progressiva somente se houver autorização.





