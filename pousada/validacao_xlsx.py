"""Conferências de segurança num .xlsx recebido, ANTES de abri-lo com o openpyxl.

Um .xlsx é um zip. Um zip pequeno pode "explodir" na memória (zip bomb); por isso olhamos o
tamanho descompactado declarado, a quantidade de partes e a taxa de compressão antes de ler.
Tudo é feito na memória: nenhum arquivo é gravado em disco.
"""
import hashlib
import io
import zipfile

ASSINATURA_ZIP = b"PK\x03\x04"
LIMITE_DESCOMPACTADO = 20 * 1024 * 1024   # soma de todas as partes depois de descompactar
LIMITE_PARTE = 10 * 1024 * 1024           # cada parte (a maior costuma ser uma aba)
MAX_PARTES = 500
MAX_TAXA_COMPRESSAO = 100                 # descompactado / compactado
MAX_ABAS = 24
MAX_CELULAS_POR_PARTE = 200_000           # uma planilha de reservas real tem poucas dezenas de milhares
MAX_LINHAS_POR_PARTE = 100_000
MAX_TITULO_ABA = 100


class ErroPlanilha(ValueError):
    """Arquivo recusado pelas conferências de segurança (a mensagem já está em português)."""


def sha256_do_arquivo(dados):
    return hashlib.sha256(dados).hexdigest()


def conferir_zip(dados):
    """Levanta ValueError (mensagem em português) se o arquivo não for um .xlsx seguro de abrir."""
    if not dados.startswith(ASSINATURA_ZIP):
        raise ErroPlanilha("O arquivo não parece ser uma planilha .xlsx (não tem a assinatura de um arquivo Excel)")
    try:
        zf = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile:
        raise ErroPlanilha("O arquivo está danificado ou não é uma planilha .xlsx válida")
    with zf:
        partes = zf.infolist()
        if len(partes) > MAX_PARTES:
            raise ErroPlanilha("Planilha com partes demais (arquivo suspeito)")
        total = sum(p.file_size for p in partes)
        if total > LIMITE_DESCOMPACTADO or any(p.file_size > LIMITE_PARTE for p in partes):
            raise ErroPlanilha("Planilha grande demais depois de descompactada (arquivo suspeito)")
        compactado = sum(p.compress_size for p in partes) or 1
        if total / compactado > MAX_TAXA_COMPRESSAO:
            raise ErroPlanilha("Taxa de compressão suspeita (possível arquivo malicioso)")
        nomes = {p.filename for p in partes}
        if "[Content_Types].xml" not in nomes or "xl/workbook.xml" not in nomes:
            raise ErroPlanilha("O arquivo não tem a estrutura de uma planilha do Excel")
        for p in partes:
            if p.filename.lower().endswith((".xml", ".rels", ".vml")):
                _conferir_xml(p.filename, zf.read(p))


def _conferir_xml(nome, conteudo):
    """Um .xlsx de verdade não tem DTD: <!DOCTYPE>/<!ENTITY> é "bomba de entidades" (XML bomb) ou XXE.

    Barramos aqui, sem depender do defusedxml estar instalado. Também limita a quantidade de células e
    linhas de uma aba, pois milhões de células vazias gastariam minutos e gigabytes de memória no openpyxl.
    """
    if b"<!doctype" in conteudo[:4096].lower() or b"<!entity" in conteudo.lower():
        raise ErroPlanilha("O arquivo tem declarações XML não permitidas (arquivo suspeito)")
    if nome.startswith("xl/worksheets/"):
        if conteudo.count(b"<c ") + conteudo.count(b"<c>") > MAX_CELULAS_POR_PARTE or conteudo.count(b"<row") > MAX_LINHAS_POR_PARTE:
            raise ErroPlanilha("Aba com células demais (arquivo suspeito)")
