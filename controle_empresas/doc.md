# 📖 Documentação Técnica — Controle de Empresas

> Explicação passo a passo de como o código de `controle_empresas.py` funciona por dentro: cada bloco, classe e função, na ordem em que aparecem no arquivo.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)
![Arquitetura](https://img.shields.io/badge/Arquitetura-MVC%20simplificado-9b59b6)

---

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Configuração inicial](#2-configuração-inicial)
3. [Funções utilitárias](#3-funções-utilitárias)
4. [Integração com o Google Sheets](#4-integração-com-o-google-sheets)
5. [Avatares circulares das empresas](#5-avatares-circulares-das-empresas)
6. [Mini gráfico de tendência de preço](#6-mini-gráfico-de-tendência-de-preço)
7. [Página 3 — Compras de um produto](#7-página-3--compras-de-um-produto-producteentriespage)
8. [Página 2 — Lista de produtos](#8-página-2--lista-de-produtos-productlistpage)
9. [Página 1 — Seleção de empresa](#9-página-1--seleção-de-empresa-companyselectpage)
10. [Janela principal e navegação](#10-janela-principal-e-navegação-mainwindow)
11. [Fluxo completo de uma tela até a outra](#11-fluxo-completo-de-uma-tela-até-a-outra)
12. [Ponto de entrada (`main`)](#12-ponto-de-entrada-main)

---

## 1. Visão geral da arquitetura

O app segue uma ideia parecida com **MVC**, mas simplificada:

- **Modelo** → a planilha do Google Sheets (não existe banco local).
- **Controlador** → as funções `sheets_buscar`, `sheets_salvar`, `sheets_remover` e a classe `SheetsWorker`, que fazem a ponte entre a interface e a planilha.
- **Visão** → quatro "páginas" (widgets do PyQt6), empilhadas dentro de um `QStackedWidget`, que o usuário navega como se fossem telas de um app mobile:

```
CompanySelectPage  →  ProductListPage  →  ProductEntriesPage
  (escolhe a          (lista os            (mostra/edita as
   empresa)             produtos)            compras do produto)
```

Um ponto importante: **nenhuma tela guarda estado permanente sozinha**. Sempre que o usuário volta ou reabre uma tela, o app dispara uma nova busca no Sheets — isso evita mostrar dados desatualizados se a planilha mudou entre uma visita e outra.

Como toda chamada de rede pode demorar, ela **nunca roda na thread principal da interface** (que travaria a janela). Em vez disso, cada chamada roda dentro de uma `QThread` (a classe `SheetsWorker`), e o resultado chega de volta através de um **sinal Qt** (`pyqtSignal`).

---

## 2. Configuração inicial

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

GOOGLE_SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/.../exec"
```

- `BASE_DIR` descobre a pasta onde o próprio arquivo `.py` está, e `ASSETS_DIR` aponta para a subpasta `assets/`, onde ficam as logos das empresas. Usar `__file__` em vez de um caminho fixo garante que o app funcione independente de onde ele for executado.
- `GOOGLE_SHEETS_WEBHOOK_URL` é a **única "porta de entrada"** do app para os dados. Todo o resto do código depende dessa URL estar configurada corretamente.

```python
COMPANIES = [
    {"nome": "Granola Pura", "logo": ..., "logo_zoom": 0.86, "cor": "#c98a3e", "cor_texto": "#1a1208"},
    {"nome": "Narua", "logo": ..., "logo_zoom": 0.76, "cor": "#8a4b12", "cor_texto": "#ffffff"},
    {"nome": "Contas em Casa", "logo": None, "icone_texto": "🏠", "cor": "#f1c40f", "cor_texto": "#1a1a1a"},
]
```

Essa lista é o **cadastro de empresas** do app. Cada dicionário descreve como aquela empresa aparece na tela: nome, logo (ou um emoji/texto quando não há logo), cor de destaque e a cor do texto que fica em cima dessa cor (para manter contraste legível). Adicionar uma nova empresa é só adicionar um novo dicionário aqui — nenhum outro lugar do código precisa mudar.

```python
BORDA_COR = "#e8e8e8"
BORDA_ESPESSURA = 3

COLUNAS_ENTRADAS = ["Data", "Quantidade", "Preço Unitário", "Preço Total"]
COL_DATA, COL_QTD, COL_PRECO_UNIT, COL_TOTAL = range(4)

ROWS_INICIAIS = 3
```

- `BORDA_COR`/`BORDA_ESPESSURA` são usadas ao desenhar as logos circulares.
- `COLUNAS_ENTRADAS` define os títulos das colunas da tabela de compras, e as constantes `COL_DATA`, `COL_QTD`, `COL_PRECO_UNIT`, `COL_TOTAL` (0, 1, 2, 3) evitam usar números "mágicos" espalhados pelo código — em vez de `tabela.item(row, 2)`, o código usa `tabela.item(row, COL_PRECO_UNIT)`, o que é bem mais legível.
- `ROWS_INICIAIS = 3` é quantas linhas em branco aparecem quando o usuário abre um produto que ainda não tem nenhuma compra registrada.

---

## 3. Funções utilitárias

Pequenas funções "puras" (sem depender do Qt), reaproveitadas em várias telas.

### `format_moeda(valor)`

```python
def format_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
```

Converte um número (`1234.5`) para o formato de moeda brasileira (`R$ 1.234,50`). O truque aqui: o Python formata `1234.5` como `1,234.50` (separador americano), então a função troca temporariamente a vírgula por um `X`, troca o ponto por vírgula, e por fim o `X` por ponto — assim os separadores ficam no padrão brasileiro sem precisar de bibliotecas externas de localização.

### `parse_numero(texto)`

```python
def parse_numero(texto: str) -> float:
    texto = (texto or "").strip().replace("R$", "").strip()
    if not texto:
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0
```

Faz o caminho inverso: pega o que o usuário digitou numa célula da tabela (que pode vir como `"12,50"`, `"12.50"` ou até `"R$ 12,50"`) e devolve um `float` que o Python consegue usar em cálculos. Se o texto tiver vírgula, assume formato brasileiro e remove os pontos de milhar antes de trocar a vírgula por ponto decimal. Se o texto for inválido (ex: usuário digitou letras), devolve `0.0` em vez de quebrar o programa — isso é o que permite que o usuário digite valores parciais/errados sem o app travar.

### `gerar_id()`

```python
def gerar_id() -> str:
    return uuid.uuid4().hex[:12]
```

Gera um identificador único e curto (12 caracteres) para cada nova linha de compra, usado para saber depois qual linha da planilha corresponde a qual linha da tabela na tela — sem esse ID, não daria pra saber se uma edição deve **criar** uma linha nova no Sheets ou **atualizar** uma já existente.

### `normalizar_data_sheets(valor)`

```python
def normalizar_data_sheets(valor) -> str:
    texto = str(valor if valor is not None else "").strip()
    if not texto:
        return ""

    if "T" in texto and texto.endswith("Z"):
        for formato in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(texto, formato).strftime("%d/%m/%Y")
            except ValueError:
                continue

    return texto
```

Isso resolve uma particularidade do Google Sheets: quando o app envia uma data como texto (`"01/07/2026"`), o Sheets às vezes **converte automaticamente** essa célula para um valor de data de verdade. Quando isso acontece, o Apps Script devolve essa data no formato ISO com horário (`"2026-07-01T03:00:00.000Z"`), que não é o formato que o resto do app espera (`dd/MM/yyyy`).

A função checa se o texto tem essa "cara" de data ISO (contém `T` e termina em `Z`) e, se tiver, converte de volta para `dd/MM/yyyy`. Se o texto já vier normal, devolve como está. Essa normalização é feita **uma única vez**, logo depois de buscar os dados (dentro de `sheets_buscar`), para que todo o resto do app (tabela de compras, lista de produtos, gráfico) já trabalhe sempre com o mesmo formato de data.

### `obter_ultima_compra(linhas_produto)`

```python
def obter_ultima_compra(linhas_produto: list):
    if not linhas_produto:
        return None
    melhor, melhor_data = None, None
    for linha in linhas_produto:
        data_qd = QDate.fromString(str(linha.get("data", "")), "dd/MM/yyyy")
        if data_qd.isValid() and (melhor_data is None or data_qd > melhor_data):
            melhor_data, melhor = data_qd, linha
    return melhor if melhor is not None else linhas_produto[-1]
```

Recebe a lista de compras de **um** produto e devolve a compra com a data mais recente. Percorre a lista comparando as datas convertidas com `QDate` (para comparar de verdade como datas, não como texto). Se nenhuma data for válida, devolve simplesmente o último item da lista, como um "fallback" seguro. É usada na tela de lista de produtos, para mostrar "última compra" e seu valor.

---

## 4. Integração com o Google Sheets

Esse bloco é o "cliente HTTP" do app: quem fala com o Web App do Apps Script.

### `ErroSheets`

```python
class ErroSheets(Exception):
    """Erro de comunicação com o Google Sheets..."""
```

Uma exceção customizada. Em vez de deixar erros genéricos do Python (`URLError`, `JSONDecodeError` etc.) vazarem para o resto do app, todo erro relacionado ao Sheets é convertido para `ErroSheets`. Isso simplifica o tratamento de erro nas telas: elas só precisam saber lidar com **um** tipo de exceção.

### `_requisitar(url, dados, metodo, timeout)`

```python
def _requisitar(url, dados=None, metodo="GET", timeout=20) -> dict:
    if not GOOGLE_SHEETS_WEBHOOK_URL:
        raise ErroSheets("A URL do Google Sheets não foi configurada...")
    try:
        requisicao = urllib.request.Request(url, data=dados, headers=..., method=metodo)
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo_bruto = resposta.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ErroSheets(f"O Google respondeu com erro HTTP {e.code}.") from e
    except urllib.error.URLError as e:
        raise ErroSheets(f"Não foi possível conectar ao Google Sheets: {e.reason}") from e
    except OSError as e:
        raise ErroSheets(f"Tempo esgotado ou falha de rede...: {e}") from e

    try:
        corpo = json.loads(corpo_bruto)
    except (ValueError, json.JSONDecodeError) as e:
        ...
        raise ErroSheets(...) from e

    if not corpo.get("ok"):
        raise ErroSheets(corpo.get("erro", "Erro desconhecido..."))
    return corpo
```

É a função "de baixo nível" que todas as outras usam. Passo a passo:

1. **Confere se a URL foi configurada.** Se `GOOGLE_SHEETS_WEBHOOK_URL` estiver vazia, nem tenta fazer a chamada — já avisa o erro de configuração.
2. **Monta e envia a requisição HTTP** com `urllib.request` (biblioteca padrão do Python, sem precisar instalar `requests`). O parâmetro `dados` (bytes de um JSON) só é enviado quando é um `POST`; em `GET` ele fica `None`.
3. **Captura três tipos de falha de rede** separadamente, para dar mensagens de erro mais claras ao usuário: erro HTTP (ex: 500), erro de conexão (ex: sem internet) e erro de timeout/DNS (`OSError`, que às vezes escapa do `URLError`).
4. **Faz o parse do JSON** da resposta. Se o Apps Script devolver algo que não é JSON válido (por exemplo, uma página de erro HTML do Google, o que acontece quando o script não está publicado corretamente), a função devolve um erro explicando isso, mostrando um trecho da resposta recebida para ajudar a diagnosticar.
5. **Confere o campo `"ok"`** que o próprio Apps Script devolve. Mesmo que a requisição HTTP tenha "dado certo" (200 OK), o Apps Script pode reportar uma falha de lógica (ex: ID não encontrado) através desse campo — nesse caso a função também levanta `ErroSheets`.

### `sheets_buscar(empresa=None)`

```python
def sheets_buscar(empresa: str = None) -> list:
    url = GOOGLE_SHEETS_WEBHOOK_URL
    if empresa:
        url += "?" + urllib.parse.urlencode({"empresa": empresa})
    corpo = _requisitar(url, metodo="GET", timeout=40)
    linhas = corpo.get("linhas", [])

    for linha in linhas:
        linha["data"] = normalizar_data_sheets(linha.get("data"))

    return linhas
```

Faz um `GET` na planilha. Se um nome de empresa for passado, ele é adicionado como parâmetro na URL (`?empresa=Narua`), para o Apps Script já devolver só os registros daquela empresa. Depois de receber a resposta, aplica `normalizar_data_sheets` em todas as linhas, garantindo que a data já chegue pronta pro resto do app usar. Usa timeout de 40s (maior que o padrão de 20s), já que listar pode demorar mais em planilhas grandes.

### `sheets_salvar(novas, existentes)`

```python
def sheets_salvar(novas: list, existentes: list) -> None:
    payload = json.dumps({"acao": "salvar", "novas": novas, "existentes": existentes}).encode("utf-8")
    _requisitar(GOOGLE_SHEETS_WEBHOOK_URL, dados=payload, metodo="POST")
```

Envia um `POST` com duas listas: `novas` (linhas que ainda não existem na planilha — vão virar `append`) e `existentes` (linhas que já têm um ID e vão ser atualizadas). O Apps Script decide o que fazer com cada lista.

### `sheets_remover(ids)`

```python
def sheets_remover(ids: list) -> None:
    payload = json.dumps({"acao": "remover", "ids": ids}).encode("utf-8")
    _requisitar(GOOGLE_SHEETS_WEBHOOK_URL, dados=payload, metodo="POST")
```

Envia um `POST` pedindo para apagar as linhas com os IDs informados. O Apps Script apaga a linha de verdade (não deixa célula em branco no meio da planilha).

### `SheetsWorker` (a ponte com a interface)

```python
class SheetsWorker(QThread):
    concluido = pyqtSignal(bool, object)

    def __init__(self, funcao, *args, **kwargs):
        super().__init__()
        self._funcao = funcao
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            resultado = self._funcao(*self._args, **self._kwargs)
            self.concluido.emit(True, resultado)
        except ErroSheets as e:
            self.concluido.emit(False, str(e))
        except Exception as e:
            self.concluido.emit(False, f"Erro inesperado: {e}")
```

Essa classe é o que **evita que a janela trave** enquanto o app fala com o Google. Ela é uma `QThread` "genérica": recebe qualquer uma das três funções acima (`sheets_buscar`, `sheets_salvar` ou `sheets_remover`) mais seus argumentos, e as executa numa thread separada quando `.start()` é chamado.

Quando termina (`run()`), ela emite o sinal `concluido` com dois valores:
- `True, resultado` se deu certo (o `resultado` é o que a função devolveu — ex: a lista de linhas);
- `False, mensagem_de_erro` se algo falhou.

Cada tela do app "escuta" esse sinal conectando uma função a ele (`worker.concluido.connect(...)`), que roda de volta na thread principal — por isso é seguro atualizar a interface dentro dela.

**Padrão de uso, repetido em todo o app:**
```python
self._worker = SheetsWorker(sheets_buscar, self.empresa["nome"])
self._worker.concluido.connect(self._on_carregamento_concluido)
self._worker.start()
```

---

## 5. Avatares circulares das empresas

### `recortar_em_circulo(pixmap_original, tamanho, zoom)`

Recebe a imagem original da logo e devolve uma versão circular, do tamanho pedido. Passo a passo:

1. Calcula o menor lado da imagem (`lado_o`) e recorta um quadrado no centro dela, cujo tamanho é reduzido pelo `zoom` (um `zoom` de `0.8`, por exemplo, "aproxima" a imagem, cortando bordas indesejadas).
2. Cria um `QPixmap` novo, transparente, do tamanho final.
3. Escala o recorte para caber exatamente nesse tamanho, mantendo a proporção (`KeepAspectRatioByExpanding`).
4. Usa um `QPainter` com um **caminho de recorte** (`QPainterPath.addEllipse`) para só desenhar o que está dentro do círculo — é isso que produz o efeito circular.
5. Por fim, desenha uma borda fina (`BORDA_COR`/`BORDA_ESPESSURA`) por cima, para dar um acabamento mais "polido".

### `criar_avatar_circular(empresa, tamanho=130)`

Função de mais alto nível, usada na tela de seleção de empresa. Se a empresa tiver uma logo configurada e o arquivo existir no disco, chama `recortar_em_circulo`. Caso contrário, cria um `QLabel` colorido com o texto/emoji de `icone_texto` (ou as duas primeiras letras do nome, em maiúsculo, como último recurso) — assim o app nunca quebra por falta de uma imagem.

---

## 6. Mini gráfico de tendência de preço

### `MiniGraficoPreco` (QWidget)

Um widget pequeno (230x84px) que desenha, à mão, um gráfico de linha simplificado da evolução de preços — sem depender de nenhuma biblioteca de gráficos.

- **`set_valores(valores)`**: recebe a lista de preços (em ordem cronológica) e força o redesenho (`self.update()`), que dispara `paintEvent`.
- **`paintEvent(event)`**: é chamado automaticamente pelo Qt sempre que o widget precisa ser (re)desenhado. O que ele faz:
  1. Desenha o fundo arredondado escuro.
  2. Se houver menos de 2 valores, mostra a mensagem "sem dados suficientes" e para por aí.
  3. Calcula o mínimo e o máximo dos valores, para converter cada preço numa posição vertical (`y`) proporcional dentro da área do widget — quanto maior o preço, mais para cima.
  4. Distribui os pontos igualmente na horizontal (`x`), de acordo com a posição de cada valor na lista.
  5. Decide a cor com base na tendência: se o **último** preço for maior que o **primeiro**, a linha fica vermelha (subiu); caso contrário, verde (caiu ou estável).
  6. Desenha uma curva suave conectando os pontos, usando curvas de Bézier (`cubicTo`), em vez de linhas retas — isso dá o efeito "arredondado" do gráfico.
  7. Preenche a área abaixo da curva com um **gradiente** que vai da cor da linha (mais opaca no topo) até transparente (na base) — o efeito visual de "sombra" sob a linha.
  8. Desenha um pontinho destacado no último valor (o mais recente).
  9. Escreve no canto o valor máximo e mínimo formatados como moeda.

Esse widget é usado dentro da tela de compras (`ProductEntriesPage`), alimentado com os preços unitários ordenados por data.

---

## 7. Página 3 — Compras de um produto (`ProductEntriesPage`)

Essa é a tela mais complexa do app: mostra e edita **todas as compras registradas de um produto específico**.

### Estado interno

```python
self.empresa = empresa
self.produto = produto
self.cor = empresa["cor"]
self.voltar_callback = voltar_callback
self._carregando = False           # evita reagir a mudanças feitas pelo próprio código
self._operacao_em_andamento = False  # bloqueia botões durante chamadas de rede
self._worker = None
```

O flag `_carregando` é importante: sempre que o código preenche a tabela programaticamente (ao abrir a tela, ao recarregar, etc.), ele é ligado antes e desligado depois. Isso evita que o evento `itemChanged` (disparado toda vez que uma célula muda, inclusive por código) recalcule totais e indicadores durante esse preenchimento — o recálculo só deve acontecer quando é o **usuário** editando.

### Montagem da UI (`_montar_ui`)

Monta, de cima para baixo:
1. **Linha de título** (`_criar_linha_titulo`) — botão "Voltar", indicadores de melhor/pior compra, o mini gráfico, e o nome "Empresa › Produto" centralizado. Um `QLabel` vazio à direita (`espacador`) equilibra visualmente o bloco da esquerda, mantendo o título realmente centralizado.
2. **Linha de filtro por data** (`_criar_linha_filtro`) — dois `QDateEdit` ("De" / "Até") e os botões "Filtrar" / "Limpar filtro".
3. **A tabela de compras** — 4 colunas (`COLUNAS_ENTRADAS`), com o cabeçalho pintado na cor da empresa. Ela escuta `itemChanged` (`self.tabela.itemChanged.connect(self._on_item_changed)`).
4. **Label de total do produto**.
5. **Linha de botões** (`_criar_linha_botoes`) — Adicionar linha / Remover linha / Recarregar do Sheets / Salvar.
6. **Label de status**, que mostra mensagens de sucesso (verde) ou erro (vermelho) das operações.

### Bloqueio de botões durante operações (`_definir_ocupado`)

```python
def _definir_ocupado(self, ocupado: bool, mensagem: str = ""):
    self._operacao_em_andamento = ocupado
    for botao in (self.btn_add, self.btn_remover, self.btn_salvar, self.btn_recarregar):
        botao.setEnabled(not ocupado)
    if mensagem:
        self.status_label.setStyleSheet("color: #d9a441;")
        self.status_label.setText(mensagem)
```

Desabilita os botões relevantes enquanto uma chamada ao Sheets está em andamento (evita que o usuário clique duas vezes em "Salvar" e mande a mesma coisa duas vezes) e mostra uma mensagem amarela de "carregando".

### Adicionar / popular linhas

- **`_adicionar_linha(dados=None)`**: cria uma nova linha na tabela. Se `dados` for passado (vindo do Sheets), preenche com os valores existentes; senão, cria uma linha em branco com a data de hoje já preenchida. O **ID da planilha** fica guardado de forma "invisível" dentro do item da coluna Data, usando `Qt.ItemDataRole.UserRole` — assim ele não aparece na tela, mas o código consegue recuperá-lo depois com `_id_da_linha`. A coluna Total é marcada como não editável (`~Qt.ItemFlag.ItemIsEditable`), já que ela é sempre calculada, nunca digitada.
- **`_popular_tabela(linhas)`**: limpa a tabela e a repovoa. Se a lista de linhas vier vazia (produto novo, sem compras), cria `ROWS_INICIAIS` linhas em branco para o usuário já começar a preencher.
- **`_id_da_linha(row)`**: recupera o ID guardado no `UserRole` da coluna Data daquela linha (ou `None`, se a linha ainda não foi salva no Sheets).

### Remover uma linha (`_remover_linha` → `_on_remocao_concluida`)

1. Pega a linha selecionada; se nenhuma estiver selecionada, avisa e para.
2. Se a linha **não tem ID** (nunca foi salva no Sheets), remove localmente na hora — não há nada pra apagar remotamente.
3. Se **tem ID**, pede confirmação (`QMessageBox.question`), já que isso vai apagar um dado real da planilha.
4. Confirmado, dispara um `SheetsWorker(sheets_remover, [id_linha])` e bloqueia a tela até a resposta.
5. Quando o worker termina, `_on_remocao_concluida` remove a linha da tabela (se deu certo) ou mostra o erro (se falhou).

### Recalcular ao editar (`_on_item_changed` → `_recalcular_linha` → `_atualizar_indicadores`)

Esse é o "motor" reativo da tela:

- `_on_item_changed(item)`: ignora o evento se `_carregando` estiver ativo. Se a coluna editada foi Quantidade ou Preço Unitário, chama `_recalcular_linha` para atualizar o Total daquela linha. Em seguida, sempre chama `_atualizar_indicadores`.
- `_recalcular_linha(row)`: lê quantidade e preço da linha (usando `parse_numero`, que tolera texto mal formatado), multiplica os dois e escreve o resultado formatado (`format_moeda`) na coluna Total — que fica travada para não ser editada manualmente.
- `_atualizar_indicadores()`: percorre **todas as linhas visíveis** (ignora linhas escondidas pelo filtro de data) e:
  - soma o total geral do produto;
  - monta uma lista de `(data, texto_data, preço)` só das linhas com preço válido;
  - atualiza o label de total;
  - encontra a compra de **menor** preço (melhor compra) e de **maior** preço (pior compra);
  - ordena os registros por data e passa a lista de preços, na ordem cronológica, para o `MiniGraficoPreco.set_valores`.

### Filtro por data (`_aplicar_filtro_data` / `_limpar_filtro_data`)

`_aplicar_filtro_data` lê as duas datas escolhidas (`De`/`Até`), valida que "De" não é depois de "Até", e esconde (`setRowHidden`) toda linha cuja data esteja fora do intervalo (ou que tenha uma data inválida). Depois recalcula os indicadores, já que eles ignoram linhas escondidas. `_limpar_filtro_data` reexibe todas as linhas e reseta os campos de data.

### Salvar (`_salvar` → `_on_salvamento_concluido`)

1. Percorre todas as linhas da tabela, ignorando qualquer uma com quantidade ou preço inválido/zerado (linhas em branco não são enviadas).
2. Para cada linha válida, monta um dicionário `registro` com `data`, `quantidade`, `preco_unitario`, `preco_total`.
3. Se a linha já tiver um ID (via `_id_da_linha`), ela é uma **atualização** → vai para a lista `existentes`. Senão, gera um novo ID (`gerar_id`), adiciona `empresa`/`produto` ao registro (necessário para o Sheets saber onde inserir) e vai para a lista `novas`. Também guarda, em `linhas_por_id_novo`, qual linha da tabela corresponde a cada novo ID — é assim que depois o código sabe onde "gravar de volta" o ID recém-criado.
4. Se não houver nada pra enviar, apenas avisa e para.
5. Caso contrário, dispara `SheetsWorker(sheets_salvar, novas, existentes)`.
6. Quando termina, `_on_salvamento_concluido` grava o ID de cada linha nova de volta no `UserRole` dela (usando o mapa `linhas_por_id_novo`) — assim, se o usuário salvar de novo sem recarregar, essas linhas já são reconhecidas como "existentes" em vez de criar duplicatas.

### Recarregar do Sheets (`_recarregar_do_sheets` → `_on_recarregamento_concluido`)

Busca de novo todos os registros da empresa e filtra só os do produto atual (`linha.get("produto") == self.produto`), repopulando a tabela do zero — útil se outra pessoa alterou a planilha por fora do app.

---

## 8. Página 2 — Lista de produtos (`ProductListPage`)

Mostra todos os produtos de uma empresa, com a data e o valor da última compra de cada um.

### Estado interno

```python
self._linhas_por_produto = {}   # nome do produto -> lista de linhas da planilha
self._produtos_pendentes = []   # produtos criados nesta sessão, sem compra salva ainda
self._ordem_crescente = True    # A-Z ou Z-A
self._texto_pesquisa = ""
self._geracao_carregamento = 0  # usado pelo watchdog de timeout (ver abaixo)
```

`_produtos_pendentes` existe porque, quando o usuário cria um produto novo pelo botão "Adicionar novo item", esse produto **ainda não existe na planilha** (só passa a existir quando a primeira compra é salva). Enquanto isso, ele fica "pendurado" nessa lista, só para continuar aparecendo na tabela.

### Carregar dados com proteção contra travamento (`recarregar`)

```python
def recarregar(self):
    ...
    self._geracao_carregamento += 1
    geracao_desta_chamada = self._geracao_carregamento

    self._worker = SheetsWorker(sheets_buscar, self.empresa["nome"])
    self._worker.concluido.connect(self._on_carregamento_concluido)
    self._worker.start()

    QTimer.singleShot(45000, lambda: self._verificar_timeout_carregamento(geracao_desta_chamada))
```

Aqui aparece um detalhe interessante: além do `timeout` já configurado dentro da própria requisição HTTP (40s), existe um **watchdog** adicional de 45s usando `QTimer.singleShot`. Ele existe para cobrir casos raros em que uma falha de rede/DNS trava a chamada sem respeitar o timeout interno do `urllib` — nesse cenário, sem esse watchdog, a tela ficaria presa para sempre em "Carregando...".

O contador `_geracao_carregamento` resolve um problema clássico de concorrência: se o usuário clicar em "Recarregar" várias vezes seguidas, cada chamada a `recarregar()` incrementa esse contador e guarda o valor daquela chamada especificamente (`geracao_desta_chamada`). Quando o watchdog dispara 45s depois, ele só age se **essa ainda for a geração mais recente** — ou seja, se nenhuma busca mais nova foi iniciada nesse meio-tempo. Isso evita que um watchdog "antigo" interrompa uma busca "nova" que ainda está em andamento.

### Quando os dados chegam (`_on_carregamento_concluido`)

```python
self._linhas_por_produto = {}
for linha in resultado:
    self._linhas_por_produto.setdefault(linha["produto"], []).append(linha)

self._produtos_pendentes = [p for p in self._produtos_pendentes if p not in self._linhas_por_produto]

self._reconstruir_tabela()
```

Agrupa a lista "achatada" de linhas que veio do Sheets num dicionário `{produto: [linhas]}`, usando `setdefault` para criar a lista na primeira vez que um produto aparece. Em seguida, "limpa" a lista de pendentes: qualquer produto que já apareceu nos dados reais do Sheets deixa de ser "pendente" (já tem pelo menos uma compra salva).

### Reconstruir, ordenar e pesquisar (`_reconstruir_tabela`)

```python
nomes_produtos = list(self._linhas_por_produto.keys()) + self._produtos_pendentes
nomes_produtos = sorted(nomes_produtos, key=lambda n: n.lower(), reverse=not self._ordem_crescente)

if self._texto_pesquisa:
    termo = self._texto_pesquisa.lower()
    nomes_produtos = [n for n in nomes_produtos if termo in n.lower()]
```

Junta produtos "reais" (do Sheets) com produtos "pendentes" (criados nesta sessão), ordena alfabeticamente (ignorando maiúsculas/minúsculas) e, se houver texto de pesquisa, filtra só os que contêm esse texto. Esse é o único lugar em que a tabela é reconstruída — tanto `_alternar_ordem` quanto `_on_texto_pesquisa_mudou` simplesmente chamam essa função de novo.

### Cada linha da tabela (`_inserir_linha_produto`)

Para cada produto, busca a última compra com `obter_ultima_compra` e mostra sua data e valor. A célula na última coluna não é um texto — é um **botão** (`QPushButton("Abrir lista →")`) inserido com `setCellWidget`, que ao ser clicado chama `_abrir_produto(nome_produto)`. Um duplo clique em qualquer célula da linha também abre o produto (via `itemDoubleClicked`).

### Adicionar e remover produtos

- **`_adicionar_produto`**: abre um `QInputDialog` pedindo o nome, valida que não é vazio nem duplicado, e adiciona à lista `_produtos_pendentes`.
- **`_remover_produto`**: se o produto **não tem nenhum ID** (é só "pendente", nunca foi salvo), remove localmente sem chamar o Sheets. Se **tem IDs**, pede confirmação e dispara `sheets_remover` com a lista de todos os IDs daquele produto de uma vez (remove todas as compras do produto na mesma chamada).

---

## 9. Página 1 — Seleção de empresa (`CompanySelectPage`)

A tela mais simples: para cada empresa em `COMPANIES`, cria um "card" vertical com o avatar circular (via `criar_avatar_circular`) e um botão colorido com o nome da empresa, que ao ser clicado chama `escolher_callback(empresa)`.

Se `GOOGLE_SHEETS_WEBHOOK_URL` estiver vazia, mostra um aviso vermelho no topo, para deixar claro que o app não vai funcionar sem essa configuração — em vez de o usuário só descobrir isso depois, ao tentar abrir uma empresa e receber um erro confuso.

---

## 10. Janela principal e navegação (`MainWindow`)

```python
self.stack = QStackedWidget()
self.setCentralWidget(self.stack)

self.pagina_selecao = CompanySelectPage(self.abrir_empresa)
self.stack.addWidget(self.pagina_selecao)

self._paginas_produtos = {}    # nome da empresa -> ProductListPage (cacheada)
self._pagina_entradas_atual = None
```

O `QStackedWidget` é o mecanismo de navegação: ele guarda várias telas empilhadas e mostra só uma por vez (`setCurrentWidget`). É o mesmo princípio de uma pilha de "activities" num app mobile.

### `abrir_empresa(empresa)`

```python
if nome_empresa not in self._paginas_produtos:
    pagina = ProductListPage(empresa, ...)
    self._paginas_produtos[nome_empresa] = pagina
    self.stack.addWidget(pagina)
else:
    self._paginas_produtos[nome_empresa].recarregar()

self.stack.setCurrentWidget(self._paginas_produtos[nome_empresa])
```

A página de lista de produtos **é reaproveitada** por empresa: na primeira vez que o usuário abre "Narua", uma `ProductListPage` é criada e guardada no dicionário `_paginas_produtos`. Da segunda vez em diante, em vez de criar tudo de novo, o código só chama `.recarregar()` nela — que busca os dados atualizados sem reconstruir a interface do zero.

### `abrir_produto(empresa, produto, linhas)`

```python
pagina = ProductEntriesPage(empresa, produto, linhas, voltar_callback=...)
if self._pagina_entradas_atual is not None:
    self.stack.removeWidget(self._pagina_entradas_atual)
    self._pagina_entradas_atual.deleteLater()

self._pagina_entradas_atual = pagina
self.stack.addWidget(pagina)
self.stack.setCurrentWidget(pagina)
```

Diferente da lista de produtos, a página de **compras de um produto não é reaproveitada** — toda vez que o usuário abre um produto, uma `ProductEntriesPage` nova é criada. Isso é intencional: como os dados vêm sempre "frescos" da lista de produtos (que acabou de recarregar do Sheets), é mais simples e seguro recriar a tela do que tentar atualizar uma existente. A página anterior é removida da pilha (`removeWidget`) e agendada para ser destruída (`deleteLater`, o jeito seguro do Qt de liberar memória sem correr risco de travar algo que ainda está em uso).

### Voltar (`voltar_para_lista_produtos` / `voltar_para_selecao`)

Ao voltar da tela de compras para a lista de produtos, o código também chama `.recarregar()` na lista — garantindo que qualquer alteração feita na tela de compras (nova compra salva, produto removido etc.) já apareça refletida assim que o usuário volta.

---

## 11. Fluxo completo de uma tela até a outra

Um resumo visual de tudo o que foi explicado, seguindo o caminho de "abrir a empresa Narua, ver o produto X e salvar uma nova compra":

```
1. CompanySelectPage
   usuário clica em "Narua"
        │
        ▼
2. MainWindow.abrir_empresa(empresa_narua)
   cria (ou reaproveita) a ProductListPage
        │
        ▼
3. ProductListPage.recarregar()
   dispara SheetsWorker(sheets_buscar, "Narua")  ──► GET no Apps Script
        │
        ▼ (sinal "concluido")
4. ProductListPage._on_carregamento_concluido()
   agrupa linhas por produto, reconstrói a tabela
        │
        │ usuário clica em "Abrir lista →" no produto X
        ▼
5. MainWindow.abrir_produto(empresa, "Produto X", linhas)
   cria uma nova ProductEntriesPage
        │
        │ usuário edita quantidade/preço, clica em "Salvar"
        ▼
6. ProductEntriesPage._salvar()
   monta listas "novas"/"existentes", dispara
   SheetsWorker(sheets_salvar, novas, existentes)  ──► POST no Apps Script
        │
        ▼ (sinal "concluido")
7. ProductEntriesPage._on_salvamento_concluido()
   grava os novos IDs nas linhas, mostra "✓ Salvo com sucesso"
```

---

## 12. Ponto de entrada (`main`)

```python
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- `QApplication(sys.argv)` inicializa o motor do Qt — é obrigatório existir exatamente uma instância dessa classe antes de criar qualquer widget.
- `app.setStyle("Fusion")` aplica um tema visual consistente entre Windows e Linux (em vez do estilo nativo de cada sistema operacional, que varia bastante).
- `janela.show()` exibe a `MainWindow` (que por sua vez mostra a `CompanySelectPage`, a primeira tela do `QStackedWidget`).
- `app.exec()` inicia o **loop de eventos** do Qt — é essa chamada que mantém o app "vivo", escutando cliques, digitação e os sinais dos `SheetsWorker`, até a janela ser fechada. `sys.exit(...)` garante que o código de saída do processo reflita como o Qt encerrou.

---

## Glossário rápido

| Termo | Significado no contexto do app |
|---|---|
| **Web App / Apps Script** | Script hospedado no Google que expõe a planilha como uma pequena API HTTP |
| **`QThread`** | Mecanismo do Qt para rodar código em segundo plano, sem travar a interface |
| **`pyqtSignal`** | "Evento" do Qt: uma forma segura de uma thread avisar a interface que algo aconteceu |
| **`UserRole`** | Um espaço "escondido" dentro de um item de tabela do Qt, usado aqui para guardar o ID da planilha sem exibi-lo na tela |
| **Linha "pendente"** | Produto criado na interface que ainda não tem nenhuma compra salva no Sheets |