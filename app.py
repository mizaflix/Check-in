import os
from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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
from sqlalchemy import event


app = Flask(__name__)

app.config['SECRET_KEY'] = 'chave_secreta_checkkids_ipjardim'

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

UPLOAD_FOLDER = os.path.join(
    'static',
    'uploads'
)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

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
    
    is_admin = db.Column(db.Boolean, default=False) # <- ESTE É O ADMIN MASTER
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

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

# ==========================================
# ROTAS DO SISTEMA
# ==========================================

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        user = Usuario.query.filter_by(email=email).first()

        if user and check_password_hash(user.senha_hash, senha):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('E-mail ou senha inválidos.', 'danger')

    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        perfil = request.form.get('perfil')

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

            # Mantendo sua regra atual:
            # perfil "admin" entra no fluxo de professor
            is_prof = perfil == 'admin'

            novo_usuario = Usuario(
                nome='Novo Usuário',
                email=email,
                senha_hash=senha_criptografada,
                is_admin=False,
                is_professor=is_prof
            )

            db.session.add(novo_usuario)

            # Commit protegido
            db.session.commit()

            # Login somente após salvar com sucesso
            login_user(novo_usuario)

            if is_prof:
                return redirect(url_for('cadastro_professor_perfil'))

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
        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_professor:
        return redirect(url_for('dashboard_professor'))

    responsavel = Responsavel.query.filter_by(usuario_id=current_user.id).first()
    criancas = Crianca.query.filter_by(usuario_id=current_user.id).all()
    
    # Busca alertas urgentes enviados pelos professores para este pai/mãe
    alertas = Notificacao.query.filter_by(usuario_id=current_user.id, lida=False).order_by(Notificacao.data_hora.desc()).all()
    
    return render_template('dashboard.html', responsavel=responsavel, criancas=criancas, alertas=alertas)

# Rota simples para o pai marcar o alerta como visto/lido
@app.route('/marcar_notificacao_lida/<int:notif_id>', methods=['POST'])
@login_required
def marcar_notificacao_lida(notif_id):
    notif = Notificacao.query.get_or_404(notif_id)
    if notif.usuario_id == current_user.id:
        notif.lida = True
        db.session.commit()
    return redirect(url_for('dashboard'))

# ==========================================
# FLUXO EXCLUSIVO DO PROFESSOR
# ==========================================
@app.route('/cadastro_professor_perfil', methods=['GET', 'POST'])
@login_required
def cadastro_professor_perfil():
    if request.method == 'POST':
        current_user.is_professor = True
        current_user.nome = request.form.get('nome')
        current_user.cpf = request.form.get('cpf')
        current_user.data_nascimento = request.form.get('data_nascimento')
        current_user.sexo = request.form.get('sexo')
        current_user.telefone = request.form.get('telefone')
        current_user.cep = request.form.get('cep')
        
        # Lógica para salvar a foto (se enviada)
        foto = request.files.get('foto')
        if foto and foto.filename != '':
            filename = secure_filename(foto.filename)
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.foto_perfil = filename
            
        db.session.commit()
        flash('Perfil de professor cadastrado com sucesso!', 'success')
        
        # Após o cadastro pessoal, redireciona para o dashboard (ou para a tela de disponibilidade)
        return redirect(url_for('dashboard_professor'))
        
    return render_template('cadastro_professor_perfil.html')
@app.route('/finalizar_cadastro_professor', methods=['GET', 'POST'])
@login_required
def finalizar_cadastro_professor():
    if request.method == 'POST':
        telefone = request.form.get('telefone')
        funcao_papeis = request.form.get('funcao_papeis')
        
        classes_interest = request.form.getlist('classes_interest')
        dias_disponiveis = request.form.getlist('dias_disponiveis') # Pega Manhã e/ou Noite
        
        current_user.telefone = telefone
        current_user.funcao_papeis = funcao_papeis
        current_user.classes_preferidas = ",".join(classes_interest)
        
        current_user.disponibilidade_dias = ",".join(dias_disponiveis) 
               
        db.session.commit()
        
        flash('Sua disponibilidade foi salva com sucesso!', 'success')
        return redirect(url_for('dashboard_professor'))
    
    classes_disponiveis = ['3-4', '5-6', '7'] 
    return render_template('cadastro_professor.html', classes_disponiveis=classes_disponiveis)


