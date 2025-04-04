# Catalog Prog. BRASIL MAIS - SCCON/Planet

Plugin QGIS para acesso a imagens dos satélites da empresa Planet Labs e aos alertas de detecção de mudança (desmatamento e afins), vinculados ao Programa BRASIL MAIS (https://plataforma-pf.sccon.com.br), do Ministério da Justiça e Segurança Pública.

## Funcionalidades

- Acesso a mosaicos mensais da Planet Labs
- Visualização de imagens diárias com filtragem por cobertura de nuvens
- Acesso a índices espectrais: NDVI, NDWI, MSAVI2, VARI, MTVI2, CIR
- Consulta a alertas de desmatamento e queimadas via serviços SCCON

## Requisitos

- QGIS 3.0 ou superior
- Credenciais de acesso ao sistema da Planet Labs e à plataforma do Programa BRASIL MAIS

## Instalação

O plugin está disponível como experimental e pode ser instalado diretamente do Gerenciador de Plugins do QGIS:

1. Abra o QGIS
2. Navegue até Plugins > Gerenciar e Instalar Plugins
3. Vá para a aba "Configurações" e habilite "Mostrar plugins experimentais"
4. Na aba "Todos" ou "Não instalados", pesquise por "Brasil MAIS"
5. Clique em "Instalar Plugin"

## Uso

1. Após a instalação, o ícone do plugin estará disponível na barra de ferramentas "Brasil Mais"
2. Insira e valide sua API Key da Planet Labs na aba "API Key" do plugin
3. Utilize as abas "Mosaicos Mensais" para acessar mosaicos mensais, a aba "Imagens Diárias" para acessar imagens diárias e a aba "Índices Espectrais" para acessar os índices espectrais disponíveis pela Planet Labs, como NDVI, NDWI etc.
4. Para acessar os alertas do Programa BRASIL MAIS, use a aba "Serviços SCCON" do plugin. Para encontrar o URL de alertas,faça o login na plataforma do Programa BRASIL MAIS (https://plataforma-pf.sccon.com.br/), clique na opção "Geo Serviços" da janela "GEO SERVIÇOS E PLUGIN QGIS" e copie a URL de "Alertas de detecção de mudança".


## Autor

- conrado.cbp (cbpetersen6@hotmail.com)

## Licença

[GNU General Public License v3.0](LICENSE)
