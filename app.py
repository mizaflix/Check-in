import os
from datetime import datetime, date, timedelta
import sqlite3
import uuid
import re
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import event, inspect, text, or_

# Carrega .env em desenvolvimento local, sem exigir dotenv no servidor.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import urllib.request


app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave_secreta_checkkids_ipjardim')

database_url = os.getenv(
    'DATABASE_URL',
    'sqlite:///banco.db'
)

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config['SQLALCHEMY_DATABASE_URI'] = database_url

if database_url.startswith('sqlite'):

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'timeout': 60,
            'check_same_thread': False
        },
        'pool_pre_ping': True
    }

else:

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True
    }

# Fotos armazenadas localmente na pasta static/uploads por padrão.
# Em VPS/Docker, mantenha essa pasta em um volume persistente.
UPLOAD_FOLDER_CONFIG = os.getenv('UPLOAD_FOLDER', '').strip()
UPLOAD_FOLDER = os.path.abspath(
    UPLOAD_FOLDER_CONFIG or os.path.join(app.root_path, 'static', 'uploads')
)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8 MB por requisição
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MESES_PT = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

# ==========================================================
# EVOLUTION API / WHATSAPP
# ==========================================================
EVOLUTION_API_URL      = os.getenv('EVOLUTION_API_URL', '').strip().rstrip('/')
EVOLUTION_API_KEY      = os.getenv('EVOLUTION_API_KEY', '').strip()
EVOLUTION_INSTANCE     = os.getenv('EVOLUTION_INSTANCE', '').strip()


def normalizar_telefone_brasil(telefone):
    """Converte telefone brasileiro para E.164 sem o '+' (55XXXXXXXXXXX)."""
    digitos = re.sub(r'\D', '', telefone or '')

    if digitos.startswith('55') and len(digitos) in (12, 13):
        return digitos

    if len(digitos) in (10, 11):
        return '55' + digitos

    return None


def evolution_configurado():
    return bool(EVOLUTION_API_URL and EVOLUTION_API_KEY and EVOLUTION_INSTANCE)


def enviar_whatsapp(telefone, nome_crianca, nome_turma):
    """
    Envia um alerta para o responsável pelo WhatsApp via Evolution API v2.

    Endpoint: POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}
    Header:   apikey: {EVOLUTION_API_KEY}
    Body:     { "number": "55...", "text": "..." }
    """
    if not evolution_configurado():
        return False, 'Evolution API não configurada no ambiente.'

    destino = normalizar_telefone_brasil(telefone)
    if not destino:
        return False, 'Número de WhatsApp inválido ou ausente.'

    texto = (
        f'🚨 Atenção! O responsável por {nome_crianca} '
        f'precisa comparecer à sala {nome_turma}. '
        'Por favor, dirija-se à sala assim que possível.'
    )

    payload = json.dumps({
        'number': destino,
        'text': texto,
    }).encode('utf-8')

    url = f'{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}'

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'apikey': EVOLUTION_API_KEY,
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            corpo = resp.read().decode('utf-8')
            dados = json.loads(corpo)

        print('=' * 60)
        print('WHATSAPP ENVIADO VIA EVOLUTION API')
        print('Destino:', destino)
        print('Resposta:', dados)
        print('=' * 60)

        # Evolution retorna {"key": {"id": "..."}, "status": "PENDING"} em sucesso
        message_id = (dados.get('key') or {}).get('id') or dados.get('id', 'ok')
        return True, message_id

    except urllib.error.HTTPError as e:
        corpo = e.read().decode('utf-8', errors='replace')
        print('=' * 60)
        print('ERRO EVOLUTION API / WHATSAPP')
        print('Status HTTP:', e.code)
        print('Corpo:', corpo)
        print('=' * 60)
        return False, f'HTTP {e.code}: {corpo}'

    except Exception as e:
        print('=' * 60)
        print('ERRO AO ENVIAR WHATSAPP')
        print(repr(e))
        print('=' * 60)
        return False, repr(e)



def salvar_foto(arquivo, prefixo):
    """Salva a foto localmente em UPLOAD_FOLDER e retorna apenas o nome do arquivo."""
    if not arquivo or not arquivo.filename:
        return 'default.png'

    nome_original = secure_filename(arquivo.filename)
    extensao = os.path.splitext(nome_original)[1].lower()
    if extensao not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Formato de imagem não permitido. Use JPG, PNG, GIF ou WEBP.')

    tipo = (getattr(arquivo, 'mimetype', '') or '').lower()
    if tipo and not tipo.startswith('image/'):
        raise ValueError('O arquivo enviado não parece ser uma imagem válida.')

    nome_arquivo = f"{prefixo}_{uuid.uuid4().hex}{extensao}"
    destino = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)

    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        arquivo.stream.seek(0)
        arquivo.save(destino)
        if not os.path.isfile(destino) or os.path.getsize(destino) == 0:
            raise OSError('O arquivo enviado ficou vazio após o salvamento.')
    except Exception as erro:
        try:
            if os.path.exists(destino):
                os.remove(destino)
        except OSError:
            pass
        print('[UPLOAD] Falha ao salvar imagem localmente:', repr(erro))
        raise RuntimeError(
            'Não foi possível salvar a imagem na pasta de uploads. '
            'Verifique as permissões de escrita de static/uploads.'
        ) from erro

    return nome_arquivo


