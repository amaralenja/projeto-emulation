# Vídeos por código — versão 2.3.39

## Pela internet: qualquer PC, sem pasta compartilhada

O fluxo online usa **GitHub Releases** como armazenamento do original e dos
quadros preparados. Eles são anexos de um Release, não arquivos do histórico Git.
O repositório configurado deve ser público; qualquer pessoa com acesso aos links
poderá baixar os vídeos. Nenhum vídeo é enviado apenas por atualizar o programa.

### No PC que publica

1. Atualize o sistema e reabra o painel para carregar a versão 2.3.39.
2. Na aba **Vídeos**, selecione e prepare o vídeo com o enquadramento desejado.
3. No card **Publicar no GitHub para outros PCs**, confira o nome do vídeo e o
   repositório. O padrão é `amaralenja/projeto-emulation`.
4. Marque a confirmação de publicação pública e clique em **Publicar vídeo
   selecionado no GitHub**.
5. Aguarde a conclusão. Copie o campo **Código online para copiar no outro PC**.

O publicador utiliza a credencial do Git para `github.com` ou a variável de
ambiente `GH_TOKEN`/`GITHUB_TOKEN` do servidor. A conta precisa ter acesso de
escrita ao repositório e permissão de conteúdo para criar Releases. Não coloque
chaves no README, no código online ou em mensagens do chat. O PC que baixa não
precisa de conta GitHub nem da credencial do publicador.

O programa prepara partes de até 1 GiB, cria um Release em rascunho, envia as
partes e verifica os hashes retornados pelo GitHub. Só publica o Release quando
todas as partes e o manifesto forem confirmados. Uma falha mantém o rascunho:
repetir a publicação reutiliza as partes já confirmadas. Arquivos divergentes
em um Release já publicado não são sobrescritos automaticamente.

### No PC que baixa

1. Abra a versão atualizada do sistema, na aba **Vídeos**.
2. No card **Baixar vídeo pela internet**, cole o código `VC2.…` completo.
3. Clique em **Baixar e preparar** e aguarde a confirmação.
4. Selecione o vídeo na biblioteca e vincule-o normalmente à tarefa desejada.

Não informe uma pasta de outro computador. O PC original pode estar desligado
depois de concluir a publicação. O Release precisa continuar disponível no
GitHub. Um código antigo `VC1-…` não se torna online automaticamente: publique o
vídeo primeiro e copie o novo código `VC2.…`.

O download mostra progresso, verifica cada parte e remonta os arquivos. Se
falhar, execute novamente com o mesmo código: as partes completas são
reutilizadas, e somente a parte interrompida precisa recomeçar. A importação
preserva o código online nos metadados locais para que possa ser copiado depois.

### Espaço e limitações do fluxo online

Publicar pela primeira vez exige uma cópia adicional do original e dos quadros
para dividir o pacote. Essa cópia permanece em
`%LOCALAPPDATA%\emulation-cam\online-publish` para permitir novas tentativas.
O receptor reserva aproximadamente duas vezes o tamanho total do pacote mais
1 GiB para baixar, montar e importar; após uma importação bem-sucedida, remove
o cache temporário de download. Um download interrompido permanece em
`%LOCALAPPDATA%\emulation-cam\online-downloads` para retomada.

