var CABECALHO = ["ID", "Empresa", "Produto", "Nome", "Data", "Quantidade", "Preço Unitário", "Preço Total"];
var NUM_COLUNAS = CABECALHO.length;

var CACHE_CHAVE_BASE = "linhas_planilha";
var CACHE_SEGUNDOS = 60;      // quanto tempo o cache vale antes de reler a planilha
var CACHE_TAMANHO_CHUNK = 90000; // um pouco abaixo do limite de 100KB por chave


// --------------------------------------------------------------------------
// Planilha
// --------------------------------------------------------------------------

// Guarda o ID interno (estável mesmo se a aba for renomeada) da aba usada
// da primeira vez, e sempre volta pra ela — em vez de usar getActiveSheet(),
// que muda conforme qual aba está aberta no navegador no momento da chamada.
// Pra apontar pra outra aba, apague a Script Property ID_ABA_DADOS em
// Configurações do projeto > Propriedades do script.
function getPlanilha() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var props = PropertiesService.getScriptProperties();
  var idAbaFixada = props.getProperty("ID_ABA_DADOS");

  var planilha = null;
  if (idAbaFixada) {
    var idNumerico = Number(idAbaFixada);
    var abas = ss.getSheets();
    for (var i = 0; i < abas.length; i++) {
      if (abas[i].getSheetId() === idNumerico) {
        planilha = abas[i];
        break;
      }
    }
  }

  if (!planilha) {
    // primeira execução (ou a aba fixada foi excluída): usa a aba ativa
    // agora e trava nela pra sempre
    planilha = ss.getActiveSheet();
    props.setProperty("ID_ABA_DADOS", String(planilha.getSheetId()));
  }

  if (planilha.getLastRow() === 0) {
    planilha.appendRow(CABECALHO);
  }
  garantirColunaNome(planilha);
  garantirFormatoTexto(planilha);
  return planilha;
}

// Migração automática: planilhas criadas antes da coluna "Nome" existir têm
// o cabeçalho antigo (ID, Empresa, Produto, Data, ...). Detecta isso e abre
// espaço pra "Nome" logo depois de "Produto", empurrando Data/Quantidade/
// Preço Unitário/Preço Total uma coluna pra direita sem perder nenhum dado
// (insertColumnBefore desloca o conteúdo das células, não apaga). Roda só
// uma vez por planilha — depois disso o cabeçalho já bate com CABECALHO.
function garantirColunaNome(planilha) {
  var props = PropertiesService.getScriptProperties();
  var chave = "COLUNA_NOME_ADICIONADA_" + planilha.getSheetId();
  if (props.getProperty(chave) === "1") return;

  var larguraCabecalho = Math.max(planilha.getLastColumn(), 1);
  var cabecalhoAtual = planilha.getRange(1, 1, 1, larguraCabecalho).getValues()[0];
  if (cabecalhoAtual.indexOf("Nome") === -1) {
    planilha.insertColumnBefore(4); // coluna D: antes da antiga "Data"
    planilha.getRange(1, 4).setValue("Nome");
    // a coluna Data mudou de D pra E: força garantirFormatoTexto a rodar de
    // novo agora, senão o formato de texto puro ficaria preso na coluna errada
    props.deleteProperty("FORMATO_TEXTO_APLICADO_" + planilha.getSheetId());
  }
  props.setProperty(chave, "1");
}

// Formata as colunas ID e Data como texto puro ("@"), pra o Sheets nunca mais
// converter um ID todo numérico em número (perdendo zero à esquerda) nem uma
// data em data real (que depois volta com o fuso errado). Roda só uma vez.
function garantirFormatoTexto(planilha) {
  var props = PropertiesService.getScriptProperties();
  var chave = "FORMATO_TEXTO_APLICADO_" + planilha.getSheetId();
  if (props.getProperty(chave) === "1") return;
  planilha.getRange("A:A").setNumberFormat("@"); // ID
  planilha.getRange("E:E").setNumberFormat("@"); // Data (coluna E desde a coluna "Nome" ser adicionada)
  props.setProperty(chave, "1");
}