@app.template_global('url_foto')
def url_foto(referencia):
    """Converte nome de arquivo local em URL; usa avatar padrão se não existir."""
    if not referencia or str(referencia).strip() in {'default.png', 'None'}:
        return url_for('static', filename='img/avatar-default.svg')

    referencia = str(referencia).strip()
    # Compatibilidade com URLs externas antigas; novas fotos são sempre locais.
    if referencia.startswith(('https://', 'http://')):
        return referencia

    return url_for('uploaded_file', filename=os.path.basename(referencia))


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve arquivos da pasta local de uploads."""
    nome_seguro = os.path.basename(filename)
    caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
    if not os.path.isfile(caminho):
        return redirect(url_for('static', filename='img/avatar-default.svg'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], nome_seguro)

def formatar_mes_codigo(mes_codigo):
    try:
        ano, mes = [int(parte) for parte in mes_codigo.split('-')]
        if mes < 1 or mes > 12:
            raise ValueError
        return date(ano, mes, 1), f"{MESES_PT[mes - 1]}/{ano}"
    except (ValueError, TypeError):
        raise ValueError('Mês de referência inválido. Use o formato YYYY-MM.')

def domingos_do_mes(mes_codigo, limite=4):
    primeiro_dia, _ = formatar_mes_codigo(mes_codigo)
    deslocamento = (6 - primeiro_dia.weekday()) % 7
    primeiro_domingo = primeiro_dia + timedelta(days=deslocamento)
    return [primeiro_domingo + timedelta(days=7 * i) for i in range(limite)]

def professor_disponivel_no_dia(professor, data, turno):
    """Verifica disponibilidade para uma data/turno, aceitando formatos antigos."""
    disponibilidade = professor.disponibilidade_dias or ''
    tokens = {item.strip() for item in disponibilidade.split(',') if item.strip()}

    if isinstance(data, date):
        data_iso = data.isoformat()
        data_label = data.strftime('%d/%m')
    else:
        data_iso = str(data)
        try:
            data_label = date.fromisoformat(data_iso).strftime('%d/%m')
        except ValueError:
            data_label = data_iso

    # Formato atual: YYYY-MM-DD|Turno
    if f"{data_iso}|{turno}" in tokens:
        return True

    # Compatibilidade com o formato anterior: DD/MM|Turno
    if f"{data_label}|{turno}" in tokens:
        return True

    # Compatibilidade com o formato antigo que salvava apenas o turno.
    return turno in tokens

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = (
    "Por favor, faça login para acessar esta página."
)

# ==========================================
# MODELOS DO BANCO DE DADOS
# ==========================================
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=True)
    senha_hash = db.Column(db.String(200), nullable=False)
    # Contas de equipe criadas pela administração precisam trocar a senha inicial.
    precisa_trocar_senha = db.Column(
        db.Boolean, nullable=False, default=False, server_default=text('false')
    )
    
    is_admin = db.Column(db.Boolean, default=False)
    is_professor = db.Column(db.Boolean, default=False)
    
    # NOVOS CAMPOS DO PERFIL DO PROFESSOR
    cpf = db.Column(db.String(14), nullable=True)
    data_nascimento = db.Column(db.String(10), nullable=True)
    sexo = db.Column(db.String(20), nullable=True)
    cep = db.Column(db.String(10), nullable=True)
    foto_perfil = db.Column(db.String(255), default='default.png')
    
    # Campos de escala/função
    funcao_papeis = db.Column(db.String(20), default='professor') 
    disponibilidade_dias = db.Column(db.String(200), nullable=True)
    classes_preferidas = db.Column(db.String(100), nullable=True)
    
    # NOVA TRAVA DE SEGURANÇA:
    pode_editar_escala = db.Column(db.Boolean, default=False) 
    
    criancas = db.relationship('Crianca', backref='responsavel', lazy=True)

    whatsapp_opt_in = db.Column(
    db.Boolean,
    nullable=False,
    default=False,
    server_default='false'
)
class Responsavel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), nullable=False)
    data_nascimento = db.Column(db.String(10), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    vinculo = db.Column(db.String(50), nullable=False)
    endereco = db.Column(db.String(200), nullable=True)
    foto_url = db.Column(db.String(200), nullable=True, default='default.png')
    whatsapp_opt_in = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default='false'
    )

class Crianca(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    data_nascimento = db.Column(db.String(20), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    alergias_condicoes = db.Column(db.String(200), nullable=True)
    foto_url = db.Column(db.String(200), nullable=True, default='default.png')
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    checkins = db.relationship('Checkin', backref='crianca', lazy=True)

    @property
    def esta_presente(self):
        checkin_ativo = Checkin.query.filter_by(crianca_id=self.id, data_hora_saida=None).first()
        return checkin_ativo is not None

class Turma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_classe = db.Column(db.String(100), nullable=False)
    dia_aula = db.Column(db.String(50), nullable=True)
    numeracao_escala = db.Column(db.String(20), nullable=True)

    professor_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=True
    )

    auxiliar_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=True
    )

    responsabilidade = db.Column(
        db.String(50),
        default='Professor Titular'
    )

    disponibilidade = db.Column(db.String(50))
    turno = db.Column(db.String(50))
    status = db.Column(db.String(20), default='fechada')

    professor_rel = db.relationship(
        'Usuario',
        foreign_keys=[professor_id]
    )

    auxiliar_rel = db.relationship(
        'Usuario',
        foreign_keys=[auxiliar_id]
    )

    checkins = db.relationship(
        'Checkin',
        backref='turma',
        lazy=True
    )

class Checkin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crianca_id = db.Column(db.Integer, db.ForeignKey('crianca.id'), nullable=False)
    turma_id = db.Column(db.Integer, db.ForeignKey('turma.id'), nullable=True) # Vínculo com a sala
    data_hora_entrada = db.Column(db.DateTime, default=datetime.utcnow)
    data_hora_saida = db.Column(db.DateTime, nullable=True)

class Notificacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False) # ID do Pai/Mãe que vai receber
    mensagem = db.Column(db.String(255), nullable=False)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)
    lida = db.Column(db.Boolean, default=False)

@app.after_request
def desativar_cache_paginas_autenticadas(response):
    if current_user.is_authenticated:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.before_request
def exigir_troca_de_senha_inicial():
    """Bloqueia o restante do sistema até a equipe trocar a senha inicial."""
    if not current_user.is_authenticated:
        return None

    if not getattr(current_user, 'precisa_trocar_senha', False):
        return None

    endpoints_liberados = {
        'trocar_senha_inicial',
        'logout',
        'static',
        'uploaded_file',
    }
    if request.endpoint in endpoints_liberados:
        return None

    return redirect(url_for('trocar_senha_inicial'))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


def usuario_pode_gerenciar_turma(turma):
    """Permite ao admin, professor titular ou auxiliar gerenciar a turma."""
    return (
        current_user.is_admin
        or turma.professor_id == current_user.id
        or turma.auxiliar_id == current_user.id
    )


# ==========================================
# ROTAS DO SISTEMA
# ==========================================

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and request.method == 'POST':
        logout_user()

    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        user = Usuario.query.filter_by(email=email).first()

        if user and check_password_hash(user.senha_hash, senha):
            login_user(user)
            if getattr(user, 'precisa_trocar_senha', False):
                return redirect(url_for('trocar_senha_inicial'))
            return redirect(url_for('dashboard'))
        else:
            flash('E-mail ou senha inválidos.', 'danger')

    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        # O cadastro público cria exclusivamente contas de responsáveis.
        # Qualquer campo perfil enviado manualmente pelo navegador é ignorado.

        # Validação
        if not email or not senha:
            flash('Preencha o e-mail e a senha.', 'danger')
            return redirect(url_for('cadastro'))

        # Verifica se já existe
        user_existente = Usuario.query.filter_by(email=email).first()

        if user_existente:
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('cadastro'))

        try:
            senha_criptografada = generate_password_hash(senha)

            novo_usuario = Usuario(
                nome='Novo Usuário',
                email=email,
                senha_hash=senha_criptografada,
                is_admin=False,
                is_professor=False,
                precisa_trocar_senha=False
            )

            db.session.add(novo_usuario)

            # Commit protegido
            db.session.commit()

            # Login somente após salvar com sucesso
            login_user(novo_usuario)

            return redirect(url_for('finalizar_cadastro'))

        except Exception as e:
            db.session.rollback()

            print("=" * 60)
            print("ERRO NO CADASTRO")
            print(repr(e))
            print("=" * 60)

            flash(
                'Não foi possível concluir o cadastro. '
                'Tente novamente.',
                'danger'
            )

            return redirect(url_for('cadastro'))

    return render_template('cadastro.html')

@app.route('/finalizar_cadastro', methods=['GET', 'POST'])
@login_required
def finalizar_cadastro():

    if request.method == 'POST':

        current_user.nome = request.form.get('nome')
        current_user.telefone = request.form.get('telefone')
        current_user.whatsapp_opt_in = (
            request.form.get('whatsapp_opt_in') == 'on'
        )

        try:
            foto_nome = salvar_foto(request.files.get('foto'), 'responsavel')
        except (ValueError, RuntimeError) as erro:
            flash(str(erro), 'danger')
            return redirect(url_for('finalizar_cadastro'))

        current_user.foto_perfil = foto_nome

        responsavel_principal = Responsavel(
            usuario_id=current_user.id,
            nome=request.form.get('nome'),
            cpf=request.form.get('cpf'),
            data_nascimento=request.form.get('data_nascimento'),
            sexo=request.form.get('sexo'),
            telefone=request.form.get('telefone'),
            vinculo=request.form.get('vinculo'),
            endereco=request.form.get('endereco'),
            foto_url=foto_nome
        )

        db.session.add(responsavel_principal)

        db.session.commit()

        return redirect(url_for('dashboard'))

    return render_template('finalizar_cadastro.html')

@app.route('/trocar-senha-inicial', methods=['GET', 'POST'])
@login_required
def trocar_senha_inicial():
    if not getattr(current_user, 'precisa_trocar_senha', False):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        senha = request.form.get('senha', '')
        confirmar = request.form.get('confirmar_senha', '')

        if len(senha) < 8:
            flash('A nova senha deve ter pelo menos 8 caracteres.', 'danger')
        elif senha != confirmar:
            flash('A confirmação da senha não confere.', 'danger')
        elif check_password_hash(current_user.senha_hash, senha):
            flash('Escolha uma senha diferente da senha inicial.', 'danger')
        else:
            current_user.senha_hash = generate_password_hash(senha)
            current_user.precisa_trocar_senha = False
            db.session.commit()
            flash('Senha atualizada. Bem-vindo(a) ao CheckKids!', 'success')
            return redirect(url_for('dashboard'))

    return render_template('trocar_senha_inicial.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Administradores sempre entram primeiro na área administrativa, mesmo
    # quando também possuem perfil de professor/auxiliar.
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    if current_user.is_professor:
        return redirect(url_for('dashboard_professor'))

    responsavel = Responsavel.query.filter_by(usuario_id=current_user.id).first()
    criancas = Crianca.query.filter_by(usuario_id=current_user.id).all()
    
    # Busca alertas urgentes enviados pelos professores para este pai/mãe
    alertas = Notificacao.query.filter_by(
        usuario_id=current_user.id,
        lida=False
    ).order_by(Notificacao.data_hora.desc()).all()
    qtd_notificacoes = len(alertas)
    
    return render_template(
        'dashboard.html',
        responsavel=responsavel,
        criancas=criancas,
        alertas=alertas,
        qtd_notificacoes=qtd_notificacoes
    )

# Rota simples para o pai marcar o alerta como visto/lido
@app.route('/marcar_notificacao_lida/<int:notif_id>', methods=['POST'])
@login_required
def marcar_notificacao_lida(notif_id):
    notif = Notificacao.query.get_or_404(notif_id)
    if notif.usuario_id != current_user.id:
        return jsonify({'erro': 'Acesso negado'}), 403

    notif.lida = True
    db.session.commit()
    return redirect(url_for('notificacoes'))

# ==========================================
# FLUXO EXCLUSIVO DO PROFESSOR
# ==========================================
@app.route('/cadastro_professor_perfil', methods=['GET', 'POST'])
@login_required
def cadastro_professor_perfil():
    # Esta tela só complementa o perfil de quem já foi autorizado pelo admin.
    if not current_user.is_professor and not current_user.is_admin:
        flash('Somente professores cadastrados pela administração podem acessar esta área.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        current_user.nome = request.form.get('nome')
        current_user.cpf = request.form.get('cpf')
        current_user.data_nascimento = request.form.get('data_nascimento')
        current_user.sexo = request.form.get('sexo')
        current_user.telefone = request.form.get('telefone')
        current_user.cep = request.form.get('cep')
        
        # Salva a foto de perfil na pasta local de uploads.
        foto = request.files.get('foto')
        if foto and foto.filename:
            try:
                current_user.foto_perfil = salvar_foto(foto, 'professor')
            except (ValueError, RuntimeError) as erro:
                db.session.rollback()
                flash(str(erro), 'danger')
                return redirect(url_for('cadastro_professor_perfil'))

        db.session.commit()
        flash('Perfil de professor cadastrado com sucesso!', 'success')
        
        # Após o cadastro pessoal, redireciona para o dashboard (ou para a tela de disponibilidade)
        return redirect(url_for('dashboard_professor'))
        
    return render_template('cadastro_professor_perfil.html')
@app.route('/finalizar_cadastro_professor', methods=['GET', 'POST'])
@login_required
def finalizar_cadastro_professor():
    if not current_user.is_professor or not current_user.pode_editar_escala:
        flash('O preenchimento da escala está bloqueado no momento.', 'warning')
        return redirect(url_for('dashboard_professor'))

    if request.method == 'POST':
        mes_escala = request.form.get('mes_escala', '').strip()
        try:
            _, mes_label = formatar_mes_codigo(mes_escala)
            datas = domingos_do_mes(mes_escala)
        except ValueError:
            flash('Selecione um mês válido para preencher a escala.', 'danger')
            return redirect(url_for('finalizar_cadastro_professor'))

        disponibilidades = request.form.getlist('disponibilidade_dias')
        tokens_validos = {
            f"{domingo.isoformat()}|{turno}"
            for domingo in datas
            for turno in ('Manhã', 'Noite')
        }
        # Aceita também o formato DD/MM|Turno enviado por versões anteriores.
        tokens_validos |= {
            f"{domingo.strftime('%d/%m')}|{turno}"
            for domingo in datas
            for turno in ('Manhã', 'Noite')
        }
        disponibilidades = [item for item in disponibilidades if item in tokens_validos]

        # Converte automaticamente o formato antigo para o formato atual.
        mapa_antigo = {
            f"{domingo.strftime('%d/%m')}|{turno}": f"{domingo.isoformat()}|{turno}"
            for domingo in datas
            for turno in ('Manhã', 'Noite')
        }
        disponibilidades = [mapa_antigo.get(item, item) for item in disponibilidades]

        if not disponibilidades:
            flash('Selecione pelo menos um dia e turno em que você pode atuar.', 'warning')
            return redirect(url_for('finalizar_cadastro_professor', mes=mes_escala))

        classes_interest = request.form.getlist('classes_interest')
        if not classes_interest:
            flash('Selecione pelo menos uma classe de preferência.', 'warning')
            return redirect(url_for('finalizar_cadastro_professor', mes=mes_escala))

        current_user.nome = request.form.get('nome', current_user.nome).strip() or current_user.nome
        current_user.telefone = request.form.get('telefone', '').strip()
        current_user.funcao_papeis = request.form.get('funcao_papeis') or 'professor'
        current_user.classes_preferidas = ','.join(classes_interest)
        current_user.disponibilidade_dias = ','.join(disponibilidades)
        db.session.commit()

        flash(f'Disponibilidade de {mes_label} salva com sucesso!', 'success')
        return redirect(url_for('dashboard_professor'))

    mes_escala = request.args.get('mes', '').strip() or datetime.now().strftime('%Y-%m')
    try:
        _, mes_label = formatar_mes_codigo(mes_escala)
        datas = domingos_do_mes(mes_escala)
    except ValueError:
        mes_escala = datetime.now().strftime('%Y-%m')
        _, mes_label = formatar_mes_codigo(mes_escala)
        datas = domingos_do_mes(mes_escala)

    selecionados = {
        item.strip()
        for item in (current_user.disponibilidade_dias or '').split(',')
        if item.strip()
    }

    # Normaliza seleções antigas para que os checkboxes atuais apareçam marcados.
    for domingo in datas:
        for turno in ('Manhã', 'Noite'):
            antigo = f"{domingo.strftime('%d/%m')}|{turno}"
            atual = f"{domingo.isoformat()}|{turno}"
            if antigo in selecionados:
                selecionados.add(atual)

    classes_selecionadas = {
        item.strip()
        for item in (current_user.classes_preferidas or '').split(',')
        if item.strip()
    }

    return render_template(
        'cadastro_professor.html',
        classes_disponiveis=['3-4', '5-6', '7'],
        mes_escala=mes_escala,
        mes_label=mes_label,
        datas_semana=datas,
        disponibilidades_selecionadas=selecionados,
        classes_selecionadas=classes_selecionadas,
        funcao_atual=current_user.funcao_papeis or 'professor',
        telefone_atual=current_user.telefone or ''
    )


@app.route('/dashboard_professor')
@login_required
def dashboard_professor():
    if not current_user.is_professor and not current_user.is_admin:
        flash('Acesso restrito.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Busca todas as turmas onde o usuário atual foi alocado na escala automática (seja como professor ou auxiliar)
    turmas = Turma.query.filter(
        (Turma.professor_id == current_user.id) | (Turma.auxiliar_id == current_user.id)
    ).order_by(Turma.dia_aula, Turma.numeracao_escala, Turma.nome_classe).all()
    qtd_notificacoes = Notificacao.query.filter_by(
        usuario_id=current_user.id,
        lida=False
    ).count()

    return render_template(
        'dashboard_professor.html',
        turmas=turmas,
        qtd_notificacoes=qtd_notificacoes
    )

@app.route('/adicionar_classe', methods=['GET', 'POST'])
@login_required
def adicionar_classe():
    if not current_user.is_professor and not current_user.is_admin:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nova_turma = Turma(
            professor_id=current_user.id,
            nome_classe=request.form.get('classe'),
            responsabilidade=request.form.get('responsabilidade'),
            disponibilidade=request.form.get('disponibilidade'),
            turno=request.form.get('turno'),
            status='fechada'
        )
        db.session.add(nova_turma)
        db.session.commit()
        return redirect(url_for('dashboard_professor'))
        
    return render_template('adicionar_classe.html')

@app.route('/gerenciar_turma/<int:turma_id>/<string:acao>')
@login_required
def gerenciar_turma(turma_id, acao):
    turma = Turma.query.get_or_404(turma_id)

    if not usuario_pode_gerenciar_turma(turma):
        return jsonify({'erro': 'Acesso negado'}), 403

    if acao == 'iniciar_checkin':
        if turma.status != 'fechada':
            flash('Esta turma não está disponível para iniciar um novo check-in.', 'warning')
            return redirect(url_for('dashboard_professor'))

        turma.status = 'checkin'
        db.session.commit()
        return redirect(url_for('tela_qr', turma_id=turma.id))

    elif acao == 'iniciar_aula':
        if turma.status != 'checkin':
            flash('O check-in desta turma ainda não está aberto.', 'warning')
            return redirect(url_for('dashboard_professor'))

        turma.status = 'acontecendo'
        db.session.commit()
        return redirect(url_for('dashboard_professor'))

    elif acao == 'reabrir_checkin':
        if turma.status != 'acontecendo':
            flash('Só é possível reabrir o check-in depois de finalizá-lo e antes do check-out.', 'warning')
            return redirect(url_for('dashboard_professor'))

        # O QR Code continua usando o mesmo identificador da turma.
        turma.status = 'checkin'
        db.session.commit()
        flash('Check-in reaberto. O mesmo QR Code voltou a aceitar entradas.', 'success')
        return redirect(url_for('tela_qr', turma_id=turma.id))

    elif acao == 'iniciar_checkout':
        if turma.status != 'acontecendo':
            flash('O check-out só pode ser iniciado após o término do período de check-in.', 'warning')
            return redirect(url_for('dashboard_professor'))

        turma.status = 'checkout'
        db.session.commit()
        return redirect(url_for('tela_qr_checkout', turma_id=turma.id))

    elif acao == 'finalizar_checkout':
        if turma.status != 'checkout':
            flash('O check-out desta turma não está aberto.', 'warning')
            return redirect(url_for('dashboard_professor'))

        presentes = Checkin.query.filter_by(
            turma_id=turma.id,
            data_hora_saida=None
        ).count()

        if presentes > 0:
            flash(
                f'Ainda há {presentes} criança(s) presente(s). Realize todos os check-outs antes de concluir a turma.',
                'warning'
            )
            return redirect(url_for('tela_qr_checkout', turma_id=turma.id))

        turma.status = 'finalizada'
        db.session.commit()
        flash('Check-out concluído. A turma foi marcada como concluída.', 'success')
        return redirect(url_for('dashboard_professor'))

    elif acao == 'finalizar':
        # Compatibilidade com links antigos: agora "finalizar" inicia o check-out.
        return redirect(url_for('gerenciar_turma', turma_id=turma.id, acao='iniciar_checkout'))

    return jsonify({'erro': 'Ação inválida'}), 400


@app.route('/tela_qr/<int:turma_id>')
@login_required
def tela_qr(turma_id):
    turma = Turma.query.get_or_404(turma_id)

    if not usuario_pode_gerenciar_turma(turma):
        return jsonify({'erro': 'Acesso negado'}), 403

    if turma.status == 'checkout':
        return redirect(url_for('tela_qr_checkout', turma_id=turma.id))

    if turma.status == 'finalizada':
        return redirect(url_for('lista_presenca', turma_id=turma.id))

    if turma.status != 'checkin':
        return redirect(url_for('dashboard_professor'))

    qtd_presentes = Checkin.query.filter_by(
        turma_id=turma.id,
        data_hora_saida=None
    ).count()

    return render_template(
        'tela_qr.html',
        turma=turma,
        qtd_presentes=qtd_presentes,
        modo='checkin'
    )


@app.route('/api/turma/<int:turma_id>/contagem')
@login_required
def contagem_turma(turma_id):
    """Retorna a contagem atual para atualização leve da tela do QR Code."""
    turma = Turma.query.get_or_404(turma_id)

    if not usuario_pode_gerenciar_turma(turma):
        return jsonify({'erro': 'Acesso negado'}), 403

    qtd_presentes = Checkin.query.filter_by(
        turma_id=turma.id,
        data_hora_saida=None
    ).count()

    resposta = jsonify({
        'turma_id': turma.id,
        'status': turma.status,
        'qtd_presentes': qtd_presentes,
        'atualizado_em': datetime.utcnow().isoformat() + 'Z'
    })
    resposta.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resposta


@app.route('/tela_qr_checkout/<int:turma_id>')
@login_required
def tela_qr_checkout(turma_id):
    turma = Turma.query.get_or_404(turma_id)

    if not usuario_pode_gerenciar_turma(turma):
        return jsonify({'erro': 'Acesso negado'}), 403

    if turma.status != 'checkout':
        if turma.status == 'finalizada':
            return redirect(url_for('lista_presenca', turma_id=turma.id))
        return redirect(url_for('dashboard_professor'))

    qtd_presentes = Checkin.query.filter_by(
        turma_id=turma.id,
        data_hora_saida=None
    ).count()

    return render_template(
        'tela_qr.html',
        turma=turma,
        qtd_presentes=qtd_presentes,
        modo='checkout'
    )


@app.route('/lista_presenca/<int:turma_id>')
@login_required
def lista_presenca(turma_id):
    turma = Turma.query.get_or_404(turma_id)

    if not usuario_pode_gerenciar_turma(turma):
        return jsonify({'erro': 'Acesso negado'}), 403

    # Mantemos todo o histórico para que a lista continue disponível após a turma ser concluída.
    checkins = Checkin.query.filter_by(
        turma_id=turma.id
    ).order_by(Checkin.data_hora_entrada.asc()).all()

    qtd_presentes = sum(1 for checkin in checkins if checkin.data_hora_saida is None)

    return render_template(
        'lista_presenca.html',
        turma=turma,
        checkins=checkins,
        qtd_presentes=qtd_presentes,
        total_checkins=len(checkins)
    )


@app.route(
    '/chamar_responsavel/<int:crianca_id>/<int:turma_id>',
    methods=['POST']
)
@login_required
def chamar_responsavel(crianca_id, turma_id):

    if not current_user.is_professor and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    crianca = Crianca.query.get_or_404(crianca_id)
    turma = Turma.query.get_or_404(turma_id)

    # ==========================================
    # NOTIFICAÇÃO INTERNA
    # ==========================================

    mensagem_alerta = (
        f"🚨 Atenção! O professor da sala necessita da sua presença "
        f"para tratar de {crianca.nome}. "
        f"Por favor, dirija-se à sala."
    )

    nova_notif = Notificacao(
        usuario_id=crianca.responsavel_id,
        mensagem=mensagem_alerta
    )

    db.session.add(nova_notif)
    db.session.commit()

    # ==========================================
    # RESPONSÁVEL = CONTA USUARIO
    # ==========================================

    usuario_responsavel = db.session.get(
        Usuario,
        crianca.responsavel_id
    )

    whatsapp_enviado = False

    if not usuario_responsavel:

        detalhe_whatsapp = (
            'A conta do responsável não foi encontrada.'
        )

    else:

        telefone = usuario_responsavel.telefone
        opt_in = bool(
            usuario_responsavel.whatsapp_opt_in
        )

        if not telefone:

            detalhe_whatsapp = (
                'O responsável não possui telefone cadastrado.'
            )

        elif not opt_in:

            detalhe_whatsapp = (
                'O responsável não autorizou o recebimento '
                'de mensagens pelo WhatsApp.'
            )

            print(
                '[WHATSAPP] Envio ignorado:',
                detalhe_whatsapp
            )

        else:

            whatsapp_enviado, detalhe_whatsapp = enviar_whatsapp(
                telefone,
                crianca.nome,
                turma.nome_classe
            )

    # ==========================================
    # RESULTADO
    # ==========================================

    if whatsapp_enviado:

        flash(
            f'O responsável de {crianca.nome} foi notificado '
            'no painel e pelo WhatsApp.',
            'success'
        )

    else:

        flash(
            f'O responsável de {crianca.nome} foi notificado no painel. '
            'O WhatsApp não foi enviado.',
            'warning'
        )

        print(
            '[WHATSAPP] Detalhe:',
            detalhe_whatsapp
        )

    return redirect(
        url_for(
            'lista_presenca',
            turma_id=turma_id
        )
    )

@app.route('/detalhes_crianca/<int:crianca_id>')
@login_required
def detalhes_crianca(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)
    turma_id = request.args.get('turma_id', type=int)

    if turma_id:
        turma = Turma.query.get_or_404(turma_id)
        if not usuario_pode_gerenciar_turma(turma):
            return jsonify({'erro': 'Acesso negado'}), 403
    else:
        turma = None

    responsavel = Responsavel.query.filter_by(
        usuario_id=crianca.responsavel_id
    ).first()

    return render_template(
        'detalhes_crianca.html',
        crianca=crianca,
        responsavel=responsavel,
        turma=turma
    )

# ==========================================
# OUTRAS ROTAS COMPLEMENTARES
# ==========================================

@app.route('/notificacoes')
@login_required
def notificacoes():
    notificacoes_usuario = Notificacao.query.filter_by(
        usuario_id=current_user.id
    ).order_by(Notificacao.data_hora.desc()).all()
    return render_template(
        'notificacoes.html',
        notificacoes=notificacoes_usuario
    )

@app.route('/configuracoes')
@login_required
def configuracoes():
    return render_template('configuracoes.html')

@app.route('/alterar-senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    """Permite ao usuário autenticado trocar sua própria senha."""
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual', '')
        nova_senha = request.form.get('nova_senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not check_password_hash(current_user.senha_hash, senha_atual):
            flash('A senha atual não confere.', 'danger')
        elif len(nova_senha) < 8:
            flash('A nova senha deve ter pelo menos 8 caracteres.', 'danger')
        elif nova_senha != confirmar_senha:
            flash('A confirmação da nova senha não confere.', 'danger')
        elif check_password_hash(current_user.senha_hash, nova_senha):
            flash('A nova senha precisa ser diferente da senha atual.', 'danger')
        else:
            current_user.senha_hash = generate_password_hash(nova_senha)
            current_user.precisa_trocar_senha = False
            db.session.commit()
            flash('Sua senha foi alterada com sucesso.', 'success')
            return redirect(url_for('configuracoes'))

    return render_template('alterar_senha.html')

@app.route('/sobre_professores')
@login_required
def sobre_professores():
    return render_template('sobre_professores.html')

@app.route('/calendario')
@login_required
def calendario():
    return render_template('calendario.html')

@app.route('/politica_privacidade')
def politica_privacidade():
    # A política funciona em dois contextos:
    # 1) fluxo inicial de cadastro, vindo do login;
    # 2) consulta normal, vinda de Configurações.
    modo_cadastro = request.args.get('modo') == 'cadastro'
    return render_template(
        'politica_privacidade.html',
        modo_cadastro=modo_cadastro
    )

@app.route('/minha_conta', methods=['GET', 'POST'])
@login_required
def minha_conta():
    responsavel = Responsavel.query.filter_by(usuario_id=current_user.id).first()

    if request.method == 'POST':
        foto = request.files.get('foto')
        nova_foto = None
        if foto and foto.filename:
            try:
                nova_foto = salvar_foto(foto, 'responsavel' if not current_user.is_professor else 'usuario')
            except (ValueError, RuntimeError) as erro:
                flash(str(erro), 'danger')
                return redirect(url_for('minha_conta'))

        current_user.nome = request.form.get('nome', '').strip() or current_user.nome
        current_user.telefone = request.form.get('telefone', '').strip() or None

        if responsavel:
            responsavel.nome = current_user.nome
            responsavel.telefone = current_user.telefone or responsavel.telefone
            if nova_foto:
                responsavel.foto_url = nova_foto

        if nova_foto:
            current_user.foto_perfil = nova_foto

        db.session.commit()
        flash('Seus dados e sua foto de perfil foram atualizados.', 'success')
        return redirect(url_for('minha_conta'))

    return render_template('minha_conta.html', responsavel=responsavel)

@app.route('/adicionar_responsavel', methods=['GET', 'POST'])
@login_required
def adicionar_responsavel():
    if request.method == 'POST':
        try:
            foto_nome = salvar_foto(request.files.get('foto'), 'responsavel')
        except (ValueError, RuntimeError) as erro:
            flash(str(erro), 'danger')
            return redirect(url_for('adicionar_responsavel'))

        novo_responsavel = Responsavel(
            usuario_id=current_user.id,
            nome=request.form.get('nome'),
            cpf=request.form.get('cpf'),
            data_nascimento=request.form.get('data_nascimento'),
            sexo=request.form.get('sexo'),
            telefone=request.form.get('telefone'),
            vinculo=request.form.get('vinculo'),
            endereco=request.form.get('endereco'),
            foto_url=foto_nome,
            whatsapp_opt_in=request.form.get('whatsapp_opt_in') == 'on'
        )
        db.session.add(novo_responsavel)
        if foto_nome != 'default.png':
            current_user.foto_perfil = foto_nome
        db.session.commit()
        return redirect(url_for('dashboard'))
        
    return render_template('adicionar_responsavel.html')

@app.route('/cadastrar_crianca', methods=['GET', 'POST'])
@login_required
def cadastrar_crianca():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        data_nascimento = request.form.get('data_nascimento')
        sexo = request.form.get('sexo')

        tem_restricao = request.form.get('tem_restricao_alimentar') == 'on'
        tem_alergia = request.form.get('tem_alergia') == 'on'
        restricao = request.form.get('restricao_alimentar', '').strip()
        alergia = request.form.get('alergia', '').strip()

        if tem_restricao and not restricao:
            flash('Informe qual é a restrição alimentar.', 'warning')
            return redirect(url_for('cadastrar_crianca'))

        if tem_alergia and not alergia:
            flash('Informe qual é a alergia.', 'warning')
            return redirect(url_for('cadastrar_crianca'))

        detalhes_saude = []
        if restricao:
            detalhes_saude.append(f'Restrição alimentar: {restricao}')
        if alergia:
            detalhes_saude.append(f'Alergia: {alergia}')

        try:
            foto_nome = salvar_foto(request.files.get('foto'), 'crianca')
        except (ValueError, RuntimeError) as erro:
            flash(str(erro), 'danger')
            return redirect(url_for('cadastrar_crianca'))

        nova_crianca = Crianca(
            nome=nome,
            data_nascimento=data_nascimento,
            sexo=sexo,
            alergias_condicoes=' | '.join(detalhes_saude) if detalhes_saude else 'Nenhuma',
            foto_url=foto_nome,
            responsavel_id=current_user.id,
            usuario_id=current_user.id
        )

        db.session.add(nova_crianca)
        db.session.commit()
        
        flash('Criança cadastrada com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('cadastro_crianca.html')

@app.route('/toggle_checkin/<int:crianca_id>', methods=['POST'])
@login_required
def toggle_checkin(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)

    if crianca.responsavel_id != current_user.id and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    turma_id = request.form.get('turma_id', type=int)
    if not turma_id:
        flash('Não foi possível identificar a turma do QR Code.', 'danger')
        return redirect(url_for('dashboard'))

    turma = Turma.query.get(turma_id)
    if not turma:
        flash('A turma informada não existe mais.', 'danger')
        return redirect(url_for('dashboard'))

    # CHECK-IN: só é aceito enquanto a turma estiver na etapa de check-in.
    if turma.status == 'checkin':
        checkin_ativo = Checkin.query.filter_by(
            crianca_id=crianca.id,
            turma_id=turma.id,
            data_hora_saida=None
        ).first()

        if checkin_ativo:
            flash(f'{crianca.nome} já está presente nesta turma.', 'warning')
            return redirect(url_for('dashboard'))

        # Evita que a mesma criança fique presente em duas turmas ao mesmo tempo.
        outro_checkin_ativo = Checkin.query.filter(
            Checkin.crianca_id == crianca.id,
            Checkin.data_hora_saida.is_(None),
            Checkin.turma_id != turma.id
        ).first()

        if outro_checkin_ativo:
            flash(f'{crianca.nome} já possui um check-in ativo em outra turma.', 'warning')
            return redirect(url_for('dashboard'))

        novo_checkin = Checkin(
            crianca_id=crianca.id,
            turma_id=turma.id
        )
        db.session.add(novo_checkin)
        db.session.commit()

        flash(f'Check-in de {crianca.nome} realizado com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    # CHECK-OUT: só é aceito enquanto a turma estiver na etapa de check-out.
    if turma.status == 'checkout':
        checkin_ativo = Checkin.query.filter_by(
            crianca_id=crianca.id,
            turma_id=turma.id,
            data_hora_saida=None
        ).first()

        if not checkin_ativo:
            flash(
                f'Não existe um check-in ativo de {crianca.nome} nesta turma para realizar o check-out.',
                'warning'
            )
            return redirect(url_for('dashboard'))

        checkin_ativo.data_hora_saida = datetime.utcnow()
        db.session.commit()

        flash(f'Check-out de {crianca.nome} realizado com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    flash('Esta turma não está aceitando check-in ou check-out no momento.', 'warning')
    return redirect(url_for('dashboard'))


@app.route('/realizar_checkin')
@login_required
def realizar_checkin():
    todas_criancas = Crianca.query.all()
    return render_template('checkin.html', criancas=todas_criancas)

@app.route('/escanear_qr/<int:crianca_id>')
@login_required
def escanear_qr(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)
    if crianca.responsavel_id != current_user.id and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403
    return render_template('escanear_qr.html', crianca=crianca)
# ==========================================
# PAINEL DO ADMIN MASTER
# ==========================================
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    # Proteção de acesso: Só o admin master entra
    if not current_user.is_admin:
        flash('Acesso negado. Área restrita à diretoria.', 'danger')
        return redirect(url_for('dashboard'))

    # Indicadores gerais para a visão administrativa.
    professores = Usuario.query.filter_by(is_professor=True).order_by(Usuario.nome.asc()).all()
    criancas = Crianca.query.count()
    turmas = Turma.query.count()
    responsaveis = Responsavel.query.count()
    total_usuarios = Usuario.query.count()
    turmas_abertas = Turma.query.filter(Turma.status.in_(['checkin', 'acontecendo', 'checkout'])).count()

    return render_template(
        'admin_dashboard.html',
        professores=professores,
        total_criancas=criancas,
        total_turmas=turmas,
        total_responsaveis=responsaveis,
        total_usuarios=total_usuarios,
        turmas_abertas=turmas_abertas,
        mes_padrao=datetime.now().strftime('%Y-%m')
    )


@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    if not current_user.is_admin:
        flash('Acesso negado. Área restrita à administração.', 'danger')
        return redirect(url_for('dashboard'))

    termo = request.args.get('q', '').strip()
    filtro_papel = request.args.get('papel', '').strip()
    consulta = Usuario.query

    if termo:
        padrao = f'%{termo}%'
        consulta = consulta.filter(or_(Usuario.nome.ilike(padrao), Usuario.email.ilike(padrao)))

    if filtro_papel == 'admin':
        consulta = consulta.filter(Usuario.is_admin.is_(True))
    elif filtro_papel == 'professor':
        consulta = consulta.filter(Usuario.is_professor.is_(True))
    elif filtro_papel == 'responsavel':
        consulta = consulta.filter(Usuario.is_admin.is_(False), Usuario.is_professor.is_(False))

    usuarios = consulta.order_by(Usuario.nome.asc()).all()
    return render_template(
        'admin_usuarios.html',
        usuarios=usuarios,
        termo=termo,
        filtro_papel=filtro_papel,
        total_usuarios=Usuario.query.count()
    )


def papel_usuario(usuario):
    if usuario.is_admin and usuario.is_professor:
        return 'admin_professor'
    if usuario.is_admin:
        return 'admin'
    if usuario.is_professor:
        papel = (usuario.funcao_papeis or 'professor').lower()
        return papel if papel in ('professor', 'auxiliar', 'ambos') else 'professor'
    return 'responsavel'


@app.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def admin_novo_usuario():
    if not current_user.is_admin:
        flash('Acesso negado. Área restrita à administração.', 'danger')
        return redirect(url_for('dashboard'))

    papel_atual = request.form.get('papel', 'professor') if request.method == 'POST' else 'professor'

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        telefone = request.form.get('telefone', '').strip()
        senha_form = request.form.get('senha', '')
        papel = papel_atual

        papeis_validos = ('responsavel', 'professor', 'auxiliar', 'ambos', 'admin', 'admin_professor')
        is_admin = papel in ('admin', 'admin_professor')
        is_professor = papel in ('professor', 'auxiliar', 'ambos', 'admin_professor')
        senha_inicial = ''
        precisa_trocar = False

        if is_professor and not is_admin:
            # A senha padrão é mantida no .env/ambiente da VPS, nunca no código.
            senha_inicial = os.getenv('SENHA_PADRAO_PROFESSOR', '').strip()
            precisa_trocar = True
        else:
            senha_inicial = senha_form

        if not nome or not email:
            flash('Preencha nome e e-mail.', 'danger')
        elif papel not in papeis_validos:
            flash('Selecione um perfil válido.', 'danger')
        elif Usuario.query.filter_by(email=email).first():
            flash('Já existe um usuário cadastrado com esse e-mail.', 'danger')
        elif is_professor and not is_admin and not senha_inicial:
            flash('Configure SENHA_PADRAO_PROFESSOR no .env/ambiente da VPS antes de criar professores.', 'danger')
        elif len(senha_inicial) < 8:
            flash('A senha inicial deve ter pelo menos 8 caracteres.', 'danger')
        else:
            funcao = papel if papel in ('professor', 'auxiliar', 'ambos') else ('ambos' if papel == 'admin_professor' else 'responsavel')
            usuario = Usuario(
                nome=nome,
                email=email,
                telefone=telefone or None,
                senha_hash=generate_password_hash(senha_inicial),
                is_admin=is_admin,
                is_professor=is_professor,
                funcao_papeis=funcao,
                pode_editar_escala=False,
                precisa_trocar_senha=precisa_trocar
            )
            db.session.add(usuario)
            db.session.commit()
            if precisa_trocar:
                flash(
                    f'Conta de {nome} criada. Entregue ao professor a senha inicial configurada no servidor; '
                    'ele deverá trocá-la no primeiro acesso.',
                    'success'
                )
            else:
                flash(f'Usuário {nome} criado com sucesso.', 'success')
            return redirect(url_for('admin_usuarios'))

    return render_template(
        'admin_usuario_form.html',
        usuario=None,
        papel_atual=papel_atual,
        senha_padrao_professor_configurada=bool(os.getenv('SENHA_PADRAO_PROFESSOR', '').strip())
    )

@app.route('/admin/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@login_required
def admin_editar_usuario(usuario_id):
    if not current_user.is_admin:
        flash('Acesso negado. Área restrita à administração.', 'danger')
        return redirect(url_for('dashboard'))

    usuario = Usuario.query.get_or_404(usuario_id)
    papel_atual = papel_usuario(usuario)

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        telefone = request.form.get('telefone', '').strip()
        nova_senha = request.form.get('senha', '')
        papel = request.form.get('papel', papel_atual)
        era_professor = bool(usuario.is_professor)

        email_existente = Usuario.query.filter(Usuario.email == email, Usuario.id != usuario.id).first() if email else None
        papeis_validos = ('responsavel', 'professor', 'auxiliar', 'ambos', 'admin', 'admin_professor')
        novo_admin = papel in ('admin', 'admin_professor')
        novo_professor = papel in ('professor', 'auxiliar', 'ambos', 'admin_professor')

        if not nome or not email:
            flash('Nome e e-mail são obrigatórios.', 'danger')
        elif email_existente:
            flash('Esse e-mail já está sendo usado por outra conta.', 'danger')
        elif papel not in papeis_validos:
            flash('Selecione um perfil válido.', 'danger')
        elif nova_senha and len(nova_senha) < 8:
            flash('A nova senha deve ter pelo menos 8 caracteres.', 'danger')
        elif novo_professor and not novo_admin and not era_professor and len(os.getenv('SENHA_PADRAO_PROFESSOR', '').strip()) < 8:
            flash('Configure SENHA_PADRAO_PROFESSOR com pelo menos 8 caracteres no ambiente da VPS antes de transformar esta conta em professor.', 'danger')
        elif usuario.id == current_user.id and not novo_admin:
            flash('Por segurança, você não pode remover seu próprio acesso administrativo.', 'danger')
        elif usuario.is_admin and not novo_admin and Usuario.query.filter_by(is_admin=True).count() <= 1:
            flash('O sistema precisa manter pelo menos um administrador.', 'danger')
        elif usuario.is_professor and not novo_professor and Turma.query.filter(or_(Turma.professor_id == usuario.id, Turma.auxiliar_id == usuario.id)).first() is not None:
            flash('Este profissional está atribuído a uma ou mais turmas. Reatribua a escala antes de remover o perfil de professor/auxiliar.', 'danger')
        else:
            usuario.nome = nome
            usuario.email = email
            usuario.telefone = telefone or None
            usuario.is_admin = novo_admin
            usuario.is_professor = novo_professor
            usuario.funcao_papeis = papel if papel in ('professor', 'auxiliar', 'ambos') else ('ambos' if papel == 'admin_professor' else 'responsavel')
            if novo_professor and not novo_admin:
                if nova_senha:
                    usuario.senha_hash = generate_password_hash(nova_senha)
                    usuario.precisa_trocar_senha = True
                elif not era_professor:
                    senha_padrao = os.getenv('SENHA_PADRAO_PROFESSOR', '').strip()
                    usuario.senha_hash = generate_password_hash(senha_padrao)
                    usuario.precisa_trocar_senha = True
            elif nova_senha:
                usuario.senha_hash = generate_password_hash(nova_senha)
                usuario.precisa_trocar_senha = False
            elif not novo_professor:
                usuario.precisa_trocar_senha = False

            # Mantém os dados básicos de contato sincronizados para perfis de responsável já existentes.
            responsaveis_vinculados = Responsavel.query.filter_by(usuario_id=usuario.id).all()
            for responsavel in responsaveis_vinculados:
                responsavel.nome = nome
                if telefone:
                    responsavel.telefone = telefone

            db.session.commit()
            flash(f'Usuário {nome} atualizado com sucesso.', 'success')
            return redirect(url_for('admin_usuarios'))

        papel_atual = papel

    return render_template('admin_usuario_form.html', usuario=usuario, papel_atual=papel_atual)


@app.route('/admin/usuarios/<int:usuario_id>/excluir', methods=['POST'])
@login_required
def admin_excluir_usuario(usuario_id):
    if not current_user.is_admin:
        flash('Acesso negado. Área restrita à administração.', 'danger')
        return redirect(url_for('dashboard'))

    usuario = Usuario.query.get_or_404(usuario_id)
    if usuario.id == current_user.id:
        flash('Você não pode excluir a própria conta enquanto estiver conectado.', 'danger')
        return redirect(url_for('admin_usuarios'))

    if usuario.is_admin and Usuario.query.filter_by(is_admin=True).count() <= 1:
        flash('Não é possível excluir o último administrador do sistema.', 'danger')
        return redirect(url_for('admin_usuarios'))

    possui_vinculos = any([
        Crianca.query.filter_by(responsavel_id=usuario.id).first() is not None,
        Crianca.query.filter_by(usuario_id=usuario.id).first() is not None,
        Responsavel.query.filter_by(usuario_id=usuario.id).first() is not None,
        Notificacao.query.filter_by(usuario_id=usuario.id).first() is not None,
        Turma.query.filter(or_(Turma.professor_id == usuario.id, Turma.auxiliar_id == usuario.id)).first() is not None,
    ])
    if possui_vinculos:
        flash('Este usuário possui crianças, notificações, perfil de responsável ou vínculo com escala. Edite o perfil em vez de excluir para preservar o histórico.', 'warning')
        return redirect(url_for('admin_usuarios'))

    nome = usuario.nome
    db.session.delete(usuario)
    db.session.commit()
    flash(f'Usuário {nome} excluído com sucesso.', 'success')
    return redirect(url_for('admin_usuarios'))


@app.route('/admin/toggle_escala/<int:prof_id>')
@login_required
def toggle_escala(prof_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
        
    prof = Usuario.query.get_or_404(prof_id)
    # Ativa/Desativa o acesso do professor para preencher a escala
    prof.pode_editar_escala = not prof.pode_editar_escala 
    db.session.commit()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/liberar_escala/<int:prof_id>')
@login_required
def liberar_escala(prof_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
        
    prof = Usuario.query.get_or_404(prof_id)
    # Inverte o status (Se estava bloqueado, libera. Se estava liberado, bloqueia)
    prof.pode_editar_escala = not prof.pode_editar_escala 
    db.session.commit()
    
    status = "liberada" if prof.pode_editar_escala else "bloqueada"
    flash(f'Escala de {prof.nome} foi {status}!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/bloquear_todas_escalas')
@login_required
def bloquear_todas_escalas():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    
    professores = Usuario.query.filter_by(is_professor=True).all()
    for prof in professores:
        prof.pode_editar_escala = False
    
    db.session.commit()
    flash('Todas as escalas foram bloqueadas. Agora você pode gerar a escala automática.', 'success')
    return redirect(url_for('admin_dashboard'))

# ==========================================
# 1. FUNÇÃO GERAR ESCALA (Manhã/Noite + Restrições)
# ==========================================
@app.route('/admin/gerar_escala', methods=['POST'])
@login_required
def gerar_escala():
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))

    mes_codigo = request.form.get('mes_referencia', '').strip()
    try:
        _, mes_label = formatar_mes_codigo(mes_codigo)
        domingos = domingos_do_mes(mes_codigo)
    except ValueError:
        flash('Selecione um mês de referência válido.', 'danger')
        return redirect(url_for('admin_dashboard'))

    existe_escala = Turma.query.filter_by(dia_aula=mes_label).first()
    if existe_escala:
        flash(
            f'Erro: Já existe uma escala gerada para "{mes_label}". '
            'Exclua a existente em "Ver Escala" antes de gerar nova.',
            'danger'
        )
        return redirect(url_for('admin_dashboard'))

    professores_liberados = Usuario.query.filter_by(
        is_professor=True,
        pode_editar_escala=True
    ).count()
    if professores_liberados > 0:
        flash(
            'Erro: Você precisa bloquear a edição de escala de todos os professores antes de gerar.',
            'danger'
        )
        return redirect(url_for('admin_dashboard'))

    professores = Usuario.query.filter_by(is_professor=True).all()
    if not professores:
        flash('Erro: Não há nenhum professor cadastrado no sistema.', 'danger')
        return redirect(url_for('admin_dashboard'))

    contagem_escalas = {prof.id: 0 for prof in professores}
    turnos = ['Manhã', 'Noite']
    classes_padrao = ['3-4', '5-6', '7']

    todos_profs = [
        p for p in professores
        if not p.funcao_papeis or p.funcao_papeis in ['professor', 'ambos']
    ]
    todos_auxs = [
        p for p in professores
        if not p.funcao_papeis or p.funcao_papeis in ['auxiliar', 'ambos']
    ]

    for indice_semana, domingo in enumerate(domingos, start=1):
        escalados_neste_domingo = set()
        semana_label = f'Semana {indice_semana}'
        data_label = domingo.strftime('%d/%m')
        numeracao_semana = f'{semana_label} - {data_label}'

        for turno in turnos:
            for classe in classes_padrao:
                candidatos_prof = [
                    p for p in todos_profs
                    if classe in (p.classes_preferidas or '')
                    and professor_disponivel_no_dia(p, domingo, turno)
                ]
                candidatos_aux = [
                    p for p in todos_auxs
                    if classe in (p.classes_preferidas or '')
                    and professor_disponivel_no_dia(p, domingo, turno)
                ]

                candidatos_prof_livres = [
                    p for p in candidatos_prof
                    if p.id not in escalados_neste_domingo
                ]
                candidatos_aux_livres = [
                    p for p in candidatos_aux
                    if p.id not in escalados_neste_domingo
                ]

                prof_selecionado = None
                if candidatos_prof_livres:
                    candidatos_prof_livres.sort(key=lambda x: contagem_escalas[x.id])
                    prof_selecionado = candidatos_prof_livres[0]
                elif candidatos_prof:
                    candidatos_prof.sort(key=lambda x: contagem_escalas[x.id])
                    prof_selecionado = candidatos_prof[0]

                if prof_selecionado:
                    escalados_neste_domingo.add(prof_selecionado.id)
                    contagem_escalas[prof_selecionado.id] += 1

                if prof_selecionado:
                    candidatos_aux_livres = [
                        a for a in candidatos_aux_livres
                        if a.id != prof_selecionado.id
                    ]
                    candidatos_aux = [
                        a for a in candidatos_aux
                        if a.id != prof_selecionado.id
                    ]

                aux_selecionado = None
                if candidatos_aux_livres:
                    candidatos_aux_livres.sort(key=lambda x: contagem_escalas[x.id])
                    aux_selecionado = candidatos_aux_livres[0]
                elif candidatos_aux:
                    candidatos_aux.sort(key=lambda x: contagem_escalas[x.id])
                    aux_selecionado = candidatos_aux[0]

                if aux_selecionado:
                    escalados_neste_domingo.add(aux_selecionado.id)
                    contagem_escalas[aux_selecionado.id] += 1

                db.session.add(Turma(
                    nome_classe=classe,
                    dia_aula=mes_label,
                    numeracao_escala=numeracao_semana,
                    turno=turno,
                    professor_id=prof_selecionado.id if prof_selecionado else None,
                    auxiliar_id=aux_selecionado.id if aux_selecionado else None,
                    responsabilidade='Titular e Auxiliar',
                    status='fechada'
                ))

    db.session.commit()
    flash(
        f'Escala de {mes_label} (com as datas dos domingos) gerada com sucesso!',
        'success'
    )
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/excluir_mes/<path:mes>')
@login_required
def excluir_mes(mes):
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))

    try:
        turmas = Turma.query.filter_by(dia_aula=mes).all()

        if not turmas:
            flash(f'Nenhuma escala encontrada para "{mes}".', 'warning')
            return redirect(url_for('admin_escala'))

        turma_ids = [turma.id for turma in turmas]

        # Checkins mantêm o histórico, mas deixam de apontar para uma turma
        # que será removida. Isso evita violação de chave estrangeira no PostgreSQL.
        Checkin.query.filter(
            Checkin.turma_id.in_(turma_ids)
        ).update(
            {Checkin.turma_id: None},
            synchronize_session=False
        )

        Turma.query.filter(
            Turma.id.in_(turma_ids)
        ).delete(
            synchronize_session=False
        )

        db.session.commit()

        flash(
            f'Toda a escala de "{mes}" foi apagada com sucesso.',
            'success'
        )

    except Exception as e:
        db.session.rollback()
        import traceback
        print('=' * 60)
        print('ERRO AO EXCLUIR MÊS')
        print('Mês:', mes)
        print('Erro:', repr(e))
        traceback.print_exc()
        print('=' * 60)
        flash('Não foi possível excluir a escala deste mês. Verifique os logs.', 'danger')

    return redirect(url_for('admin_escala'))

@app.route('/admin/excluir_turma/<int:turma_id>')
@login_required
def excluir_turma(turma_id):
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))

    try:
        turma = Turma.query.get_or_404(turma_id)

        Checkin.query.filter_by(
            turma_id=turma.id
        ).update(
            {Checkin.turma_id: None},
            synchronize_session=False
        )

        db.session.delete(turma)
        db.session.commit()
        flash('Aula específica excluída.', 'success')

    except Exception as e:
        db.session.rollback()
        import traceback
        print('=' * 60)
        print('ERRO AO EXCLUIR TURMA')
        print('Turma:', turma_id)
        print('Erro:', repr(e))
        traceback.print_exc()
        print('=' * 60)
        flash('Não foi possível excluir a aula. Verifique os logs.', 'danger')

    return redirect(url_for('admin_escala'))

@app.route('/admin/editar_turma/<int:turma_id>', methods=['GET', 'POST'], endpoint='editar_turma')
@login_required
def editar_turma(turma_id):
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))
    
    turma = Turma.query.get_or_404(turma_id)
    professores = Usuario.query.filter_by(is_professor=True).all()
    
    if request.method == 'POST':
        prof_id = request.form.get('professor_id')
        aux_id = request.form.get('auxiliar_id')
        
        turma.professor_id = prof_id if prof_id else None
        turma.auxiliar_id = aux_id if aux_id else None
        
        db.session.commit()
        flash('Escala atualizada com sucesso!', 'success')
        return redirect(url_for('admin_escala'))
        
    return render_template('editar_turma.html', turma=turma, professores=professores)

# Atualize também a rota admin_escala para listar os meses criados:
@app.route('/admin-escala')
@login_required
def admin_escala():
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))
    
    # Ordena pelo mês, depois pela semana, depois pela classe
    todas_turmas = Turma.query.order_by(Turma.dia_aula, Turma.numeracao_escala, Turma.nome_classe).all()
    usuarios = {u.id: u.nome for u in Usuario.query.all()}
    
    # Extrai uma lista só com os nomes dos meses que existem no banco (sem repetir)
    meses_unicos = []
    for t in todas_turmas:
        if t.dia_aula not in meses_unicos:
            meses_unicos.append(t.dia_aula)
            
    return render_template('admin_escala.html', turmas=todas_turmas, usuarios=usuarios, meses=meses_unicos)

# ==========================================
# NOVA TELA DE PERFIL/CONFIGURAÇÕES (BASEADA NA IMAGEM)
# ==========================================
@app.route('/perfil_professor')
@login_required
def perfil_professor():
    if not current_user.is_professor:
        return redirect(url_for('dashboard'))
    return render_template('perfil_professor.html')

# ==========================================
# GERAÇÃO DE DADOS DE TESTE
# ==========================================
def criar_usuario_teste():
    # Não cria contas públicas/de equipe com senha conhecida em produção.
    # Para desenvolvimento isolado, habilite explicitamente no ambiente.
    habilitado = os.getenv('CRIAR_USUARIOS_TESTE', 'false').strip().lower() in ('1', 'true', 'yes', 'sim')
    if not habilitado:
        print('Criação automática de usuários de teste desativada.')
        return

    try:
        # ==========================================
        # USUÁRIO RESPONSÁVEL DE TESTE
        # ==========================================
        user = Usuario.query.filter_by(
            email='teste@ipjardim.com'
        ).first()

        if not user:
            senha_criptografada = generate_password_hash('123456')

            novo_usuario = Usuario(
                nome='João Responsável',
                email='teste@ipjardim.com',
                telefone='(83) 99999-8888',
                senha_hash=senha_criptografada,
                is_admin=False,
                is_professor=False
            )

            db.session.add(novo_usuario)

        # ==========================================
        # USUÁRIO PROFESSOR DE TESTE
        # ==========================================
        prof = Usuario.query.filter_by(
            email='professor@ipjardim.com'
        ).first()

        if not prof:
            senha_prof_criptografada = generate_password_hash('123456')

            novo_prof = Usuario(
                nome='Prof. Carlos Silva',
                email='professor@ipjardim.com',
                telefone='(83) 98888-7777',
                senha_hash=senha_prof_criptografada,
                is_admin=False,
                is_professor=True
            )

            db.session.add(novo_prof)

        db.session.commit()

        print("Contas de teste prontas!")

    except Exception as e:
        db.session.rollback()
        print("Erro ao criar contas de teste:", repr(e))

def proteger_contas_de_teste_antigas():
    """Força a troca de senhas conhecidas das contas de teste criadas por versões antigas."""
    if os.getenv('CRIAR_USUARIOS_TESTE', 'false').strip().lower() in ('1', 'true', 'yes', 'sim'):
        return

    emails_teste = ('teste@ipjardim.com', 'professor@ipjardim.com')
    alterados = 0
    for email in emails_teste:
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and check_password_hash(usuario.senha_hash, '123456'):
            usuario.precisa_trocar_senha = True
            alterados += 1

    if alterados:
        db.session.commit()
        print(f'{alterados} conta(s) de teste antiga(s) exigirão troca de senha no próximo acesso.')


def configurar_sqlite():
    """
    Configura o SQLite uma única vez durante a inicialização.
    Não usa SQLAlchemy para evitar executar PRAGMA a cada conexão.
    """

    if not database_url.startswith('sqlite'):
        return

    db_path = os.path.join(
        app.instance_path,
        'banco.db'
    )

    os.makedirs(
        app.instance_path,
        exist_ok=True
    )

    print("=" * 60)
    print("BANCO SQLITE:")
    print(db_path)
    print("=" * 60)

    connection = None

    try:
        connection = sqlite3.connect(
            db_path,
            timeout=60
        )

        cursor = connection.cursor()

        cursor.execute(
            "PRAGMA busy_timeout=60000"
        )

        cursor.execute(
            "PRAGMA journal_mode=WAL"
        )

        cursor.execute(
            "PRAGMA synchronous=NORMAL"
        )

        connection.commit()

        cursor.close()

        print("SQLite configurado com sucesso.")
        print("Modo WAL ativado.")

    except sqlite3.OperationalError as e:

        print("=" * 60)
        print("ERRO AO CONFIGURAR SQLITE")
        print(repr(e))
        print("=" * 60)

        raise

    finally:

        if connection:
            connection.close()


# ==========================================================
# MIGRAÇÃO COMPATÍVEL COM BANCOS EXISTENTES
# ==========================================================

def garantir_coluna_whatsapp_opt_in():
    """Garante a coluna de consentimento no banco já existente."""
    inspector = inspect(db.engine)

    if 'responsavel' not in inspector.get_table_names():
        return

    colunas = {col['name'] for col in inspector.get_columns('responsavel')}

    if 'whatsapp_opt_in' in colunas:
        return

    if db.engine.dialect.name == 'postgresql':
        comando = (
            'ALTER TABLE responsavel ' 
            'ADD COLUMN IF NOT EXISTS whatsapp_opt_in BOOLEAN NOT NULL DEFAULT FALSE'
        )
    else:
        comando = (
            'ALTER TABLE responsavel ' 
            'ADD COLUMN whatsapp_opt_in BOOLEAN NOT NULL DEFAULT 0'
        )

    with db.engine.begin() as conn:
        conn.execute(text(comando))

    print('Coluna responsavel.whatsapp_opt_in criada.')


def garantir_coluna_precisa_trocar_senha():
    """Adiciona o controle de troca obrigatória sem apagar os usuários atuais."""
    inspector = inspect(db.engine)
    if 'usuario' not in inspector.get_table_names():
        return

    colunas = {col['name'] for col in inspector.get_columns('usuario')}
    if 'precisa_trocar_senha' in colunas:
        return

    if db.engine.dialect.name == 'postgresql':
        comando = (
            'ALTER TABLE usuario ADD COLUMN IF NOT EXISTS '
            'precisa_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE'
        )
    else:
        comando = (
            'ALTER TABLE usuario ADD COLUMN precisa_trocar_senha '
            'BOOLEAN NOT NULL DEFAULT 0'
        )

    with db.engine.begin() as conn:
        conn.execute(text(comando))

    print('Coluna usuario.precisa_trocar_senha criada.')


# ==========================================================
# INICIALIZAÇÃO DO BANCO
# ==========================================================

def inicializar_banco():
    """
    Inicializa o banco de dados localmente ou no servidor.

    - configura SQLite quando utilizado;
    - cria tabelas ainda inexistentes;
    - aplica migrações compatíveis com bancos existentes;
    - usuários de teste só são criados com CRIAR_USUARIOS_TESTE=true.
    """

    print("=" * 60)
    print("INICIALIZANDO BANCO DE DADOS")
    print("=" * 60)

    try:

        with app.app_context():

            # Configuração específica do SQLite
            configurar_sqlite()

            # Cria as tabelas definidas nos modelos
            db.create_all()

            # Adapta tabelas existentes sem remover dados.
            garantir_coluna_whatsapp_opt_in()
            garantir_coluna_precisa_trocar_senha()

            print("Tabelas verificadas/criadas com sucesso.")

            # Cria usuários de teste
            criar_usuario_teste()
            proteger_contas_de_teste_antigas()

            print("Rotina opcional de usuários de teste concluída.")

    except Exception as e:

        db.session.rollback()

        print("=" * 60)
        print("ERRO AO INICIALIZAR BANCO")
        print(repr(e))
        print("=" * 60)

        raise


# ==========================================================
# INICIALIZAÇÃO AUTOMÁTICA
# ==========================================================

# Scripts administrativos (ex.: migração das fotos) podem importar os modelos
# sem disparar a criação de usuários de teste ou inicialização do banco.
if os.getenv('CHECKKIDS_SKIP_INIT') != '1':
    inicializar_banco()


# ==========================================================
# EXECUÇÃO LOCAL
# ==========================================================

if __name__ == '__main__':

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False,
        threaded=True
    )
