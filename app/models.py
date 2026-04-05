"""app/models.py — Modelos SQLAlchemy (SQLite)."""

from datetime import datetime

from app import db


class TabuaMares(db.Model):
    """Metadados da importação da tábua de marés."""

    __tablename__ = "tabua_mares"

    id = db.Column(db.Integer, primary_key=True)
    ano = db.Column(db.Integer, nullable=False)
    local = db.Column(db.Text)
    estado = db.Column(db.Text)
    latitude = db.Column(db.Text)
    longitude = db.Column(db.Text)
    fuso = db.Column(db.Text)
    nivel_medio = db.Column(db.Float)
    arquivo_nome = db.Column(db.Text)
    importado_em = db.Column(db.DateTime, default=datetime.utcnow)

    extremos = db.relationship("Extremo", backref="tabua", cascade="all, delete-orphan")
    trechos = db.relationship("Trecho", backref="tabua", cascade="all, delete-orphan")


class Extremo(db.Model):
    """Dados brutos extraídos do PDF (um registro por extremo de maré)."""

    __tablename__ = "extremos"

    id = db.Column(db.Integer, primary_key=True)
    tabua_id = db.Column(db.Integer, db.ForeignKey("tabua_mares.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Text, nullable=False)  # "HH:MM"
    altura_m = db.Column(db.Float, nullable=False)


class Trecho(db.Model):
    """Trechos EN/VZ calculados."""

    __tablename__ = "trechos"

    id = db.Column(db.Integer, primary_key=True)
    tabua_id = db.Column(db.Integer, db.ForeignKey("tabua_mares.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    status = db.Column(db.Text, nullable=False)      # "EN" ou "VZ"
    amplitude = db.Column(db.Text, nullable=False)    # "4.90"
    inicio = db.Column(db.Text, nullable=False)       # arredondado "06:30"
    fim = db.Column(db.Text, nullable=False)          # arredondado "10:30"
    inicio_real = db.Column(db.Text, nullable=False)
    fim_real = db.Column(db.Text, nullable=False)
    fim_dia_seguinte = db.Column(db.Text, nullable=False)  # "S" ou "N"
    e1_hora = db.Column(db.Text)
    e1_mare = db.Column(db.Float)
    e2_hora = db.Column(db.Text)
    e2_mare = db.Column(db.Float)
    mes = db.Column(db.Integer)

    programacao = db.relationship("Programacao", backref="trecho", uselist=False,
                                  cascade="all, delete-orphan")


class Programacao(db.Model):
    """Dados operacionais preenchidos pelo gerente."""

    __tablename__ = "programacao"

    id = db.Column(db.Integer, primary_key=True)
    trecho_id = db.Column(db.Integer, db.ForeignKey("trechos.id"), unique=True, nullable=False)
    area = db.Column(db.Text)
    kp_inicio = db.Column(db.Text)
    kp_final = db.Column(db.Text)
    linha_de = db.Column(db.Text)
    linha_ate = db.Column(db.Text)
    sistema_dragagem = db.Column(db.Text)
    observacoes = db.Column(db.Text)
    dist_fundo = db.Column(db.Text)
    ang_tela = db.Column(db.Text)
    ang_nozzle = db.Column(db.Text)
    direcao = db.Column(db.Text)
    vel_frente = db.Column(db.Text)
    vel_re = db.Column(db.Text)
    consumo_diesel = db.Column(db.Text)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Realocacao(db.Model):
    """Histórico de cancelamentos feitos pelo comandante."""

    __tablename__ = "realocacoes"

    id = db.Column(db.Integer, primary_key=True)
    trecho_cancelado_id = db.Column(db.Integer, db.ForeignKey("trechos.id"), nullable=False)
    status_afetado = db.Column(db.Text, nullable=False)       # "EN" ou "VZ"
    total_trechos_afetados = db.Column(db.Integer, nullable=False)
    dados_originais = db.Column(db.Text, nullable=False)       # JSON snapshot
    motivo = db.Column(db.Text, nullable=False)
    realizado_em = db.Column(db.DateTime, default=datetime.utcnow)

    trecho_cancelado = db.relationship("Trecho", backref="realocacoes")


class ConfigProjeto(db.Model):
    """Cabeçalho / metadados do projeto."""

    __tablename__ = "config_projeto"

    id = db.Column(db.Integer, primary_key=True)
    empresa = db.Column(db.Text, default="Vanoord - Serviços de Operações Maritimas Ltda.")
    vessel = db.Column(db.Text, default="Rio Madeira")
    project = db.Column(db.Text, default="35.4207")
    site = db.Column(db.Text, default="São Luís - MA")


class ValoresPadrao(db.Model):
    """Defaults operacionais aplicáveis em lote."""

    __tablename__ = "valores_padrao"

    id = db.Column(db.Integer, primary_key=True)
    sistema_dragagem = db.Column(db.Text, default="EH")
    dist_fundo = db.Column(db.Text, default="0,1 a 0,2")
    ang_tela = db.Column(db.Text, default="±0")
    ang_nozzle = db.Column(db.Text, default="±75°")
    direcao = db.Column(db.Text, default="")
    vel_frente = db.Column(db.Text, default="1.5")
    vel_re = db.Column(db.Text, default="1.5")
    consumo_diesel = db.Column(db.Text, default="0")
