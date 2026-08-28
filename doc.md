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
>
> **Changelog de auditoria (revisão de bugs):** uma revisão dedicada (11 problemas confirmados) encontrou e corrigiu: (1) o backend gravava/lia sempre na aba "ativa" da planilha em vez de uma aba fixa; (2) datas podiam voltar com 1 dia de diferença dependendo do fuso horário da planilha; (3) um ID todo numérico podia perder um zero à esquerda; (4) o Apps Script descartava edições de linhas não encontradas sem avisar (respondia "ok" mesmo assim); (5) a exclusão instantânea de linha/produto, ao remover uma trava de segurança antiga, podia derrubar o app se duas ações de rede fossem disparadas em sequência rápida; (6) o backend não tinha nenhum bloqueio contra duas requisições simultâneas; (7) desfazer uma remoção que falhou "esquecia" que a linha restaurada tinha uma edição pendente; (8) o mesmo desfazer também zerava o Total mostrado; (9) o rastreamento de "linha editada" podia, em teoria, confundir uma linha nunca tocada com uma editada. Tudo detalhado nas seções marcadas com 🆕⁴.
>
> **Changelog de estrutura + importação por foto (esta revisão):** cada compra ganhou um campo **Nome** (novas colunas `COL_NOME`/"Nome" na tabela e no Sheets), separando "que tipo de produto é" (a pasta, ex: "Aveia Flocos") de "qual embalagem/marca foi comprada" (o Nome de cada linha, ex: "Aveia Flocos Marca X"). A tabela de compras passou a ter 5 colunas (Nome, Data, Quantidade, Preço Unitário, Preço Total) e a navegação por Enter ganhou mais um passo (Nome → Data → Quantidade → Preço Unitário). Novo botão **"📷 Importar nota fiscal"** na lista de produtos: envia a foto da nota para a **API do Google Gemini** (`ler_nota_fiscal_ia`), que devolve os itens já estruturados; o app sugere a pasta certa comparando palavras com as pastas já existentes (`sugerir_pasta`) e abre uma página de conferência (`ImportarNotaFiscalPage`) antes de qualquer coisa ir pro Sheets — nada é salvo sem revisão manual. A chave da API e o modelo ficam em `~/.config/controle_empresas/config.json` (`carregar_config`/`salvar_config`), configuráveis pelo diálogo `ConfigDialog`. No backend, `garantirColunaNome` migra a planilha sozinha na primeira requisição depois do redeploy, sem precisar editar as colunas na mão. Marcado nas seções com 🆕⁵.
>
> **Changelog de IA (substituição do OCR):** a primeira versão do "importar de foto" usava **Tesseract OCR** local (`pytesseract` + `numpy` + heurística de regex) para ler o texto da nota. Isso foi **removido por completo** e trocado pela leitura via API do Google Gemini, que é muito mais precisa (entende o layout da nota, separa itens de linhas de total/imposto, lê fotos tortas) e não exige nada instalado no sistema além do PyQt6 — a chamada HTTP usa só `urllib`. A leitura roda em segundo plano (`SheetsWorker`), sem travar a interface. Se o modelo configurado for desligado pelo Google, a primeira falha `404` dispara `_ia_descobrir_modelo`, que acha um Flash válido na conta e grava no `config.json` automaticamente. Todo nome lido passa por `_nome_apresentavel`, que padroniza como frase — só a primeira letra maiúscula e o resto minúsculo ("ARROZ TIPO 1 5KG" e "Arroz Tipo 1 5kg" viram os dois "Arroz tipo 1 5kg") — pra lista não misturar CAIXA ALTA, Title Case e frase. Por fim, `_consolidar_itens_iguais` junta numa linha só os itens da mesma nota com nome, preço unitário e data idênticos, somando a quantidade — resolve as verduras/carnes vendidas por peso, que a nota lista uma vez por pesagem ("4 brócolis, 5 repolhos") mesmo com o preço do quilo igual.
>
> **Changelog de importação por link do QR code:** além da foto, um botão **"🔗 Importar por link"** aceita o endereço do QR code de uma NFC-e. `ler_nota_fiscal_link` baixa a página oficial de consulta da SEFAZ (com um `User-Agent` de navegador), reduz o HTML a texto puro (`_texto_de_html`) e manda para o mesmo modelo, que extrai os itens do texto (dados oficiais e completos). As duas importações compartilham `_ia_gerar_itens` (monta o corpo, faz a chamada, aplica o fallback de modelo) e caem na mesma `ImportarNotaFiscalPage` — quando não há imagem, o painel esquerdo mostra um aviso em vez da foto. Portais que protegem a consulta com CAPTCHA (Santa Catarina, por exemplo) são detectados e o app orienta a usar a foto.
>
> **Changelog de segurança e limpeza (🆕⁵):** a URL do Web App do Apps Script — que dá acesso de leitura/escrita à planilha inteira — **saiu do código**: era uma constante hardcoded (e chegou a ser commitada no git). Agora vem de `sheets_webhook_url()` (variável de ambiente `GOOGLE_SHEETS_WEBHOOK_URL` ou `config.json`), e o antigo `ConfigIADialog` virou **`ConfigDialog`**, com um campo pra colar essa URL (segredo, oculto por padrão) além da chave da IA. A leitura por foto deixou de descartar linhas incompletas em silêncio (pede confirmação), e `_inserir_linha_produto` ficou tolerante a valores em branco. A [Seção 20](#20-notas-de-análise--código-morto-bugs-e-segurança) reúne todas as notas de análise, incluindo a recomendação de **rotacionar a URL do Web App** (ela continua no histórico do git já enviado ao GitHub).
>
> **Changelog de empacotamento e refatoração (🆕⁶):** o app foi preparado pra virar um **executável único** (PyInstaller — `.exe` no Windows), sem o usuário final precisar de Python. Mudou: (1) os caminhos — assets agora são resolvidos por `resource_path()` (acha tanto solto quanto dentro do pacote), e `config`/`cache` foram pra **pastas graváveis por-usuário do SO** (`%APPDATA%`/`%LOCALAPPDATA%` no Windows, `~/.config`/`~/.cache` no Linux) em vez de ficarem ao lado do executável; `migrar_cache_antigo()` move o cache da pasta antiga uma vez. (2) As três telas cheias (`ProductEntriesPage`, `ImportarNotaFiscalPage`, `ProductListPage`) agora herdam de **`PaginaBase`**, que concentra o encanamento antes triplicado (`_disparar_worker`, `marcar_destruida`/`_destruida`, `_definir_ocupado`, `_texto_celula`, `_estilo_botao_destaque`). Arquivos novos: `controle_empresas.spec`, `requirements.txt`. Ver a [Seção 21](#21-empacotamento-e-instalação-).
>
> **Changelog de distribuição e blindagem (🆕⁷, esta revisão):** (1) **CI de build** — `.github/workflows/build.yml` gera o `.exe` (Windows) e o binário (Linux) e publica numa Release do GitHub a cada tag `v*`, pra qualquer pessoa baixar pronto. (2) **Guia de instalação passo a passo** por sistema no `Readme.md` e resumido aqui (Seção 21). (3) Blindagem: `salvar_config` grava de forma **atômica** e já com permissão `600` (sem a janela de tempo do `chmod` posterior, e leitura concorrente nunca vê JSON truncado); `ler_nota_fiscal_link` recusa endereços de **rede interna/loopback** (`_recusar_host_interno`); `LabelElidavel` força **texto puro** (nome de produto com cara de HTML não é mais interpretado como rich text).

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
13. [Ponto de entrada (`main`) e tema escuro](#13-ponto-de-entrada-main-e-tema-escuro)
14. [Backend Apps Script (`apps_script_backend.gs`) 🆕](#14-backend-apps-script-apps_script_backendgs-)
15. [Campo Nome por compra 🆕⁵](#15-campo-nome-por-compra-)
16. [Configuração e segredos em disco (`config.json`) 🆕⁵](#16-configuração-e-segredos-em-disco-configjson-)
17. [Leitura de nota fiscal com IA — foto e link 🆕⁵](#17-leitura-de-nota-fiscal-com-ia--foto-e-link-)
18. [Diálogo `ConfigDialog` 🆕⁵](#18-diálogo-configdialog-)
19. [Página de conferência `ImportarNotaFiscalPage` 🆕⁵](#19-página-de-conferência-importarnotafiscalpage-)
20. [Notas de análise — código morto, bugs e segurança 🆕⁵](#20-notas-de-análise--código-morto-bugs-e-segurança)
21. [Empacotamento e instalação 🆕⁶ 🆕⁷](#21-empacotamento-e-instalação-)

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
                            │
                            └─ 🆕⁵ ImportarNotaFiscalPage
                               (confere os itens que a IA leu de uma
                                nota fiscal, antes de salvar no Sheets)
```

🆕⁵ A partir da lista de produtos também dá pra abrir a `ImportarNotaFiscalPage` (mais uma tela do `QStackedWidget`, ver [Seção 19](#19-página-de-conferência-importarnotafiscalpage-)) e o diálogo modal `ConfigDialog` (ver [Seção 18](#18-diálogo-configdialog-)).

Um ponto importante: **nenhuma tela guarda estado permanente sozinha**. Sempre que o usuário volta ou reabre uma tela, o app dispara uma nova busca no Sheets — isso evita mostrar dados desatualizados se a planilha mudou entre uma visita e outra. 🆕 Desde a versão atual, essa busca é precedida por uma leitura instantânea do **cache local** (ver Seção 5), então a tela não fica mais "em branco" enquanto espera a rede.

Como toda chamada de rede pode demorar, ela **nunca roda na thread principal da interface** (que travaria a janela). Em vez disso, cada chamada roda dentro de uma `QThread` (a classe `SheetsWorker`), e o resultado chega de volta através de um **sinal Qt** (`pyqtSignal`).

🆕 **Sobre o ciclo de vida das telas:** como cada `SheetsWorker` roda em paralelo e pode terminar depois que a tela que o criou já foi fechada (por exemplo, o usuário voltou e abriu outro produto antes da resposta do "Salvar" chegar), a `ProductEntriesPage` agora rastreia explicitamente se ela já foi destruída, e ignora qualquer resultado de rede que chegue depois disso. Isso é detalhado na [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage).

---

## 2. Configuração inicial

```python
# 🆕⁶ caminhos cientes de "solto" x "empacotado" (PyInstaller)
def resource_path(*partes):        # assets: acompanham o app (sys._MEIPASS quando empacotado)
    ...
def _dir_dados_usuario(tipo):      # 'config' ou 'cache' -> pasta gravável por-usuário do SO
    ...

ASSETS_DIR  = resource_path("assets")
CONFIG_DIR  = _dir_dados_usuario("config")   # %APPDATA%/.. no Windows, ~/.config/.. no Linux
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_DIR   = _dir_dados_usuario("cache")    # %LOCALAPPDATA%/.. no Windows, ~/.cache/.. no Linux

# 🆕⁵ nenhum segredo no código: a URL do Web App e a chave da API vêm do
# config.json (fora do git) ou de variável de ambiente. Ver Seção 16.
MODELO_IA_PADRAO = "gemini-2.5-flash"
```

- 🆕⁶ **`resource_path(*partes)`** resolve um recurso somente-leitura que acompanha o app (as logos em `assets/`). Rodando solto, a base é a pasta do `.py`; empacotado com o PyInstaller, é `sys._MEIPASS` (a pasta temporária onde o `.exe` se desempacota). Sem isso, `assets/` some quando o app vira executável.
- 🆕⁶ **`_dir_dados_usuario("config"|"cache")`** devolve uma pasta **gravável por-usuário do sistema operacional** — nunca ao lado do executável, porque no Windows a pasta do programa costuma ser somente-leitura. No Windows: `%APPDATA%\controle_empresas` (config) e `%LOCALAPPDATA%\controle_empresas` (cache). No Linux: `~/.config/controle_empresas` e `~/.cache/controle_empresas` (respeitando `XDG_CONFIG_HOME`/`XDG_CACHE_HOME`). O caminho do config no Linux **não mudou**, então o `config.json` de quem já usava continua valendo; o cache mudou de lugar e `migrar_cache_antigo()` (ver [Seção 5](#5-cache-local-em-disco-)) faz a mudança uma vez.
- 🆕⁵ **A URL do Web App do Apps Script não é mais uma constante no código.** Ela dá acesso de leitura/escrita à planilha inteira — é um segredo — e vinha hardcoded (e chegou a ser commitada, ver Seção 20). Agora vem de `sheets_webhook_url()` (variável de ambiente `GOOGLE_SHEETS_WEBHOOK_URL` ou `config.json`), configurável no diálogo "⚙️ Configurar" (ver [Seção 18](#18-diálogo-configdialog-)). Continua sendo a única "porta de entrada" do app para os dados.
- 🆕⁵ O `config.json` (em `CONFIG_PATH`) guarda a **URL da planilha**, a **chave da API do Google Gemini** e o modelo escolhido — fora da pasta do projeto porque são segredos e não devem entrar no git (ver [Seção 16](#16-configuração-e-segredos-em-disco-configjson-)). `MODELO_IA_PADRAO` é o modelo usado pra ler notas quando o `config.json` não define outro.

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

COLUNAS_ENTRADAS = ["Nome", "Data", "Quantidade", "Preço Unitário", "Preço Total"]  # 🆕⁵
COL_NOME, COL_DATA, COL_QTD, COL_PRECO_UNIT, COL_TOTAL = range(5)

ROWS_INICIAIS = 1
```

- `BORDA_COR`/`BORDA_ESPESSURA` são usadas ao desenhar as logos circulares.
- `COLUNAS_ENTRADAS` define os títulos das colunas da tabela de compras, e as constantes `COL_NOME`, `COL_DATA`, `COL_QTD`, `COL_PRECO_UNIT`, `COL_TOTAL` (0, 1, 2, 3, 4) evitam usar números "mágicos" espalhados pelo código — em vez de `tabela.item(row, 3)`, o código usa `tabela.item(row, COL_PRECO_UNIT)`, o que é bem mais legível. 🆕⁵ A coluna **Nome** foi adicionada no início: guarda o texto exato da marca/embalagem daquela compra (ver [Seção 15](#15-campo-nome-por-compra-)); o ID da linha na planilha continua guardado no `UserRole` do item da coluna **Data** (que agora é a coluna 1, não a 0).
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
    if not url:   # 🆕⁵ agora confere o argumento, não uma constante global
        raise ErroSheets("A URL da planilha não foi configurada. Abra '⚙️ Configurar'...")
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

1. **Confere se a URL foi configurada.** 🆕⁵ Cada função pública resolve a URL com `sheets_webhook_url()` e a passa como argumento; se vier vazia (nada no `config.json` nem na variável de ambiente), `_requisitar` nem tenta a chamada — já avisa pra abrir "⚙️ Configurar".
2. **Monta e envia a requisição HTTP** com `urllib.request` (biblioteca padrão do Python, sem precisar instalar `requests`). O parâmetro `dados` (bytes de um JSON) só é enviado quando é um `POST`; em `GET` ele fica `None`.
3. **Captura três tipos de falha de rede** separadamente, para dar mensagens de erro mais claras ao usuário: erro HTTP (ex: 500), erro de conexão (ex: sem internet) e erro de timeout/DNS (`OSError`, que às vezes escapa do `URLError`).
4. **Faz o parse do JSON** da resposta. Se o Apps Script devolver algo que não é JSON válido (por exemplo, uma página de erro HTML do Google, o que acontece quando o script não está publicado corretamente), a função devolve um erro explicando isso, mostrando um trecho da resposta recebida para ajudar a diagnosticar.
5. **Confere o campo `"ok"`** que o próprio Apps Script devolve. Mesmo que a requisição HTTP tenha "dado certo" (200 OK), o Apps Script pode reportar uma falha de lógica (ex: ID não encontrado) através desse campo — nesse caso a função também levanta `ErroSheets`.

### `sheets_buscar(empresa=None)`

```python
def sheets_buscar(empresa: str = None) -> list:
    url = sheets_webhook_url()   # 🆕⁵
    if empresa and url:
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
def sheets_salvar(novas: list, existentes: list) -> list:
    payload = json.dumps({"acao": "salvar", "novas": novas, "existentes": existentes}).encode("utf-8")
    corpo = _requisitar(sheets_webhook_url(), dados=payload, metodo="POST")
    return corpo.get("idsNaoEncontrados", [])
```

Envia um `POST` com duas listas: `novas` (linhas que ainda não existem na planilha — vão virar gravação em lote) e `existentes` (linhas que já têm um ID e vão ser atualizadas). O Apps Script decide o que fazer com cada lista. 🆕 Do lado do Apps Script, as linhas novas agora são gravadas todas de uma vez (um único `setValues` em bloco) em vez de uma chamada por linha — ver Seção 14.

🆕⁴ **Devolve quais IDs "existentes" não foram encontrados na planilha.** Antes, se uma linha fosse apagada por fora do app (por outra sessão, por exemplo) entre o usuário editá-la e clicar em Salvar, o Apps Script simplesmente descartava aquela edição e respondia "ok" do mesmo jeito — o Python achava que tinha salvo tudo. Agora o backend devolve `idsNaoEncontrados` (ver [Seção 14](#14-backend-apps-script-apps_script_backendgs-)), e `sheets_salvar` repassa essa lista pra quem chamou (`ProductEntriesPage._on_salvamento_concluido`, ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage)), que decide o que fazer com cada linha problemática em vez de assumir que está tudo salvo.

### `sheets_remover(ids)`

```python
def sheets_remover(ids: list) -> None:
    payload = json.dumps({"acao": "remover", "ids": ids}).encode("utf-8")
    _requisitar(sheets_webhook_url(), dados=payload, metodo="POST")
```

Envia um `POST` pedindo para apagar as linhas com os IDs informados. O Apps Script apaga a linha de verdade (não deixa célula em branco no meio da planilha).

### 🆕⁵ `sheets_renomear_produtos(itens)`

```python
def sheets_renomear_produtos(itens: list) -> list:
    payload = json.dumps({"acao": "renomearProdutos", "itens": itens}).encode("utf-8")
    corpo = _requisitar(sheets_webhook_url(), dados=payload, metodo="POST")
    return corpo.get("idsNaoEncontrados", [])
```

Envia um `POST` com a ação `"renomearProdutos"` (ver [Seção 14](#14-backend-apps-script-apps_script_backendgs-)): cada item de `itens` é um dict com `"id"` e, opcionalmente, `"produto"` e/ou `"nome"` — o backend sobrescreve só a coluna informada, por ID. A ideia é consolidar num só lugar produtos parecidos que viraram pastas separadas. **Nenhuma tela chama essa função ainda** — a ferramenta de mesclagem na interface não foi construída; por enquanto o código é só o "encanamento" pronto pra ela (ver notas de análise no fim da revisão).

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
        except (ErroSheets, ErroIA) as e:   # 🆕⁵ ErroIA
            self.concluido.emit(False, str(e))
        except Exception as e:
            self.concluido.emit(False, f"Erro inesperado: {e}")
```

Essa classe é o que **evita que a janela trave** enquanto o app fala com o Google. Ela é uma `QThread` "genérica": recebe qualquer função de rede pura mais seus argumentos, e a executa numa thread separada quando `.start()` é chamado. 🆕⁵ Além de `sheets_buscar` / `sheets_salvar` / `sheets_remover`, ela também roda `ler_nota_fiscal_ia` e `ler_nota_fiscal_link` (ver [Seção 17](#17-leitura-de-nota-fiscal-com-ia--foto-e-link-)) — por isso o `except` agora captura também `ErroIA`, a exceção da leitura de notas, e a repassa como mensagem de erro em vez de deixá-la virar um "Erro inesperado".

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

Grava a lista de linhas mais recente da empresa em disco, criando a pasta de cache se ainda não existir. É chamada logo depois de uma busca bem-sucedida no Sheets (dentro de `ProductListPage._on_carregamento_concluido`, ver [Seção 9](#9-página-2--lista-de-produtos-productlistpage)). Se a escrita falhar por qualquer motivo (disco cheio, sem permissão etc.), o erro é ignorado — de novo, o cache nunca deve derrubar o app.

### 🆕⁶ `migrar_cache_antigo()`

```python
def migrar_cache_antigo() -> None:
    # até esta versão o cache ficava em <pasta do script>/cache;
    # agora fica em CACHE_DIR (pasta por-usuário do SO). Move os .json
    # de lá pra cá, uma vez, best-effort.
```

Chamada uma vez no início de `main()`. `CACHE_DIR` deixou de ser `<pasta do script>/cache` e passou a ser uma pasta gravável por-usuário (ver [Seção 2](#2-configuração-inicial)) — obrigatório pra funcionar empacotado no Windows. Pra quem já usava o app, essa função move os `.json` da pasta antiga pra nova na primeira execução, pra não perder o "aparece na hora". Não roda quando empacotado (aí nunca houve pasta antiga) e qualquer erro é silenciosamente ignorado — o cache é descartável.

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

🆕⁷ O construtor faz `setTextFormat(Qt.TextFormat.PlainText)`: o nome do produto vem da planilha (editável pelo usuário) e da IA, e sem isso um nome com cara de HTML (`"<b>...`, `"<img src=x>"`) seria interpretado como rich text pelo `QLabel`.

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

        proxima_coluna = {COL_NOME: COL_DATA, COL_DATA: COL_QTD, COL_QTD: COL_PRECO_UNIT}.get(col)  # 🆕⁵
        if proxima_coluna is None:
            return

        self.setCurrentCell(row, proxima_coluna)
        self.editItem(self.item(row, proxima_coluna))
```

Ao confirmar uma célula em edição, o Qt avisa a view **qual tecla motivou o fechamento** através de um "hint" entregue ao método `closeEditor`. Essa subclasse intercepta esse hint especificamente quando ele indica que foi o **Enter/Return** que fechou o editor: em vez de deixar o comportamento padrão (que apenas confirma o valor, sem mover o cursor), ela fecha o editor manualmente (`NoHint`) e decide o próximo passo, seguindo o fluxo de preenchimento de uma compra:

- 🆕⁵ Na coluna **Nome**, Enter abre a edição da célula **Data** da mesma linha.
- Na coluna **Data**, Enter abre a edição da célula **Quantidade** da mesma linha.
- Na coluna **Quantidade**, Enter abre a edição da célula **Preço Unitário** da mesma linha.
- Na coluna **Preço Unitário**, o dicionário `proxima_coluna` não tem uma entrada correspondente (`.get()` devolve `None`), então a função simplesmente retorna — o valor já foi confirmado, mas o cursor **não avança e nenhuma linha nova é criada**. (A coluna Total nunca entra nesse fluxo por ser somente leitura.)

Essa classe substitui o `QTableWidget` usado na tabela de compras (`self.tabela`, dentro de `ProductEntriesPage._montar_ui`, ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage)).

🆕³ **Bug da primeira versão, e o porquê do `_HINT_ENTER`:** a primeira tentativa comparava o hint recebido com `QAbstractItemDelegate.EndEditHint.EditNextItem` (o hint oficialmente documentado para a tecla Tab) — mas testando na prática, o hint que o Enter realmente dispara é outro. Pior: o *nome* desse hint na enumeração do Python varia por versão do binding PyQt6 — na documentação oficial (e em versões mais novas do PyQt6) ele se chama `SubmitModelData`, mas em versões mais antigas existe um erro de digitação conhecido no binding, e o mesmo hint aparece com o nome `SubmitModelCache`. Como `if hint != EditNextItem` nunca era verdadeiro pro Enter, o código simplesmente caía no comportamento padrão do Qt (nada acontecia) — daí o Enter "não fazer nada" ao ser apertado na coluna Data. A correção usa `getattr(..., "SubmitModelData", None) or ...SubmitModelCache` para resolver o hint certo em tempo de importação, tentando primeiro o nome oficial e caindo para o nome com erro de digitação se o oficial não existir nessa instalação — funcionando nas duas versões do binding.

### 🆕⁶ Base das telas cheias (`PaginaBase`)

As três telas cheias — `ProductEntriesPage`, `ImportarNotaFiscalPage` e `ProductListPage` — copiavam o mesmo encanamento. Agora todas herdam de `PaginaBase(QWidget)`, que reúne:

| Membro | O que faz |
|---|---|
| `_workers_ativos` / `_disparar_worker(fn, *args, ao_concluir=)` | Dispara um `SheetsWorker` e o mantém numa lista até terminar — referência forte pra uma segunda chamada em paralelo não fazer a primeira `QThread` (ainda rodando, sem dono) ser coletada no meio e derrubar o app. Ao terminar, o worker sai da lista e `ao_concluir` é chamado. |
| `_destruida` / `marcar_destruida()` | A `MainWindow` chama `marcar_destruida()` antes de destruir uma página; os callbacks de rede atrasados checam `self._destruida` e desistem em vez de mexer em widgets já apagados (`RuntimeError: wrapped C/C++ object ... has been deleted`). `ProductListPage` é reaproveitada (nunca destruída), então herda a flag mas não a usa. |
| `_definir_ocupado(ocupado, mensagem="")` | Liga/desliga `_operacao_em_andamento` e desabilita os botões de `_botoes_bloqueaveis()` (cada página sobrescreve essa tupla); opcionalmente escreve `mensagem` no `status_label`. |
| `_texto_celula(row, col)` | Texto de uma célula da `self.tabela`, já com `.strip()`, ou `""`. |
| `_estilo_botao_destaque()` | O CSS do botão primário na cor da empresa. |

As referências a `_disparar_worker`/`_destruida`/etc. nas seções abaixo continuam válidas — só o **lugar** onde estão definidos mudou (de cada página pra `PaginaBase`).

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
self._workers_ativos = []          # 🆕⁴ ver "_disparar_worker", abaixo
self._remocoes_em_andamento = 0    # 🆕⁴ ver "_disparar_worker", abaixo
self._alteracoes_nao_salvas = False  # 🆕² ver "Sair sem salvar", abaixo
self._itens_editados = set()       # ver "Salvar", abaixo
self._destruida = False            # 🆕 ver abaixo
```

O flag `_carregando` é importante: sempre que o código preenche a tabela programaticamente (ao abrir a tela, ao recarregar, etc.), ele é ligado antes e desligado depois. Isso evita que o evento `itemChanged` (disparado toda vez que uma célula muda, inclusive por código) recalcule totais e indicadores durante esse preenchimento — o recálculo só deve acontecer quando é o **usuário** editando.

### 🆕⁴ `_disparar_worker(funcao, *args, ao_concluir)` — evita perder a referência a uma QThread ainda rodando

```python
def _disparar_worker(self, funcao, *args, ao_concluir):
    worker = SheetsWorker(funcao, *args)
    self._workers_ativos.append(worker)

    def _finalizar(ok, resultado):
        if worker in self._workers_ativos:
            self._workers_ativos.remove(worker)
        ao_concluir(ok, resultado)

    worker.concluido.connect(_finalizar)
    worker.start()
    return worker
```

Antigamente, todo lugar que disparava uma chamada de rede fazia `self._worker = SheetsWorker(...)` — um **único** atributo, reaproveitado por Salvar, Remover e Recarregar. Isso funcionava enquanto só uma chamada por vez estava em voo. Mas quando a remoção de linha/produto passou a ser otimista (a linha some da tela na hora, sem esperar a rede — ver "Remover uma linha", abaixo), ficou fácil disparar uma segunda chamada (outra remoção, um Salvar) **antes** da primeira responder. Como `self._worker` é um único atributo, a segunda chamada sobrescrevia a referência à primeira `QThread`, que — ainda rodando em segundo plano, sem nenhuma referência Python a mantê-la viva — podia ser destruída pelo coletor de lixo no meio da execução, e isso arrisca derrubar o app.

A correção substitui esse atributo único por uma **lista** (`self._workers_ativos`), com todo disparo de worker passando por `_disparar_worker`: o worker novo entra na lista assim que é criado e só sai dela quando termina (`_finalizar`, chamado antes do callback de negócio de verdade). Assim, não importa quantas chamadas estejam em voo ao mesmo tempo — cada uma continua tendo uma referência Python válida até terminar. Essa mesma função (e a mesma lista) existem, de forma independente, também em `ProductListPage` (ver [Seção 9](#9-página-2--lista-de-produtos-productlistpage)).

Além disso, `self._remocoes_em_andamento` (um contador, não um booleano) é incrementado quando uma remoção começa e decrementado quando ela termina — `_salvar` e `_recarregar_do_sheets` agora recusam começar enquanto esse contador for maior que zero, porque os dois dependem de números de linha que uma remoção em andamento pode deslocar. Remoções não bloqueiam **umas às outras** (cada uma cuida só da sua própria linha/produto, de forma independente).

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
3. **A tabela de compras** — 🆕² agora uma `TabelaComNavegacaoEnter` (ver [Seção 7](#7-mini-gráfico-de-tendência-de-preço)) em vez de `QTableWidget` puro, com 🆕⁵ 5 colunas (`COLUNAS_ENTRADAS` = Nome, Data, Quantidade, Preço Unitário, Preço Total — a coluna **Nome** entrou no início, ver [Seção 15](#15-campo-nome-por-compra-)) e cabeçalho pintado na cor da empresa. Ela escuta `itemChanged` (`self.tabela.itemChanged.connect(self._on_item_changed)`).
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
4. **Remoção otimista:** a linha some da tabela **na hora**, antes mesmo da rede responder — sem bloquear a tela. `_disparar_worker(sheets_remover, [id_linha], ...)` roda a chamada em segundo plano; `self._remocoes_em_andamento` é incrementado enquanto ela está em voo.
5. Quando o worker termina, `_on_remocao_concluida` primeiro decrementa `_remocoes_em_andamento`, depois verifica `self._destruida` 🆕 e, se a página ainda estiver viva: em caso de sucesso só atualiza a mensagem de status (a linha já sumiu); em caso de falha, **desfaz** a remoção chamando `_adicionar_linha(dados_removidos)` de volta e mostra o erro.

🆕⁴ **`_snapshot_linha(row)` e `_esquecer_edicao(row)` — os dois cuidados extras da remoção otimista:**

```python
def _snapshot_linha(self, row: int) -> dict:
    qtd_txt = self._texto_celula(row, COL_QTD)
    preco_txt = self._texto_celula(row, COL_PRECO_UNIT)
    item_data = self.tabela.item(row, COL_DATA)
    return {
        "id": self._id_da_linha(row),
        "nome": self._texto_celula(row, COL_NOME),  # 🆕⁵
        "data": self._texto_celula(row, COL_DATA),
        "quantidade": qtd_txt,
        "preco_unitario": preco_txt,
        "preco_total": parse_numero(qtd_txt) * parse_numero(preco_txt),
        "_editada": item_data is not None and id(item_data) in self._itens_editados,
    }
```

Antes de remover a linha da tela, `_snapshot_linha` guarda tudo que é preciso pra restaurá-la caso a remoção falhe — inclusive `preco_total` (a primeira versão não guardava isso, e a linha restaurada aparecia com "R$ 0,00" no Total até o usuário editar de novo) e uma flag interna `_editada`, que lembra se essa linha tinha uma edição pendente de salvar. Se a remoção falhar e a linha voltar, `_on_remocao_concluida` usa essa flag pra também restaurar a marca de "editada" (`self._itens_editados`) — sem isso, uma edição feita antes de tentar remover a linha seria silenciosamente esquecida (o próximo Salvar não a reenviaria).

```python
def _esquecer_edicao(self, row: int):
    item_data = self.tabela.item(row, COL_DATA)
    if item_data is not None:
        self._itens_editados.discard(id(item_data))
```

Chamada logo antes de toda remoção (com ou sem confirmação de rede). O rastreamento de "linha editada" (ver "Salvar", abaixo) guarda o `id()` do objeto Python do item da coluna Data — o endereço de memória dele. Quando um item é destruído (por exemplo, ao remover a linha), o Python pode **reciclar** aquele mesmo endereço depois, pra um item completamente diferente. Sem esse "esquecimento" prévio, uma linha nunca tocada pelo usuário podia acabar marcada como "editada" por coincidência, e ser reenviada ao Sheets à toa no próximo Salvar.

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

1. Recusa começar se `_operacao_em_andamento` ou `_remocoes_em_andamento > 0` (🆕⁴ — uma remoção em andamento pode deslocar os números de linha que este salvamento está prestes a usar).
2. Percorre todas as linhas da tabela, ignorando qualquer uma com quantidade ou preço inválido/zerado (linhas em branco não são enviadas).
3. Para cada linha válida **e ou nova ou marcada como editada** (`self._itens_editados` — ver abaixo), monta um dicionário `registro` com `nome` 🆕⁵, `data`, `quantidade`, `preco_unitario`, `preco_total`.
4. Se a linha já tiver um ID (via `_id_da_linha`), ela é uma **atualização** → vai para a lista `existentes`. Senão, gera um novo ID (`gerar_id`), adiciona `empresa`/`produto` ao registro (necessário para o Sheets saber onde inserir) e vai para a lista `novas`. Também guarda, em `linhas_por_id_novo`, qual linha da tabela corresponde a cada novo ID, e em `itens_enviados` o `id()` de cada linha realmente incluída no envio.
5. Se não houver nada pra enviar, apenas avisa e para.
6. Caso contrário, dispara `_disparar_worker(sheets_salvar, novas, existentes, ...)`.
7. Quando termina, `_on_salvamento_concluido` primeiro verifica `self._destruida` 🆕 e, se a página ainda estiver viva, grava o ID de cada linha nova de volta no `UserRole` dela (usando o mapa `linhas_por_id_novo`) — assim, se o usuário salvar de novo sem recarregar, essas linhas já são reconhecidas como "existentes" em vez de criar duplicatas.

### `_itens_editados` — só reenvia o que realmente mudou

```python
if id_linha and id(item_data) not in self._itens_editados:
    continue  # já está salva e não foi tocada — não reenvia à toa
```

`self._itens_editados` é um `set` com o `id()` (endereço de memória do objeto Python) do item da coluna Data de cada linha que o **usuário** editou desde o último carregamento/salvamento (marcado em `_on_item_changed`, sempre que `_carregando` não estiver ativo). Sem isso, todo clique em Salvar reenviaria **todas** as compras já salvas daquele produto, mesmo as que não mudaram — desperdiçando chamadas ao Apps Script (e tempo) à toa. Linhas novas (sem ID) sempre são enviadas, independente dessa marca.

🆕⁴ **Como o resultado do envio afeta `_itens_editados` (`_on_salvamento_concluido`):**

```python
if ids_nao_encontrados:
    ...
    self._itens_editados -= (itens_enviados - itens_com_problema)
    self._alteracoes_nao_salvas = bool(self._itens_editados)
    ...
else:
    self._itens_editados -= itens_enviados
    self._alteracoes_nao_salvas = bool(self._itens_editados)
    ...
```

A primeira versão desse recurso, ao salvar com sucesso, simplesmente zerava `self._itens_editados` por inteiro (`= set()`). Isso tinha um problema: como a tabela continua editável enquanto um Salvar está em andamento (só os botões ficam desabilitados), uma edição feita **durante** esse tempo tinha sua marca apagada junto — e o próximo Salvar a ignorava, achando que já estava tudo em dia, perdendo a edição em silêncio. A correção troca a limpeza total por uma **subtração**: só os `itens_enviados` (as linhas que realmente fizeram parte deste envio) saem do conjunto; qualquer edição concorrente, feita numa linha diferente enquanto o envio acontecia, continua marcada.

Além disso, se o Apps Script devolver `idsNaoEncontrados` (ver acima e [Seção 14](#14-backend-apps-script-apps_script_backendgs-)) — linhas "existentes" que não foram achadas na planilha e por isso não foram atualizadas — essas linhas específicas **continuam** marcadas como editadas (não somem do `_itens_editados`), `_alteracoes_nao_salvas` volta a `True`, e um aviso (`QMessageBox.warning` + status vermelho) avisa quantas linhas ficaram pendentes, em vez do app assumir silenciosamente que tudo foi salvo.

### Recarregar do Sheets (`_recarregar_do_sheets` → `_on_recarregamento_concluido`)

Busca de novo todos os registros da empresa e filtra só os do produto atual (`linha.get("produto") == self.produto`), repopulando a tabela do zero — útil se outra pessoa alterou a planilha por fora do app. Assim como `_salvar`, 🆕⁴ recusa começar se `_operacao_em_andamento` ou `_remocoes_em_andamento > 0` (repopular a tabela do zero enquanto uma remoção ainda não confirmou bagunçaria as premissas dela). `_on_recarregamento_concluido` também **verifica `self._destruida` 🆕** antes de tocar em qualquer widget.

---

## 9. Página 2 — Lista de produtos (`ProductListPage`)

Mostra todos os produtos de uma empresa, com a data e o valor da última compra de cada um.

### Estado interno

```python
self._linhas_por_produto = {}   # nome do produto -> lista de linhas da planilha
self._produtos_pendentes = []   # produtos criados nesta sessão, sem compra salva ainda
self._workers_ativos = []       # 🆕⁴ ver _disparar_worker na Seção 8
self._remocoes_em_andamento = 0  # 🆕⁴ ver _disparar_worker na Seção 8
self._ordem_crescente = True    # A-Z ou Z-A
self._texto_pesquisa = ""
self._geracao_carregamento = 0  # usado pelo watchdog de timeout (ver abaixo)
```

🆕⁴ Essa página tem sua própria cópia de `_disparar_worker` (idêntica à de `ProductEntriesPage`, ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage)) — mesma lógica de manter uma referência forte a cada `SheetsWorker` em `_workers_ativos` até ele terminar, evitando que uma segunda chamada (por exemplo, remover dois produtos rapidamente) sobrescreva a referência à primeira `QThread` ainda rodando.

`_produtos_pendentes` existe porque, quando o usuário cria um produto novo pelo botão "Adicionar novo item", esse produto **ainda não existe na planilha** (só passa a existir quando a primeira compra é salva). Enquanto isso, ele fica "pendurado" nessa lista, só para continuar aparecendo na tabela.

### 🆕 Carregar com cache primeiro, rede depois (`recarregar`)

```python
def recarregar(self):
    if self._operacao_em_andamento or self._remocoes_em_andamento > 0:
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
    self._disparar_worker(sheets_buscar, self.empresa["nome"], ao_concluir=self._on_carregamento_concluido)
    ...
```

🆕⁴ O guard `_remocoes_em_andamento > 0` evita repopular a tabela do zero enquanto uma remoção de produto ainda não confirmou — se a busca ao Sheets ainda trouxer o produto que está sendo removido (porque o cache de 60s do backend ainda não expirou, por exemplo), ele reapareceria na tela até a remoção terminar e escondê-lo de novo, um estado confuso que esse guard evita simplesmente adiando o recarregamento.

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

### 🆕⁵ Importar nota fiscal e configurar a IA

A barra de botões dessa página ganhou três botões ligados à leitura de notas por IA:

- **`📷 Importar nota fiscal`** (`_importar_de_foto`) — chama `_garantir_ia_configurada()` (se ainda não há chave da API, oferece abrir o diálogo de configuração), abre um `QFileDialog` pra escolher a foto, e dispara `ler_nota_fiscal_ia` num `SheetsWorker` (ver [Seção 17](#17-leitura-de-nota-fiscal-com-ia--foto-e-link-)). O resultado cai em `_on_leitura_ia`.
- **`🔗 Importar por link`** (`_importar_por_link`) — mesma ideia, mas pede o endereço do QR code da NFC-e num `QInputDialog` e dispara `ler_nota_fiscal_link`.
- **`⚙️ Configurar`** (`_configurar_ia`) — abre o `ConfigDialog` (ver [Seção 18](#18-diálogo-configdialog-)).

`_on_leitura_ia(sucesso, resultado, origem)` é o callback comum das duas importações. Em caso de erro, mostra um `QMessageBox.critical`. Em caso de sucesso, monta a lista de pastas (produtos) já existentes daquela empresa e chama `abrir_importar_foto_callback` — que a `MainWindow` liga à criação de uma `ImportarNotaFiscalPage` (ver [Seção 19](#19-página-de-conferência-importarnotafiscalpage-)). Se a IA não reconheceu nenhum item, um aviso explica que dá pra abrir a tela de conferência mesmo assim e digitar os itens na mão. `origem` é o caminho da imagem (ou `""` quando veio de link), usado pela página de conferência pra decidir se mostra a foto ou um aviso.

`_definir_ocupado` dessa página desabilita também os três botões acima enquanto uma leitura está em andamento.

### Adicionar e remover produtos

- **`_adicionar_produto`**: abre um `QInputDialog` pedindo o nome, valida que não é vazio nem duplicado, e adiciona à lista `_produtos_pendentes`. 🆕² Em seguida chama `self._abrir_produto(nome)` — o produto recém-criado é aberto na hora, direto na tela de compras, sem o usuário precisar localizá-lo na lista (que pode estar ordenada ou filtrada de um jeito que o esconda).
- **`_remover_produto`**: se o produto **não tem nenhum ID** (é só "pendente", nunca foi salvo), remove localmente sem chamar o Sheets. Se **tem IDs**, pede confirmação e faz uma **remoção otimista**: o produto some da lista (`self._linhas_por_produto.pop(...)` + `_reconstruir_tabela()`) **antes** da rede confirmar, e só então `_disparar_worker` dispara `sheets_remover` com todos os IDs daquele produto de uma vez. 🆕⁴ `self._remocoes_em_andamento` é incrementado antes de disparar e decrementado no início de `_on_remocao_produto_concluida` — usado por `recarregar()` (ver abaixo) pra saber que uma remoção ainda não confirmou. Se a remoção falhar, o produto (com as linhas originais) volta pra `_linhas_por_produto` e a tabela é reconstruída de novo.

---

## 10. Página 1 — Seleção de empresa (`CompanySelectPage`)

A tela mais simples: para cada empresa em `COMPANIES`, cria um "card" vertical com o avatar circular (via `criar_avatar_circular`) e um botão colorido com o nome da empresa, que ao ser clicado chama `escolher_callback(empresa)`.

🆕⁵ Se `sheets_webhook_url()` vier vazia (nada configurado), mostra um aviso vermelho no topo orientando a abrir uma empresa e clicar em "⚙️ Configurar" — em vez de o usuário só descobrir isso depois, ao tentar abrir uma empresa e receber um erro confuso.

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

## 13. Ponto de entrada (`main`) e tema escuro

```python
def main():
    migrar_cache_antigo()                        # 🆕⁶
    app = QApplication(sys.argv)
    app.setApplicationName("Controle de Empresas")  # 🆕⁶
    app.setStyle("Fusion")
    aplicar_tema_escuro(app)   # 🆕⁵
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- 🆕⁶ `migrar_cache_antigo()` move o cache da pasta antiga (`<script>/cache`) pra nova pasta por-usuário, uma vez (ver [Seção 5](#5-cache-local-em-disco-)).
- `QApplication(sys.argv)` inicializa o motor do Qt — é obrigatório existir exatamente uma instância dessa classe antes de criar qualquer widget. 🆕⁶ `setApplicationName` dá um nome ao app que o Qt usa nos títulos de diálogos nativos (abrir arquivo, etc.).
- `app.setStyle("Fusion")` aplica um tema visual consistente entre Windows e Linux (em vez do estilo nativo de cada sistema operacional, que varia bastante).
- 🆕⁵ `aplicar_tema_escuro(app)` monta um `QPalette` escuro fixo (janela, base das tabelas, texto, botões, seleção, além das cores do grupo `Disabled`) e aplica com `app.setPalette(...)`. O objetivo é o app ficar **sempre** com o mesmo visual escuro, independente do tema (claro/escuro) do sistema ou do ambiente onde for executado — antes, num sistema em tema claro, os campos ficavam com texto claro sobre fundo claro em alguns lugares. As cores de destaque de cada empresa (cabeçalhos de tabela, botões primários) continuam vindo de `COMPANIES`, por cima dessa paleta.
- `janela.show()` exibe a `MainWindow` (que por sua vez mostra a `CompanySelectPage`, a primeira tela do `QStackedWidget`).
- `app.exec()` inicia o **loop de eventos** do Qt — é essa chamada que mantém o app "vivo", escutando cliques, digitação e os sinais dos `SheetsWorker`, até a janela ser fechada. `sys.exit(...)` garante que o código de saída do processo reflita como o Qt encerrou.

---

## 14. Backend Apps Script (`apps_script_backend.gs`) 🆕

Esse arquivo roda **dentro do Google**, ligado à planilha (Extensões → Apps Script), e é o único ponto de contato entre o Python e os dados. Ele expõe duas "rotas" HTTP: `doGet` (ler) e `doPost` (salvar/remover).

### Estrutura da planilha

```
ID | Empresa | Produto | Nome | Data | Quantidade | Preço Unitário | Preço Total
```

🆕 O array `CABECALHO` foi corrigido para refletir as colunas de verdade — uma versão antiga listava só 5 nomes, o que não batia com o que era realmente gravado.

🆕⁵ A coluna **Nome** (posição 4, logo depois de "Produto") foi adicionada: "Produto" é a **pasta/tipo** (ex: "Aveia Flocos") e "Nome" é o texto da **marca/embalagem daquela compra** (ex: "Aveia Flocos Marca X") — ver [Seção 15](#15-campo-nome-por-compra-). `NUM_COLUNAS` passou a ser 8. Planilhas criadas antes dessa coluna são migradas sozinhas por `garantirColunaNome` (abaixo).

### 🆕⁵ `garantirColunaNome(planilha)` — migração automática da coluna Nome

```javascript
function garantirColunaNome(planilha) {
  var props = PropertiesService.getScriptProperties();
  var chave = "COLUNA_NOME_ADICIONADA_" + planilha.getSheetId();
  if (props.getProperty(chave) === "1") return;

  var larguraCabecalho = Math.max(planilha.getLastColumn(), 1);
  var cabecalhoAtual = planilha.getRange(1, 1, 1, larguraCabecalho).getValues()[0];
  if (cabecalhoAtual.indexOf("Nome") === -1) {
    planilha.insertColumnBefore(4);       // coluna D: antes da antiga "Data"
    planilha.getRange(1, 4).setValue("Nome");
    props.deleteProperty("FORMATO_TEXTO_APLICADO_" + planilha.getSheetId());
  }
  props.setProperty(chave, "1");
}
```

Chamada dentro de `getPlanilha()`, antes de `garantirFormatoTexto`. Planilhas antigas têm o cabeçalho `ID | Empresa | Produto | Data | ...` (sem "Nome"). A função detecta isso (`indexOf("Nome") === -1`) e usa `insertColumnBefore(4)` pra abrir uma coluna vazia na posição D, empurrando Data/Quantidade/Preço Unitário/Preço Total uma coluna pra direita **sem perder nenhum dado** (o `insertColumnBefore` desloca o conteúdo das células, não apaga). Como a coluna Data saiu de D pra E, a função também apaga a Script Property `FORMATO_TEXTO_APLICADO_...` pra `garantirFormatoTexto` rodar de novo e reaplicar o formato de texto puro na coluna certa. Roda uma única vez por aba (controlada pela Script Property `COLUNA_NOME_ADICIONADA_<sheetId>`).

### 🆕⁴ `getPlanilha()` — presa numa aba fixa, não na aba "ativa"

```javascript
function getPlanilha() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var props = PropertiesService.getScriptProperties();
  var idAbaFixada = props.getProperty("ID_ABA_DADOS");

  var planilha = null;
  if (idAbaFixada) {
    var idNumerico = Number(idAbaFixada);
    var abas = ss.getSheets();
    for (var i = 0; i < abas.length; i++) {
      if (abas[i].getSheetId() === idNumerico) { planilha = abas[i]; break; }
    }
  }

  if (!planilha) {
    planilha = ss.getActiveSheet();
    props.setProperty("ID_ABA_DADOS", String(planilha.getSheetId()));
  }

  if (planilha.getLastRow() === 0) {
    planilha.appendRow(CABECALHO);
  }
  garantirColunaNome(planilha);   // 🆕⁵ migra planilhas antigas (ver acima)
  garantirFormatoTexto(planilha);
  return planilha;
}
```

**O bug:** a versão anterior usava `SpreadsheetApp.getActiveSpreadsheet().getActiveSheet()` — "a aba que estiver aberta no navegador nesse momento". Se a planilha tivesse mais de uma aba (por exemplo, uma aba de resumo além da de dados) e alguém clicasse na outra aba, a próxima leitura/escrita do app acontecia **na aba errada**, sem nenhum erro aparecer — os dados "sumiam" ou eram gravados no lugar errado.

**A correção:** na primeira execução, `getPlanilha()` guarda o `getSheetId()` da aba usada (um número interno que não muda mesmo que a aba seja renomeada) numa **Script Property** (`ID_ABA_DADOS` — configuração que persiste entre execuções do Apps Script, independente da planilha). Nas próximas vezes, ele procura a aba com esse ID entre todas as abas da planilha, ignorando qual estiver "ativa" no navegador. Pra apontar pra uma aba diferente no futuro, basta apagar essa Script Property em *Configurações do projeto → Propriedades do script* — a próxima execução vai fixar de novo, na aba que estiver ativa naquele momento.

### 🆕⁴ `garantirFormatoTexto(planilha)` — corrige a raiz de dois bugs de conversão automática

```javascript
function garantirFormatoTexto(planilha) {
  var props = PropertiesService.getScriptProperties();
  var chave = "FORMATO_TEXTO_APLICADO_" + planilha.getSheetId();
  if (props.getProperty(chave) === "1") return;
  planilha.getRange("A:A").setNumberFormat("@"); // ID
  planilha.getRange("E:E").setNumberFormat("@"); // 🆕⁵ Data (era D; virou E com a coluna "Nome")
  props.setProperty(chave, "1");
}
```

O Google Sheets "adivinha" o tipo de uma célula pelo que parece ter sido digitado nela — mesmo quando o valor chega via API (`setValues()`), não digitado por uma pessoa. Isso causava dois bugs:

- Um **ID** gerado por `gerar_id()` (hexadecimal: `0-9` e `a-f`) que, por acaso, só tivesse dígitos (ex: `"012345678901"`) podia ser convertido pro **número** `12345678901` — perdendo o zero à esquerda. Da próxima vez que o app tentasse editar/remover essa linha usando o ID original (com o zero), a busca no índice (`construirIndiceIds`) nunca batia, e a operação era silenciosamente ignorada.
- Uma **Data** enviada como texto (`"10/08/2026"`) podia virar uma data de verdade — o que trazia o bug de fuso horário explicado logo abaixo.

A correção formata as colunas **A** (ID) e **E** (Data — 🆕⁵ era a **D** antes da coluna "Nome" existir) como **texto puro** (`"@"`) assim que a aba é preparada, então o Sheets nunca mais tenta "converter" nada escrito nelas — o texto exato que o app manda é o texto exato que fica gravado. Roda só uma vez por aba (controlado por outra Script Property), então não pesa nas chamadas seguintes.

### 🆕⁴ `normalizarDataLida(valor)` — corrige mesmo linhas já convertidas antes dessa correção

```javascript
function normalizarDataLida(valor) {
  if (Object.prototype.toString.call(valor) === "[object Date]") {
    var fuso = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
    return Utilities.formatDate(valor, fuso, "dd/MM/yyyy");
  }
  return valor;
}
```

Formatar a coluna como texto (acima) evita que **novas** datas sejam convertidas, mas não desfaz o que já tinha sido convertido **antes** dessa correção existir — uma célula que já é um objeto `Date` de verdade continua sendo um `Date`, format de coluna ou não. Se `lerTodasLinhasDaPlanilha` simplesmente devolvesse esse `Date` pro JSON, o `JSON.stringify()` do JavaScript chama `toISOString()` nele — que é **sempre em UTC**. Numa planilha configurada num fuso à frente de UTC (comum fora do Brasil), a meia-noite local de `10/08` vira algo como `"2026-08-09T23:00:00.000Z"` — um timestamp do dia **anterior**. O `normalizar_data_sheets` do lado Python (ver [Seção 3](#3-funções-utilitárias)) só pega a parte da data desse texto, então a compra salva como `10/08` reaparecia como `09/08` — silenciosamente, sem nenhum erro.

A correção detecta esse caso (`Object.prototype.toString.call(valor) === "[object Date]"`) e formata a data de volta usando o **fuso horário configurado na própria planilha** (`getSpreadsheetTimeZone()`) — o mesmo fuso que a pessoa vê ao abrir a planilha no navegador — em vez de deixar o JavaScript serializar em UTC. Isso corrige o problema tanto pra linhas antigas (já convertidas) quanto serve de rede de segurança pra qualquer célula que escape da formatação de texto por algum motivo (por exemplo, editada manualmente por uma pessoa direto na planilha).

### `lerTodasLinhasDaPlanilha()`

Lê a planilha inteira **de uma vez** (`getDataRange().getValues()`) e converte cada linha num objeto JS `{id, empresa, produto, nome, data, quantidade, preco_unitario, preco_total}` 🆕⁵ (o campo `nome` vem de `linha[3]`, e `data`/`quantidade`/`preco_unitario`/`preco_total` passaram de `linha[3..6]` pra `linha[4..7]`), pulando linhas sem ID (vazias). 🆕⁴ `id` agora sempre passa por `String(...)` (nunca deixa um ID todo numérico virar `Number` na resposta) e `data` passa por `normalizarDataLida` (explicado acima).

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

### 🆕⁴ `doPost(e)` — agora serializado com `LockService`

```javascript
function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (erro) {
    return responder({ ok: false, erro: "Servidor ocupado, tente novamente em instantes." });
  }
  try {
    var planilha = getPlanilha();
    ...
  } catch (erro) {
    return responder({ ok: false, erro: String(erro) });
  } finally {
    lock.releaseLock();
  }
}
```

**O bug:** nada impedia duas execuções do `doPost` (duas chamadas simultâneas do app, ou do app + de outra aba/dispositivo) de rodar ao mesmo tempo. Cada uma constrói seu próprio índice de linhas (`construirIndiceIds`) no início — se uma delas remover linhas (deslocando tudo que vem depois pra cima) enquanto a outra ainda está usando um índice construído **antes** dessa remoção, a segunda `setValues()` acaba caindo numa linha deslocada, sobrescrevendo os dados de um registro errado.

**A correção:** `LockService.getScriptLock()` garante que só uma execução do `doPost` mexa na planilha por vez — as outras esperam (até 10s) a vez delas, em vez de rodar em paralelo e disputar os mesmos números de linha. `doGet` (só leitura) não usa lock, pra não deixar as buscas mais lentas à toa.

### `salvarRegistros` / `removerRegistros`

```javascript
function salvarRegistros(planilha, novas, existentes) {
  if (novas.length > 0) {
    var linhaInicial = planilha.getLastRow() + 1;
    var dados = novas.map(function (l) {
      return [l.id, l.empresa, l.produto, l.nome, l.data, l.quantidade, l.preco_unitario, l.preco_total];  // 🆕⁵ l.nome
    });
    planilha.getRange(linhaInicial, 1, dados.length, NUM_COLUNAS).setValues(dados);
  }

  if (existentes.length === 0) return { idsNaoEncontrados: [] };

  var indice = construirIndiceIds(planilha);
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

  // ... grava linhasAlvo (1 chamada se for só uma linha, ou um bloco de
  // leitura+escrita se forem várias — ver otimização de desempenho abaixo)

  return { idsNaoEncontrados: idsNaoEncontrados };
}
```

🆕 As linhas **novas** deixaram de ser gravadas com um `appendRow()` por linha (cada um sendo uma chamada separada à API do Sheets) e passaram a ser gravadas todas de uma vez, com um único `setValues()` numa faixa de células contígua começando logo após a última linha usada.

🆕⁴ **`idsNaoEncontrados` — parar de descartar edições em silêncio.** Antes, um `existentes.map(...).filter(...)` simplesmente **descartava** qualquer linha cujo ID não estivesse no índice (por exemplo, apagada por outra sessão entre o usuário editar e clicar Salvar) — e `doPost` respondia `{ ok: true }` do mesmo jeito, como se tudo tivesse sido salvo. Agora `salvarRegistros` separa esses casos em `idsNaoEncontrados` e devolve essa lista; `doPost` repassa ela na resposta (`{ ok: true, idsNaoEncontrados: [...] }`), e o Python (`ProductEntriesPage._on_salvamento_concluido`, ver [Seção 8](#8-página-3--compras-de-um-produto-producteentriespage)) usa essa informação pra manter essas linhas específicas marcadas como pendentes, em vez de assumir que está tudo salvo.

Pra **várias** linhas existentes editadas na mesma chamada, em vez de uma `setValues()` por linha, o código lê o bloco do menor ao maior número de linha de uma vez, atualiza só as linhas alvo em memória, e grava tudo de volta com um único `setValues()` — trocamos ler/escrever algumas células a mais (as linhas do meio que não mudaram) por bem menos chamadas à planilha, que é o que realmente pesa no tempo de resposta. Pra uma linha só (o caso mais comum), grava direto, sem essa leitura extra. 🆕⁵ Em ambos os casos, o intervalo escrito começa na coluna 4 e agora tem **5 colunas** (`Nome`, `Data`, `Quantidade`, `Preço Unitário`, `Preço Total`) — era 4 antes da coluna "Nome".

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

  // agrupa linhas vizinhas num único deleteRows(), em vez de um deleteRow()
  // por linha
  var i = 0;
  while (i < linhasParaRemover.length) {
    var fimBloco = linhasParaRemover[i];
    var tamanhoBloco = 1;
    while (i + tamanhoBloco < linhasParaRemover.length &&
           linhasParaRemover[i + tamanhoBloco] === fimBloco - tamanhoBloco) {
      tamanhoBloco++;
    }
    planilha.deleteRows(fimBloco - tamanhoBloco + 1, tamanhoBloco);
    i += tamanhoBloco;
  }
  return linhasParaRemover.length;
}
```

Mesma lógica de índice único, mas com um cuidado a mais: linhas **vizinhas** na planilha (números consecutivos, comum quando um produto teve todas as suas compras salvas de uma vez) são agrupadas num único `deleteRows(inicio, quantidade)`, em vez de um `deleteRow()` por linha — menos chamadas à planilha quando é possível, sem mudar o resultado (a remoção continua acontecendo de baixo para cima, pra não bagunçar os índices das linhas seguintes).

### 🆕⁵ `renomearProdutos(planilha, itens)` — ação `"renomearProdutos"` do `doPost`

```javascript
function renomearProdutos(planilha, itens) {
  var idsNaoEncontrados = [];
  if (!itens.length) return { idsNaoEncontrados: idsNaoEncontrados };

  var indice = construirIndiceIds(planilha); // uma única leitura, não uma por item
  itens.forEach(function (item) {
    var linha = indice[String(item.id)];
    if (!linha) { idsNaoEncontrados.push(item.id); return; }
    if (item.produto !== undefined) planilha.getRange(linha, 3).setValue(item.produto);
    if (item.nome !== undefined)    planilha.getRange(linha, 4).setValue(item.nome);
  });
  return { idsNaoEncontrados: idsNaoEncontrados };
}
```

Renomeia, por ID, a **pasta** (coluna 3, "Produto") e/ou o **nome** (coluna 4, "Nome") de linhas já salvas — só a coluna informada em cada item é sobrescrita. Serve pra consolidar produtos parecidos que viraram pastas separadas por engano (ex: "Vinho pergola" e "Vinho randon" → pasta "Vinho", com a marca guardada no Nome de cada linha). Usa `construirIndiceIds` uma vez só, como as outras operações de escrita. `doPost` trata a ação `"renomearProdutos"`, chama `invalidarCache()` e responde `{ ok: true, idsNaoEncontrados: [...] }`.

> ⚠️ **Estado atual:** o backend implementa isso por completo, e há a função `sheets_renomear_produtos` no Python (Seção 4), **mas nenhuma tela do app chama essa função** — a "ferramenta de mesclagem/migração" mencionada ainda não foi construída na interface. Ver as notas de análise no final da revisão.

Por fim, `doPost` chama `invalidarCache()` depois de qualquer `salvar`, `remover` ou `renomearProdutos` bem-sucedido, garantindo que a próxima leitura (`doGet`) já reflita os dados novos, em vez de servir uma versão em cache desatualizada.

---

## 15. Campo Nome por compra 🆕⁵

Antes, um "produto" era uma coisa só: a pasta **e** o nome da compra eram o mesmo texto. Isso obrigava a criar uma pasta separada pra cada marca ("Vinho Pergola", "Vinho Randon", "Vinho Miolo"...), poluindo a lista.

Agora há dois níveis:

| Conceito | Onde mora | Exemplo |
|---|---|---|
| **Pasta / tipo de produto** | coluna "Produto" no Sheets; chave de `_linhas_por_produto`; título das telas | `Aveia Flocos` |
| **Nome da compra** | 🆕⁵ coluna "Nome" no Sheets; `COL_NOME` na tabela de compras | `Aveia Flocos Marca X 500g` |

Cada linha da tabela de compras (`ProductEntriesPage`) tem seu próprio Nome, editável como qualquer outra célula. `_adicionar_linha` cria o `QTableWidgetItem` da coluna `COL_NOME`; `_snapshot_linha`, `_salvar` e o backend (`salvarRegistros`, `lerTodasLinhasDaPlanilha`) carregam o campo `nome` junto com data/quantidade/preço. A navegação por Enter começa em Nome (ver [Seção 7](#7-mini-gráfico-de-tendência-de-preço)). Quem só quer registrar uma compra rápida pode deixar o Nome em branco — ele não é obrigatório pra salvar (só pasta, quantidade e preço são).

O ID da linha na planilha continua guardado no `UserRole` do item da **coluna Data** — como Data virou a coluna 1 (era a 0), toda referência a essa identidade no código usa a constante `COL_DATA`, então a mudança de índice foi transparente.

---

## 16. Configuração e segredos em disco (`config.json`) 🆕⁵

A leitura de notas por IA precisa de uma **chave da API do Google Gemini**, que é um segredo — não pode ficar no código nem no git. Ela vive em `~/.config/controle_empresas/config.json`, com estas funções cuidando do arquivo:

### `carregar_config()` / `salvar_config(dados)`

```python
def carregar_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def salvar_config(dados: dict) -> None:      # 🆕⁷ escrita atômica + 0600 desde o os.open
    os.makedirs(CONFIG_DIR, exist_ok=True)
    temporario = CONFIG_PATH + ".tmp"
    fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    os.replace(temporario, CONFIG_PATH)      # troca atômica
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
```

- `carregar_config` nunca levanta exceção: se o arquivo não existe, está corrompido ou é um JSON que não é objeto, devolve `{}` — nesse caso o app abre mas não carrega nenhuma empresa até a URL da planilha ser configurada. Pode ser chamada de várias threads (a leitura da nota roda num `SheetsWorker`).
- 🆕⁷ `salvar_config` grava **num arquivo temporário e faz `os.replace`** (troca atômica): um `carregar_config` concorrente vê a versão antiga inteira ou a nova inteira, nunca um JSON truncado. O arquivo já nasce com `os.open(..., 0o600)` — antes havia uma janela entre criar com o umask (tipicamente `644`) e o `chmod` posterior. Em sistemas de arquivos sem permissões POSIX (pen drive) o `chmod` falha silenciosamente e o app segue.

Chaves gravadas no `config.json`: `sheets_webhook_url`, `gemini_api_key`, `gemini_modelo`.

### `sheets_webhook_url()` / `ia_api_key()` / `ia_modelo()`

```python
def sheets_webhook_url() -> str:   # 🆕⁵
    return (os.environ.get("GOOGLE_SHEETS_WEBHOOK_URL")
            or carregar_config().get("sheets_webhook_url") or "").strip()

def ia_api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or carregar_config().get("gemini_api_key") or "").strip()

def ia_modelo() -> str:
    return (carregar_config().get("gemini_modelo") or "").strip() or MODELO_IA_PADRAO
```

Os dois "resolvedores" de segredo seguem o mesmo padrão: **variável de ambiente primeiro** (`GOOGLE_SHEETS_WEBHOOK_URL` / `GEMINI_API_KEY` — útil pra CI, contêiner, ou pra quem não quer gravar nada em disco), `config.json` depois, e `""` se não houver nenhum. `ia_modelo` usa o modelo salvo, ou `MODELO_IA_PADRAO` (`"gemini-2.5-flash"`) se nada estiver configurado.

🆕⁵ `sheets_webhook_url()` substituiu a antiga constante `GOOGLE_SHEETS_WEBHOOK_URL` hardcoded no topo do arquivo — que é um segredo (dá acesso total à planilha) e não pode ficar no código nem no git.

---

## 17. Leitura de nota fiscal com IA — foto e link 🆕⁵

Esse bloco substituiu por completo o antigo OCR local (Tesseract + numpy + regex). Agora a imagem — ou o texto da página da SEFAZ — vai direto pra **API do Google Gemini**, que devolve os itens já estruturados. Roda sempre dentro de um `SheetsWorker` (thread), então a interface não trava.

### `ErroIA`

Exceção única de todo esse bloco (chave ausente/recusada, rede fora, modelo inexistente, limite de uso, resposta inesperada). O `SheetsWorker` captura `ErroIA` junto com `ErroSheets` (ver [Seção 4](#4-integração-com-o-google-sheets)).

### `_ia_requisitar(url, dados, timeout, api_key)`

O "cliente HTTP" do Gemini: `POST` (quando há `dados`) ou `GET`, com a chave no cabeçalho `x-goog-api-key`. Traduz cada falha pra uma `ErroIA` com mensagem em português:

| HTTP | Mensagem |
|---|---|
| 401 / 403 / "api key" no corpo | "A chave da API foi recusada pelo Google… Confira em '⚙️ Configurar'." |
| 404 | "O modelo '…' não existe ou não está liberado pra sua chave." |
| 429 | "Limite de uso da API do Gemini atingido. Espere alguns minutos…" |
| outros | "O Google respondeu com erro HTTP …" |

O parâmetro `api_key` permite **testar uma chave que ainda não foi salva** (usado pelo `ConfigDialog` ao clicar em "Buscar modelos").

### `ler_nota_fiscal_ia(caminho_imagem)`

Valida que há chave configurada, lê os bytes da imagem, recusa arquivo vazio ou acima de ~18 MB (`_IA_LIMITE_IMAGEM` — a API aceita ~20 MB contando o base64), descobre o MIME pela extensão (`_IA_MIMES`; cai em `image/jpeg` se não reconhecer) e chama `_ia_gerar_itens` com duas partes: a imagem em base64 (`inline_data`) e o prompt `_IA_PROMPT_NOTA`.

### `ler_nota_fiscal_link(url)`

Para NFC-e: a nota traz um QR code que aponta pra página oficial de consulta da SEFAZ, com **todos os itens e preços exatos** — mais confiável que ler a foto. A função:

1. valida que a URL começa com `http://`/`https://` e **recusa endereços de rede interna** (`_recusar_host_interno`: `localhost`, `.local`, e IPs de loopback / privados / link-local / reservados) — 🆕⁷ o link é digitado pelo usuário e o fetch acontece na máquina dele, então isso barra um link colado por engano que faria o app sondar a rede local. *(Não cobre DNS rebinding — um domínio que resolve pra IP interno; pra um app local de um usuário só, o risco disso é baixo.)*
2. baixa a página com um `User-Agent` de navegador (alguns portais bloqueiam clientes "estranhos"), lendo no máximo 4 MB;
3. reduz o HTML a texto puro com `_texto_de_html` (tira `<script>`/`<style>`/`<noscript>`, remove todas as tags, desescapa entidades, colapsa espaços);
4. se o texto vier muito curto **e** contiver palavras de tela de CAPTCHA/"não sou um robô"/"habilite o javascript", levanta `ErroIA` explicando que aquele estado (Santa Catarina, por exemplo) protege a consulta com um desafio que o app não passa — e que a saída é a importação por foto;
5. corta o texto em 60,000 caracteres e chama `_ia_gerar_itens` com o prompt `_IA_PROMPT_LINK` + o texto.

### `_ia_gerar_itens(parts)` — a chamada, com fallback de modelo

Monta o corpo com `responseMimeType: "application/json"`, `responseSchema: _IA_SCHEMA_NOTA` (força o formato `{itens: [{nome, data, quantidade, preco_unitario}]}`) e `temperature: 0`. Chama `_ia_requisitar` no modelo configurado.

🆕⁵ **Se a chamada falhar com "modelo não existe" (404)** — o Google desligou o modelo, ou o `MODELO_IA_PADRAO` embutido ficou velho — `_ia_descobrir_modelo()` acha um Flash válido na conta, grava no `config.json` e a chamada é refeita **uma vez**, com o modelo novo. Qualquer outro erro (rede, 429, 500) é repassado sem mexer no config — a checagem de "não existe" acontece **antes** de `_ia_descobrir_modelo` para um limite de uso passageiro não trocar a escolha de modelo do usuário à toa (bug corrigido nesta revisão).

### `_ia_descobrir_modelo()`

Chama `listar_modelos_ia()`, escolhe o primeiro nome que tenha `flash` e não tenha `lite`/`image`/`thinking` (ou qualquer `flash`, ou o primeiro modelo da lista como último recurso), grava em `config["gemini_modelo"]` e devolve o nome. Devolve `""` se a listagem também falhar.

### `_ia_itens_da_resposta(dados)`

Extrai o JSON de dentro da resposta do Gemini, com mensagens específicas pra cada modo de falha: nenhum candidato (+ `blockReason` se o conteúdo foi bloqueado), texto vazio com `finishReason == "MAX_TOKENS"` ("a nota tem itens demais pra uma leitura só"), JSON inválido, etc. Para cada item cru, monta um dict com:

- `nome` → `_nome_apresentavel(nome)` (padroniza como frase — ver abaixo);
- `data` → `_ia_normalizar_data(...)` (aceita `dd/mm/aaaa`, `aaaa-mm-dd`, `dd/mm/aa`; devolve sempre `dd/MM/yyyy` ou `""`);
- `quantidade` / `preco_unitario` → `_ia_para_numero(valor, padrao)` (aceita vírgula ou ponto; devolve o padrão se ≤ 0 ou inválido).

Itens sem nome são descartados. No fim, passa a lista por `_consolidar_itens_iguais`.

### `_nome_apresentavel(texto)`

```python
def _nome_apresentavel(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().capitalize()
```

Colapsa espaços e devolve o texto como **frase**: só a primeira letra maiúscula, todo o resto minúsculo. Nota fiscal quase sempre vem em CAIXA ALTA (`ARROZ TIPO 1 5KG`) e a IA às vezes devolve em Title Case (`Arroz Tipo 1 5kg`) — os dois viram `Arroz tipo 1 5kg`, pra a lista não misturar três estilos de capitalização. Efeito colateral aceito: marcas com maiúscula interna (`Coca-Cola`, `iPhone`) também são rebaixadas; o docstring da função marca onde adicionar exceções se algum dia incomodar.

> Histórico: uma versão anterior só corrigia quando o texto era "predominantemente maiúsculo" e deixava o Title Case passar — o que fazia nomes subirem pro Sheets com capitalização inconsistente. Passou a ser incondicional a pedido do usuário.

### `_consolidar_itens_iguais(itens)`

Junta numa linha só os itens da **mesma nota** com nome, preço unitário (arredondado a 2 casas) e data idênticos, **somando a quantidade**. Resolve verduras e carnes vendidas por peso: a nota lista uma linha por pesagem ("4 unidades de brócolis, 5 de repolho"), mas como o preço do quilo é o mesmo, o que interessa é uma linha com o peso total. Preserva a ordem de aparição.

### `sugerir_pasta(nome_lido, pastas_existentes)` e `_palavras_para_comparacao(texto)`

Ao abrir a tela de conferência, cada item lido precisa ir pra uma pasta. `sugerir_pasta` compara as **palavras** do nome lido (minúsculas, sem acento — via `_palavras_para_comparacao`, que usa `unicodedata.normalize("NFKD", ...)`) com as de cada pasta existente. A pontuação é a **fração das palavras da pasta** presentes no nome lido — assim "Aveia Flocos Marca X" cobre 100% da pasta "Aveia Flocos" mas só ~50% de "Aveia Grão". Devolve a melhor pasta se a pontuação for ≥ 0.6, senão `None` (e quem chamou oferece criar uma pasta nova, ou usa o próprio nome lido como sugestão).

### `listar_modelos_ia(api_key=None)`

`GET` em `…/models?pageSize=200`, filtra os que suportam `generateContent`, tira o prefixo `models/` e devolve a lista ordenada. Usado pelo `ConfigDialog` ("Buscar modelos") e por `_ia_descobrir_modelo`.

---

## 18. Diálogo `ConfigDialog` 🆕⁵

`QDialog` modal (aberto pelo botão "⚙️ Configurar" da lista de produtos, e como "porteiro" antes de importar uma nota) pra configurar os segredos e o modelo da IA. Campos:

- **URL da planilha** — `QLineEdit` em modo `Password` + botão 👁 (via o helper `_campo_segredo`). É o endereço do Web App do Apps Script; **obrigatório** — sem ele o app não carrega nenhuma empresa.
- **Chave da API (IA)** — mesmo componente. **Opcional**: só serve pra ler notas fiscais.
- **Modelo** — `QComboBox` editável. O botão **"Buscar modelos"** chama `listar_modelos_ia(api_key=<chave digitada>)` e popula o combo com os modelos que **aquela** chave libera, pré-selecionando um Flash (preferindo um que não seja `lite`/`image`). Essa chamada é síncrona e roda na thread da interface (`QApplication.processEvents()` só atualiza a mensagem "Buscando…"), então a janela fica momentaneamente parada durante a busca — aceitável num diálogo de configuração, mas é uma diferença em relação à leitura de notas, que roda em thread.

`_campo_segredo(valor, placeholder)` é um helper que monta um `QLineEdit` em modo senha + botão 👁 pra revelar — os dois segredos ficam ocultos por padrão.

Ao salvar (`_salvar`): exige pelo menos a URL da planilha; se ela estiver preenchida, valida que casa com `https://script.google.com/.../exec`. Grava `sheets_webhook_url`, `gemini_api_key` e `gemini_modelo` via `salvar_config` (tratando erro de escrita com um `QMessageBox.critical`) e fecha com `accept()`.

`ProductListPage._garantir_ia_configurada()` usa esse diálogo como "porteiro" da importação de notas: se ainda não há chave (`ia_api_key()` vazio), pergunta se o usuário quer configurar agora, abre o `ConfigDialog` e só deixa a importação prosseguir se ao final houver uma chave.

---

## 19. Página de conferência `ImportarNotaFiscalPage` 🆕⁵

Página cheia (mais uma tela do `QStackedWidget`, não uma janela flutuante) pra revisar os itens que a IA leu, **antes** de qualquer coisa ir pro Sheets. Layout em duas colunas:

- **Esquerda** — a foto da nota (quando a importação veio de foto), num `QScrollArea`, pra conferência lado a lado. Quando veio de link, mostra um aviso ("os itens vieram da página oficial da SEFAZ… confira mesmo assim") em vez da imagem. A distinção é `veio_de_foto = bool(self.caminho_imagem) and not QPixmap(self.caminho_imagem).isNull()`.
- **Direita** — uma `QTableWidget` com uma linha por item lido e 5 colunas: **Pasta (produto)**, **Nome**, **Data**, **Quantidade**, **Preço Unitário**. A coluna Pasta é um `QComboBox` editável, já preenchido com a sugestão de `sugerir_pasta` (ou o próprio nome lido); as pastas existentes ficam na lista suspensa, e digitar uma pasta nova cria a pasta na hora ao confirmar.

Botões: **+ Adicionar item** / **- Remover item selecionado** / **✅ Confirmar tudo**.

`_confirmar_tudo()` percorre as linhas, conta as incompletas (sem pasta, ou com quantidade/preço ≤ 0) numa variável `ignoradas`, monta um `registro` por linha válida (com `id` novo, `empresa`, `produto` = a pasta, `nome`, `data`, `quantidade`, `preco_unitario`, `preco_total`) e dispara `sheets_salvar(novas, [])` num `SheetsWorker` (mantido em `self._workers_ativos`, mesmo padrão das outras páginas). Se **todas** as linhas forem inválidas, avisa e não faz nada. 🆕⁵ Se **algumas** forem inválidas, um `QMessageBox.question` diz quantas serão ignoradas e pede confirmação antes de salvar as outras (antes elas eram descartadas em silêncio). Em caso de sucesso, chama `ao_confirmar_callback(len(novas))` — que a `MainWindow` liga a um `QMessageBox` "N itens salvos" seguido de voltar pra lista de produtos (que recarrega e mostra os itens novos).

Segue os mesmos cuidados de ciclo de vida das outras telas: flag `_destruida` / `marcar_destruida()` (checada antes de tocar em widgets num callback de rede atrasado) e `_definir_ocupado` desabilitando os botões, inclusive "← Cancelar", durante o salvamento.

---

## 20. Notas de análise — código morto, bugs e segurança

Levantamento acumulado das revisões 🆕⁵. Nenhum item é um crash garantido do fluxo normal; são pontas soltas, casos de borda e exposição de segredo.

### 🔒 Segurança

- **A URL do Web App do Apps Script estava hardcoded no código — e está no histórico do git.** Ela é uma "URL-capacidade": com o acesso do Web App em "Qualquer pessoa", quem tem a URL lê e escreve na planilha inteira, sem autenticação. Ela foi commitada (`1214db9`) e depois trocada por `""` (`22310eb`), mas **continua nos dois commits**, que já foram enviados pro GitHub (`origin/main`). **Providências:**
  1. Feito: a URL saiu do código (`sheets_webhook_url()`, config.json / variável de ambiente) — commits novos ficam limpos.
  2. **Recomendado: rotacionar a URL.** No editor do Apps Script, crie uma **nova implantação** (gera uma URL nova) e **arquive/exclua a antiga** — isso mata a URL vazada. Depois cole a nova em "⚙️ Configurar".
  3. Opcional: reescrever o histórico (`git filter-repo` + `push --force`) pra apagar a URL dos commits antigos. Só vale a pena junto com o passo 2.
- **A chave da API do Gemini nunca esteve no repositório** — sempre foi lida do `config.json` (permissão `600`) ou da variável de ambiente. OK.
- 🆕⁵ **`.gitignore` versionado** — passou a ser commitado; ignora `cache/`, `build/`, `dist/` e `config.json`, pra dados de compra, saída de build e segredos não entrarem no repo por acidente.
- 🆕⁷ **`ler_nota_fiscal_link` — mitigado em parte.** Ainda não há allowlist de domínios da SEFAZ (são dezenas, um por estado), mas `_recusar_host_interno` agora barra `localhost` e IPs de rede interna. Resíduo: DNS rebinding (domínio → IP interno) e redirects não são checados — aceitável pro perfil "app local de um usuário só".
- 🆕⁷ **Escrita de config atômica** — `salvar_config` grava em `.tmp` + `os.replace` e abre já com `0600`; some a janela de permissão frouxa e o risco de leitura de JSON truncado por outra thread.
- 🆕⁷ **`LabelElidavel` força texto puro** — nome de produto/empresa vindo da planilha ou da IA não é mais interpretado como rich text pelo QLabel.

### Código morto / incompleto

- **`sheets_renomear_produtos` (Python) não tem nenhum chamador.** O backend `renomearProdutos` está 100% implementado e a ação `"renomearProdutos"` do `doPost` funciona, mas **nenhuma tela** invoca `sheets_renomear_produtos` — a "ferramenta de mesclagem/migração de pastas" citada nos comentários não existe na interface. É encanamento pronto pra uma feature que não foi construída. Decidir: construir a tela, ou remover a função Python (e, se quiser, a ação do backend) até a feature entrar de fato.

### Bugs corrigidos nas revisões 🆕⁵

- **`_nome_apresentavel` deixava Title Case passar** — nomes subiam pro Sheets com capitalização inconsistente (CAIXA ALTA, Title Case e frase misturados). Agora é sempre frase.
- **Troca de modelo indevida em erro não-404** — `_ia_gerar_itens` chamava `_ia_descobrir_modelo()` (que **grava** um modelo novo no `config.json`) em **qualquer** `ErroIA`, inclusive limite de uso (429) e falha de rede. Um 429 passageiro podia rebaixar em definitivo, digamos, `gemini-2.5-pro` → `gemini-2.0-flash`. Corrigido: só troca se o erro for especificamente "modelo não existe".
- **`ImportarNotaFiscalPage._confirmar_tudo` descartava linhas incompletas em silêncio.** Agora conta as ignoradas e pede confirmação (`"N linha(s)… vão ser ignoradas. Salvar as outras M?"`) antes de salvar.
- **`_inserir_linha_produto` fazia `quantidade * preco_unitario` sem `parse_numero`** — se uma dessas viesse como string vazia do cache/Sheets, dava `TypeError` ao montar a lista de produtos. Agora passa pelas duas por `parse_numero`.

### Pontos a considerar (não corrigidos)

- **`_ia_descobrir_modelo`, sem nenhum Flash na conta, cai em `nomes[0]`** — que pode ser um modelo Pro (mais caro) — e **grava** essa escolha. Improvável (toda conta Gemini tem Flash), mas o fallback poderia parar em `MODELO_IA_PADRAO` sem gravar.
- **`ConfigDialog._buscar_modelos` faz a chamada de rede na thread da interface** — a janela congela por até 30s se a API demorar. As leituras de nota já rodam em thread; esse diálogo não.
- **Quantidade/preço da IA aparecem como `2.0` / `12.9` na tabela de conferência** (repr de float). Cosmético.
- **`apps_script_backend.gs` está sem quebra de linha no fim do arquivo** (`\ No newline at end of file`). Trivial.
- 🆕⁶ **Portabilidade — resolvido:** `assets/` agora passa por `resource_path()` e `config`/`cache` foram pra pastas por-usuário do SO. Ver [Seção 21](#21-empacotamento-e-instalação-).
- 🆕⁶ **Build/CI não testados neste ambiente:** o `.spec`, o `.github/workflows/build.yml` e o código frozen-safe foram escritos, mas o primeiro `.exe`/binário e a primeira execução do workflow precisam rodar no GitHub Actions ou numa máquina com PyInstaller — não deu pra validar aqui.

---

## 21. Empacotamento e instalação 🆕⁶ 🆕⁷

O objetivo é o usuário final receber **um arquivo** e dar duplo clique — sem instalar Python. O `Readme.md` tem o passo a passo com telas; aqui fica o resumo técnico.

### Instalar (usuário final)

| Sistema | Jeito mais fácil | Pelo código-fonte |
|---|---|---|
| **Windows** | Releases → baixar `ControleEmpresas-windows.exe` → duplo clique (no aviso do SmartScreen: "Mais informações" → "Executar assim mesmo"). | Instalar Python 3.10+ com "Add to PATH"; `pip install PyQt6`; `python controle_empresas.py`. |
| **Linux** | Releases → baixar `ControleEmpresas-linux` → `chmod +x` → `./ControleEmpresas-linux`. Se faltar lib: `sudo apt install libxcb-cursor0 libxcb-xinerama0 libegl1`. | `sudo apt install python3-pyqt6` (ou pip num venv); `python3 controle_empresas.py`. |

Depois: **"⚙️ Configurar"** → colar a URL do Web App do Apps Script (e, opcional, a chave do Gemini). Fica em `config.json` na pasta de config do usuário (Seção 2) — atualizar o app não apaga.

### Arquivos de build

- **`controle_empresas.spec`** — receita do PyInstaller. `datas=[('assets', 'assets')]` embute as logos; `console=False` (app de janela); `excludes=[...]` corta libs não usadas pra o binário não inchar.
- **`requirements.txt`** — `PyQt6` (execução) + `pyinstaller` (build).
- **`.github/workflows/build.yml`** — 🆕⁷ CI: a cada tag `v*` (`git tag v1.0 && git push origin v1.0`), o GitHub roda `pyinstaller` no Windows **e** no Linux e anexa os dois executáveis numa Release. Também dá pra disparar na mão em *Actions → build → Run workflow*. A publicação usa `gh release create/upload` (CLI oficial, sem action de terceiros) com `permissions: contents: write`.

### Build manual

```
pip install -r requirements.txt
pyinstaller controle_empresas.spec      # -> dist/ControleEmpresas(.exe)
```

O PyInstaller **não faz cross-compile**: pra um `.exe` de Windows, rodar dentro do Windows. O mesmo `.spec` gera um binário Linux no Linux.

### O que o código precisou pra funcionar empacotado (ver [Seção 2](#2-configuração-inicial))

1. **`resource_path()`** — empacotado (`getattr(sys, "frozen", False)`), os assets estão em `sys._MEIPASS`, não ao lado do `.py`.
2. **Config e cache em pasta por-usuário** — no Windows a pasta do `.exe` costuma ser somente-leitura; gravar lá falharia. Vão pra `%APPDATA%` / `%LOCALAPPDATA%`.
3. **`migrar_cache_antigo()`** (Seção 5) — transição suave pra quem já rodava do `.py`.
4. **`app.setApplicationName("Controle de Empresas")`** no `main()` — usado pelo Qt em títulos de diálogos nativos.

### Ainda dá pra melhorar (futuro)

- Ícone próprio (`.ico`) no `.spec`.
- Instalador de verdade (Inno Setup / MSIX) — atalho no Menu Iniciar, desinstalador.
- Assinar o executável, pra o SmartScreen não reclamar.
- **Build não validado neste ambiente:** não há PyInstaller aqui; o `.spec`, o `.yml` e o código frozen-safe foram escritos, mas o primeiro build real precisa rodar no CI ou numa máquina com PyInstaller.

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
| 🆕⁴ **`_disparar_worker`** | Método (em `ProductEntriesPage` e `ProductListPage`) que dispara um `SheetsWorker` mantendo-o numa lista (`_workers_ativos`) até terminar, evitando que uma segunda chamada em paralelo sobrescreva a referência à primeira `QThread` ainda rodando |
| 🆕⁴ **`_remocoes_em_andamento`** | Contador de remoções ainda não confirmadas; `_salvar`/`_recarregar_do_sheets` (e o `recarregar` da lista de produtos) recusam começar enquanto ele for maior que zero |
| 🆕⁴ **`ID_ABA_DADOS`** | Script Property do Apps Script que guarda o `getSheetId()` da aba "fixada" — usada por `getPlanilha()` pra sempre voltar na mesma aba, em vez de seguir a aba "ativa" no navegador |
| 🆕⁴ **`idsNaoEncontrados`** | Lista devolvida por `salvarRegistros`/`doPost` com os IDs "existentes" que não foram achados na planilha — o Python usa isso pra manter essas linhas específicas como pendentes, em vez de assumir que tudo foi salvo |
| 🆕⁵ **Pasta (produto)** | O tipo do produto (coluna "Produto"), ex: "Aveia Flocos" — agrupa várias compras/marcas |
| 🆕⁵ **Nome (da compra)** | Coluna "Nome" / `COL_NOME`: o texto da marca/embalagem daquela compra específica, ex: "Aveia Flocos Marca X 500g" |
| 🆕⁵ **`config.json`** | `~/.config/controle_empresas/config.json` (permissão `600`, fora do git): guarda `sheets_webhook_url`, `gemini_api_key` e `gemini_modelo` |
| 🆕⁵ **`sheets_webhook_url()`** | Resolve a URL do Web App (variável de ambiente `GOOGLE_SHEETS_WEBHOOK_URL` → `config.json` → `""`); substituiu a constante hardcoded. A URL é um segredo: quem a tem lê/escreve na planilha |
| 🆕⁵ **`ConfigDialog`** | Antigo `ConfigIADialog`: diálogo "⚙️ Configurar" com a URL da planilha (obrigatória) + a chave da API do Gemini e o modelo (opcionais); os dois segredos ficam ocultos por padrão |
| 🆕⁵ **`ErroIA`** | Exceção única da leitura de notas por IA (chave recusada, rede fora, modelo inexistente, limite de uso…); capturada pelo `SheetsWorker` junto com `ErroSheets` |
| 🆕⁵ **`_nome_apresentavel`** | Padroniza todo nome lido da nota como frase (só a 1ª letra maiúscula), pra a lista não misturar CAIXA ALTA / Title Case / frase |
| 🆕⁵ **`_ia_descobrir_modelo`** | Quando o modelo configurado dá 404, acha um Flash válido na conta e grava no `config.json` — só em erro 404, não em 429/rede |
| 🆕⁵ **`sugerir_pasta`** | Sugere a pasta de destino de um item lido comparando as palavras do nome com as pastas existentes (limiar 0.6) |
| 🆕⁵ **`ImportarNotaFiscalPage`** | Tela de conferência dos itens que a IA leu de uma nota; nada vai pro Sheets sem o usuário revisar e clicar em "✅ Confirmar tudo" |
| 🆕⁵ **`renomearProdutos`** | Ação do backend (e `sheets_renomear_produtos` no Python) que renomeia pasta/nome por ID — implementada, mas ainda sem tela que a use |
| 🆕⁶ **`PaginaBase`** | Classe base das três telas cheias; reúne o encanamento antes triplicado (`_disparar_worker`, `_destruida`/`marcar_destruida`, `_definir_ocupado` + `_botoes_bloqueaveis`, `_texto_celula`, `_estilo_botao_destaque`) |
| 🆕⁶ **`resource_path()`** | Resolve um recurso somente-leitura que acompanha o app (as logos); sabe achar tanto rodando do `.py` quanto empacotado (`sys._MEIPASS`) |
| 🆕⁶ **Pasta por-usuário** | `config.json` e cache ficam em `%APPDATA%`/`%LOCALAPPDATA%` (Windows) ou `~/.config`/`~/.cache` (Linux), nunca ao lado do executável — que no Windows costuma ser somente-leitura |
| 🆕⁶ **`.spec` (PyInstaller)** | `controle_empresas.spec`: receita que gera `dist/ControleEmpresas(.exe)`, um arquivo só, com os assets embutidos |
| 🆕⁴ **`LockService`** | Serviço do Apps Script usado em `doPost` pra impedir que duas requisições de escrita rodem ao mesmo tempo e disputem os mesmos números de linha |