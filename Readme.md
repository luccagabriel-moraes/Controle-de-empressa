# 🏢 Controle de Empresas

> Gerenciador de compras e preços por empresa, com Google Sheets como banco de dados e interface gráfica.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-PyQt6-41CD52?logo=qt&logoColor=white)
![Banco](https://img.shields.io/badge/Banco-Google%20Sheets-34A853?logo=googlesheets&logoColor=white)
![Uso](https://img.shields.io/badge/Uso-Local-orange)
![Plataforma](https://img.shields.io/badge/Plataforma-Linux%20%7C%20Windows-blue)

---

## 📥 Instalar e abrir o app

Escolha o seu sistema. Se você **não** mexe com programação, siga o **Jeito 1** (baixar pronto).

<details open>
<summary><h3>🪟 Windows</h3></summary>

#### Jeito 1 — baixar o programa pronto (recomendado)

1. Abra a página de **[Releases](../../releases)** deste repositório (menu à direita, "Releases").
2. Na versão mais recente, baixe o arquivo **`ControleEmpresas-windows.exe`**.
3. Salve numa pasta sua (ex: `Documentos\ControleEmpresas`).
4. Dê **duplo clique** no arquivo.
   - O Windows pode mostrar uma tela azul *"O Windows protegeu o computador"*. É porque o programa não é assinado. Clique em **"Mais informações"** → **"Executar assim mesmo"**. (Só na primeira vez.)
5. O app abre. Vá para **[Primeira configuração](#primeira-configuração-uma-vez-por-computador)** abaixo.

> Não precisa instalar Python nem nada: o `.exe` já vem com tudo dentro. Pra atualizar, é só baixar o `.exe` novo e substituir o antigo — suas configurações ficam guardadas à parte.

#### Jeito 2 — rodar pelo código-fonte

1. Instale o **[Python 3.10 ou mais novo](https://www.python.org/downloads/)**. **Marque a caixa "Add Python to PATH"** durante a instalação.
2. Baixe este repositório: botão verde **"Code"** → **"Download ZIP"** e extraia; ou, se tiver o Git: `git clone https://github.com/luccagabriel-moraes/Controle-de-empressa.git`
3. Abra o **Prompt de Comando** (tecla Windows, digite `cmd`, Enter) e vá até a pasta:
   ```bat
   cd caminho\para\a\pasta\do\projeto
   pip install PyQt6
   python controle_empresas.py
   ```

</details>

<details>
<summary><h3>🐧 Linux</h3></summary>

#### Jeito 1 — baixar o programa pronto (recomendado)

1. Abra a página de **[Releases](../../releases)** e baixe o arquivo **`ControleEmpresas-linux`** da versão mais recente.
2. No terminal, na pasta onde salvou:
   ```bash
   chmod +x ControleEmpresas-linux      # dá permissão de execução (só uma vez)
   ./ControleEmpresas-linux
   ```
   Ou, no gerenciador de arquivos: botão direito → Propriedades → Permissões → marque "permitir execução", depois duplo clique.
3. O app abre. Vá para **[Primeira configuração](#primeira-configuração-uma-vez-por-computador)** abaixo.

> Se o app não abrir, quase sempre falta uma biblioteca do sistema. No Debian/Ubuntu:
> `sudo apt install libxcb-cursor0 libxcb-xinerama0 libegl1`

#### Jeito 2 — rodar pelo código-fonte

```bash
git clone https://github.com/luccagabriel-moraes/Controle-de-empressa.git
cd Controle-de-empressa

# opção A (recomendada no Linux): PyQt6 do sistema
sudo apt install python3-pyqt6        # Debian/Ubuntu
#   ou:  sudo dnf install python3-pyqt6   (Fedora)
#   ou:  sudo pacman -S python-pyqt6      (Arch)

# opção B: PyQt6 do pip, num ambiente isolado
python3 -m venv .venv && source .venv/bin/activate && pip install PyQt6

python3 controle_empresas.py
```

</details>

### Primeira configuração (uma vez por computador)

O app precisa saber **em qual planilha** gravar. Isso não vem embutido (é um segredo — quem tem o endereço consegue ler e escrever na planilha).

1. Com o app aberto, clique em qualquer empresa e depois no botão **"⚙️ Configurar"** (canto inferior direito).
2. No campo **"URL da planilha"**, cole o endereço do Web App do Apps Script (termina em `/exec`). Peça esse endereço a quem cuida da planilha, ou veja **[Publicar a planilha](#publicar-a-planilha-para-quem-administra)**.
3. *(Opcional — só se for importar notas fiscais por foto/link)* cole também a **chave da API do Google Gemini**. É gratuita: crie em [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
4. Clique em **Salvar**. Pronto — o app abre as empresas e as compras da planilha.

Essas informações ficam salvas **só na sua máquina**:

| Sistema | Onde |
|---|---|
| Windows | `%APPDATA%\controle_empresas\config.json` |
| Linux | `~/.config/controle_empresas/config.json` |

Atualizar o app **não apaga** essa configuração.

---

## Como funciona

O Google Sheets é a fonte de verdade dos dados — toda leitura e escrita "de verdade" acontece direto na planilha, através de um **Web App do Google Apps Script**. A URL desse Web App (que dá acesso de leitura/escrita à planilha inteira) **não fica no código**: você a configura na primeira vez em **"⚙️ Configurar"**, e ela é gravada num `config.json` na pasta de configuração do usuário (`%APPDATA%` no Windows, `~/.config` no Linux) — fora do repositório — ou passada pela variável de ambiente `GOOGLE_SHEETS_WEBHOOK_URL`. O app também mantém um pequeno **cache local em disco** (na pasta de cache do usuário), usado só para a tela aparecer instantaneamente ao abrir uma empresa; ele nunca substitui a planilha, é sempre atualizado a partir dela em segundo plano.

1. **Selecionar a empresa** — escolha entre os cards de empresas cadastradas.
2. **Ver os produtos** — lista os produtos da empresa, com data e valor da última compra de cada um.
3. **Abrir um produto** — mostra o histórico completo de compras, com total, melhor/pior preço e um mini gráfico de tendência.

Cada produto é uma **pasta por tipo** (ex: "Aveia Flocos"), e cada compra dentro dela tem seu próprio campo **Nome** — o texto exato de como veio na nota/marca daquela compra (ex: "Aveia Flocos Marca X" numa linha, "Aveia Flocos Marca Y" em outra, ambas dentro da mesma pasta "Aveia Flocos"). Isso separa "que tipo de produto é" (a pasta) de "qual embalagem/marca foi comprada daquela vez" (o Nome de cada linha).

### 📷 Importar compra de uma foto (IA)

Em vez de digitar a compra na mão, dá pra selecionar uma foto de uma nota impressa/cupom: a imagem é enviada para a **API do Google Gemini**, que lê a nota inteira e devolve os itens já separados (Nome, Data, Quantidade, Preço Unitário) — entendendo o layout da nota e ignorando linhas de total, imposto e dados do estabelecimento. Todo nome lido é padronizado como frase — só a primeira letra maiúscula e o resto minúsculo ("ARROZ TIPO 1 5KG" e "Arroz Tipo 1 5kg" viram os dois "Arroz tipo 1 5kg"), pra lista ficar uniforme —, e itens repetidos com o mesmo nome e o mesmo preço unitário (verduras e carnes pesadas várias vezes na mesma nota) são somados numa linha só, com o peso total. O app então sugere em qual pasta (produto) cada item entra, comparando as palavras do nome lido com as pastas já cadastradas daquela empresa (ex: uma nota "Aveia Flocos Marca X" sugere a pasta "Aveia Flocos", mas não confunde com "Aveia Grão"). Antes de qualquer coisa ir pro Sheets, uma janela mostra os campos reconhecidos pra você conferir e corrigir — inclusive trocar a pasta sugerida ou criar uma nova.

Precisa de uma **chave da API do Google Gemini** (gratuita, criada em [aistudio.google.com/apikey](https://aistudio.google.com/apikey)). No app, clique em **"⚙️ Configurar"**, cole a chave e escolha o modelo (o botão "Buscar modelos" lista os disponíveis para a sua chave; o padrão é um modelo *Flash*, rápido e de baixo custo). A chave fica salva no mesmo `config.json` da pasta de config do usuário (permissão `600` no Linux, fora do repositório) — ou pode ser passada pela variável de ambiente `GEMINI_API_KEY`. Não há OCR local: sem chave configurada, o botão "📷 Importar nota fiscal" abre direto a tela de configuração.

### 🔗 Importar por link do QR code (NFC-e)

As notas de consumidor (NFC-e) trazem um QR code que aponta para a página oficial de consulta da SEFAZ, com **todos os itens, quantidades e preços exatos** — dado mais confiável do que ler a foto. No botão **"🔗 Importar por link"**, escaneie o QR com a câmera do celular, copie o endereço e cole no app: ele baixa essa página, extrai só o texto e manda para a mesma IA, que devolve os itens já estruturados. Cai na mesma tela de conferência da importação por foto.

Alguns estados (Santa Catarina, por exemplo) protegem a consulta pública com um CAPTCHA que o app não consegue passar — nesses casos ele avisa e você usa a importação por foto. Onde o portal não bloqueia (boa parte dos estados), o link funciona direto.

Toda alteração (adicionar, editar ou remover uma linha) é enviada em tempo real para a planilha:

| Ação | Requisição | O que acontece |
|---|---|---|
| Abrir empresa/produto | `GET` | Busca os registros na planilha (via cache de leitura no Apps Script, quando disponível) |
| Adicionar / editar e salvar | `POST` (`acao: "salvar"`) | Grava linhas novas em lote e atualiza as existentes |
| Remover linha ou produto | `POST` (`acao: "remover"`) | Apaga a linha de verdade, sem deixar espaço em branco |

## Usabilidade da tela de compras

- **Preenchimento rápido com Enter:** ao apertar Enter, o foco pula pelos campos na ordem Nome → Data → Quantidade → Preço Unitário — sem precisar clicar em cada um. Em Preço Unitário o Enter só confirma o valor e para ali (não cria uma linha nova).
- **Produto novo começa enxuto:** um produto sem nenhuma compra ainda abre com só 1 linha em branco (em vez de 3) e já é aberto automaticamente assim que criado, sem precisar procurá-lo na lista.
- **Aviso ao sair sem salvar:** se você editou algo na tabela de compras e clicar em "← Voltar" sem ter salvado, o app pede confirmação antes de descartar as alterações.
- **Nomes longos não quebram mais a tela:** títulos e nomes de produto muito grandes são truncados com "..." em vez de desalinhar o layout — passe o mouse por cima para ver o nome completo.

## Desempenho e confiabilidade

- **Cache local (Python):** ao abrir uma empresa, o app mostra na hora os últimos dados salvos em `cache/`, enquanto busca a versão atual do Sheets em segundo plano — sem precisar esperar a rede pra ver algo na tela.
- **Cache de leitura (Apps Script):** o backend guarda a última listagem por 60 segundos, evitando reler a planilha inteira a cada requisição. Qualquer `salvar`/`remover` invalida esse cache na hora, então nunca há dado desatualizado depois de uma alteração.
- **Escrita em lote:** linhas novas são gravadas todas de uma vez, e um índice de IDs é montado uma única vez por requisição — em vez de relerem a planilha item por item, o que pesa bastante em listas grandes.
- **Navegação segura:** cada tela sabe se já foi fechada antes de uma resposta do Sheets chegar, então respostas atrasadas (por exemplo, depois de trocar de produto rapidamente) são simplesmente ignoradas em vez de causar um erro.

## Tecnologias

- **Python 3.10+**
- `PyQt6` — interface gráfica (única dependência de execução)
- `pyinstaller` — só pra gerar o executável distribuível (`.exe` no Windows)
- `urllib` / `json` / `base64` (biblioteca padrão) — HTTP com o Apps Script e com a API do Gemini, cache local em disco
- **Google Apps Script** — Web App que expõe a planilha como uma API simples, com cache e escrita em lote
- **API do Google Gemini** — leitura das notas fiscais fotografadas (visão + saída estruturada)

## Estrutura

```
controle_empresas.py         # app principal (arquivo único)
controle_empresas.spec       # receita do PyInstaller pra gerar o .exe / binário
requirements.txt             # PyQt6 (execução) + pyinstaller (build)
apps_script_backend.gs       # código do Web App (cole no editor do Apps Script)
assets/                      # logos das empresas (embutidas no executável pelo .spec)
.github/workflows/build.yml  # CI: gera .exe + binário e publica na aba Releases

# gerados / graváveis, fora do repositório:
build/  dist/                 # saída do PyInstaller
Windows:  %APPDATA%\controle_empresas\config.json   +  %LOCALAPPDATA%\controle_empresas\cache\
Linux:    ~/.config/controle_empresas/config.json   +  ~/.cache/controle_empresas/
          (config.json guarda a URL da planilha + a chave do Gemini + o modelo — segredos)
```

O arquivo principal é organizado em blocos:

1. Configuração e caminhos (`resource_path`, pastas por-usuário de config/cache, `COMPANIES`, cores)
2. Funções utilitárias (formatação de moeda, datas, IDs)
3. Configuração e segredos em disco (`carregar_config`, `salvar_config`, `sheets_webhook_url`, `ia_api_key`, `ia_modelo`)
4. Leitura de nota fiscal com IA — por foto (`ler_nota_fiscal_ia`) ou por link do QR code (`ler_nota_fiscal_link`)
5. Cache local em disco (`cache_carregar`, `cache_salvar`, `migrar_cache_antigo`)
6. Integração com o Google Sheets (`sheets_buscar`, `sheets_salvar`, `sheets_remover`, `sheets_renomear_produtos`, `SheetsWorker`)
7. Avatares circulares das empresas
8. Mini gráfico de tendência de preço, rótulo elidível (`LabelElidavel`), tabela com navegação por Enter (`TabelaComNavegacaoEnter`) e base das telas (`PaginaBase`)
9. Página de compras de um produto (`ProductEntriesPage`)
10. Diálogo de configuração (`ConfigDialog`)
11. Página de conferência dos itens lidos de uma nota fiscal (`ImportarNotaFiscalPage`)
12. Página de lista de produtos de uma empresa (`ProductListPage`)
13. Página de seleção de empresa (`CompanySelectPage`)
14. Janela principal (`MainWindow`), tema escuro e `main()`

Documentação completa, função por função (incluindo o backend `.gs`), em [`doc.md`](doc.md).

## 🛠 Para quem administra o projeto

### Publicar a planilha (para quem administra)

O app não fala direto com o Google Sheets — fala com um **Web App do Google Apps Script** ligado à planilha.

1. Abra a planilha no Google Sheets → menu **Extensões → Apps Script**.
2. Apague o conteúdo e cole o `apps_script_backend.gs` deste repositório. Salve.
3. **Implantar → Nova implantação → tipo "App da Web"**; em *"Quem pode acessar"* escolha **"Qualquer pessoa"**. Implante e copie a **URL** gerada (termina em `/exec`).
4. Distribua essa URL só para quem deve ter acesso — cada pessoa cola em **"⚙️ Configurar"** no app. Trate-a como uma senha.
5. Se um dia precisar publicar uma correção do `.gs`, **edite a implantação existente e gere uma nova versão** (não crie uma implantação nova) — assim a URL continua a mesma. A coluna "Nome" é criada na planilha automaticamente na primeira requisição depois disso.

> **Segurança:** essa URL dá acesso de leitura/escrita à planilha inteira, sem login. Se ela vazar (por exemplo, foi colada num arquivo versionado), a correção é **rotacionar**: crie uma nova implantação (URL nova) e arquive a antiga.

### 📦 Gerar os executáveis

**Automático (recomendado):** este repositório tem um workflow do GitHub Actions (`.github/workflows/build.yml`). Ao criar uma tag de versão, ele gera o `.exe` (Windows) e o binário (Linux) e publica numa Release:

```bash
git tag v1.0
git push origin v1.0
```

Também dá pra rodar na mão pela aba **Actions → build → Run workflow**.

**Manual, na sua máquina:**

```bash
pip install -r requirements.txt
pyinstaller controle_empresas.spec
```

Gera **um arquivo** em `dist/` (`ControleEmpresas.exe` no Windows, `ControleEmpresas` no Linux). O PyInstaller **não** faz cross-compile: pra um `.exe` de Windows, rode o comando dentro do Windows. As logos de `assets/` já vão embutidas no executável; `config.json` e cache ficam sempre em pastas graváveis por usuário do sistema, nunca ao lado do executável.

## Personalização

As empresas exibidas na tela inicial ficam na lista `COMPANIES`, em `controle_empresas.py`. Para cada uma é possível definir:

- `nome` — nome exibido
- `logo` — caminho de uma imagem (ou `None` para usar um ícone/texto)
- `cor` / `cor_texto` — cores de destaque e do texto sobre elas

No `apps_script_backend.gs`, o tempo de vida do cache de leitura pode ser ajustado na constante `CACHE_SEGUNDOS` (padrão: 60 segundos) — valores maiores reduzem ainda mais as leituras da planilha, mas aumentam o tempo até que uma edição feita direto no Google Sheets (fora do app) apareça para todo mundo.

## Licença

MIT