// Se a célula já foi convertida pelo Sheets num objeto Date de verdade
// (aconteceu com linhas gravadas antes da coluna virar texto puro), formata
// de volta pro fuso horário DA PRÓPRIA PLANILHA — em vez de deixar o
// JSON.stringify serializar em UTC, que pode deslocar o dia salvo.
function normalizarDataLida(valor) {
  if (Object.prototype.toString.call(valor) === "[object Date]") {
    var fuso = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
    return Utilities.formatDate(valor, fuso, "dd/MM/yyyy");
  }
  return valor;
}

function lerTodasLinhasDaPlanilha() {
  var planilha = getPlanilha();
  var valores = planilha.getDataRange().getValues();
  var linhas = [];
  for (var i = 1; i < valores.length; i++) {
    var linha = valores[i];
    if (!linha[0]) continue; // pula linhas vazias
    linhas.push({
      id: String(linha[0]), // nunca deixa um ID todo numérico virar Number aqui
      empresa: linha[1],
      produto: linha[2],
      nome: linha[3],
      data: normalizarDataLida(linha[4]),
      quantidade: linha[5],
      preco_unitario: linha[6],
      preco_total: linha[7],
    });
  }
  return linhas;
}

// Constrói, com UMA ÚNICA leitura da coluna A, um mapa "id -> número da linha".
// Reaproveitado por todas as atualizações/remoções de uma mesma requisição.
function construirIndiceIds(planilha) {
  var indice = {};
  var ultimaLinha = planilha.getLastRow();
  if (ultimaLinha < 2) return indice;
  var ids = planilha.getRange(2, 1, ultimaLinha - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (ids[i][0] !== "") indice[String(ids[i][0])] = i + 2; // +2: cabeçalho + índice 1-based
  }
  return indice;
}


// --------------------------------------------------------------------------
// Cache (evita reler a planilha inteira a cada GET)
// --------------------------------------------------------------------------

function cacheSalvarLista(linhas) {
  try {
    var cache = CacheService.getScriptCache();
    var texto = JSON.stringify(linhas);
    var numChunks = Math.max(1, Math.ceil(texto.length / CACHE_TAMANHO_CHUNK));

    var valores = {};
    for (var i = 0; i < numChunks; i++) {
      valores[CACHE_CHAVE_BASE + "_" + i] = texto.substr(i * CACHE_TAMANHO_CHUNK, CACHE_TAMANHO_CHUNK);
    }
    valores[CACHE_CHAVE_BASE + "_meta"] = String(numChunks);
    cache.putAll(valores, CACHE_SEGUNDOS);
  } catch (erro) {
    // Cache é só otimização: se a lista for grande demais até pra isso,
    // simplesmente seguimos sem cache em vez de quebrar a requisição.
  }
}

function cacheCarregarLista() {
  try {
    var cache = CacheService.getScriptCache();
    var metaStr = cache.get(CACHE_CHAVE_BASE + "_meta");
    if (!metaStr) return null;

    var numChunks = parseInt(metaStr, 10);
    var chaves = [];
    for (var i = 0; i < numChunks; i++) chaves.push(CACHE_CHAVE_BASE + "_" + i);

    var partes = cache.getAll(chaves);
    var texto = "";
    for (var i = 0; i < numChunks; i++) {
      var parte = partes[CACHE_CHAVE_BASE + "_" + i];
      if (parte === undefined) return null; // algum chunk expirou/sumiu -> descarta tudo
      texto += parte;
    }
    return JSON.parse(texto);
  } catch (erro) {
    return null; // qualquer problema no cache -> volta a ler da planilha normalmente
  }
}

function invalidarCache() {
  try {
    var cache = CacheService.getScriptCache();
    var metaStr = cache.get(CACHE_CHAVE_BASE + "_meta");
    var chaves = [CACHE_CHAVE_BASE + "_meta"];
    if (metaStr) {
      var numChunks = parseInt(metaStr, 10);
      for (var i = 0; i < numChunks; i++) chaves.push(CACHE_CHAVE_BASE + "_" + i);
    }
    cache.removeAll(chaves);
  } catch (erro) {
    // se falhar, o pior caso é o cache expirar sozinho em até 60s
  }
}