@app.route('/dashboard_professor')
@login_required
def dashboard_professor():
    if not current_user.is_professor and not current_user.is_admin:
        flash('Acesso restrito.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Busca todas as turmas onde o usuário atual foi alocado na escala automática (seja como professor ou auxiliar)
    turmas = Turma.query.filter(
        (Turma.professor_id == current_user.id) | (Turma.auxiliar_id == current_user.id)
    ).all()
    
    return render_template('dashboard_professor.html', turmas=turmas)

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
    if turma.professor_id != current_user.id and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    if acao == 'iniciar_checkin':
        turma.status = 'checkin'
        db.session.commit()
        # MUDANÇA AQUI: Redireciona direto para a tela do QR Code!
        return redirect(url_for('tela_qr', turma_id=turma.id))
        
    elif acao == 'iniciar_aula':
        turma.status = 'acontecendo'
        db.session.commit()
        # MUDANÇA AQUI: Volta pro dashboard depois de "Finalizar Check-in"
        return redirect(url_for('dashboard_professor'))
        
    elif acao == 'iniciar_checkout':
        turma.status = 'checkout'
    elif acao == 'finalizar':
        turma.status = 'fechada'
        # Limpa automaticamente as presenças da sala ao fechar
        checkins_ativos = Checkin.query.filter_by(turma_id=turma.id, data_hora_saida=None).all()
        for c in checkins_ativos:
            c.data_hora_saida = datetime.utcnow()

    db.session.commit()
    return redirect(url_for('dashboard_professor'))

@app.route('/tela_qr/<int:turma_id>')
@login_required
def tela_qr(turma_id):
    turma = Turma.query.get_or_404(turma_id)
    qtd_presentes = Checkin.query.filter_by(turma_id=turma.id, data_hora_saida=None).count()
    return render_template('tela_qr.html', turma=turma, qtd_presentes=qtd_presentes)

@app.route('/lista_presenca/<int:turma_id>')
@login_required
def lista_presenca(turma_id):
    turma = Turma.query.get_or_404(turma_id)
    # Pegamos os checkins ativos e garantimos que carregue os dados da criança vinculada
    checkins = Checkin.query.filter_by(turma_id=turma.id, data_hora_saida=None).all()
    return render_template('lista_presenca.html', turma=turma, checkins=checkins)


@app.route('/chamar_responsavel/<int:crianca_id>/<int:turma_id>', methods=['POST'])
@login_required
def chamar_responsavel(crianca_id, turma_id):
    if not current_user.is_professor and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    crianca = Crianca.query.get_or_404(crianca_id)
    
    # Criar a mensagem de alerta para o pai
    mensagem_alerta = f"🚨 Atenção! O professor da sala necessita da sua presença para tratar de {crianca.nome}. Por favor, dirija-se à sala."
    
    # Salva a notificação interna no banco de dados para o usuário responsável
    nova_notif = Notificacao(
        usuario_id=crianca.responsavel_id,
        mensagem=mensagem_alerta
    )
    
    db.session.add(nova_notif)
    db.session.commit()
    
    flash(f'O responsável de {crianca.nome} foi notificado no painel do site com sucesso!', 'success')
    return redirect(url_for('lista_presenca', turma_id=turma_id))

@app.route('/detalhes_crianca/<int:crianca_id>')
@login_required
def detalhes_crianca(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)
    responsavel = Responsavel.query.filter_by(usuario_id=crianca.usuario_id).first()
    return render_template('detalhes_crianca.html', crianca=crianca, responsavel=responsavel)

# ==========================================
# OUTRAS ROTAS COMPLEMENTARES
# ==========================================

@app.route('/notificacoes')
@login_required
def notificacoes():
    return render_template('notificacoes.html')

@app.route('/configuracoes')
@login_required
def configuracoes():
    return render_template('configuracoes.html')

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
    return render_template('politica_privacidade.html')

@app.route('/minha_conta', methods=['GET', 'POST'])
@login_required
def minha_conta():
    if request.method == 'POST':
        current_user.nome = request.form.get('nome')
        current_user.telefone = request.form.get('telefone')
        db.session.commit()
        return redirect(url_for('configuracoes'))
    return render_template('minha_conta.html')

@app.route('/adicionar_responsavel', methods=['GET', 'POST'])
@login_required
def adicionar_responsavel():
    if request.method == 'POST':
        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        novo_responsavel = Responsavel(
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
        db.session.add(novo_responsavel)
        db.session.commit()
        return redirect(url_for('dashboard'))
        
    return render_template('adicionar_responsavel.html')

@app.route('/cadastrar_crianca', methods=['GET', 'POST'])
@login_required
def cadastrar_crianca():
    if request.method == 'POST':
        nome = request.form.get('nome')
        data_nascimento = request.form.get('data_nascimento')
        sexo = request.form.get('sexo')
        alergias = request.form.get('alergias_condicoes')

        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        nova_crianca = Crianca(
            nome=nome,
            data_nascimento=data_nascimento,
            sexo=sexo,
            alergias_condicoes=alergias if alergias else "Nenhuma",
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

    # Captura o ID da turma lido pelo QR Code na câmera do celular
    turma_id = request.form.get('turma_id')

    checkin_ativo = Checkin.query.filter_by(crianca_id=crianca.id, data_hora_saida=None).first()

    if checkin_ativo:
        # Se já estava presente, faz o CHECK-OUT
        checkin_ativo.data_hora_saida = datetime.utcnow()
        flash(f'Check-out de {crianca.nome} realizado!', 'success')
    else:
        # Se não estava, faz o CHECK-IN na turma lida pelo QR Code
        novo_checkin = Checkin(crianca_id=crianca.id, turma_id=turma_id)
        db.session.add(novo_checkin)
        flash(f'Check-in de {crianca.nome} realizado com sucesso!', 'success')

    db.session.commit()
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

    # Pega todos os dados do banco para o Admin ter visão geral
    professores = Usuario.query.filter_by(is_professor=True).all()
    criancas = Crianca.query.all()
    turmas = Turma.query.all()
    responsaveis = Responsavel.query.all()
    
    return render_template('admin_dashboard.html', professores=professores, criancas=criancas, turmas=turmas, responsaveis=responsaveis)

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

    mes_referencia = request.form.get('mes_referencia', 'Próximo Mês').strip()
    
    # Verifica se já gerou esse mês
    existe_escala = Turma.query.filter_by(dia_aula=mes_referencia).first()
    if existe_escala:
        flash(f'Erro: Já existe uma escala gerada para "{mes_referencia}". Exclua a existente em "Ver Escala" antes de gerar nova.', 'danger')
        return redirect(url_for('admin_dashboard'))

    professores_liberados = Usuario.query.filter_by(is_professor=True, pode_editar_escala=True).count()
    if professores_liberados > 0:
        flash('Erro: Você precisa bloquear a edição de escala de todos os professores antes de gerar.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    professores = Usuario.query.filter_by(is_professor=True).all()
    if not professores:
        flash('Erro: Não há nenhum professor cadastrado no sistema.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    contagem_escalas = {prof.id: 0 for prof in professores}
    
    semanas = ['Semana 1', 'Semana 2', 'Semana 3', 'Semana 4']
    turnos = ['Manhã', 'Noite']  # <-- ADICIONADO OS DOIS TURNOS
    classes_padrao = ['3-4', '5-6', '7']
    
    todos_profs = [p for p in professores if not p.funcao_papeis or p.funcao_papeis in ['professor', 'ambos']]
    todos_auxs = [p for p in professores if not p.funcao_papeis or p.funcao_papeis in ['auxiliar', 'ambos']]

    for semana in semanas:
        # Cria uma lista para anotar quem já trabalhou NESTE domingo (manhã ou noite)
        escalados_neste_domingo = set()
        
        for turno in turnos:
            numeracao_turno = f"{semana} - {turno}"
            
            for classe in classes_padrao:
                # 1. FILTRA RIGOROSAMENTE: Sala preferida + Turno disponível (Manhã ou Noite)
                candidatos_prof = []
                for p in todos_profs:
                    prefs = p.classes_preferidas or ""
                    # 👇 Nome correto da coluna do banco aqui: disponibilidade_dias
                    dias = getattr(p, 'disponibilidade_dias', None) or "" 
                    
                    if classe in prefs and turno in dias:
                        candidatos_prof.append(p)

                candidatos_aux = []
                for p in todos_auxs:
                    prefs = p.classes_preferidas or ""
                    # 👇 Nome correto da coluna do banco aqui: disponibilidade_dias
                    dias = getattr(p, 'disponibilidade_dias', None) or ""
                    
                    if classe in prefs and turno in dias:
                        candidatos_aux.append(p)
                
                # 2. Tenta pegar professores que ainda NÃO trabalharam neste domingo
                candidatos_prof_livres = [p for p in candidatos_prof if p.id not in escalados_neste_domingo]
                candidatos_aux_livres = [p for p in candidatos_aux if p.id not in escalados_neste_domingo]
                
                # 3. ESCOLHE O TITULAR
                prof_selecionado = None
                if candidatos_prof_livres:
                    candidatos_prof_livres.sort(key=lambda x: contagem_escalas[x.id])
                    prof_selecionado = candidatos_prof_livres[0]
                elif candidatos_prof:
                    # Fallback: Se não tem ninguém livre, repete alguém (só em caso de falta de pessoal)
                    candidatos_prof.sort(key=lambda x: contagem_escalas[x.id])
                    prof_selecionado = candidatos_prof[0]
                
                if prof_selecionado:
                    escalados_neste_domingo.add(prof_selecionado.id)
                    contagem_escalas[prof_selecionado.id] += 1
                
                # 4. ESCOLHE O AUXILIAR
                aux_selecionado = None
                # Remove o titular da lista de opções de auxiliar para ele não fazer os dois papéis na mesma sala
                if prof_selecionado:
                    candidatos_aux_livres = [a for a in candidatos_aux_livres if a.id != prof_selecionado.id]
                    candidatos_aux = [a for a in candidatos_aux if a.id != prof_selecionado.id]

                if candidatos_aux_livres:
                    candidatos_aux_livres.sort(key=lambda x: contagem_escalas[x.id])
                    aux_selecionado = candidatos_aux_livres[0]
                elif candidatos_aux:
                    candidatos_aux.sort(key=lambda x: contagem_escalas[x.id])
                    aux_selecionado = candidatos_aux[0]
                    
                if aux_selecionado:
                    escalados_neste_domingo.add(aux_selecionado.id)
                    contagem_escalas[aux_selecionado.id] += 1

                # 5. SALVA A TURMA
                nova_turma = Turma(
                    nome_classe=classe,
                    dia_aula=mes_referencia,
                    numeracao_escala=numeracao_turno,  # Ex: "Semana 1 - Manhã"
                    professor_id=prof_selecionado.id if prof_selecionado else None,
                    auxiliar_id=aux_selecionado.id if aux_selecionado else None,
                    responsabilidade='Titular e Auxiliar',
                    status='fechada'
                )
                db.session.add(nova_turma)

    db.session.commit()
    flash(f'Escala de {mes_referencia} (Manhã e Noite) gerada com sucesso!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/excluir_mes/<path:mes>')
@login_required
def excluir_mes(mes):
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))
    
    # Apaga todas as turmas daquele mês de uma vez
    Turma.query.filter_by(dia_aula=mes).delete()
    db.session.commit()
    flash(f'Toda a escala de "{mes}" foi apagada com sucesso.', 'success')
    return redirect(url_for('admin_escala'))

@app.route('/admin/excluir_turma/<int:turma_id>')
@login_required
def excluir_turma(turma_id):
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('dashboard'))
    
    turma = Turma.query.get_or_404(turma_id)
    db.session.delete(turma)
    db.session.commit()
    flash('Aula específica excluída.', 'success')
    return redirect(url_for('admin_escala'))

@app.route('/admin/editar_turma/<int:turma_id>', methods=['GET', 'POST'])
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

def configurar_sqlite():
    """
    Configura o SQLite uma única vez durante a inicialização.
    Não usa SQLAlchemy para evitar executar PRAGMA a cada conexão.
    """

    if not database_url.startswith('sqlite'):
        return

    # O Flask-SQLAlchemy coloca bancos SQLite relativos
    # dentro da pasta instance/.
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
if __name__ == '__main__':

    with app.app_context():

        # Configura o SQLite uma única vez
        configurar_sqlite()

        # Cria as tabelas
        db.create_all()

        # Cria usuários de teste
        try:
            criar_usuario_teste()

        except Exception as e:
            db.session.rollback()

            print(
                "Erro ao criar contas de teste:",
                repr(e)
            )

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False,
        threaded=True
    )