O GitHub permite até 1000 anexos por Release, cada um menor que 2 GiB; este
publicador usa partes de até 1 GiB e valida o número de anexos.
Referência: [limites de Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
A velocidade depende do upload da origem, do download do destino e dos discos.
Não há reconversão, mas ainda é necessário transmitir os bytes dos arquivos.

### Formato do código online

```text
VC2.<base64url sem padding da URL HTTPS do manifesto>.<SHA256 do manifesto>
```

O código carrega o endereço público e o hash do manifesto, não a mídia. O
manifesto mantém os campos do formato VC1 abaixo e acrescenta `files`, com listas
ordenadas de partes para `original` e `frames.i420`. Cada parte contém `name`,
`size` e `sha256`. Somente URLs HTTPS sem credenciais são aceitas.

Módulos: `camvideo/video_online.py` e `camvideo/github_video.py`.
Testes: `python -m unittest discover -s camvideo -p test_video_online.py` e
`node --test camvideo/test_video_codes_ui.cjs`. Os testes de transporte e GitHub
usam respostas controladas; a disponibilidade de um vídeo real só é confirmada
depois de uma publicação e download reais.

## Alternativa local: pasta compartilhada (VC1)

Cada vídeo preparado recebe um identificador `VC1-…`. Ele permite reutilizar o
original e os quadros da câmera em outro PC sem repetir a conversão. O GitHub
distribui o programa e esta documentação. Os arquivos grandes ficam em uma pasta
que os dois computadores conseguem acessar, como um compartilhamento do Windows
ou um disco externo levado ao outro computador.

O código VC1 não contém o vídeo nem gera seus quadros sozinho. Este fluxo local
não cria compartilhamento do Windows nem permite download pela internet. Para
isso, use o fluxo VC2 acima.

## Publicar no primeiro PC

1. Atualize o sistema para 2.3.38 e reabra o painel.
2. Na aba **Vídeos**, selecione o vídeo e prepare seus quadros pelo fluxo existente.
3. No card **Vídeos por código**, informe o caminho absoluto da pasta de destino.
   Exemplo local: `D:\VideosPreparados`. Para acesso pela rede, configure uma pasta
   compartilhada no Windows, acessível como `\\PC-ORIGEM\VideosPreparados`.
4. Clique em **Publicar vídeo preparado** e aguarde a confirmação.
5. Copie o identificador exibido em **Código do vídeo selecionado**.

A opção de preenchimento/recorte selecionada deve corresponder ao cache preparado.
Cada variante possui um código diferente. Publicar novamente o mesmo código
verifica o pacote existente e o reutiliza.

## Importar no outro PC

1. Instale a versão atualizada do sistema e abra a aba **Vídeos**.
2. Informe o caminho acessível nesse PC, como `\\PC-ORIGEM\VideosPreparados`.
   Se estiver usando disco externo, informe a pasta nele.
3. Cole o código e clique em **Importar pelo código**.
4. Aguarde **Pacote importado**. Selecione o vídeo normalmente na biblioteca e
   vincule-o à tarefa desejada.

A importação copia e verifica os arquivos, recria os metadados locais e aproveita
o cache existente da câmera. Não troca automaticamente o vídeo dos celulares nem
inicia uma gravação. O original continua necessário para a biblioteca e a
compatibilidade com o fluxo atual. Se outro vídeo já tiver o mesmo nome, o novo
recebe um sufixo numérico, preservando o arquivo anterior.

## Espaço, tempo e disponibilidade

O perfil atual é I420, 640 × 360, 30 quadros por segundo. Cada quadro ocupa
345.600 bytes. Trinta minutos ocupam aproximadamente **17,38 GiB de quadros**,
além do original. Reserve esse espaço tanto na pasta compartilhada quanto no PC
que importa. A transferência inicial depende da rede e do disco: evitar a
conversão não elimina a cópia dos dados.

O painel exibe a etapa da transferência e a confirmação final; não há percentual
contínuo por byte nesta versão. Publicação/importação ficam indisponíveis enquanto
o painel estiver ocupado ou preparando vídeos em segundo plano. Não feche o
servidor durante a transferência. O PC que hospeda a pasta precisa estar acessível
durante a importação; depois os arquivos locais podem ser reutilizados.

## Como o código funciona

Implementação: `camvideo/video_codes.py`.

```text
sourceSha256 = SHA256(bytes do vídeo original)
profile = "i420-640x360-30-v1"
fill = "True" ou "False"
code = "VC1-" + SHA256(UTF8(sourceSha256 + ":" + profile + ":" + fill))
```

Os hashes são hexadecimais minúsculos completos, com 64 caracteres. O caminho e
o nome do arquivo não alteram o código; o conteúdo, o perfil e a variante alteram.
O identificador representa a origem e a receita de preparação. O hash separado
dos quadros verifica os bytes do pacote publicado.

```text
pasta-compartilhada/
  VC1-<64 caracteres hexadecimais>/
    manifest.json
    original
    frames.i420
```

O manifesto contém `code`, `profile`, `name`, `fill`, `sourceSha256`,
`rawSha256`, `sourceSize` e `rawSize`. O arquivo `original` mantém os bytes do
vídeo, sem extensão; seu nome original é recuperado do manifesto.

A publicação usa uma pasta temporária e só disponibiliza o pacote após completar
a cópia. A importação verifica tamanho, perfil e hashes antes de registrar o cache
local. Pacotes corrompidos geram erro. Um cache local corrompido não é substituído
automaticamente porque pode estar em uso. Hashes detectam corrupção; use uma
pasta de origem confiável, pois eles não autenticam quem publicou o pacote.

## Verificação automatizada

Na raiz do projeto, execute:

```powershell
python -m unittest discover -s camvideo -p test_video_codes.py
```

Os testes cobrem transferência entre pastas, reutilização, códigos das variantes,
colisão de nomes, rejeição de caminhos inválidos, alterações do original e
corrupção dos quadros. Use os arquivos reais para uma primeira importação de
ponta a ponta na rede que será utilizada.
