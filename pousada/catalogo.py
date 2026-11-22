"""Catálogo de itens de consumo (Despesas): categorias, validação, ordem alfabética e gravação com log imutável.

O lançamento de despesa só ESCOLHE um item e a quantidade; descrição e preço unitário são COPIADOS para o lançamento
(congelados): mudar o preço depois não altera o histórico. Itens nunca são apagados (só desativados). Centavos inteiros.
Sem Flask aqui: quem decide o que cada perfil pode são as rotas (rotas_catalogo.py).
"""
import json
import unicodedata

from .despesas import Recusa, _inteiro, texto_validado
from .regras import MAX_DESPESA_UNIT

# chave -> (rótulo mostrado, categoria do lançamento de despesa). A 2ª coluna respeita o CHECK da migração 012.
CATEGORIAS = {"bebidas": ("Bebidas", "bar"), "porcoes": ("Porções", "restaurante"),
              "lavanderia": ("Lavanderia", "lavanderia"), "outros": ("Outros", "outros")}
CAMPOS = ("categoria", "grupo", "descricao", "preco_centavos")


def chave_ordem(texto):
    """Texto sem acentos, minúsculo e com espaços simples: base da ordem alfabética e da unicidade (Água = agua)."""
    sem = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sem.casefold().split())


def validar_item(corpo):
    """Corpo do POST/PUT -> dict limpo (categoria, grupo, descricao, preco_centavos). Texto livre passa pelo detector de cartão."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    if not isinstance(corpo.get("categoria"), str) or corpo["categoria"] not in CATEGORIAS:
        raise Recusa("Categoria inválida")
    grupo = corpo.get("grupo")
    grupo = "" if grupo is None or (isinstance(grupo, str) and not grupo.strip()) else texto_validado(grupo, "o grupo", 2, 40)
    preco = corpo.get("preco_centavos")
    if not _inteiro(preco) or preco < 1:
        raise Recusa("Preço inválido (informe um valor maior que zero)")
    if preco > MAX_DESPESA_UNIT:
        raise Recusa("Preço acima do máximo permitido")
    return {"categoria": corpo["categoria"], "grupo": grupo, "descricao": texto_validado(corpo.get("descricao"), "a descrição", 2, 80),
            "preco_centavos": preco}


def _versao(v):
    if not _inteiro(v) or v < 1:
        raise Recusa("Informe a versão do item (recarregue a tela)", 400)
    return v


def validar_versao(corpo):
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    return _versao(corpo.get("versao"))


def publico(l, completo):
    """Linha do banco -> item da API. 'completo' (administrador) acrescenta ativo e versão."""
    d = {"id": l["id"], "categoria": l["categoria"], "categoria_rotulo": CATEGORIAS[l["categoria"]][0], "grupo": l["grupo"],
         "descricao": l["descricao"], "preco_centavos": l["preco_centavos"], "versao": l["versao"]}
    if completo:
        d["ativo"] = bool(l["ativo"])
    return d


def listar(con, so_ativos=True):
    """Itens em ordem alfabética determinística: categoria (pelo rótulo), grupo, descrição (sem acento), id."""
    linhas = con.execute("SELECT * FROM catalogo_item" + (" WHERE ativo=1" if so_ativos else "")).fetchall()
    return sorted(linhas, key=lambda l: (chave_ordem(CATEGORIAS[l["categoria"]][0]), l["grupo_ordem"], l["descricao_ordem"], l["id"]))


def obter(con, iid):
    return con.execute("SELECT * FROM catalogo_item WHERE id=?", (iid,)).fetchone()


def _estado(l):
    return {c: l[c] for c in CAMPOS} | {"ativo": l["ativo"]}


def _log(con, iid, acao, antes, depois, ator, momento):
    con.execute("INSERT INTO catalogo_log (item_id,acao,antes,depois,em,usuario_id,usuario_login,ip) VALUES (?,?,?,?,?,?,?,?)",
                (iid, acao, json.dumps(antes, ensure_ascii=False, sort_keys=True) if antes else None,
                 json.dumps(depois, ensure_ascii=False, sort_keys=True), momento.strftime("%Y-%m-%d %H:%M:%S"),
                 ator["id"], ator["login"], ator["ip"]))


def criar(con, d, ator, momento):
    cur = con.execute("INSERT INTO catalogo_item (categoria,grupo,descricao,preco_centavos,grupo_ordem,descricao_ordem,criado_em) "
                      "VALUES (?,?,?,?,?,?,?)", (d["categoria"], d["grupo"], d["descricao"], d["preco_centavos"], chave_ordem(d["grupo"]),
                                                  chave_ordem(d["descricao"]), momento.strftime("%Y-%m-%d %H:%M:%S")))
    _log(con, cur.lastrowid, "criado", None, dict(d, ativo=1), ator, momento)
    return cur.lastrowid


def _conferir_versao(l, versao):
    if l is None:
        raise Recusa("Item não encontrado", 404)
    if l["versao"] != versao:
        raise Recusa("Este item foi alterado por outra pessoa. Recarregue a tela e confira.", 409)


def editar(con, iid, d, versao, ator, momento):
    l = obter(con, iid)
    _conferir_versao(l, versao)
    con.execute("UPDATE catalogo_item SET categoria=?,grupo=?,descricao=?,preco_centavos=?,grupo_ordem=?,descricao_ordem=?,versao=versao+1 WHERE id=?",
                (d["categoria"], d["grupo"], d["descricao"], d["preco_centavos"], chave_ordem(d["grupo"]), chave_ordem(d["descricao"]), iid))
    _log(con, iid, "editado", _estado(l), dict(d, ativo=l["ativo"]), ator, momento)


def definir_ativo(con, iid, ativo, versao, ator, momento):
    l = obter(con, iid)
    _conferir_versao(l, versao)
    if bool(l["ativo"]) == ativo:
        raise Recusa("O item já está %s" % ("ativo" if ativo else "desativado"), 409)
    con.execute("UPDATE catalogo_item SET ativo=?, versao=versao+1 WHERE id=?", (1 if ativo else 0, iid))
    _log(con, iid, "reativado" if ativo else "desativado", _estado(l), dict(_estado(l), ativo=1 if ativo else 0), ator, momento)


def historico(con, iid, limite=100):
    return [{"id": r["id"], "acao": r["acao"], "em": r["em"], "por": r["usuario_login"],
             "antes": json.loads(r["antes"]) if r["antes"] else None, "depois": json.loads(r["depois"])}
            for r in con.execute("SELECT * FROM catalogo_log WHERE item_id=? ORDER BY id DESC LIMIT ?", (iid, limite))]