// --------------------------------------------------------------------------
// Resposta HTTP
// --------------------------------------------------------------------------

function responder(objeto) {
  return ContentService.createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}


// --------------------------------------------------------------------------
// GET /exec?empresa=Nome  -> lista os registros (todos, ou só de uma empresa)
// --------------------------------------------------------------------------

function doGet(e) {
  try {
    var filtroEmpresa = (e && e.parameter && e.parameter.empresa) || null;

    var linhas = cacheCarregarLista();
    if (!linhas) {
      linhas = lerTodasLinhasDaPlanilha();
      cacheSalvarLista(linhas);
    }

    if (filtroEmpresa) {
      linhas = linhas.filter(function (l) { return l.empresa === filtroEmpresa; });
    }

    return responder({ ok: true, linhas: linhas });
  } catch (erro) {
    return responder({ ok: false, erro: String(erro) });
  }
}


// --------------------------------------------------------------------------
// POST /exec  -> body JSON com "acao": "salvar" ou "remover"
// --------------------------------------------------------------------------

// Serializa doPost inteiro: sem isso, duas gravações/remoções ao mesmo tempo
// podiam disputar o mesmo índice de linhas (uma desloca linhas enquanto a
// outra ainda usa números de linha lidos antes do deslocamento).
function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (erro) {
    return responder({ ok: false, erro: "Servidor ocupado, tente novamente em instantes." });
  }

  try {
    var planilha = getPlanilha();
    var corpo = JSON.parse(e.postData.contents);

    if (corpo.acao === "salvar") {
      var resultadoSalvar = salvarRegistros(planilha, corpo.novas || [], corpo.existentes || []);
      invalidarCache();
      return responder({ ok: true, idsNaoEncontrados: resultadoSalvar.idsNaoEncontrados });
    }

    if (corpo.acao === "remover") {
      var removidas = removerRegistros(planilha, corpo.ids || []);
      invalidarCache();
      return responder({ ok: true, removidas: removidas });
    }

    if (corpo.acao === "renomearProdutos") {
      var resultadoRenomear = renomearProdutos(planilha, corpo.itens || []);
      invalidarCache();
      return responder({ ok: true, idsNaoEncontrados: resultadoRenomear.idsNaoEncontrados });
    }

    return responder({ ok: false, erro: "Ação desconhecida: " + corpo.acao });
  } catch (erro) {
    return responder({ ok: false, erro: String(erro) });
  } finally {
    lock.releaseLock();
  }
}

