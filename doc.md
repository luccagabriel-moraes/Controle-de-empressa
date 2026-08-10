# 📖 Documentação Técnica — Controle de Empresas

> Explicação passo a passo de como o código de `controle_empresas.py` (e do backend `apps_script_backend.gs`) funciona por dentro: cada bloco, classe e função, na ordem em que aparecem no arquivo.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)
![Arquitetura](https://img.shields.io/badge/Arquitetura-MVC%20simplificado-9b59b6)

> **Changelog desta versão:** correção de um crash (`RuntimeError: wrapped C/C++ object ... has been deleted`) causado por respostas de rede chegando depois que uma tela já tinha sido fechada; cache local em disco para a lista de produtos aparecer instantaneamente; e otimizações no backend Apps Script (cache de leitura, escrita em lote, índice de IDs) para acelerar listas grandes. Tudo isso está documentado nas seções marcadas com 🆕.
>
> **Changelog de usabilidade (esta revisão):** navegação por Enter na tabela de compras (Data → Quantidade → Preço Unitário); produto novo nasce com 1 linha em branco (era 3) e já abre automaticamente ao ser criado; aviso de confirmação ao clicar em "← Voltar" havendo alterações não salvas; e nomes/títulos muito longos agora truncam com reticências (+ tooltip) em vez de desalinhar o layout. Marcado nas seções com 🆕².
>
> **Changelog de correção (pós-revisão):** a primeira versão da navegação por Enter e do rótulo elidível tinha dois bugs — o hint do Qt usado para detectar o Enter estava errado (e seu nome no PyQt6 varia por versão do binding), e o rótulo elidível calculava a largura de corte antes de estar no layout de verdade, então nunca truncava nada. Os dois foram corrigidos e confirmados com testes isolados. Marcado nas seções com 🆕³.

---

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Configuração inicial](#2-configuração-inicial)
3. [Funções utilitárias](#3-funções-utilitárias)
4. [Integração com o Google Sheets](#4-integração-com-o-google-sheets)
5. [Cache local em disco 🆕](#5-cache-local-em-disco-)
6. [Avatares circulares das empresas](#6-avatares-circulares-das-empresas)
7. [Mini gráfico de tendência de preço](#7-mini-gráfico-de-tendência-de-preço)
8. [Página 3 — Compras de um produto](#8-página-3--compras-de-um-produto-producteentriespage)
9. [Página 2 — Lista de produtos](#9-página-2--lista-de-produtos-productlistpage)
10. [Página 1 — Seleção de empresa](#10-página-1--seleção-de-empresa-companyselectpage)
11. [Janela principal e navegação](#11-janela-principal-e-navegação-mainwindow)
12. [Fluxo completo de uma tela até a outra](#12-fluxo-completo-de-uma-tela-até-a-outra)
13. [Ponto de entrada (`main`)](#13-ponto-de-entrada-main)
14. [Backend Apps Script (`apps_script_backend.gs`) 🆕](#14-backend-apps-script-apps_script_backendgs-)

---

## 1. Visão geral da arquitetura

O app segue uma ideia parecida com **MVC**, mas simplificada:

- **Modelo** → a planilha do Google Sheets (não existe banco local "de verdade" — o que existe agora é só um cache leve em disco, ver [Seção 5](#5-cache-local-em-disco-)).
- **Controlador** → as funções `sheets_buscar`, `sheets_salvar`, `sheets_remover` e a classe `SheetsWorker`, que fazem a ponte entre a interface e a planilha.
- **Visão** → quatro "páginas" (widgets do PyQt6), empilhadas dentro de um `QStackedWidget`, que o usuário navega como se fossem telas de um app mobile:

```
CompanySelectPage  →  ProductListPage  →  ProductEntriesPage
  (escolhe a          (lista os            (mostra/edita as
   empresa)             produtos)            compras do produto)
```

Um ponto importante: **nenhuma tela guarda estado permanente sozinha**. Sempre que o usuário volta ou reabre uma tela, o app dispara uma nova busca no Sheets — isso evita mostrar dados desatualizados se a planilha mudou entre uma visita e outra. 🆕 Desde a versão atual, essa busca é precedida por uma leitura instantânea do **cache local** (ver Seção 5), então a tela não fica mais "em branco" enquanto espera a rede.

Como toda chamada de rede pode demorar, ela **nunca roda na thread principal da interface** (que travaria a janela). Em vez disso, cada chamada roda dentro de uma `QThread` (a classe `SheetsWorker`), e o resultado chega de volta através de um **sinal Qt** (`pyqtSignal`).

🆕 **Sobre o ciclo de vida das telas:** como cada `SheetsWorker` roda em paralelo e pode terminar depois que a tela que o criou já foi fechada (por exemplo, o usuário voltou e abriu outro produto antes da resposta do "Salvar" chegar), a `ProductEntriesPage` agora rastreia explicitamente se ela já foi destruída, e ignora qualquer resultado de rede que chegue depois disso. Isso é detalhado na [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage).

---

## 2. Configuração inicial

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CACHE_DIR = os.path.join(BASE_DIR, "cache")  # 🆕

GOOGLE_SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/.../exec"
```

- `BASE_DIR` descobre a pasta onde o próprio arquivo `.py` está, e `ASSETS_DIR` aponta para a subpasta `assets/`, onde ficam as logos das empresas. Usar `__file__` em vez de um caminho fixo garante que o app funcione independente de onde ele for executado.
- 🆕 `CACHE_DIR` aponta para uma subpasta `cache/`, criada automaticamente na primeira vez que o app salva alguma coisa em cache (ver [Seção 5](#5-cache-local-em-disco-)). Ela guarda um arquivo `.json` por empresa.
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

ROWS_INICIAIS = 1
```

- `BORDA_COR`/`BORDA_ESPESSURA` são usadas ao desenhar as logos circulares.
- `COLUNAS_ENTRADAS` define os títulos das colunas da tabela de compras, e as constantes `COL_DATA`, `COL_QTD`, `COL_PRECO_UNIT`, `COL_TOTAL` (0, 1, 2, 3) evitam usar números "mágicos" espalhados pelo código — em vez de `tabela.item(row, 2)`, o código usa `tabela.item(row, COL_PRECO_UNIT)`, o que é bem mais legível.
- `ROWS_INICIAIS` é quantas linhas em branco aparecem quando o usuário abre um produto que ainda não tem nenhuma compra registrada. 🆕² Era `3`; passou a ser `1` — o usuário pediu menos ruído visual ao criar um produto novo, e usa "+ Adicionar linha" se precisar de mais.

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

Faz um `GET` na planilha. Se um nome de empresa for passado, ele é adicionado como parâmetro na URL (`?empresa=Narua`), para o Apps Script já devolver só os registros daquela empresa. 🆕 Do lado do Apps Script, essa resposta agora normalmente vem de um **cache de 60 segundos** em vez de reler a planilha inteira a cada chamada (ver [Seção 14](#14-backend-apps-script-apps_script_backendgs-)) — o Python não precisa saber disso, mas é por isso que buscas repetidas em pouco tempo ficam bem mais rápidas. Depois de receber a resposta, `sheets_buscar` aplica `normalizar_data_sheets` em todas as linhas, garantindo que a data já chegue pronta pro resto do app usar. Usa timeout de 40s (maior que o padrão de 20s), já que listar pode demorar mais em planilhas grandes.

### `sheets_salvar(novas, existentes)`

```python
def sheets_salvar(novas: list, existentes: list) -> None:
    payload = json.dumps({"acao": "salvar", "novas": novas, "existentes": existentes}).encode("utf-8")
    _requisitar(GOOGLE_SHEETS_WEBHOOK_URL, dados=payload, metodo="POST")
```

Envia um `POST` com duas listas: `novas` (linhas que ainda não existem na planilha — vão virar gravação em lote) e `existentes` (linhas que já têm um ID e vão ser atualizadas). O Apps Script decide o que fazer com cada lista. 🆕 Do lado do Apps Script, as linhas novas agora são gravadas todas de uma vez (um único `setValues` em bloco) em vez de uma chamada por linha — ver Seção 14.

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

🆕 **Cuidado que essa arquitetura exige:** como o `SheetsWorker` roda em paralelo à interface, ele pode terminar **depois** que a tela que o criou já não existe mais (por exemplo, o usuário navegou pra outro lugar antes da resposta chegar). Se o callback conectado ao sinal tentar mexer em widgets que o Qt já destruiu, o resultado é um `RuntimeError: wrapped C/C++ object ... has been deleted`. A solução adotada foi dar à `ProductEntriesPage` uma flag `_destruida`, verificada no início de todo callback — ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage).

**Padrão de uso, repetido em todo o app:**
```python
self._worker = SheetsWorker(sheets_buscar, self.empresa["nome"])
self._worker.concluido.connect(self._on_carregamento_concluido)
self._worker.start()
```

---

## 5. Cache local em disco 🆕

Esse bloco é novo e existe só por um motivo: **fazer a tela aparecer com dados na hora**, mesmo antes do Google Sheets responder, em vez de mostrar "Carregando..." toda vez que uma empresa é aberta.

### `_cache_arquivo(empresa)`

```python
def _cache_arquivo(empresa: str) -> str:
    nome_seguro = "".join(c if c.isalnum() else "_" for c in empresa)
    return os.path.join(CACHE_DIR, f"{nome_seguro}.json")
```

Monta o caminho do arquivo de cache de uma empresa, trocando qualquer caractere que não seja letra/número por `_` — assim nomes de empresa com espaços ou acentos não geram nomes de arquivo inválidos.

### `cache_carregar(empresa)`

```python
def cache_carregar(empresa: str):
    caminho = _cache_arquivo(empresa)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
```

Lê o arquivo `.json` daquela empresa, se existir. Se o arquivo não existir, estiver corrompido ou der qualquer erro de leitura, devolve `None` silenciosamente — o cache é só uma otimização, então qualquer problema nele nunca deve impedir o app de funcionar (ele simplesmente cai de volta no comportamento de sempre buscar do Sheets).

### `cache_salvar(empresa, linhas)`

```python
def cache_salvar(empresa: str, linhas: list):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_arquivo(empresa), "w", encoding="utf-8") as f:
            json.dump(linhas, f, ensure_ascii=False)
    except OSError:
        pass
```

Grava a lista de linhas mais recente da empresa em disco, criando a pasta `cache/` se ainda não existir. É chamada logo depois de uma busca bem-sucedida no Sheets (dentro de `ProductListPage._on_carregamento_concluido`, ver [Seção 9](#9-página-2--lista-de-produtos-productlistpage)). Se a escrita falhar por qualquer motivo (disco cheio, sem permissão etc.), o erro é ignorado — de novo, o cache nunca deve derrubar o app.

**Onde isso entra no fluxo:** quando `ProductListPage.recarregar()` é chamado, ele primeiro tenta `cache_carregar(...)` e, se achar algo, já popula a tabela imediatamente com esses dados (mostrando uma mensagem tipo "Mostrando dados salvos localmente — atualizando..."). Só depois disso ele dispara o `SheetsWorker` de verdade, que vai atualizar a tela com os dados reais assim que chegarem. Se a busca real falhar mas já havia dados de cache na tela, esses dados **continuam visíveis** — o usuário só é avisado que a atualização não funcionou, em vez de a tela ficar vazia.

---

## 6. Avatares circulares das empresas

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

## 7. Mini gráfico de tendência de preço

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

### Rótulo elidível (`LabelElidavel`) 🆕²

```python
class LabelElidavel(QLabel):
    def setText(self, texto: str):
        self._texto_completo = texto
        self.setToolTip(texto)
        super().setText(texto)
        self._reelidir()

    def minimumSizeHint(self):
        largura_minima = self.fontMetrics().horizontalAdvance("...")
        return QSize(largura_minima, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reelidir()

    def _reelidir(self):
        texto_elidido = self.fontMetrics().elidedText(
            self._texto_completo, Qt.TextElideMode.ElideRight, self.width()
        )
        super().setText(texto_elidido)
```

Resolve o problema de nomes de produto muito grandes desalinhando a tela: em vez de um `QLabel` comum (que cresce sem limite e empurra o resto do layout), esse `QLabel` guarda o texto completo internamente (`_texto_completo`) e, toda vez que é redesenhado ou redimensionado, calcula — via `QFontMetrics.elidedText` — a versão truncada com reticências (`"Empresa › Nome de produto gigan…"`) que cabe na largura atual do widget. O texto original nunca é perdido: fica sempre disponível como tooltip ao passar o mouse por cima. É usado no título "Empresa › Produto" da tela de compras (`ProductEntriesPage`, ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage)), que antes era um `QLabel` normal.

🆕³ **Bug da primeira versão, e por que `minimumSizeHint()` precisou ser sobrescrito:** só truncar no `resizeEvent` não bastava. Por padrão, o `minimumSizeHint()` de um `QLabel` acompanha o **texto atual** do label. No instante em que o `LabelElidavel` é construído, ele ainda não tem pai nem está dentro de nenhum layout — nesse momento, `self.width()` reflete o tamanho padrão de uma janela solta (bem maior que o espaço real disponível depois), então a primeira tentativa de eliminar não corta nada, e o texto completo (grande) fica gravado como o texto "oficial" do label. A partir daí, o `minimumSizeHint()` do Qt reporta esse texto grande como o tamanho mínimo — e o layout, por definição, nunca entrega a um widget menos espaço do que o mínimo dele. Resultado: o `resizeEvent` nunca chega a ser chamado com uma largura pequena o bastante pra truncar de verdade, e a tela volta a ficar torta. A correção foi sobrescrever `minimumSizeHint()` para **nunca** depender do texto atual — ele sempre devolve só a largura de `"..."`, liberando o layout para espremer esse rótulo à vontade. É esse espremer que dispara o `resizeEvent` com a largura real disponível, e só aí a elisão de fato acontece.

### Tabela com navegação por Enter (`TabelaComNavegacaoEnter`) 🆕²

```python
class TabelaComNavegacaoEnter(QTableWidget):
    _HINT_ENTER = getattr(
        QAbstractItemDelegate.EndEditHint, "SubmitModelData", None
    ) or QAbstractItemDelegate.EndEditHint.SubmitModelCache

    def closeEditor(self, editor, hint):
        if hint != self._HINT_ENTER:
            super().closeEditor(editor, hint)
            return

        row, col = self.currentRow(), self.currentColumn()
        super().closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

        proxima_coluna = {COL_DATA: COL_QTD, COL_QTD: COL_PRECO_UNIT}.get(col)
        if proxima_coluna is None:
            return

        self.setCurrentCell(row, proxima_coluna)
        self.editItem(self.item(row, proxima_coluna))
```

Ao confirmar uma célula em edição, o Qt avisa a view **qual tecla motivou o fechamento** através de um "hint" entregue ao método `closeEditor`. Essa subclasse intercepta esse hint especificamente quando ele indica que foi o **Enter/Return** que fechou o editor: em vez de deixar o comportamento padrão (que apenas confirma o valor, sem mover o cursor), ela fecha o editor manualmente (`NoHint`) e decide o próximo passo, seguindo o fluxo de preenchimento de uma compra:

- Na coluna **Data**, Enter abre a edição da célula **Quantidade** da mesma linha.
- Na coluna **Quantidade**, Enter abre a edição da célula **Preço Unitário** da mesma linha.
- Na coluna **Preço Unitário**, o dicionário `proxima_coluna` não tem uma entrada correspondente (`.get()` devolve `None`), então a função simplesmente retorna — o valor já foi confirmado, mas o cursor **não avança e nenhuma linha nova é criada**. (A coluna Total nunca entra nesse fluxo por ser somente leitura.)

Essa classe substitui o `QTableWidget` usado na tabela de compras (`self.tabela`, dentro de `ProductEntriesPage._montar_ui`, ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage)).

🆕³ **Bug da primeira versão, e o porquê do `_HINT_ENTER`:** a primeira tentativa comparava o hint recebido com `QAbstractItemDelegate.EndEditHint.EditNextItem` (o hint oficialmente documentado para a tecla Tab) — mas testando na prática, o hint que o Enter realmente dispara é outro. Pior: o *nome* desse hint na enumeração do Python varia por versão do binding PyQt6 — na documentação oficial (e em versões mais novas do PyQt6) ele se chama `SubmitModelData`, mas em versões mais antigas existe um erro de digitação conhecido no binding, e o mesmo hint aparece com o nome `SubmitModelCache`. Como `if hint != EditNextItem` nunca era verdadeiro pro Enter, o código simplesmente caía no comportamento padrão do Qt (nada acontecia) — daí o Enter "não fazer nada" ao ser apertado na coluna Data. A correção usa `getattr(..., "SubmitModelData", None) or ...SubmitModelCache` para resolver o hint certo em tempo de importação, tentando primeiro o nome oficial e caindo para o nome com erro de digitação se o oficial não existir nessa instalação — funcionando nas duas versões do binding.

---

## 8. Página 3 — Compras de um produto (`ProductEntriesPage`)

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
self._alteracoes_nao_salvas = False  # 🆕² ver "Sair sem salvar", abaixo
self._destruida = False            # 🆕 ver abaixo
```

O flag `_carregando` é importante: sempre que o código preenche a tabela programaticamente (ao abrir a tela, ao recarregar, etc.), ele é ligado antes e desligado depois. Isso evita que o evento `itemChanged` (disparado toda vez que uma célula muda, inclusive por código) recalcule totais e indicadores durante esse preenchimento — o recálculo só deve acontecer quando é o **usuário** editando.

### 🆕 `_destruida` e `marcar_destruida()` — a correção do crash

```python
def marcar_destruida(self):
    self._destruida = True
```

Esse é o ponto central da correção do erro `RuntimeError: wrapped C/C++ object of type QPushButton has been deleted`.

**Como o crash acontecia:** a `MainWindow` cria uma `ProductEntriesPage` nova toda vez que o usuário abre um produto ([Seção 11](#11-janela-principal-e-navegação-mainwindow)), e destrói (`deleteLater()`) a página anterior. Se o usuário clicasse em "💾 Salvar", depois voltasse e abrisse outro produto **antes** da resposta do Sheets chegar, a página antiga era destruída com o `SheetsWorker` ainda rodando em segundo plano. Quando a resposta finalmente chegava, o callback (`_on_salvamento_concluido`) tentava reabilitar botões (`botao.setEnabled(...)`) de uma página que o Qt já tinha apagado da memória — e isso derrubava o programa.

**A correção:** antes de destruir uma `ProductEntriesPage`, a `MainWindow` agora chama `pagina.marcar_destruida()` (ver [Seção 11](#11-janela-principal-e-navegação-mainwindow)). E todo callback de rede da página — `_on_remocao_concluida`, `_on_salvamento_concluido`, `_on_recarregamento_concluido` — começa assim:

```python
def _on_salvamento_concluido(self, sucesso, mensagem, linhas_por_id_novo):
    if self._destruida:
        return  # a página já foi fechada/trocada enquanto a rede respondia
    ...
```

Ou seja: se a resposta chegar tarde demais, ela é simplesmente descartada, em vez de tentar atualizar uma tela que não existe mais.

Como reforço adicional, o botão **"← Voltar"** (`self.btn_voltar`) passou a ser incluído na lista de botões desabilitados por `_definir_ocupado` durante uma operação — reduzindo a chance de o usuário sair da tela bem no meio de um salvamento/remoção:

```python
def _definir_ocupado(self, ocupado: bool, mensagem: str = ""):
    self._operacao_em_andamento = ocupado
    for botao in (self.btn_add, self.btn_remover, self.btn_salvar, self.btn_recarregar, self.btn_voltar):  # 🆕 btn_voltar
        botao.setEnabled(not ocupado)
    ...
```

### Montagem da UI (`_montar_ui`)

Monta, de cima para baixo:
1. **Linha de título** (`_criar_linha_titulo`) — botão "Voltar" (guardado como `self.btn_voltar` 🆕, em vez de variável local, para poder ser desabilitado por `_definir_ocupado`; 🆕² agora chama `_tentar_voltar` em vez do `voltar_callback` direto, ver abaixo), indicadores de melhor/pior compra, o mini gráfico, e o título "Empresa › Produto" centralizado — 🆕² agora um `LabelElidavel` em vez de `QLabel` comum, pra não desalinhar a tela quando o nome do produto é muito grande (ver [Seção 7](#7-mini-gráfico-de-tendência-de-preço)). Um `QLabel` vazio à direita (`espacador`) equilibra visualmente o bloco da esquerda, mantendo o título realmente centralizado.
2. **Linha de filtro por data** (`_criar_linha_filtro`) — dois `QDateEdit` ("De" / "Até") e os botões "Filtrar" / "Limpar filtro".
3. **A tabela de compras** — 🆕² agora uma `TabelaComNavegacaoEnter` (ver [Seção 7](#7-mini-gráfico-de-tendência-de-preço)) em vez de `QTableWidget` puro, com 4 colunas (`COLUNAS_ENTRADAS`) e cabeçalho pintado na cor da empresa. Ela escuta `itemChanged` (`self.tabela.itemChanged.connect(self._on_item_changed)`).
4. **Label de total do produto**.
5. **Linha de botões** (`_criar_linha_botoes`) — Adicionar linha / Remover linha / Recarregar do Sheets / Salvar.
6. **Label de status**, que mostra mensagens de sucesso (verde) ou erro (vermelho) das operações.

### Adicionar / popular linhas

- **`_adicionar_linha(dados=None)`**: cria uma nova linha na tabela. Se `dados` for passado (vindo do Sheets), preenche com os valores existentes; senão, cria uma linha em branco com a data de hoje já preenchida. O **ID da planilha** fica guardado de forma "invisível" dentro do item da coluna Data, usando `Qt.ItemDataRole.UserRole` — assim ele não aparece na tela, mas o código consegue recuperá-lo depois com `_id_da_linha`. A coluna Total é marcada como não editável (`~Qt.ItemFlag.ItemIsEditable`), já que ela é sempre calculada, nunca digitada.
- **`_popular_tabela(linhas)`**: limpa a tabela e a repovoa. Se a lista de linhas vier vazia (produto novo, sem compras), cria `ROWS_INICIAIS` linhas em branco para o usuário já começar a preencher.
- **`_id_da_linha(row)`**: recupera o ID guardado no `UserRole` da coluna Data daquela linha (ou `None`, se a linha ainda não foi salva no Sheets).

### Remover uma linha (`_remover_linha` → `_on_remocao_concluida`)

1. Pega a linha selecionada; se nenhuma estiver selecionada, avisa e para.
2. Se a linha **não tem ID** (nunca foi salva no Sheets), remove localmente na hora — não há nada pra apagar remotamente.
3. Se **tem ID**, pede confirmação (`QMessageBox.question`), já que isso vai apagar um dado real da planilha.
4. Confirmado, dispara um `SheetsWorker(sheets_remover, [id_linha])` e bloqueia a tela até a resposta.
5. Quando o worker termina, `_on_remocao_concluida` **primeiro verifica `self._destruida` 🆕** e, se a página ainda estiver viva, remove a linha da tabela (se deu certo) ou mostra o erro (se falhou).

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

### 🆕² Sair sem salvar (`_tentar_voltar`)

```python
def _tentar_voltar(self):
    if self._alteracoes_nao_salvas:
        resposta = QMessageBox.question(
            self, "Sair sem salvar",
            "Você tem alterações que ainda não foram salvas. Quer sair mesmo assim?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
    self.voltar_callback()
```

O botão "← Voltar" não chama mais `voltar_callback` diretamente — ele passou a chamar `_tentar_voltar`, que primeiro confere a flag `self._alteracoes_nao_salvas`. Essa flag é ligada dentro de `_on_item_changed` sempre que o **usuário** edita uma célula (linha nova preenchida ou edição numa linha já existente — preencher a tabela programaticamente, com `_carregando` ativo, nunca liga essa flag). Ela é desligada em dois momentos: logo após `_popular_tabela` terminar de (re)carregar os dados (não há nada "novo" a perder ainda) e logo após um salvamento bem-sucedido em `_on_salvamento_concluido`. Se existir alguma alteração pendente, um `QMessageBox.question` pede confirmação antes de voltar; se o usuário escolher "Não", a navegação é cancelada e ele continua na tela de compras.

### Salvar (`_salvar` → `_on_salvamento_concluido`)

1. Percorre todas as linhas da tabela, ignorando qualquer uma com quantidade ou preço inválido/zerado (linhas em branco não são enviadas).
2. Para cada linha válida, monta um dicionário `registro` com `data`, `quantidade`, `preco_unitario`, `preco_total`.
3. Se a linha já tiver um ID (via `_id_da_linha`), ela é uma **atualização** → vai para a lista `existentes`. Senão, gera um novo ID (`gerar_id`), adiciona `empresa`/`produto` ao registro (necessário para o Sheets saber onde inserir) e vai para a lista `novas`. Também guarda, em `linhas_por_id_novo`, qual linha da tabela corresponde a cada novo ID — é assim que depois o código sabe onde "gravar de volta" o ID recém-criado.
4. Se não houver nada pra enviar, apenas avisa e para.
5. Caso contrário, dispara `SheetsWorker(sheets_salvar, novas, existentes)`.
6. Quando termina, `_on_salvamento_concluido` **primeiro verifica `self._destruida` 🆕** e, se a página ainda estiver viva, grava o ID de cada linha nova de volta no `UserRole` dela (usando o mapa `linhas_por_id_novo`) — assim, se o usuário salvar de novo sem recarregar, essas linhas já são reconhecidas como "existentes" em vez de criar duplicatas.

### Recarregar do Sheets (`_recarregar_do_sheets` → `_on_recarregamento_concluido`)

Busca de novo todos os registros da empresa e filtra só os do produto atual (`linha.get("produto") == self.produto`), repopulando a tabela do zero — útil se outra pessoa alterou a planilha por fora do app. `_on_recarregamento_concluido` também **verifica `self._destruida` 🆕** antes de tocar em qualquer widget.

---

## 9. Página 2 — Lista de produtos (`ProductListPage`)

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

### 🆕 Carregar com cache primeiro, rede depois (`recarregar`)

```python
def recarregar(self):
    if self._operacao_em_andamento:
        return

    # 1) Mostra na hora o que já temos em cache local, sem esperar a rede.
    dados_cache = cache_carregar(self.empresa["nome"])
    if dados_cache:
        self._linhas_por_produto = {}
        for linha in dados_cache:
            self._linhas_por_produto.setdefault(linha["produto"], []).append(linha)
        self._produtos_pendentes = [p for p in self._produtos_pendentes if p not in self._linhas_por_produto]
        self._reconstruir_tabela()
        self.dica_label.setText("Mostrando dados salvos localmente — atualizando com o Google Sheets...")
    else:
        self.dica_label.setText("Carregando produtos do Google Sheets...")

    # 2) Em paralelo, busca a versão atual no Sheets pra confirmar/atualizar.
    self._definir_ocupado(True)
    ...
    self._worker = SheetsWorker(sheets_buscar, self.empresa["nome"])
    self._worker.concluido.connect(self._on_carregamento_concluido)
    self._worker.start()
    ...
```

Essa é a principal mudança de performance percebida do app: antes, `recarregar()` sempre mostrava "Carregando..." e ficava esperando a resposta da rede pra desenhar qualquer coisa. Agora, se existir um cache local daquela empresa (ver [Seção 5](#5-cache-local-em-disco-)), a tabela é populada **imediatamente** com esses dados, e só depois a busca real ao Sheets é disparada em segundo plano pra confirmar/atualizar. O usuário passa a ver dados quase instantaneamente ao trocar de empresa, mesmo que a rede ou o Apps Script demorem alguns segundos para responder.

Além disso, existe o `timeout` já configurado dentro da própria requisição HTTP (40s) e um **watchdog** adicional de 45s usando `QTimer.singleShot`. Ele existe para cobrir casos raros em que uma falha de rede/DNS trava a chamada sem respeitar o timeout interno do `urllib` — nesse cenário, sem esse watchdog, a tela ficaria presa para sempre em "Carregando...".

O contador `_geracao_carregamento` resolve um problema clássico de concorrência: se o usuário clicar em "Recarregar" várias vezes seguidas, cada chamada a `recarregar()` incrementa esse contador e guarda o valor daquela chamada especificamente (`geracao_desta_chamada`). Quando o watchdog dispara 45s depois, ele só age se **essa ainda for a geração mais recente** — ou seja, se nenhuma busca mais nova foi iniciada nesse meio-tempo. Isso evita que um watchdog "antigo" interrompa uma busca "nova" que ainda está em andamento.

### Quando os dados chegam (`_on_carregamento_concluido`)

```python
self._linhas_por_produto = {}
for linha in resultado:
    self._linhas_por_produto.setdefault(linha["produto"], []).append(linha)

self._produtos_pendentes = [p for p in self._produtos_pendentes if p not in self._linhas_por_produto]

cache_salvar(self.empresa["nome"], resultado)  # 🆕
self._reconstruir_tabela()
```

Agrupa a lista "achatada" de linhas que veio do Sheets num dicionário `{produto: [linhas]}`, usando `setdefault` para criar a lista na primeira vez que um produto aparece. Em seguida, "limpa" a lista de pendentes: qualquer produto que já apareceu nos dados reais do Sheets deixa de ser "pendente" (já tem pelo menos uma compra salva). 🆕 Por fim, o resultado é gravado no cache local, pra próxima abertura dessa empresa já começar instantânea.

🆕 Se a busca **falhar** mas já havia dados de cache exibidos na tela (`self._linhas_por_produto` não vazio), o código mantém esses dados visíveis e só troca a mensagem de dica para avisar que a atualização falhou — em vez de apagar tudo e mostrar um erro sobre uma tela vazia.

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

Para cada produto, busca a última compra com `obter_ultima_compra` e mostra sua data e valor. A célula na última coluna não é um texto — é um **botão** (`QPushButton("Abrir lista →")`) inserido com `setCellWidget`, que ao ser clicado chama `_abrir_produto(nome_produto)`. Um duplo clique em qualquer célula da linha também abre o produto (via `itemDoubleClicked`). 🆕² A célula com o nome do produto (`item_nome`) agora também recebe um `setToolTip(nome_produto)`, mostrando o nome completo ao passar o mouse quando ele é grande demais para a coluna.

### Adicionar e remover produtos

- **`_adicionar_produto`**: abre um `QInputDialog` pedindo o nome, valida que não é vazio nem duplicado, e adiciona à lista `_produtos_pendentes`. 🆕² Em seguida chama `self._abrir_produto(nome)` — o produto recém-criado é aberto na hora, direto na tela de compras, sem o usuário precisar localizá-lo na lista (que pode estar ordenada ou filtrada de um jeito que o esconda).
- **`_remover_produto`**: se o produto **não tem nenhum ID** (é só "pendente", nunca foi salvo), remove localmente sem chamar o Sheets. Se **tem IDs**, pede confirmação e dispara `sheets_remover` com a lista de todos os IDs daquele produto de uma vez (remove todas as compras do produto na mesma chamada).

---

## 10. Página 1 — Seleção de empresa (`CompanySelectPage`)

A tela mais simples: para cada empresa em `COMPANIES`, cria um "card" vertical com o avatar circular (via `criar_avatar_circular`) e um botão colorido com o nome da empresa, que ao ser clicado chama `escolher_callback(empresa)`.

Se `GOOGLE_SHEETS_WEBHOOK_URL` estiver vazia, mostra um aviso vermelho no topo, para deixar claro que o app não vai funcionar sem essa configuração — em vez de o usuário só descobrir isso depois, ao tentar abrir uma empresa e receber um erro confuso.

---

## 11. Janela principal e navegação (`MainWindow`)

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

A página de lista de produtos **é reaproveitada** por empresa: na primeira vez que o usuário abre "Narua", uma `ProductListPage` é criada e guardada no dicionário `_paginas_produtos`. Da segunda vez em diante, em vez de criar tudo de novo, o código só chama `.recarregar()` nela — que agora (🆕) primeiro mostra o cache local e depois busca os dados atualizados, sem reconstruir a interface do zero.

### 🆕 `abrir_produto(empresa, produto, linhas)`

```python
pagina = ProductEntriesPage(empresa, produto, linhas, voltar_callback=...)
if self._pagina_entradas_atual is not None:
    self._pagina_entradas_atual.marcar_destruida()   # 🆕
    self.stack.removeWidget(self._pagina_entradas_atual)
    self._pagina_entradas_atual.deleteLater()

self._pagina_entradas_atual = pagina
self.stack.addWidget(pagina)
self.stack.setCurrentWidget(pagina)
```

Diferente da lista de produtos, a página de **compras de um produto não é reaproveitada** — toda vez que o usuário abre um produto, uma `ProductEntriesPage` nova é criada. Isso é intencional: como os dados vêm sempre "frescos" da lista de produtos (que acabou de recarregar do Sheets), é mais simples e seguro recriar a tela do que tentar atualizar uma existente.

A página anterior é removida da pilha (`removeWidget`) e agendada para ser destruída (`deleteLater`, o jeito seguro do Qt de liberar memória sem correr risco de travar algo que ainda está em uso). 🆕 **Antes disso**, porém, `marcar_destruida()` é chamado nela — é essa linha que avisa a página antiga (e, por extensão, qualquer `SheetsWorker` seu ainda em voo) que ela está de saída, evitando o crash descrito na [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage).

### Voltar (`voltar_para_lista_produtos` / `voltar_para_selecao`)

Ao voltar da tela de compras para a lista de produtos, o código também chama `.recarregar()` na lista — garantindo que qualquer alteração feita na tela de compras (nova compra salva, produto removido etc.) já apareça refletida assim que o usuário volta.

---

## 12. Fluxo completo de uma tela até a outra

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
   🆕 mostra o cache local (se existir) na hora
   dispara SheetsWorker(sheets_buscar, "Narua")  ──► GET no Apps Script
   (🆕 o Apps Script tenta responder a partir do cache de 60s antes de reler a planilha)
        │
        ▼ (sinal "concluido")
4. ProductListPage._on_carregamento_concluido()
   agrupa linhas por produto, 🆕 salva no cache local, reconstrói a tabela
        │
        │ usuário clica em "Abrir lista →" no produto X
        ▼
5. MainWindow.abrir_produto(empresa, "Produto X", linhas)
   🆕 marca a ProductEntriesPage anterior (se houver) como destruída, antes de removê-la
   cria uma nova ProductEntriesPage
        │
        │ usuário edita quantidade/preço, clica em "Salvar"
        ▼
6. ProductEntriesPage._salvar()
   monta listas "novas"/"existentes", dispara
   SheetsWorker(sheets_salvar, novas, existentes)  ──► POST no Apps Script
   (🆕 o Apps Script grava as linhas novas em lote e invalida o cache de leitura)
        │
        ▼ (sinal "concluido")
7. ProductEntriesPage._on_salvamento_concluido()
   🆕 se a página já foi destruída nesse meio-tempo, ignora o resultado e para aqui
   senão: grava os novos IDs nas linhas, mostra "✓ Salvo com sucesso"
```

---

## 13. Ponto de entrada (`main`)

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

## 14. Backend Apps Script (`apps_script_backend.gs`) 🆕

Esse arquivo roda **dentro do Google**, ligado à planilha (Extensões → Apps Script), e é o único ponto de contato entre o Python e os dados. Ele expõe duas "rotas" HTTP: `doGet` (ler) e `doPost` (salvar/remover).

### Estrutura da planilha

```
ID | Empresa | Produto | Data | Quantidade | Preço Unitário | Preço Total
```

🆕 O array `CABECALHO` foi corrigido para refletir essas 7 colunas de verdade — na versão anterior ele só listava 5 nomes, o que não batia com o que era realmente gravado.

### `getPlanilha()` / `lerTodasLinhasDaPlanilha()`

`getPlanilha()` pega a aba ativa da planilha, criando o cabeçalho se ela estiver totalmente vazia. `lerTodasLinhasDaPlanilha()` lê a planilha inteira **de uma vez** (`getDataRange().getValues()`) e converte cada linha num objeto JS `{id, empresa, produto, data, quantidade, preco_unitario, preco_total}`, pulando linhas sem ID (vazias).

### 🆕 Cache de leitura (`cacheSalvarLista` / `cacheCarregarLista` / `invalidarCache`)

Esse é o maior ganho de velocidade do backend. `CacheService.getScriptCache()` guarda dados temporários no lado do Google, mas cada chave tem um limite de **100KB** — pouco para uma "lista imensa". Por isso, a lista inteira (já em JSON) é dividida em pedaços de até 90.000 caracteres e salva em múltiplas chaves (`linhas_planilha_0`, `linhas_planilha_1`, ...), junto com uma chave `linhas_planilha_meta` guardando quantos pedaços existem.

```javascript
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
    // se nem isso couber no cache, segue sem cache — nunca quebra a requisição
  }
}
```

`cacheCarregarLista()` faz o caminho inverso: lê a chave `_meta` pra saber quantos pedaços existem, busca todos de uma vez (`cache.getAll`) e remonta o JSON. Se qualquer pedaço estiver faltando (expirou, por exemplo), descarta tudo e devolve `null`, forçando uma releitura da planilha.

`invalidarCache()` apaga todas essas chaves. Ela é chamada em **toda** operação de escrita (`salvar` e `remover`), garantindo que ninguém veja dados desatualizados depois de uma alteração.

O tempo de vida do cache é `CACHE_SEGUNDOS = 60` — ajustável no topo do arquivo. Quanto maior, menos vezes a planilha é relida, mas maior a chance de alguém ver dados com até esse tempo de atraso caso a planilha seja editada por fora do app (direto no Google Sheets, por exemplo).

### `doGet(e)`

```javascript
function doGet(e) {
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
}
```

🆕 Agora tenta o cache primeiro; só lê a planilha de verdade em caso de cache "frio" (primeira chamada, ou depois de expirar/ser invalidado). O filtro por empresa é aplicado **depois** de obter a lista completa (do cache ou da planilha) — assim, uma única lista em cache serve pra todas as empresas, e cada empresa não precisa de um cache separado.

### 🆕 `construirIndiceIds(planilha)` — elimina o gargalo de escrita

```javascript
function construirIndiceIds(planilha) {
  var indice = {};
  var ultimaLinha = planilha.getLastRow();
  if (ultimaLinha < 2) return indice;
  var ids = planilha.getRange(2, 1, ultimaLinha - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (ids[i][0] !== "") indice[String(ids[i][0])] = i + 2;
  }
  return indice;
}
```

Antes, cada atualização ou remoção fazia sua **própria** varredura da coluna A inteira pra achar a linha correspondente àquele ID — se você salvasse 10 linhas existentes numa planilha de 5.000 linhas, isso significava 10 leituras de 5.000 células cada. Agora, essa varredura acontece **uma única vez por requisição**, construindo um mapa `{id: número_da_linha}` que é reaproveitado por todas as atualizações/remoções daquela chamada. Isso muda o custo de O(n × m) para O(n + m), o que faz muita diferença numa "lista imensa".

### `doPost(e)` / `salvarRegistros` / `removerRegistros`

```javascript
function salvarRegistros(planilha, novas, existentes) {
  if (novas.length > 0) {
    var linhaInicial = planilha.getLastRow() + 1;
    var dados = novas.map(function (l) {
      return [l.id, l.empresa, l.produto, l.data, l.quantidade, l.preco_unitario, l.preco_total];
    });
    planilha.getRange(linhaInicial, 1, dados.length, NUM_COLUNAS).setValues(dados);
  }

  if (existentes.length > 0) {
    var indice = construirIndiceIds(planilha);
    existentes.forEach(function (l) {
      var linhaIndex = indice[String(l.id)];
      if (linhaIndex) {
        planilha.getRange(linhaIndex, 4, 1, 4).setValues([[l.data, l.quantidade, l.preco_unitario, l.preco_total]]);
      }
    });
  }
}
```

🆕 As linhas **novas** deixaram de ser gravadas com um `appendRow()` por linha (cada um sendo uma chamada separada à API do Sheets) e passaram a ser gravadas todas de uma vez, com um único `setValues()` numa faixa de células contígua começando logo após a última linha usada. As linhas **existentes** usam o índice construído uma única vez, como explicado acima.

```javascript
function removerRegistros(planilha, ids) {
  if (!ids.length) return 0;
  var indice = construirIndiceIds(planilha);
  var linhasParaRemover = [];
  ids.forEach(function (id) {
    var linhaIndex = indice[String(id)];
    if (linhaIndex) linhasParaRemover.push(linhaIndex);
  });
  linhasParaRemover.sort(function (a, b) { return b - a; });
  linhasParaRemover.forEach(function (linhaIndex) {
    planilha.deleteRow(linhaIndex);
  });
  return linhasParaRemover.length;
}
```

Mesma lógica: o índice é construído uma vez, todas as linhas a remover são localizadas nele, e só então são apagadas — de baixo para cima, pra não bagunçar os índices das linhas seguintes ao deletar.

Por fim, `doPost` chama `invalidarCache()` depois de qualquer `salvar` ou `remover` bem-sucedido, garantindo que a próxima leitura (`doGet`) já reflita os dados novos, em vez de servir uma versão em cache desatualizada.

---

## Glossário rápido

| Termo | Significado no contexto do app |
|---|---|
| **Web App / Apps Script** | Script hospedado no Google que expõe a planilha como uma pequena API HTTP |
| **`QThread`** | Mecanismo do Qt para rodar código em segundo plano, sem travar a interface |
| **`pyqtSignal`** | "Evento" do Qt: uma forma segura de uma thread avisar a interface que algo aconteceu |
| **`UserRole`** | Um espaço "escondido" dentro de um item de tabela do Qt, usado aqui para guardar o ID da planilha sem exibi-lo na tela |
| **Linha "pendente"** | Produto criado na interface que ainda não tem nenhuma compra salva no Sheets |
| 🆕 **`_destruida`** | Flag na `ProductEntriesPage` que marca quando a tela foi fechada, pra callbacks de rede atrasados saberem que devem se ignorar em vez de mexer em widgets já apagados |
| 🆕 **Cache local (Python)** | Arquivo `.json` por empresa, em `cache/`, usado para popular a tela instantaneamente antes da resposta real do Sheets chegar |
| 🆕 **`CacheService` (Apps Script)** | Cache temporário do lado do Google, usado para não reler a planilha inteira a cada `GET`, respeitando o limite de 100KB por chave via divisão em pedaços |
| 🆕 **Índice de IDs** | Mapa `{id: linha}` construído uma única vez por requisição de escrita, evitando releituras repetidas da coluna de IDs |
| 🆕² **`LabelElidavel`** | `QLabel` que trunca o próprio texto com reticências quando não cabe na largura disponível, mantendo o texto completo como tooltip |
| 🆕² **`TabelaComNavegacaoEnter`** | `QTableWidget` da tela de compras cujo Enter avança Data → Quantidade → Preço Unitário em vez de descer de linha, e não avança nem cria linha nova a partir de Preço Unitário |
| 🆕² **`_alteracoes_nao_salvas`** | Flag na `ProductEntriesPage` que rastreia edições ainda não enviadas ao Sheets, usada por `_tentar_voltar` para confirmar antes de sair da tela |
| 🆕³ **`minimumSizeHint()`** | Método do Qt que informa ao layout o menor tamanho aceitável de um widget; sobrescrito em `LabelElidavel` pra não crescer junto com o texto, permitindo a elisão de verdade |
| 🆕³ **Hint de `closeEditor`** | Sinal que o Qt manda pra view avisando qual tecla fechou o editor de uma célula; o do Enter tem o nome oficial `SubmitModelData`, mas aparece como `SubmitModelCache` em algumas versões do PyQt6 |