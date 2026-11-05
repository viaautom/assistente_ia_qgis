# Assistente IA para QGIS

Plugin gratuito e open source (GPL v2+) da **Ibexdev** para QGIS 3.28+.
Descreva em português o que deseja fazer e o assistente (Claude, da Anthropic) gera código PyQGIS, mostra o código e só executa depois da sua confirmação.

> Status: em desenvolvimento (v0.1.0, experimental).

## Estrutura

```
qgis_assistente_ia/      # pasta do plugin (é ela que vai no .zip)
├── __init__.py          # classFactory
├── plugin.py            # menu, barra de ferramentas e ícone
├── metadata.txt
├── icon.png
├── LICENSE
├── ui/                  # dock.py (chat) e settings.py (configurações)
└── core/                # context.py, llm_client.py, executor.py, prompts.py
```

## Desenvolvimento

Crie um link simbólico da pasta do plugin para a pasta de plugins do perfil do QGIS:

- macOS:
  `ln -s "$PWD/qgis_assistente_ia" ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_assistente_ia`
- Linux:
  `ln -s "$PWD/qgis_assistente_ia" ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_assistente_ia`
- Windows (Prompt como administrador):
  `mklink /D "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\qgis_assistente_ia" "C:\dev\ibexdev\qgis-assistente-ia\qgis_assistente_ia"`

Reinicie o QGIS, ative o plugin em **Complementos > Gerenciar e instalar complementos** e use o **Plugin Reloader** a cada alteração.

## Licença

GNU General Public License v2 ou superior. Veja [LICENSE](LICENSE).
