# 🏢 Controle de Empresas

> Gerenciador de compras e preços por empresa, com Google Sheets como banco de dados e interface gráfica.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Interface](https://img.shields.io/badge/Interface-PyQt6-41CD52?logo=qt&logoColor=white)
![Banco](https://img.shields.io/badge/Banco-Google%20Sheets-34A853?logo=googlesheets&logoColor=white)
![Uso](https://img.shields.io/badge/Uso-Local-orange)
![Plataforma](https://img.shields.io/badge/Plataforma-Linux%20%7C%20Windows-blue)

## Como funciona

O Google Sheets é a fonte de verdade dos dados — toda leitura e escrita "de verdade" acontece direto na planilha, através de um **Web App do Google Apps Script**. O app também mantém um pequeno **cache local em disco** (pasta `cache/`), usado só para a tela aparecer instantaneamente ao abrir uma empresa; ele nunca substitui a planilha, é sempre atualizado a partir dela em segundo plano.

1. **Selecionar a empresa** — escolha entre os cards de empresas cadastradas.
2. **Ver os produtos** — lista os produtos da empresa, com data e valor da última compra de cada um.
3. **Abrir um produto** — mostra o histórico completo de compras, com total, melhor/pior preço e um mini gráfico de tendência.

Toda alteração (adicionar, editar ou remover uma linha) é enviada em tempo real para a planilha:

| Ação | Requisição | O que acontece |
|---|---|---|
| Abrir empresa/produto | `GET` | Busca os registros na planilha (via cache de leitura no Apps Script, quando disponível) |
| Adicionar / editar e salvar | `POST` (`acao: "salvar"`) | Grava linhas novas em lote e atualiza as existentes |
| Remover linha ou produto | `POST` (`acao: "remover"`) | Apaga a linha de verdade, sem deixar espaço em branco |

## Desempenho e confiabilidade

- **Cache local (Python):** ao abrir uma empresa, o app mostra na hora os últimos dados salvos em `cache/`, enquanto busca a versão atual do Sheets em segundo plano — sem precisar esperar a rede pra ver algo na tela.
- **Cache de leitura (Apps Script):** o backend guarda a última listagem por 60 segundos, evitando reler a planilha inteira a cada requisição. Qualquer `salvar`/`remover` invalida esse cache na hora, então nunca há dado desatualizado depois de uma alteração.
- **Escrita em lote:** linhas novas são gravadas todas de uma vez, e um índice de IDs é montado uma única vez por requisição — em vez de relerem a planilha item por item, o que pesa bastante em listas grandes.
- **Navegação segura:** cada tela sabe se já foi fechada antes de uma resposta do Sheets chegar, então respostas atrasadas (por exemplo, depois de trocar de produto rapidamente) são simplesmente ignoradas em vez de causar um erro.

## Tecnologias

- **Python 3.10+**
- `PyQt6` — interface gráfica
- `urllib` / `json` (biblioteca padrão) — comunicação HTTP com o Apps Script e cache local em disco
- **Google Apps Script** — Web App que expõe a planilha como uma API simples, com cache e escrita em lote

## Estrutura

```
controle_empresas.py     # app principal (única fonte de código da interface)
apps_script_backend.gs   # código do Web App (cole no editor do Apps Script)
assets/                  # logos das empresas (opcional)
cache/                   # gerado automaticamente — cache local por empresa, pode ser apagado a qualquer momento
```

O arquivo principal é organizado em blocos:

1. Configuração (empresas, cores, URL do Web App)
2. Funções utilitárias (formatação de moeda, datas, IDs)
3. Integração com o Google Sheets (`sheets_buscar`, `sheets_salvar`, `sheets_remover`)
4. Cache local em disco (`cache_carregar`, `cache_salvar`)
5. Avatares circulares das empresas
6. Mini gráfico de tendência de preço
7. Página de compras de um produto
8. Página de lista de produtos de uma empresa
9. Página de seleção de empresa
10. Janela principal

Documentação completa, função por função (incluindo o backend `.gs`), em `documentacao_controle_empresas.md`.

## Como usar

1. Instale a dependência:
   ```bash
   pip install PyQt6
   ```
2. Publique o `apps_script_backend.gs` como Web App no Google Apps Script, com acesso **"Qualquer pessoa"**, e copie a URL gerada (termina em `/exec`). Se você já tinha uma implantação publicada antes, edite-a e gere uma **nova versão** em vez de criar uma implantação nova — assim a URL continua a mesma.
3. Cole essa URL na constante `GOOGLE_SHEETS_WEBHOOK_URL`, no topo de `controle_empresas.py`.
4. Rode o app:
   ```bash
   python controle_empresas.py
   ```

## Personalização

As empresas exibidas na tela inicial ficam na lista `COMPANIES`, em `controle_empresas.py`. Para cada uma é possível definir:

- `nome` — nome exibido
- `logo` — caminho de uma imagem (ou `None` para usar um ícone/texto)
- `cor` / `cor_texto` — cores de destaque e do texto sobre elas

No `apps_script_backend.gs`, o tempo de vida do cache de leitura pode ser ajustado na constante `CACHE_SEGUNDOS` (padrão: 60 segundos) — valores maiores reduzem ainda mais as leituras da planilha, mas aumentam o tempo até que uma edição feita direto no Google Sheets (fora do app) apareça para todo mundo.

## Licença

MIT