"""app/routes.py — Rotas da API e páginas."""

from datetime import date, datetime, timedelta
from pathlib import Path

from functools import wraps

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

import json

from app import db
from app.models import (
    ConfigProjeto,
    Extremo,
    Programacao,
    Realocacao,
    TabuaMares,
    Trecho,
    ValoresPadrao,
)
from core.extractor import extract_extremos, extract_metadata, validate_extremos
from core.processor import calcular_trechos

bp = Blueprint("main", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monday_of(d: date) -> date:
    """Retorna a segunda-feira da semana de `d`."""
    return d - timedelta(days=d.weekday())


def _trecho_to_dict(trecho: Trecho) -> dict:
    """Serializa Trecho + Programacao para JSON."""
    prog = trecho.programacao
    return {
        "id": trecho.id,
        "data": trecho.data.strftime("%d/%m/%Y"),
        "status": trecho.status,
        "amplitude": trecho.amplitude,
        "inicio": trecho.inicio,
        "fim": trecho.fim,
        "inicio_real": trecho.inicio_real,
        "fim_real": trecho.fim_real,
        "fim_dia_seguinte": trecho.fim_dia_seguinte,
        "e1_hora": trecho.e1_hora,
        "e1_mare": trecho.e1_mare,
        "e2_hora": trecho.e2_hora,
        "e2_mare": trecho.e2_mare,
        "mes": trecho.mes,
        # Programação (pode ser None)
        "area": prog.area if prog else None,
        "kp_inicio": prog.kp_inicio if prog else None,
        "kp_final": prog.kp_final if prog else None,
        "linha_de": prog.linha_de if prog else None,
        "linha_ate": prog.linha_ate if prog else None,
        "sistema_dragagem": prog.sistema_dragagem if prog else None,
        "observacoes": prog.observacoes if prog else None,
        "dist_fundo": prog.dist_fundo if prog else None,
        "ang_tela": prog.ang_tela if prog else None,
        "ang_nozzle": prog.ang_nozzle if prog else None,
        "direcao": prog.direcao if prog else None,
        "vel_frente": prog.vel_frente if prog else None,
        "vel_re": prog.vel_re if prog else None,
        "consumo_diesel": prog.consumo_diesel if prog else None,
    }


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------


def requer_gerente(f):
    """Decorator: exige sessão de gerente."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("gerente"):
            return redirect(url_for("main.gerente"))
        return f(*args, **kwargs)
    return wrapper


def requer_comandante(f):
    """Decorator: exige sessão de comandante."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("comandante"):
            return redirect(url_for("main.comandante"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------


@bp.route("/")
def index():
    return redirect(url_for("main.gerente"))


@bp.route("/gerente", methods=["GET", "POST"])
def gerente():
    if request.method == "POST":
        if request.form.get("senha") == current_app.config["SENHA_GERENTE"]:
            session["gerente"] = True
            return redirect(url_for("main.gerente"))
        return render_template("login_gerente.html", error="Senha incorreta")
    if not session.get("gerente"):
        return render_template("login_gerente.html")
    return render_template("index.html")


@bp.route("/gerente/logout")
def gerente_logout():
    session.pop("gerente", None)
    return redirect(url_for("main.gerente"))


@bp.route("/comandante", methods=["GET", "POST"])
def comandante():
    if request.method == "POST":
        if request.form.get("senha") == current_app.config["SENHA_COMANDANTE"]:
            session["comandante"] = True
            return redirect(url_for("main.comandante"))
        return render_template("login_comandante.html", error="Senha incorreta")
    if not session.get("comandante"):
        return render_template("login_comandante.html")
    return render_template("comandante.html")


@bp.route("/comandante/logout")
def comandante_logout():
    session.pop("comandante", None)
    return redirect(url_for("main.comandante"))


@bp.route("/config")
@requer_gerente
def config_page():
    return render_template("config.html")


@bp.route("/visualizar")
def visualizar_page():
    return render_template("visualizar.html")


# ---------------------------------------------------------------------------
# API — Importação
# ---------------------------------------------------------------------------


@bp.route("/api/importar", methods=["POST"])
@requer_gerente
def api_importar():
    """Upload PDF da tábua → extrai + processa + salva no banco."""
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Arquivo deve ser PDF"}), 400

    # Salvar PDF
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = upload_dir / filename
    file.save(str(filepath))

    # Extrair metadados e extremos
    meta = extract_metadata(filepath)
    extremos = extract_extremos(filepath)
    warnings = validate_extremos(extremos)

    # Verificar se já existe tábua para este ano
    ano = meta.get("ano", datetime.today().year)
    existing = TabuaMares.query.filter_by(ano=ano).first()
    if existing:
        # Remover dados antigos (cascade deleta extremos, trechos, programação)
        db.session.delete(existing)
        db.session.flush()

    # Salvar tábua
    tabua = TabuaMares(
        ano=ano,
        local=meta.get("local"),
        estado=meta.get("estado"),
        latitude=meta.get("latitude"),
        longitude=meta.get("longitude"),
        fuso=meta.get("fuso"),
        nivel_medio=meta.get("nivel_medio"),
        arquivo_nome=filename,
    )
    db.session.add(tabua)
    db.session.flush()  # gera tabua.id

    # Salvar extremos
    for e in extremos:
        d = datetime.strptime(e["data"], "%d/%m/%Y").date()
        db.session.add(Extremo(
            tabua_id=tabua.id,
            data=d,
            hora=e["hora"],
            altura_m=e["mare"],
        ))

    # Calcular e salvar trechos
    trechos_data = calcular_trechos(extremos)
    for t in trechos_data:
        d = datetime.strptime(t["data"], "%d/%m/%Y").date()
        db.session.add(Trecho(
            tabua_id=tabua.id,
            data=d,
            status=t["status"],
            amplitude=t["amplitude"],
            inicio=t["inicio"],
            fim=t["fim"],
            inicio_real=t["inicio_real"],
            fim_real=t["fim_real"],
            fim_dia_seguinte=t["fim_dia_seguinte"],
            e1_hora=t["e1_hora"],
            e1_mare=t["e1_mare"],
            e2_hora=t["e2_hora"],
            e2_mare=t["e2_mare"],
            mes=t["mes"],
        ))

    db.session.commit()

    return jsonify({
        "message": f"Importado: {len(extremos)} extremos, {len(trechos_data)} trechos",
        "ano": ano,
        "extremos": len(extremos),
        "trechos": len(trechos_data),
        "avisos": warnings,
    })


# ---------------------------------------------------------------------------
# API — Trechos da semana
# ---------------------------------------------------------------------------


@bp.route("/api/trechos")
def api_trechos():
    """Retorna trechos da semana com dados operacionais.

    Query params:
        semana: YYYY-MM-DD (qualquer dia da semana; default = hoje)
    """
    semana_str = request.args.get("semana")
    if semana_str:
        ref = datetime.strptime(semana_str, "%Y-%m-%d").date()
    else:
        ref = date.today()

    seg = _monday_of(ref)
    dom = seg + timedelta(days=6)

    trechos = (
        Trecho.query
        .filter(Trecho.data >= seg, Trecho.data <= dom)
        .order_by(Trecho.data, Trecho.inicio)
        .all()
    )

    return jsonify({
        "semana_inicio": seg.strftime("%Y-%m-%d"),
        "semana_fim": dom.strftime("%Y-%m-%d"),
        "trechos": [_trecho_to_dict(t) for t in trechos],
    })


# ---------------------------------------------------------------------------
# API — Programação (atualizar dados operacionais)
# ---------------------------------------------------------------------------


PROG_FIELDS = [
    "area", "kp_inicio", "kp_final", "linha_de", "linha_ate",
    "sistema_dragagem", "observacoes", "dist_fundo", "ang_tela",
    "ang_nozzle", "direcao", "vel_frente", "vel_re", "consumo_diesel",
]

KP_RANGES = [
    (0, 50, ["Berço I", "Berço II", "Berco I", "Berco II"]),
    (50, 800, ["Bacia"]),
    (800, 3000, ["TR3"]),
    (3000, 4500, ["TR2"]),
    (4500, 6000, ["TR1"]),
]


def _validate_kp(area: str | None, kp_inicio: str | None, kp_final: str | None) -> list[str]:
    """Valida KP vs Area. Retorna lista de warnings (vazia = OK)."""
    if not area:
        return []
    expected = None
    for mn, mx, areas in KP_RANGES:
        if area in areas:
            expected = (mn, mx)
            break
    if not expected:
        return []
    warnings = []
    for label, val in [("KP Inicio", kp_inicio), ("KP Final", kp_final)]:
        if val:
            try:
                v = float(val)
                if v < expected[0] or v > expected[1]:
                    warnings.append(
                        f"{label} ({val}) fora do range esperado para {area} ({expected[0]}-{expected[1]})"
                    )
            except ValueError:
                pass
    return warnings


@bp.route("/api/programacao/<int:trecho_id>", methods=["PUT"])
@requer_gerente
def api_programacao(trecho_id: int):
    """Atualiza dados operacionais de um trecho."""
    trecho = Trecho.query.get_or_404(trecho_id)
    data = request.get_json(force=True)

    prog = trecho.programacao
    if prog is None:
        prog = Programacao(trecho_id=trecho.id)
        db.session.add(prog)

    for field in PROG_FIELDS:
        if field in data:
            setattr(prog, field, data[field])

    db.session.commit()

    warnings = _validate_kp(prog.area, prog.kp_inicio, prog.kp_final)
    result = {"message": "OK", "trecho_id": trecho_id}
    if warnings:
        result["warnings"] = warnings
    return jsonify(result)


# ---------------------------------------------------------------------------
# API — Aplicar padrões na semana
# ---------------------------------------------------------------------------


@bp.route("/api/aplicar-padroes", methods=["POST"])
@requer_gerente
def api_aplicar_padroes():
    """Aplica valores padrão nos trechos da semana."""
    data = request.get_json(force=True)
    semana_str = data.get("semana")
    if not semana_str:
        return jsonify({"error": "Parâmetro 'semana' obrigatório"}), 400

    ref = datetime.strptime(semana_str, "%Y-%m-%d").date()
    seg = _monday_of(ref)
    dom = seg + timedelta(days=6)

    padrao = ValoresPadrao.query.first()
    if not padrao:
        return jsonify({"error": "Valores padrão não configurados"}), 404

    trechos = Trecho.query.filter(Trecho.data >= seg, Trecho.data <= dom).all()

    padrao_fields = {
        "sistema_dragagem": padrao.sistema_dragagem,
        "dist_fundo": padrao.dist_fundo,
        "ang_tela": padrao.ang_tela,
        "ang_nozzle": padrao.ang_nozzle,
        "direcao": padrao.direcao,
        "vel_frente": padrao.vel_frente,
        "vel_re": padrao.vel_re,
        "consumo_diesel": padrao.consumo_diesel,
    }

    count = 0
    for trecho in trechos:
        prog = trecho.programacao
        if prog is None:
            prog = Programacao(trecho_id=trecho.id)
            db.session.add(prog)
        for field, val in padrao_fields.items():
            setattr(prog, field, val)
        count += 1

    db.session.commit()
    return jsonify({"message": f"Padrões aplicados em {count} trechos"})


# ---------------------------------------------------------------------------
# API — Limpar dados operacionais da semana
# ---------------------------------------------------------------------------


@bp.route("/api/limpar-semana", methods=["POST"])
@requer_gerente
def api_limpar_semana():
    """Remove todos os dados de programação dos trechos da semana."""
    data = request.get_json(force=True)
    semana_str = data.get("semana")
    if not semana_str:
        return jsonify({"error": "Parâmetro 'semana' obrigatório"}), 400

    ref = datetime.strptime(semana_str, "%Y-%m-%d").date()
    seg = _monday_of(ref)
    dom = seg + timedelta(days=6)

    trechos = Trecho.query.filter(Trecho.data >= seg, Trecho.data <= dom).all()
    trecho_ids = [t.id for t in trechos]

    count = 0
    for trecho in trechos:
        if trecho.programacao:
            db.session.delete(trecho.programacao)
            count += 1

    # Limpar histórico de realocações associado à semana
    if trecho_ids:
        Realocacao.query.filter(
            Realocacao.trecho_cancelado_id.in_(trecho_ids)
        ).delete(synchronize_session=False)

    db.session.commit()
    return jsonify({"message": f"Dados limpos de {count} trechos"})


# ---------------------------------------------------------------------------
# API — Cancelar trecho (comandante) com shift em cadeia
# ---------------------------------------------------------------------------


def _prog_to_dict(prog):
    """Extrai dados operacionais de uma Programacao como dict."""
    if not prog:
        return {f: None for f in PROG_FIELDS}
    return {f: getattr(prog, f, None) for f in PROG_FIELDS}


def _set_prog_fields(trecho, data_dict):
    """Define dados operacionais de um trecho a partir de um dict."""
    prog = trecho.programacao
    if prog is None:
        prog = Programacao(trecho_id=trecho.id)
        db.session.add(prog)
    for f in PROG_FIELDS:
        setattr(prog, f, data_dict.get(f))
    return prog


@bp.route("/api/cancelar-trecho", methods=["POST"])
@requer_comandante
def api_cancelar_trecho():
    """Cancela um trecho e desloca dados operacionais do mesmo status em cadeia."""
    data = request.get_json(force=True)
    trecho_id = data.get("trecho_id")
    motivo = (data.get("motivo") or "").strip()

    if not trecho_id:
        return jsonify({"error": "trecho_id obrigatório"}), 400
    if not motivo:
        return jsonify({"error": "Motivo obrigatório"}), 400

    trecho = Trecho.query.get(trecho_id)
    if not trecho:
        return jsonify({"error": "Trecho não encontrado"}), 404

    prog = trecho.programacao
    if not prog or not prog.area:
        return jsonify({"error": "Trecho não possui dados operacionais"}), 400

    status = trecho.status  # EN ou VZ

    # Buscar todos os trechos do mesmo status a partir do cancelado (inclusive),
    # ordenados por data + hora de início
    all_same_status = (
        Trecho.query
        .filter(
            Trecho.status == status,
            Trecho.tabua_id == trecho.tabua_id,
            db.or_(
                Trecho.data > trecho.data,
                db.and_(Trecho.data == trecho.data, Trecho.id >= trecho.id),
            ),
        )
        .order_by(Trecho.data, Trecho.inicio)
        .all()
    )

    # Filtrar: o cancelado (primeiro) + apenas os seguintes com dados preenchidos
    affected = [all_same_status[0]]  # o trecho cancelado sempre entra
    for t in all_same_status[1:]:
        if t.programacao and t.programacao.area:
            affected.append(t)

    # Snapshot dos dados originais de todos os trechos afetados
    snapshot = []
    for t in affected:
        snapshot.append({
            "trecho_id": t.id,
            "data": t.data.strftime("%d/%m/%Y"),
            "inicio": t.inicio,
            "fim": t.fim,
            **_prog_to_dict(t.programacao),
        })

    # Shift: dados deslocam pra frente (cada trecho recebe os dados do anterior).
    # Percorrer do fim pro início para não sobrescrever dados ainda não copiados.
    for i in range(len(affected) - 1, 0, -1):
        prev_data = _prog_to_dict(affected[i - 1].programacao)
        _set_prog_fields(affected[i], prev_data)

    # Trecho cancelado (primeiro) fica vazio com observação do motivo
    _set_prog_fields(affected[0], {f: None for f in PROG_FIELDS})
    affected[0].programacao.observacoes = f"Trecho Cancelado: {motivo}"

    # Salvar histórico
    realocacao = Realocacao(
        trecho_cancelado_id=trecho.id,
        status_afetado=status,
        total_trechos_afetados=len(affected),
        dados_originais=json.dumps(snapshot, ensure_ascii=False),
        motivo=motivo,
    )
    db.session.add(realocacao)
    db.session.commit()

    return jsonify({
        "message": f"Dragagem cancelada. {len(affected)} trecho(s) {status} foram deslocados.",
        "trechos_afetados": len(affected),
    })


@bp.route("/api/realocacoes")
def api_realocacoes():
    """Lista realocações que afetam trechos da semana."""
    semana_str = request.args.get("semana")
    if semana_str:
        ref = datetime.strptime(semana_str, "%Y-%m-%d").date()
    else:
        ref = date.today()

    seg = _monday_of(ref)
    dom = seg + timedelta(days=6)

    # Buscar trechos da semana
    trecho_ids = [
        t.id for t in
        Trecho.query.filter(Trecho.data >= seg, Trecho.data <= dom).all()
    ]

    if not trecho_ids:
        return jsonify({"realocacoes": []})

    # Realocações cujo trecho cancelado está na semana
    realocacoes = (
        Realocacao.query
        .filter(Realocacao.trecho_cancelado_id.in_(trecho_ids))
        .order_by(Realocacao.realizado_em.desc())
        .all()
    )

    result = []
    for r in realocacoes:
        t = Trecho.query.get(r.trecho_cancelado_id)
        result.append({
            "id": r.id,
            "trecho_cancelado_id": r.trecho_cancelado_id,
            "trecho_data": t.data.strftime("%d/%m/%Y") if t else None,
            "trecho_inicio": t.inicio if t else None,
            "trecho_fim": t.fim if t else None,
            "status_afetado": r.status_afetado,
            "total_trechos_afetados": r.total_trechos_afetados,
            "dados_originais": json.loads(r.dados_originais),
            "motivo": r.motivo,
            "realizado_em": r.realizado_em.strftime("%d/%m/%Y %H:%M") if r.realizado_em else None,
        })

    return jsonify({"realocacoes": result})


# ---------------------------------------------------------------------------
# API — Config do projeto
# ---------------------------------------------------------------------------


@bp.route("/api/config", methods=["GET"])
def api_config_get():
    cfg = ConfigProjeto.query.first()
    if not cfg:
        cfg = ConfigProjeto()
        db.session.add(cfg)
        db.session.commit()
    return jsonify({
        "empresa": cfg.empresa,
        "vessel": cfg.vessel,
        "project": cfg.project,
        "site": cfg.site,
    })


@bp.route("/api/config", methods=["PUT"])
@requer_gerente
def api_config_put():
    cfg = ConfigProjeto.query.first()
    if not cfg:
        cfg = ConfigProjeto()
        db.session.add(cfg)

    data = request.get_json(force=True)
    for field in ("empresa", "vessel", "project", "site"):
        if field in data:
            setattr(cfg, field, data[field])

    db.session.commit()
    return jsonify({"message": "Config atualizada"})


# ---------------------------------------------------------------------------
# API — Valores padrão
# ---------------------------------------------------------------------------


@bp.route("/api/padroes", methods=["GET"])
def api_padroes_get():
    vp = ValoresPadrao.query.first()
    if not vp:
        vp = ValoresPadrao()
        db.session.add(vp)
        db.session.commit()
    return jsonify({
        "sistema_dragagem": vp.sistema_dragagem,
        "dist_fundo": vp.dist_fundo,
        "ang_tela": vp.ang_tela,
        "ang_nozzle": vp.ang_nozzle,
        "direcao": vp.direcao,
        "vel_frente": vp.vel_frente,
        "vel_re": vp.vel_re,
        "consumo_diesel": vp.consumo_diesel,
    })


@bp.route("/api/padroes", methods=["PUT"])
@requer_gerente
def api_padroes_put():
    vp = ValoresPadrao.query.first()
    if not vp:
        vp = ValoresPadrao()
        db.session.add(vp)

    data = request.get_json(force=True)
    for field in ("sistema_dragagem", "dist_fundo", "ang_tela", "ang_nozzle",
                  "direcao", "vel_frente", "vel_re", "consumo_diesel"):
        if field in data:
            setattr(vp, field, data[field])

    db.session.commit()
    return jsonify({"message": "Padroes atualizados"})


# ---------------------------------------------------------------------------
# API — Exportação
# ---------------------------------------------------------------------------


def _get_export_data(semana_str: str | None):
    """Helper: retorna (trechos_dict[], config_dict, seg_date) para export."""
    from core.exporter import exportar_excel, exportar_pdf  # noqa: F401

    if semana_str:
        ref = datetime.strptime(semana_str, "%Y-%m-%d").date()
    else:
        ref = date.today()

    seg = _monday_of(ref)
    dom = seg + timedelta(days=6)

    trechos = (
        Trecho.query
        .filter(Trecho.data >= seg, Trecho.data <= dom)
        .order_by(Trecho.data, Trecho.inicio)
        .all()
    )

    trechos_data = [_trecho_to_dict(t) for t in trechos]

    cfg = ConfigProjeto.query.first()
    config_data = {
        "empresa": cfg.empresa if cfg else "",
        "vessel": cfg.vessel if cfg else "",
        "project": cfg.project if cfg else "",
        "site": cfg.site if cfg else "",
    }

    return trechos_data, config_data, seg


@bp.route("/api/exportar/excel")
def api_exportar_excel():
    from core.exporter import exportar_excel

    trechos_data, config_data, seg = _get_export_data(request.args.get("semana"))
    buf = exportar_excel(trechos_data, config_data, seg)

    filename = f"Programacao_Dragagem_{seg.strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@bp.route("/api/exportar/pdf")
def api_exportar_pdf():
    from core.exporter import exportar_pdf

    trechos_data, config_data, seg = _get_export_data(request.args.get("semana"))
    buf = exportar_pdf(trechos_data, config_data, seg)

    filename = f"Programacao_Dragagem_{seg.strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
