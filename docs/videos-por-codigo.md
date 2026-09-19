# Vídeos por código — versão 2.3.38

Cada vídeo preparado recebe um identificador `VC1-…`. Ele permite reutilizar o
original e os quadros da câmera em outro PC sem repetir a conversão. O GitHub
distribui o programa e esta documentação. Os arquivos grandes ficam em uma pasta
que os dois computadores conseguem acessar, como um compartilhamento do Windows
ou um disco externo levado ao outro computador.

O código não contém o vídeo nem gera seus quadros sozinho. Esta versão não cria
hospedagem online, compartilhamento do Windows ou transmissão pela internet.

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
