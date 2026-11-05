# Assistente IA para QGIS

Plugin gratuito e de código aberto (GPL v2+) para **QGIS 3.28 ou superior**, desenvolvido pela **Ibexdev**.

Descreva em português o que deseja fazer, como "coloque os nomes nos estados", "faça um buffer de 20 km nas divisas" ou "pinte cada estado de uma cor". O assistente (Claude, da Anthropic) gera o código PyQGIS, mostra o código e **só executa depois da sua confirmação**.

> Versão 0.1.0 (experimental).

## Funcionalidades

- Chat em português num painel lateral do QGIS.
- Leitura automática do contexto do projeto: camadas, tipo de geometria, SRC, campos e número de feições. **Os dados das feições (atributos e geometrias) não são enviados.**
- Código PyQGIS exibido antes de rodar, com os botões **▶ Executar**, **Copiar código** e **Salvar como script**.
- Confirmação obrigatória antes de cada execução.
- Bloqueio de operações perigosas: apagar arquivos, `os.system`, `subprocess`, acesso à rede, `eval`/`exec`.
- Aviso antes de operações que alteram dados, como apagar feições, remover camadas ou gravar arquivos.
- Correção automática: se o código der erro, o erro é enviado ao assistente para corrigir (até 2 tentativas).
- Escolha do modelo (Haiku, Sonnet ou Opus) e do idioma das respostas.

## Instalação

1. No QGIS, abra **Complementos > Gerenciar e instalar complementos**.
2. Em **Configurações**, marque **Mostrar também os complementos experimentais**.
3. Procure **Assistente IA para QGIS** e clique em **Instalar**.

## Configurar a chave de API (uma vez só)

O plugin usa a sua própria chave da Anthropic, e o custo de uso fica na sua conta.

1. Crie uma conta em https://platform.claude.com.
2. Adicione créditos em **Billing**. O uso da API é cobrado à parte da assinatura do Claude; US$ 5 rendem muitos pedidos.
3. Em **API Keys**, crie uma chave (começa com `sk-ant-`) e copie.
4. No QGIS, abra o painel do Assistente IA, clique em **⚙**, cole a chave, clique em **Testar chave** e depois em **Salvar**.

A chave fica guardada **criptografada** no gerenciador de autenticação do QGIS.

### Custo aproximado por pedido

| Modelo | Custo por pedido (aprox.) |
| --- | --- |
| Claude Haiku 5.5 | R$ 0,005 |
| Claude Sonnet 5.5 (padrão) | R$ 0,09 |
| Claude Opus 5.5 | R$ 0,18 |

Valores estimados com dólar a R$ 5,50. O custo de cada pedido aparece em **Exibir > Painéis > Mensagens de log > Assistente IA**.

## Segurança e privacidade

- Nenhum código é executado sem a sua confirmação.
- Antes de executar, o código passa por uma análise que bloqueia operações perigosas. Essa análise é uma proteção extra e não substitui a sua revisão: leia o código antes de executar e salve o projeto antes de operações que alteram dados.
- Ao assistente vão apenas os metadados do projeto (nomes de camadas, campos, SRC, contagens) e as suas mensagens. Caminhos completos e conexões de banco de dados não são enviados.

## Desenvolvimento

```
qgis_assistente_ia/      # pasta do plugin (é ela que vai no .zip)
├── plugin.py            # menu, painel e fluxo do chat
├── ui/dock.py           # painel de chat
├── ui/settings.py       # tela de configurações
├── core/context.py      # contexto do projeto
├── core/llm_client.py   # cliente da API Anthropic (QgsTask)
├── core/executor.py     # validação e execução do código
└── core/prompts.py      # prompt de sistema
```

Para desenvolver, crie um link simbólico da pasta do plugin para a pasta de plugins do perfil do QGIS:

- macOS: `ln -s "$PWD/qgis_assistente_ia" ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_assistente_ia`
- Linux: `ln -s "$PWD/qgis_assistente_ia" ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_assistente_ia`
- Windows (Prompt como administrador): `mklink /D "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\qgis_assistente_ia" "C:\caminho\do\repo\qgis_assistente_ia"`

Use o plugin **Plugin Reloader** para recarregar o plugin a cada alteração. Para gerar o .zip de publicação, rode `./scripts/empacotar.sh`.

## Suporte e projetos sob medida

Encontrou um problema? Abra uma issue em https://github.com/viaautom/assistente_ia_qgis/issues.

A Ibexdev desenvolve soluções em geotecnologia, automações em QGIS e treinamentos: ibexdesenvolvimento@gmail.com.

## Licença

GNU General Public License v2 ou superior. Veja [LICENSE](LICENSE).