// Devolve { idsNaoEncontrados } em vez de nada: se algum "existente" não for
// achado na planilha (linha apagada por fora, por exemplo), quem chamou
// precisa saber disso — antes essa edição era descartada em silêncio e a
// resposta dizia "ok" do mesmo jeito.
function salvarRegistros(planilha, novas, existentes) {
  // Linhas novas: um único setValues() em bloco, em vez de um appendRow() por linha.
  if (novas.length > 0) {
    var linhaInicial = planilha.getLastRow() + 1;
    var dados = novas.map(function (l) {
      return [l.id, l.empresa, l.produto, l.nome, l.data, l.quantidade, l.preco_unitario, l.preco_total];
    });
    planilha.getRange(linhaInicial, 1, dados.length, NUM_COLUNAS).setValues(dados);
  }

  if (existentes.length === 0) return { idsNaoEncontrados: [] };

  var indice = construirIndiceIds(planilha); // uma única leitura, não uma por item
  var linhasAlvo = [];
  var idsNaoEncontrados = [];
  existentes.forEach(function (l) {
    var linha = indice[String(l.id)];
    if (linha) {
      linhasAlvo.push({ linha: linha, dados: l });
    } else {
      idsNaoEncontrados.push(l.id);
    }
  });

  if (linhasAlvo.length === 0) return { idsNaoEncontrados: idsNaoEncontrados };

  if (linhasAlvo.length === 1) {
    // caso comum (uma linha só editada): grava direto, sem ler nada antes
    var item = linhasAlvo[0];
    planilha.getRange(item.linha, 4, 1, 5)
      .setValues([[item.dados.nome, item.dados.data, item.dados.quantidade, item.dados.preco_unitario, item.dados.preco_total]]);
    return { idsNaoEncontrados: idsNaoEncontrados };
  }

  // Várias linhas existentes editadas na mesma chamada: em vez de uma
  // chamada setValues() por linha, lê o bloco do menor ao maior número de
  // linha de uma vez, atualiza só as linhas alvo em memória, e grava tudo
  // de volta com um único setValues() — trocamos ler/escrever algumas
  // células a mais (as linhas do meio que não mudaram) por bem menos
  // chamadas à planilha, que é o que realmente pesa no tempo de resposta.
  var numeros = linhasAlvo.map(function (item) { return item.linha; });
  var linhaMin = Math.min.apply(null, numeros);
  var linhaMax = Math.max.apply(null, numeros);
  var bloco = planilha.getRange(linhaMin, 4, linhaMax - linhaMin + 1, 5).getValues();

  linhasAlvo.forEach(function (item) {
    var offset = item.linha - linhaMin;
    bloco[offset] = [item.dados.nome, item.dados.data, item.dados.quantidade, item.dados.preco_unitario, item.dados.preco_total];
  });

  planilha.getRange(linhaMin, 4, bloco.length, 5).setValues(bloco);
  return { idsNaoEncontrados: idsNaoEncontrados };
}

function removerRegistros(planilha, ids) {
  if (!ids.length) return 0;

  var indice = construirIndiceIds(planilha); // uma única leitura, não uma por ID
  var linhasParaRemover = [];
  ids.forEach(function (id) {
    var linhaIndex = indice[String(id)];
    if (linhaIndex) linhasParaRemover.push(linhaIndex);
  });

  // de baixo para cima, senão os índices das próximas linhas mudam
  linhasParaRemover.sort(function (a, b) { return b - a; });

  // agrupa linhas vizinhas num único deleteRows(), em vez de um deleteRow()
  // por linha — comum ao remover de uma vez um produto cujas compras foram
  // todas salvas na mesma sessão (ficam em linhas consecutivas)
  var i = 0;
  while (i < linhasParaRemover.length) {
    var fimBloco = linhasParaRemover[i];
    var tamanhoBloco = 1;
    while (
      i + tamanhoBloco < linhasParaRemover.length &&
      linhasParaRemover[i + tamanhoBloco] === fimBloco - tamanhoBloco
    ) {
      tamanhoBloco++;
    }
    planilha.deleteRows(fimBloco - tamanhoBloco + 1, tamanhoBloco);
    i += tamanhoBloco;
  }

  return linhasParaRemover.length;
}

// Renomeia o produto (pasta) e/ou o nome de linhas já salvas, por ID — usado
// pra consolidar produtos parecidos que viravam pastas separadas por engano
// (ex: "Vinho pergola" e "Vinho randon" -> pasta "Vinho", com o nome de cada
// marca guardado por linha). Cada item pode trazer "produto" e/ou "nome";
// só a coluna informada é sobrescrita.
function renomearProdutos(planilha, itens) {
  var idsNaoEncontrados = [];
  if (!itens.length) return { idsNaoEncontrados: idsNaoEncontrados };

  var indice = construirIndiceIds(planilha); // uma única leitura, não uma por item
  itens.forEach(function (item) {
    var linha = indice[String(item.id)];
    if (!linha) {
      idsNaoEncontrados.push(item.id);
      return;
    }
    if (item.produto !== undefined) planilha.getRange(linha, 3).setValue(item.produto);
    if (item.nome !== undefined) planilha.getRange(linha, 4).setValue(item.nome);
  });

  return { idsNaoEncontrados: idsNaoEncontrados };
}